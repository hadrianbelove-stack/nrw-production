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
import {openWatchLink, openRottenTomatoes} from '../utils/links';
import {trackMovieView, trackWatchButtonTap} from '../services/analytics';
import TrailerPlayer from '../components/TrailerPlayer';

const COUNTRY_SHORT_NAMES = {
  'united states of america': 'USA', 'united states': 'USA', 'usa': 'USA',
  'united kingdom': 'UK', 'great britain': 'UK',
  'south korea': 'S. Korea', 'south africa': 'S. Africa',
  'new zealand': 'N. Zealand', 'bosnia and herzegovina': 'Bosnia',
  'saudi arabia': 'S. Arabia',
};

const formatCountry = (country) => {
  if (!country) return null;
  const shortened = COUNTRY_SHORT_NAMES[country.toLowerCase()];
  if (shortened) return shortened;
  if (country !== country[0].toUpperCase() + country.slice(1).toLowerCase()) {
    return country[0].toUpperCase() + country.slice(1).toLowerCase();
  }
  return country;
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

  const posterUrl = movie.poster_url || movie.poster;
  const director = movie.director || movie.crew?.director;
  const cast = movie.cast || movie.crew?.cast || [];
  const genres = movie.genres || [];
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
          {/* Staff Pick badge */}
          {(movie.featured || movie.categories?.is_staff_pick) && (
            <View style={styles.staffPickBadge}>
              <Text style={styles.staffPickText}>STAFF PICK</Text>
            </View>
          )}
          {/* Restoration badge */}
          {movie.categories?.is_restoration && (
            <View style={styles.restorationBadge}>
              <Text style={styles.restorationBadgeText}>RESTORED</Text>
            </View>
          )}
        </View>

        <View style={styles.heroInfo}>
          <View style={styles.titleRow}>
            <Text style={styles.title}>{movie.title}</Text>
            {movie.digital_date && (
              <Text style={styles.titleDate}>{formatShortDate(movie.digital_date)}</Text>
            )}
          </View>

          {/* Virtual screening name */}
          {movie.categories?.is_virtual_screening && movie.virtual_screening_info?.screening_name && (
            <Text style={styles.screeningName}>
              {movie.virtual_screening_info.screening_name}
            </Text>
          )}

          {/* Metadata row */}
          <View style={styles.metaRow}>
            {year && <Text style={styles.metaText}>{year}</Text>}
            {runtime && (
              <>
                <Text style={styles.metaDot}>•</Text>
                <Text style={styles.metaText}>{formatRuntime(runtime)}</Text>
              </>
            )}
          </View>

          {/* RT Score */}
          {movie.rt_score && (
            <TouchableOpacity
              style={styles.rtContainer}
              onPress={handleRTPress}
              disabled={!movie.links?.rotten_tomatoes}>
              <View
                style={[
                  styles.rtBadge,
                  {
                    backgroundColor:
                      parseInt(movie.rt_score, 10) >= 60 ? Colors.green : Colors.red,
                  },
                ]}>
                <Text style={styles.rtScore}>{movie.rt_score}</Text>
              </View>
              <Text style={styles.rtLabel}>Rotten Tomatoes</Text>
            </TouchableOpacity>
          )}

          {/* IMDB Rating */}
          {movie.imdb_rating && (
            <View style={styles.rtContainer}>
              <View style={[styles.rtBadge, { backgroundColor: '#F5C518' }]}>
                <Text style={[styles.rtScore, { color: '#000' }]}>{movie.imdb_rating}</Text>
              </View>
              <Text style={styles.rtLabel}>IMDb</Text>
            </View>
          )}

          {/* Genres */}
          {genres.length > 0 && (
            <View style={styles.genresContainer}>
              {genres.slice(0, 3).map((genre, index) => (
                <View key={index} style={styles.genreTag}>
                  <Text style={styles.genreText}>{genre}</Text>
                </View>
              ))}
            </View>
          )}
        </View>
      </View>

      {/* Watch buttons section */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Watch Now</Text>
        <WatchButtonGroup links={watchLinks} onPress={handleWatchPress} maxButtons={4} />
      </View>

      {/* Info buttons */}
      {(movie.links?.trailer_hosted || movie.links?.trailer) && (
        <View style={styles.section}>
          <TouchableOpacity style={styles.infoButton} onPress={handleTrailerPress}>
            <Text style={styles.infoButtonText}>▶ Watch Trailer</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Synopsis */}
      {movie.synopsis && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Synopsis</Text>
          <Text style={styles.synopsis}>{movie.synopsis}</Text>
        </View>
      )}

      {/* Director */}
      {director && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Director</Text>
          <Text style={styles.crewText}>{director}</Text>
        </View>
      )}

      {/* Cast */}
      {cast.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Cast</Text>
          <Text style={styles.crewText}>
            {Array.isArray(cast) ? cast.slice(0, 5).join(', ') : cast}
          </Text>
        </View>
      )}

      {/* Additional info */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Details</Text>
        {movie.country && (
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Country</Text>
            <Text style={styles.detailValue}>{formatCountry(movie.country)}</Text>
          </View>
        )}
        {movie.original_language && (
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Language</Text>
            <Text style={styles.detailValue}>
              {movie.original_language.toUpperCase()}
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
    backgroundColor: Colors.staffPick,
    paddingHorizontal: Spacing.sm,
    paddingVertical: 4,
    borderRadius: 4,
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
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: Spacing.xs,
  },
  metaText: {
    color: Colors.textSecondary,
    fontSize: Typography.caption,
  },
  metaDot: {
    color: Colors.textMuted,
    marginHorizontal: 6,
  },
  rtContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: Spacing.sm,
  },
  rtBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
  },
  rtScore: {
    color: Colors.textPrimary,
    fontSize: Typography.caption,
    fontWeight: '700',
  },
  rtLabel: {
    color: Colors.textMuted,
    fontSize: Typography.caption - 1,
    marginLeft: Spacing.xs,
  },
  genresContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: Spacing.sm,
    gap: Spacing.xs,
  },
  genreTag: {
    backgroundColor: Colors.backgroundSecondary,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
  },
  genreText: {
    color: Colors.textSecondary,
    fontSize: Typography.caption - 1,
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
    color: Colors.textSecondary,
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
});
