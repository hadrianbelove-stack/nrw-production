/**
 * New Release Wall - Movie Detail Screen
 * Full movie info with watch buttons
 * Supports swipe left/right to navigate between movies
 *
 * Layout (ported from mockups/mobile-detail-fixed-hero.html):
 *  - Locked hero: poster + info box are one fixed-height unit (poster height).
 *    Title clamps to 2 lines; director/cast/meta one line each; score badges
 *    pinned to the bottom of the box. Layout below never shifts between films.
 *  - Scrolling content: teal pull quotes, then label-less synopsis (with the
 *    quiet gold screening note appended at the end of the capsule).
 *  - Fixed bottom button bar (outside the ScrollView): TRAILER, watch buttons,
 *    Buy Tickets (virtual screenings), Share.
 */

import React, {useCallback, useState, useRef, useEffect} from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Image,
  Dimensions as RNDimensions,
  TouchableOpacity,
  Animated,
  PanResponder,
} from 'react-native';
import {useSafeAreaInsets} from 'react-native-safe-area-context';

import {WatchButtonGroup} from '../components/WatchButton';
import {Colors, Typography, Spacing} from '../constants/colors';
import {getWatchLinks} from '../services/api';
import {
  openWatchLink,
  openRottenTomatoes,
  openMetacritic,
  openLetterboxd,
  openWikipedia,
  openImdb,
  shareMovie,
} from '../utils/links';
import {trackMovieView, trackWatchButtonTap} from '../services/analytics';
import TrailerPlayer from '../components/TrailerPlayer';
import {renderMarkdownSpans} from '../utils/markdown';

const COUNTRY_ABBREV = {
  'United States of America': 'USA', 'United States': 'USA', 'US': 'USA', 'USA': 'USA',
  'United Kingdom': 'UK', 'Great Britain': 'UK', 'GB': 'UK',
};

const formatCountry = (country) => {
  if (!country) return null;
  return COUNTRY_ABBREV[country] || country;
};

const formatShortDate = (dateStr) => {
  if (!dateStr) return null;
  const [y, m, d] = dateStr.split('-');
  const dt = new Date(y, m - 1, d);
  return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

// Wikipedia search fallback when no curated wiki link exists.
const wikiSearchUrl = (name) =>
  'https://en.wikipedia.org/wiki/Special:Search?search=' + encodeURIComponent(name);

const screenWidth = RNDimensions.get('window').width;
const posterWidth = screenWidth * 0.45;
const posterHeight = posterWidth * 1.5;
const SWIPE_THRESHOLD = 50; // Minimum swipe distance to trigger navigation

export default function MovieDetail({route}) {
  const insets = useSafeAreaInsets();
  const {movie: initialMovie, movieList = [], currentIndex: initialIndex = 0} = route.params;

  // State for current movie (enables navigation without going back)
  const [movie, setMovie] = useState(initialMovie);
  const [currentIndex, setCurrentIndex] = useState(initialIndex);

  // Arrow animation refs
  const leftArrowOpacity = useRef(new Animated.Value(0.6)).current;
  const rightArrowOpacity = useRef(new Animated.Value(0.6)).current;

  // Flash arrow when navigating
  const flashArrow = useCallback((arrowAnim) => {
    Animated.sequence([
      Animated.timing(arrowAnim, {
        toValue: 1,
        duration: 100,
        useNativeDriver: true,
      }),
      Animated.timing(arrowAnim, {
        toValue: 0.6,
        duration: 200,
        useNativeDriver: true,
      }),
    ]).start();
  }, []);

  // Navigate to next movie
  const navigateNext = useCallback(() => {
    if (movieList.length === 0) return;
    flashArrow(rightArrowOpacity);
    const nextIndex = (currentIndex + 1) % movieList.length;
    setCurrentIndex(nextIndex);
    setMovie(movieList[nextIndex]);
  }, [movieList, currentIndex, flashArrow, rightArrowOpacity]);

  // Navigate to previous movie
  const navigatePrevious = useCallback(() => {
    if (movieList.length === 0) return;
    flashArrow(leftArrowOpacity);
    const prevIndex = currentIndex === 0 ? movieList.length - 1 : currentIndex - 1;
    setCurrentIndex(prevIndex);
    setMovie(movieList[prevIndex]);
  }, [movieList, currentIndex, flashArrow, leftArrowOpacity]);

  // Pan responder for swipe gestures
  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => false,
      onMoveShouldSetPanResponder: (_, gestureState) => {
        // Only capture horizontal swipes
        return Math.abs(gestureState.dx) > Math.abs(gestureState.dy) &&
               Math.abs(gestureState.dx) > 10;
      },
      onPanResponderRelease: (_, gestureState) => {
        if (gestureState.dx > SWIPE_THRESHOLD) {
          navigatePrevious(); // Swipe right = previous
        } else if (gestureState.dx < -SWIPE_THRESHOLD) {
          navigateNext(); // Swipe left = next
        }
      },
    })
  ).current;

  // Track view when movie changes
  useEffect(() => {
    trackMovieView(movie);
  }, [movie]);

  const rawWatchLinks = getWatchLinks(movie);

  // For virtual screening movies, relabel Eventive/screening platform buttons to "Buy Ticket"
  const watchLinks = rawWatchLinks.map(link => {
    const svc = (link.service || '').toLowerCase();
    const url = (link.url || '').toLowerCase();
    const isVirtualScreeningPlatform =
      svc.includes('eventive') ||
      url.includes('eventive.org') ||
      url.includes('festivalplayer') ||
      url.includes('shift72.com');
    if (isVirtualScreeningPlatform) {
      return {...link, labelOverride: 'Buy Ticket'};
    }
    return link;
  });

  const handleWatchPress = useCallback(
    link => {
      trackWatchButtonTap(movie, link.service);
      openWatchLink(link.url);
    },
    [movie],
  );

  // Trailer player state
  const [trailerVisible, setTrailerVisible] = useState(false);

  const handleTrailerPress = useCallback(() => {
    setTrailerVisible(true);
  }, []);

  const handleRTPress = useCallback(() => {
    const url = movie.links?.rt || movie.links?.rotten_tomatoes;
    if (url) openRottenTomatoes(url);
  }, [movie]);

  const handleMCPress = useCallback(() => {
    if (movie.links?.metacritic) {
      openMetacritic(movie.links.metacritic);
    }
  }, [movie]);

  const handleLBPress = useCallback(() => {
    if (movie.links?.letterboxd) {
      openLetterboxd(movie.links.letterboxd);
    }
  }, [movie]);

  const handleIMDbPress = useCallback(() => {
    if (movie.links?.imdb) {
      openImdb(movie.links.imdb);
    }
  }, [movie]);

  const handleWikiPress = useCallback(() => {
    if (movie.links?.wikipedia) {
      openWikipedia(movie.links.wikipedia);
    }
  }, [movie]);

  const handleDirectorPress = useCallback(() => {
    const dir = movie.director || movie.crew?.director;
    if (!dir) return;
    openWikipedia(movie.links?.director_wiki || wikiSearchUrl(dir));
  }, [movie]);

  const handleCastPress = useCallback(
    (name) => {
      const url = movie.links?.cast_wiki?.[name] || wikiSearchUrl(name);
      openWikipedia(url);
    },
    [movie],
  );

  const handleSharePress = useCallback(() => {
    shareMovie(movie);
  }, [movie]);

  const posterUrl = movie.poster_url || movie.poster;
  const director = movie.director || movie.crew?.director;
  const castRaw = movie.cast || movie.crew?.cast || [];
  const cast = Array.isArray(castRaw) ? castRaw : (castRaw ? [castRaw] : []);
  const runtime = movie.runtime;
  const year = movie.year || (movie.release_date ? movie.release_date.split('-')[0] : null);

  // Format runtime
  const formatRuntime = mins => {
    if (!mins) return null;
    const hours = Math.floor(mins / 60);
    const minutes = mins % 60;
    return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
  };

  // Meta line: country · year · runtime · studio (one line, ellipsized)
  const metaParts = [];
  if (movie.country) metaParts.push(formatCountry(movie.country));
  if (year) metaParts.push(year);
  if (runtime) metaParts.push(formatRuntime(runtime));
  if (movie.studio && movie.studio !== 'Unknown') metaParts.push(movie.studio);

  const isVirtualScreening = !!movie.filters?.is_virtual_screening;
  const screeningName = movie.virtual_screening_info?.screening_name;
  const screeningEnd = movie.virtual_screening_info?.available_end;

  const hasNavigation = movieList.length > 1;
  const hasTrailer = !!(movie.links?.trailer_hosted || movie.links?.trailer);

  // Score badges (rendered inside the hero box, pinned to bottom).
  const hasScores =
    movie.links?.wikipedia ||
    movie.rt_score ||
    movie.imdb_rating ||
    (movie.metacritic_score && movie.metacritic_score !== '0') ||
    movie.letterboxd_score;

  return (
    <View style={styles.container} {...panResponder.panHandlers}>
      {/* Navigation arrow indicators */}
      {hasNavigation && (
        <>
          <View style={styles.navArrowLeft}>
            <Animated.Text style={[styles.navArrowText, {opacity: leftArrowOpacity}]}>
              ‹
            </Animated.Text>
          </View>
          <View style={styles.navArrowRight}>
            <Animated.Text style={[styles.navArrowText, {opacity: rightArrowOpacity}]}>
              ›
            </Animated.Text>
          </View>
        </>
      )}

      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}>
        {/* ---- LOCKED HERO: poster + info box are one fixed-height unit ---- */}
        <View style={styles.heroSection}>
          <View style={styles.posterContainer}>
            {posterUrl ? (
              <Image
                source={{uri: posterUrl}}
                style={styles.poster}
                resizeMode="cover"
              />
            ) : (
              <View style={styles.posterPlaceholder}>
                <Text style={styles.placeholderText}>No Poster</Text>
              </View>
            )}
            {/* Staff Pick badge */}
            {(movie.featured || movie.filters?.is_staff_pick) && (
              <View style={styles.staffPickBadge}>
                <Text style={styles.staffPickText}>★ NRW SELECT ★</Text>
              </View>
            )}
            {/* Restoration badge */}
            {movie.filters?.is_restoration && (
              <View style={styles.restorationBadge}>
                <Text style={styles.restorationBadgeText}>{(movie.reissue_label || 'RESTORATION').toUpperCase()}</Text>
              </View>
            )}
          </View>

          <View style={styles.heroInfo}>
            <Text style={styles.title} numberOfLines={2}>
              {movie.display_title || movie.title}
            </Text>

            {director && (
              <Text style={styles.heroDir} numberOfLines={1}>
                <Text style={styles.heroLabel}>Dir: </Text>
                <Text style={styles.heroLink} onPress={handleDirectorPress}>{director}</Text>
              </Text>
            )}

            {cast.length > 0 && (
              <Text style={styles.heroCast} numberOfLines={1}>
                <Text style={styles.heroLabel}>Cast: </Text>
                {cast.slice(0, 4).map((name, i) => (
                  <Text key={name + i}>
                    {i > 0 ? ', ' : ''}
                    <Text style={styles.heroLink} onPress={() => handleCastPress(name)}>{name}</Text>
                  </Text>
                ))}
              </Text>
            )}

            {metaParts.length > 0 && (
              <Text style={styles.heroMeta} numberOfLines={1}>{metaParts.join(' · ')}</Text>
            )}

            {/* Score badges pinned to the bottom of the box */}
            {hasScores && (
              <View style={styles.scores}>
                {movie.links?.wikipedia && (
                  <TouchableOpacity
                    style={[styles.score, styles.scoreWiki]}
                    onPress={handleWikiPress}
                    activeOpacity={0.7}>
                    <Text style={[styles.scoreValue, styles.scoreTextWiki]}>W</Text>
                  </TouchableOpacity>
                )}
                {movie.rt_score && (
                  <TouchableOpacity
                    style={[styles.score, styles.scoreRT]}
                    onPress={handleRTPress}
                    disabled={!(movie.links?.rt || movie.links?.rotten_tomatoes)}
                    activeOpacity={0.7}>
                    <Text style={[styles.scoreLabel, styles.scoreTextRT]}>RT</Text>
                    <Text style={[styles.scoreValue, styles.scoreTextRT]}>{movie.rt_score}</Text>
                  </TouchableOpacity>
                )}
                {movie.imdb_rating && (
                  <TouchableOpacity
                    style={[styles.score, styles.scoreIMDb]}
                    onPress={handleIMDbPress}
                    disabled={!movie.links?.imdb}
                    activeOpacity={0.7}>
                    <Text style={[styles.scoreLabel, styles.scoreTextIMDb]}>IMDb</Text>
                    <Text style={[styles.scoreValue, styles.scoreTextIMDb]}>{movie.imdb_rating}</Text>
                  </TouchableOpacity>
                )}
                {movie.metacritic_score && movie.metacritic_score !== '0' && (
                  <TouchableOpacity
                    style={[styles.score, styles.scoreMC]}
                    onPress={handleMCPress}
                    disabled={!movie.links?.metacritic}
                    activeOpacity={0.7}>
                    <Text style={[styles.scoreLabel, styles.scoreTextMC]}>MC</Text>
                    <Text style={[styles.scoreValue, styles.scoreTextMC]}>{movie.metacritic_score}</Text>
                  </TouchableOpacity>
                )}
                {movie.letterboxd_score && (
                  <TouchableOpacity
                    style={[styles.score, styles.scoreLB]}
                    onPress={handleLBPress}
                    disabled={!movie.links?.letterboxd}
                    activeOpacity={0.7}>
                    <Text style={[styles.scoreLabel, styles.scoreTextLB]}>LB</Text>
                    <Text style={[styles.scoreValue, styles.scoreTextLB]}>{movie.letterboxd_score}</Text>
                  </TouchableOpacity>
                )}
              </View>
            )}
          </View>
        </View>

        {/* Teal pull quotes (no label, no badge) */}
        {movie.pull_quotes?.length > 0 && (
          <View style={styles.pqWrap}>
            {movie.pull_quotes.map((pq, i) => {
              const attribution = [pq.critic, pq.outlet].filter(Boolean).join(', ');
              const content = (
                <View style={styles.pullQuoteCard}>
                  <Text style={styles.pqText}>{'“'}{pq.text}{'”'}</Text>
                  {attribution ? (
                    <Text style={styles.pqAttribution}>{attribution}</Text>
                  ) : null}
                </View>
              );
              return pq.review_url ? (
                <TouchableOpacity key={i} onPress={() => openWatchLink(pq.review_url)} activeOpacity={0.7}>
                  {content}
                </TouchableOpacity>
              ) : (
                <View key={i}>{content}</View>
              );
            })}
          </View>
        )}

        {/* Synopsis — no label; gold screening note appended at the end */}
        {(movie.capsule || movie.synopsis) && (
          <Text style={styles.synopsis}>
            {renderMarkdownSpans(movie.capsule || movie.synopsis)}
            {isVirtualScreening && screeningName && (
              <Text style={styles.screeningCallout}>
                {` Virtual screening via ${screeningName}${screeningEnd ? ` · through ${formatShortDate(screeningEnd)}` : ''}.`}
              </Text>
            )}
          </Text>
        )}
      </ScrollView>

      {/* ---- FIXED BOTTOM BUTTON BAR (outside ScrollView) ---- */}
      <View style={[styles.btnBar, {paddingBottom: insets.bottom + 12}]}>
        <ScrollView
          style={styles.btnBarScroll}
          contentContainerStyle={styles.btnBarContent}
          showsVerticalScrollIndicator={false}>
          {hasTrailer && (
            <TouchableOpacity style={styles.btnTrailer} onPress={handleTrailerPress} activeOpacity={0.85}>
              <Text style={styles.btnTrailerText}>TRAILER</Text>
            </TouchableOpacity>
          )}

          {watchLinks.filter(l => l.type === 'purchase').length > 0 && (
            <WatchButtonGroup
              links={watchLinks.filter(l => l.type === 'purchase')}
              onPress={handleWatchPress}
              maxButtons={4}
              stacked
            />
          )}
          {watchLinks.filter(l => l.type === 'streaming').length > 0 && (
            <WatchButtonGroup
              links={watchLinks.filter(l => l.type === 'streaming')}
              onPress={handleWatchPress}
              maxButtons={6}
              stacked
            />
          )}
          {watchLinks.filter(l => l.type === 'plex').length > 0 && (
            <WatchButtonGroup
              links={watchLinks.filter(l => l.type === 'plex')}
              onPress={handleWatchPress}
              maxButtons={1}
              stacked
            />
          )}

          <TouchableOpacity style={styles.btnShare} onPress={handleSharePress} activeOpacity={0.85}>
            <Text style={styles.btnShareText}>⤴ SHARE</Text>
          </TouchableOpacity>
        </ScrollView>
      </View>

      {/* Trailer player overlay */}
      {trailerVisible && movieList.length > 0 && (
        <TrailerPlayer
          movieList={movieList}
          initialIndex={currentIndex}
          onClose={(lastIndex) => {
            setTrailerVisible(false);
            if (lastIndex !== currentIndex && lastIndex >= 0 && lastIndex < movieList.length) {
              setCurrentIndex(lastIndex);
              setMovie(movieList[lastIndex]);
            }
          }}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: Spacing.screenPadding,
    paddingTop: Spacing.md,
    paddingBottom: Spacing.xl,
  },
  navArrowLeft: {
    position: 'absolute',
    left: 8,
    top: 0,
    bottom: 0,
    justifyContent: 'center',
    zIndex: 10,
  },
  navArrowRight: {
    position: 'absolute',
    right: 8,
    top: 0,
    bottom: 0,
    justifyContent: 'center',
    zIndex: 10,
  },
  navArrowText: {
    color: 'rgba(0, 212, 170, 0.6)',  // Teal at 60%
    fontSize: 40,
    fontWeight: '300',
  },

  // ---- Locked hero ----
  heroSection: {
    flexDirection: 'row',
    height: posterHeight,        // poster + info box are one fixed-height unit
  },
  posterContainer: {
    width: posterWidth,
    height: posterHeight,
    borderRadius: 8,
    overflow: 'hidden',
    backgroundColor: Colors.backgroundSecondary,
  },
  poster: {
    width: '100%',
    height: '100%',
  },
  posterPlaceholder: {
    width: '100%',
    height: '100%',
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: Colors.backgroundTertiary,
  },
  placeholderText: {
    color: Colors.textMuted,
    fontSize: Typography.caption,
  },
  staffPickBadge: {
    position: 'absolute',
    top: Spacing.sm,
    left: Spacing.sm,
    backgroundColor: '#081412',
    borderWidth: 1,
    borderColor: Colors.staffPick,
    paddingHorizontal: Spacing.sm,
    paddingVertical: 4,
    borderRadius: 12,
  },
  staffPickText: {
    color: Colors.staffPickText,
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  restorationBadge: {
    position: 'absolute',
    bottom: Spacing.sm,
    left: Spacing.sm,
    backgroundColor: Colors.restoration,
    paddingHorizontal: Spacing.sm,
    paddingVertical: 4,
    borderRadius: 4,
  },
  restorationBadgeText: {
    color: Colors.restorationText,
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  heroInfo: {
    flex: 1,
    marginLeft: Spacing.md,
    height: posterHeight,
    overflow: 'hidden',
  },
  title: {
    color: Colors.textPrimary,
    fontSize: Typography.subtitle,
    fontWeight: '700',
    lineHeight: 24,
  },
  heroDir: {
    color: Colors.textPrimary,
    fontSize: 13,
    fontWeight: '700',
    marginTop: 5,
  },
  heroCast: {
    color: Colors.textSecondary,
    fontSize: 13,
    marginTop: 3,
  },
  heroLabel: {
    color: Colors.primary,
    fontWeight: '700',
  },
  heroLink: {
    textDecorationLine: 'underline',
    textDecorationColor: 'rgba(255,255,255,0.32)',
  },
  heroMeta: {
    color: Colors.textMuted,
    fontSize: 12,
    marginTop: 3,
  },
  scores: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: 'auto',   // pin to bottom of the hero box
  },
  score: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
    borderWidth: 1.5,
    marginRight: 8,
    marginTop: 6,
  },
  scoreLabel: {
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 0.2,
  },
  scoreValue: {
    fontSize: 12,
    fontWeight: '700',
  },
  scoreRT: {
    borderColor: 'rgba(255,107,107,0.55)',
    backgroundColor: 'rgba(255,107,107,0.08)',
  },
  scoreTextRT: { color: '#ff6b6b' },
  scoreIMDb: {
    borderColor: 'rgba(245,197,24,0.55)',
    backgroundColor: 'rgba(245,197,24,0.08)',
  },
  scoreTextIMDb: { color: '#f5c518' },
  scoreMC: {
    borderColor: 'rgba(125,223,100,0.55)',
    backgroundColor: 'rgba(125,223,100,0.08)',
  },
  scoreTextMC: { color: '#7ddf64' },
  scoreLB: {
    borderColor: 'rgba(0,224,84,0.5)',
    backgroundColor: 'rgba(0,224,84,0.08)',
  },
  scoreTextLB: { color: '#00e054' },
  scoreWiki: {
    borderColor: 'rgba(255,255,255,0.45)',
    backgroundColor: 'rgba(255,255,255,0.08)',
  },
  scoreTextWiki: { color: '#e8e8e8' },

  // ---- Pull quotes (teal, debadged) ----
  pqWrap: {
    marginTop: Spacing.md,
    paddingTop: Spacing.sm,
    borderTopWidth: 1,
    borderTopColor: 'rgba(255,255,255,0.08)',
  },
  pullQuoteCard: {
    backgroundColor: 'rgba(0,212,170,0.07)',
    borderLeftWidth: 3,
    borderLeftColor: Colors.primary,
    borderRadius: 6,
    paddingVertical: 9,
    paddingHorizontal: 11,
    marginVertical: 5,
  },
  pqText: {
    color: Colors.primary,
    fontSize: 14,
    fontStyle: 'italic',
    lineHeight: 20,
  },
  pqAttribution: {
    color: 'rgba(0,212,170,0.6)',
    fontSize: 11,
    marginTop: 4,
  },

  // ---- Synopsis ----
  synopsis: {
    color: '#cccccc',
    fontSize: Typography.body - 1,
    lineHeight: 24,
    marginTop: Spacing.md,
  },
  screeningCallout: {
    color: '#FFD700',
    fontWeight: '700',
    fontStyle: 'italic',
  },

  // ---- Fixed bottom button bar ----
  btnBar: {
    backgroundColor: 'rgba(12,12,24,0.92)',
    borderTopWidth: 1,
    borderTopColor: 'rgba(255,255,255,0.06)',
    paddingHorizontal: Spacing.md,
    paddingTop: 10,
  },
  btnBarScroll: {
    maxHeight: RNDimensions.get('window').height * 0.42,
  },
  btnBarContent: {
    gap: 8,
  },
  btnTrailer: {
    height: 50,
    borderRadius: 10,
    backgroundColor: '#E50914',
    borderWidth: 1.5,
    borderColor: 'rgba(255,255,255,0.25)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  btnTrailerText: {
    color: '#fff',
    fontWeight: '800',
    letterSpacing: 3,
    fontSize: 15,
  },
  btnShare: {
    height: 46,
    borderRadius: 10,
    backgroundColor: 'transparent',
    borderWidth: 1.5,
    borderColor: 'rgba(0,212,170,0.5)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  btnShareText: {
    color: Colors.primary,
    fontWeight: '700',
    letterSpacing: 2,
    fontSize: 13,
  },
});
