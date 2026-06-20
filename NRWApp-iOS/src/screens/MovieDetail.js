/**
 * New Release Wall - Movie Detail Screen
 * Full movie info with watch buttons
 * Supports swipe left/right to navigate between movies
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
import {openWatchLink, openRottenTomatoes, openMetacritic, openLetterboxd, openWikipedia} from '../utils/links';
import {trackMovieView, trackWatchButtonTap} from '../services/analytics';
import TrailerPlayer from '../components/TrailerPlayer';
import {renderMarkdownSpans} from '../utils/markdown';

const LANGUAGE_NAMES = {
  en: 'English', es: 'Spanish', fr: 'French', de: 'German', it: 'Italian', pt: 'Portuguese',
  ja: 'Japanese', ko: 'Korean', zh: 'Chinese', hi: 'Hindi', ru: 'Russian', ar: 'Arabic',
  nl: 'Dutch', sv: 'Swedish', da: 'Danish', no: 'Norwegian', fi: 'Finnish', pl: 'Polish',
  tr: 'Turkish', th: 'Thai', he: 'Hebrew', fa: 'Persian', el: 'Greek', cs: 'Czech',
  hu: 'Hungarian', ro: 'Romanian', uk: 'Ukrainian', id: 'Indonesian', vi: 'Vietnamese',
  ta: 'Tamil', te: 'Telugu', is: 'Icelandic', ga: 'Irish', ca: 'Catalan',
};
const languageName = (code) => code ? (LANGUAGE_NAMES[code.toLowerCase()] || code.toUpperCase()) : null;

const COUNTRY_ABBREV = {
  'United States of America': 'USA', 'United States': 'USA', 'US': 'USA', 'USA': 'USA',
  'United Kingdom': 'UK', 'Great Britain': 'UK', 'GB': 'UK',
  'Germany': 'GER', 'DE': 'GER',
  'France': 'FRA', 'FR': 'FRA',
  'South Korea': 'KOR', 'KR': 'KOR',
  'Netherlands': 'NED', 'NL': 'NED',
  'Switzerland': 'SUI', 'CH': 'SUI',
  'South Africa': 'RSA', 'ZA': 'RSA',
  'Chile': 'CHL', 'CL': 'CHL',
  'Japan': 'JPN', 'JP': 'JPN',
  'Italy': 'ITA', 'IT': 'ITA',
  'Spain': 'ESP', 'ES': 'ESP',
  'Sweden': 'SWE', 'SE': 'SWE',
  'Denmark': 'DEN', 'DK': 'DEN',
  'Norway': 'NOR', 'NO': 'NOR',
  'Poland': 'POL', 'PL': 'POL',
  'Australia': 'AUS', 'AU': 'AUS',
  'Canada': 'CAN', 'CA': 'CAN',
  'Mexico': 'MEX', 'MX': 'MEX',
  'Brazil': 'BRA', 'BR': 'BRA',
  'Argentina': 'ARG', 'AR': 'ARG',
  'Belgium': 'BEL', 'BE': 'BEL',
  'Portugal': 'POR', 'PT': 'POR',
  'Romania': 'ROM', 'RO': 'ROM',
  'Hungary': 'HUN', 'HU': 'HUN',
  'Czech Republic': 'CZE', 'CZ': 'CZE',
  'Austria': 'AUT', 'AT': 'AUT',
  'Ireland': 'IRL', 'IE': 'IRL',
  'China': 'CHN', 'CN': 'CHN',
  'Hong Kong': 'HKG', 'HK': 'HKG',
  'Taiwan': 'TPE', 'TW': 'TPE',
  'India': 'IND', 'IN': 'IND',
  'Iran': 'IRI', 'IR': 'IRI',
  'Israel': 'ISR', 'IL': 'ISR',
  'Turkey': 'TUR', 'TR': 'TUR',
  'Greece': 'GRE', 'GR': 'GRE',
  'Finland': 'FIN', 'FI': 'FIN',
  'New Zealand': 'NZL', 'NZ': 'NZL',
  'Bosnia and Herzegovina': 'BIH', 'Saudi Arabia': 'KSA',
};

const formatCountry = (country) => {
  if (!country) return null;
  return COUNTRY_ABBREV[country] || country.slice(0, 3).toUpperCase();
};

const lbStars = (score) => {
  const n = Math.round(parseFloat(score));
  return '\u2605'.repeat(n) + '\u2606'.repeat(5 - n);
};

const formatShortDate = (dateStr) => {
  const [y, m, d] = dateStr.split('-');
  const dt = new Date(y, m - 1, d);
  return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

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
    if (movie.links?.rotten_tomatoes) {
      openRottenTomatoes(movie.links.rotten_tomatoes);
    }
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

  const handleWikiPress = useCallback(() => {
    if (movie.links?.wikipedia) {
      openWikipedia(movie.links.wikipedia);
    }
  }, [movie]);

  const posterUrl = movie.poster_url || movie.poster;
  const director = movie.director || movie.crew?.director;
  const cast = movie.cast || movie.crew?.cast || [];
  const runtime = movie.runtime;
  const year = movie.year || (movie.release_date ? movie.release_date.split('-')[0] : null);

  // Format runtime
  const formatRuntime = mins => {
    if (!mins) return null;
    const hours = Math.floor(mins / 60);
    const minutes = mins % 60;
    return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
  };

  const hasNavigation = movieList.length > 1;

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
        contentContainerStyle={{paddingBottom: insets.bottom + Spacing.xl}}>
        {/* Hero section with poster and basic info */}
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
          {/* Trailer overlay (#5: white circle + red banner) */}
          {(movie.links?.trailer_hosted || movie.links?.trailer) && posterUrl && (
            <TouchableOpacity
              style={styles.trailerOverlay}
              onPress={handleTrailerPress}
              activeOpacity={0.8}>
              <View style={styles.trailerOverlayCircle}>
                <View style={styles.trailerOverlayTriangle} />
              </View>
              <View style={styles.trailerOverlayBanner}>
                <Text style={styles.trailerOverlayText}>TRAILER</Text>
              </View>
            </TouchableOpacity>
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
              <Text style={styles.restorationBadgeText}>{(movie.reissue_label || 'RESTORED').toUpperCase()}</Text>
            </View>
          )}
        </View>

        <View style={styles.heroInfo}>
          <View style={styles.titleRow}>
            <Text style={styles.title}>{movie.display_title || movie.title}</Text>
            {(() => {
              const hp = [];
              if (movie.country) hp.push(formatCountry(movie.country) || movie.country);
              if (movie.genres?.[0]) hp.push(movie.genres[0]);
              if (movie.digital_date) hp.push(formatShortDate(movie.digital_date));
              return hp.length > 0 ? <Text style={styles.titleDate}>{hp.join(' · ')}</Text> : null;
            })()}
          </View>

          {/* Virtual screening badge */}
          {movie.filters?.is_virtual_screening && (
            <Text style={styles.screeningName}>
              {movie.virtual_screening_info?.screening_name || 'VIRTUAL SCREENING'}
            </Text>
          )}

          {/* Meta block — 3 lines */}
          {director && <Text style={styles.metaCrewLine}><Text style={styles.metaCrewLabel}>Director: </Text><Text style={styles.metaCrewName}>{director}</Text></Text>}
          {cast.length > 0 && <Text style={styles.metaCrewLine}><Text style={styles.metaCrewLabel}>Cast: </Text><Text style={styles.metaCrewName}>{Array.isArray(cast) ? cast.slice(0, 3).join(', ') : cast}</Text></Text>}
          <View style={styles.metaRow}>
            {year && <Text style={styles.metaText}>{year}</Text>}
            {runtime && (
              <>
                <Text style={styles.metaDot}>•</Text>
                <Text style={styles.metaText}>{formatRuntime(runtime)}</Text>
              </>
            )}
            {movie.studio && (
              <>
                <Text style={styles.metaDot}>•</Text>
                <Text style={styles.metaText}>{movie.studio}</Text>
              </>
            )}
          </View>
        </View>
      </View>

      {/* Scores row — RT + IMDb + MC + LB + Wiki */}
      {(movie.links?.wikipedia || movie.rt_score || (movie.metacritic_score && movie.metacritic_score !== "0") || movie.imdb_rating || movie.letterboxd_score) && (
        <View style={styles.section}>
          <View style={styles.infoRow}>
            {movie.rt_score && (
              <TouchableOpacity
                style={styles.infoBtnColored}
                onPress={handleRTPress}
                disabled={!movie.links?.rotten_tomatoes}>
                <View style={styles.infoBtnContent}>
                  <Image source={require('../assets/logos/rt.png')} style={styles.infoBtnLogo} />
                  <Text style={[styles.infoBtnColoredText, { color: '#ff6b6b' }]}>{movie.rt_score}</Text>
                </View>
              </TouchableOpacity>
            )}
            {movie.imdb_rating && (
              <View style={styles.infoBtnColored}>
                <View style={styles.infoBtnContent}>
                  <Image source={require('../assets/logos/imdb.png')} style={styles.infoBtnLogo} />
                  <Text style={[styles.infoBtnColoredText, { color: '#f5c518' }]}>{movie.imdb_rating}</Text>
                </View>
              </View>
            )}
            {movie.metacritic_score && movie.metacritic_score !== "0" && (
              <TouchableOpacity
                style={styles.infoBtnColored}
                onPress={handleMCPress}
                disabled={!movie.links?.metacritic}>
                <View style={styles.infoBtnContent}>
                  <Image source={require('../assets/logos/metacritic.png')} style={[styles.infoBtnLogo, { tintColor: '#7ddf64' }]} />
                  <Text style={[styles.infoBtnColoredText, { color: '#7ddf64' }]}>{movie.metacritic_score}</Text>
                </View>
              </TouchableOpacity>
            )}
            {movie.letterboxd_score && (
              <TouchableOpacity
                style={styles.infoBtnColored}
                onPress={handleLBPress}
                disabled={!movie.links?.letterboxd}>
                <View style={styles.infoBtnContent}>
                  <Image source={require('../assets/logos/letterboxd.png')} style={[styles.infoBtnLogo, { tintColor: '#00E054' }]} />
                  <Text style={[styles.infoBtnColoredText, { color: '#00E054' }]}>{lbStars(movie.letterboxd_score)}</Text>
                </View>
              </TouchableOpacity>
            )}
            {movie.links?.wikipedia && (
              <TouchableOpacity style={styles.infoBtnGlass} onPress={handleWikiPress}>
                <Text style={styles.infoBtnGlassText}>Wiki</Text>
              </TouchableOpacity>
            )}
          </View>
        </View>
      )}

      {/* Trailer is now a poster overlay (see posterContainer above) */}

      {/* Watch buttons — VOD first, then streaming */}
      {watchLinks.length > 0 && (
        <View style={styles.section}>
          {watchLinks.filter(l => l.type === 'purchase').length > 0 && (
            <>
              <Text style={styles.watchSectionLabel}>Rent/Buy:</Text>
              <WatchButtonGroup links={watchLinks.filter(l => l.type === 'purchase')} onPress={handleWatchPress} maxButtons={3} />
            </>
          )}
          {watchLinks.filter(l => l.type === 'streaming').length > 0 && (
            <>
              <Text style={styles.watchSectionLabel}>Stream:</Text>
              <WatchButtonGroup links={watchLinks.filter(l => l.type === 'streaming')} onPress={handleWatchPress} maxButtons={6} />
            </>
          )}
          {watchLinks.filter(l => l.type === 'plex').length > 0 && (
            <WatchButtonGroup links={watchLinks.filter(l => l.type === 'plex')} onPress={handleWatchPress} maxButtons={1} />
          )}
        </View>
      )}

      {/* Pull Quotes */}
      {movie.pull_quotes?.length > 0 && (
        <View style={styles.section}>
          {movie.pull_quotes.map((pq, i) => {
            const content = (
              <View key={i} style={styles.pullQuoteCard}>
                <Text style={styles.pqText}>{'\u201C'}{pq.text}{'\u201D'}</Text>
                {(pq.critic || pq.outlet) && (
                  <Text style={styles.pqAttribution}>{'\u2014'} {[pq.critic, pq.outlet].filter(Boolean).join(', ')}</Text>
                )}
              </View>
            );
            return pq.review_url ? (
              <TouchableOpacity key={i} onPress={() => openWatchLink(pq.review_url)} activeOpacity={0.7}>
                {content}
              </TouchableOpacity>
            ) : content;
          })}
        </View>
      )}

      {/* Synopsis */}
      {(movie.capsule || movie.synopsis) && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Synopsis</Text>
          <Text style={styles.synopsis}>
            {renderMarkdownSpans(movie.capsule || movie.synopsis)}
            {movie.filters?.is_virtual_screening && movie.virtual_screening_info?.screening_name && (
              <Text style={styles.screeningCallout}>
                {` Virtual screening available as part of the ${movie.virtual_screening_info.screening_name}.${movie.virtual_screening_info?.available_end ? ` Ends ${formatShortDate(movie.virtual_screening_info.available_end)}.` : ''}`}
              </Text>
            )}
          </Text>
        </View>
      )}

      {/* Additional info */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Details</Text>
        {movie.country && (
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Country</Text>
            <Text style={styles.detailValue}>{movie.country}</Text>
          </View>
        )}
        {movie.original_language && (
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Language</Text>
            <Text style={styles.detailValue}>
              {languageName(movie.original_language)}
            </Text>
          </View>
        )}
        {movie.digital_date && (
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Available</Text>
            <Text style={styles.detailValue}>{movie.digital_date}</Text>
          </View>
        )}
      </View>
    </ScrollView>

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
  heroSection: {
    flexDirection: 'row',
    padding: Spacing.screenPadding,
    paddingTop: Spacing.md,
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
  heroInfo: {
    flex: 1,
    marginLeft: Spacing.md,
    justifyContent: 'flex-start',
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderBottomWidth: 2,
    borderBottomColor: 'rgba(0, 212, 170, 0.4)',
    paddingBottom: 8,
    marginBottom: 8,
  },
  title: {
    color: Colors.textPrimary,
    fontSize: Typography.subtitle,
    fontWeight: '700',
    lineHeight: 26,
    flex: 1,
  },
  titleDate: {
    color: Colors.primary,
    fontSize: Typography.subtitle - 2,
    fontWeight: '700',
    marginLeft: 8,
  },
  screeningName: {
    backgroundColor: '#FFD700',
    color: '#000',
    fontSize: Typography.caption,
    fontWeight: '800',
    letterSpacing: 1.5,
    textAlign: 'center',
    paddingVertical: 8,
    paddingHorizontal: 12,
    marginBottom: Spacing.sm,
  },
  screeningCallout: {
    color: '#FFD700',
    fontWeight: '700',
    fontStyle: 'italic',
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: Spacing.xs,
  },
  metaText: {
    color: Colors.textSecondary,
    fontSize: Typography.caption,
  },
  metaCrewLine: {
    fontSize: Typography.caption,
  },
  metaCrewLabel: {
    color: Colors.primary,
    fontWeight: 'bold',
  },
  metaCrewName: {
    color: Colors.textPrimary,
    fontWeight: 'bold',
  },
  metaDot: {
    color: Colors.textMuted,
    marginHorizontal: 6,
  },
  trailerOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.45)',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 5,
  },
  trailerOverlayCircle: {
    width: 50,
    height: 50,
    borderRadius: 25,
    backgroundColor: 'rgba(255,255,255,0.95)',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 4},
    shadowOpacity: 0.3,
    shadowRadius: 10,
  },
  trailerOverlayTriangle: {
    width: 0,
    height: 0,
    borderLeftWidth: 16,
    borderTopWidth: 9,
    borderBottomWidth: 9,
    borderLeftColor: '#E50914',
    borderTopColor: 'transparent',
    borderBottomColor: 'transparent',
    marginLeft: 4,
  },
  trailerOverlayBanner: {
    width: '100%',
    paddingVertical: 7,
    backgroundColor: 'rgba(229,9,20,0.85)',
    alignItems: 'center',
    marginTop: 8,
  },
  trailerOverlayText: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '800',
    letterSpacing: 3,
  },
  infoRow: {
    flexDirection: 'row',
    gap: Spacing.sm,
  },
  infoBtnGlass: {
    flex: 1,
    backgroundColor: 'rgba(255,255,255,0.1)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.3)',
    paddingVertical: Spacing.sm,
    borderRadius: 6,
    alignItems: 'center',
  },
  infoBtnGlassText: {
    color: '#fff',
    fontSize: Typography.caption,
    fontWeight: '600',
  },
  infoBtnColored: {
    flex: 1,
    paddingVertical: Spacing.sm,
    borderRadius: 6,
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.06)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.1)',
  },
  infoBtnContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  infoBtnLogo: {
    width: 24,
    height: 18,
    resizeMode: 'contain',
  },
  infoBtnColoredText: {
    color: '#fff',
    fontSize: Typography.caption,
    fontWeight: '700',
  },
  section: {
    paddingHorizontal: Spacing.screenPadding,
    paddingTop: Spacing.lg,
  },
  sectionTitle: {
    color: Colors.textPrimary,
    fontSize: Typography.body,
    fontWeight: '600',
    marginBottom: Spacing.sm,
  },
  watchSectionLabel: {
    color: '#00d4aa',
    fontSize: Typography.caption - 1,
    fontWeight: '600',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
    marginBottom: 4,
    marginTop: 8,
  },
  infoButton: {
    backgroundColor: Colors.backgroundSecondary,
    paddingVertical: Spacing.sm + 2,
    paddingHorizontal: Spacing.md,
    borderRadius: 8,
    alignItems: 'center',
  },
  infoButtonText: {
    color: Colors.primary,
    fontSize: Typography.button,
    fontWeight: '600',
  },
  synopsis: {
    color: Colors.textPrimary,
    fontSize: Typography.body,
    lineHeight: 24,
  },
  crewText: {
    color: Colors.textSecondary,
    fontSize: Typography.body,
    lineHeight: 22,
  },
  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: Spacing.xs,
    borderBottomWidth: 1,
    borderBottomColor: Colors.backgroundSecondary,
  },
  detailLabel: {
    color: Colors.textMuted,
    fontSize: Typography.body,
  },
  detailValue: {
    color: Colors.textSecondary,
    fontSize: Typography.body,
  },
  pullQuoteCard: {
    marginBottom: Spacing.sm,
    paddingLeft: 10,
    borderLeftWidth: 2,
    borderLeftColor: 'rgba(255,255,255,0.15)',
  },
  pqText: {
    color: Colors.textSecondary,
    fontSize: Typography.caption,
    fontStyle: 'italic',
    lineHeight: 18,
  },
  pqAttribution: {
    color: Colors.textMuted,
    fontSize: Typography.caption - 1,
    marginTop: 2,
  },
});
