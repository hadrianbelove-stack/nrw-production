/**
 * New Release Wall - tvOS Movie Detail Screen
 * Full-screen layout optimized for 10-foot viewing
 */

import React, { useCallback, useRef, useState, useEffect } from 'react';
import {
  View,
  Text,
  Image,
  ScrollView,
  StyleSheet,
  Dimensions,
  Animated,
  ActivityIndicator,
  TouchableOpacity,
} from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import {
  useMovieDetail,
  getPosterUrl,
  getBackdropUrl,
  formatSynopsis,
  getMetadataString,
  getAccessibilityLabel,
} from './useMovieDetail';
import WatchButton, { InfoButton } from '../components/WatchButton.tvos';
import { Colors, Typography, Spacing } from '../constants/colors';
import { useTVEventHandler, TV_EVENTS } from '../utils/focusManager.tvos';
import {
  openAmazon,
  openAppleTV,
  openURL,
  openTrailer,
  openPlex,
  showLinkError,
} from '../utils/links.tvos';
import { fetchMovies } from '../services/api';
import { trackWatchButtonTap, trackInfoButtonTap } from '../services/analytics.tvos';

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');
const POSTER_WIDTH = SCREEN_WIDTH * 0.35;
const CONTENT_WIDTH = SCREEN_WIDTH * 0.55;

const formatShortDate = (dateStr) => {
  const [y, m, d] = dateStr.split('-');
  const dt = new Date(y, m - 1, d);
  return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

// Service colors for streaming buttons
const getServiceColor = (service) => {
  const colors = {
    netflix: '#E50914',
    'disney+': '#113CCF',
    disneyplus: '#113CCF',
    max: '#B537F2',
    hbo: '#B537F2',
    prime: '#00A8E1',
    amazon: '#00A8E1',
    hulu: '#1CE783',
    peacock: '#000000',
    appletv: '#000000',
    paramount: '#0064FF',
    plex: '#E5A00D',
  };
  const key = service.toLowerCase().replace(/[^a-z0-9]/g, '');
  return colors[key] || '#00d4aa';
};

// Simple action button with equal sizing
const ActionButton = ({ label, color, onPress, hasTVPreferredFocus = false, testID }) => {
  const [isFocused, setIsFocused] = useState(false);
  const scaleAnim = useRef(new Animated.Value(1)).current;

  const handleFocus = useCallback(() => {
    setIsFocused(true);
    Animated.spring(scaleAnim, {
      toValue: 1.1,
      useNativeDriver: true,
    }).start();
  }, [scaleAnim]);

  const handleBlur = useCallback(() => {
    setIsFocused(false);
    Animated.spring(scaleAnim, {
      toValue: 1,
      useNativeDriver: true,
    }).start();
  }, [scaleAnim]);

  return (
    <TouchableOpacity
      onPress={onPress}
      onFocus={handleFocus}
      onBlur={handleBlur}
      hasTVPreferredFocus={hasTVPreferredFocus}
      activeOpacity={0.9}
      accessible={true}
      accessibilityLabel={label}
      accessibilityRole="button"
      testID={testID}
    >
      <Animated.View
        style={[
          actionButtonStyles.button,
          { backgroundColor: color },
          isFocused && actionButtonStyles.buttonFocused,
          { transform: [{ scale: scaleAnim }] },
        ]}
      >
        <Text style={actionButtonStyles.label}>{label}</Text>
      </Animated.View>
    </TouchableOpacity>
  );
};

const actionButtonStyles = StyleSheet.create({
  button: {
    width: 200,
    height: 60,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 20,
  },
  buttonFocused: {
    borderWidth: 4,
    borderColor: '#ffffff',
  },
  label: {
    color: '#ffffff',
    fontSize: 20,
    fontWeight: '700',
    letterSpacing: 1,
  },
});

const MovieDetailTvOS = () => {
  const navigation = useNavigation();
  const route = useRoute();
  const { movie: passedMovie, id: movieId } = route.params || {};
  const scrollViewRef = useRef(null);
  const fadeAnim = useRef(new Animated.Value(0)).current;

  // Arrow animation refs for navigation feedback
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

  // Local state for loading movie from id
  const [movie, setMovie] = useState(passedMovie || null);
  const [isLoadingMovie, setIsLoadingMovie] = useState(!passedMovie && !!movieId);
  const [loadError, setLoadError] = useState(null);

  // Movie list for left/right navigation
  const [movieList, setMovieList] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);

  // Load movie from id if not passed directly (deep link case)
  useEffect(() => {
    const loadMovies = async () => {
      try {
        const { movies } = await fetchMovies();
        setMovieList(movies);

        // Find the current movie in the list
        const targetId = passedMovie?.id || movieId;
        const index = movies.findIndex(m => String(m.id) === String(targetId));

        if (passedMovie) {
          setMovie(passedMovie);
          setCurrentIndex(index >= 0 ? index : 0);
          return;
        }

        if (!movieId) return;

        setIsLoadingMovie(true);
        setLoadError(null);

        if (index >= 0) {
          setMovie(movies[index]);
          setCurrentIndex(index);
        } else {
          setLoadError('Movie not found');
        }
      } catch (error) {
        console.error('[MovieDetail] Error loading movie:', error);
        setLoadError('Failed to load movie');
      } finally {
        setIsLoadingMovie(false);
      }
    };

    loadMovies();
  }, [passedMovie, movieId]);

  // Navigate to next movie (cycles to first if at end)
  const navigateNext = useCallback(() => {
    if (movieList.length === 0) return;
    flashArrow(rightArrowOpacity);
    const nextIndex = (currentIndex + 1) % movieList.length;
    setCurrentIndex(nextIndex);
    setMovie(movieList[nextIndex]);
  }, [movieList, currentIndex, flashArrow, rightArrowOpacity]);

  // Navigate to previous movie (cycles to last if at start)
  const navigatePrevious = useCallback(() => {
    if (movieList.length === 0) return;
    flashArrow(leftArrowOpacity);
    const prevIndex = currentIndex === 0 ? movieList.length - 1 : currentIndex - 1;
    setCurrentIndex(prevIndex);
    setMovie(movieList[prevIndex]);
  }, [movieList, currentIndex, flashArrow, leftArrowOpacity]);

  // Get shared state
  const {
    watchLinks,
    infoLinks,
    plexLinks,
    purchaseLinks,
    streamingLinks,
    formattedRuntime,
    formattedGenres,
    rtScore,
    formattedCountries,
    hasWatchOptions,
    hasInfoLinks,
  } = useMovieDetail(movie);

  // Local state
  const [synopsisExpanded, setSynopsisExpanded] = useState(false);

  // Fade in on mount
  React.useEffect(() => {
    Animated.timing(fadeAnim, {
      toValue: 1,
      duration: 300,
      useNativeDriver: true,
    }).start();
  }, [fadeAnim]);

  // Handle TV remote events
  useTVEventHandler({
    [TV_EVENTS.MENU]: () => {
      navigation.goBack();
    },
    [TV_EVENTS.PLAY_PAUSE]: () => {
      // Play trailer if available
      const trailerLink = infoLinks.find((l) => l.type === 'trailer');
      if (trailerLink) {
        handleLinkPress(trailerLink);
      }
    },
    [TV_EVENTS.LEFT]: () => {
      navigatePrevious();
    },
    [TV_EVENTS.RIGHT]: () => {
      navigateNext();
    },
  });

  // Handle watch button press
  const handleWatchPress = useCallback(async (link) => {
    // Track analytics
    if (movie) {
      trackWatchButtonTap(movie, link.service, link.type);
    }

    try {
      let result;

      if (link.service === 'plex') {
        result = await openPlex(link.url);
      } else if (link.service === 'amazon') {
        result = await openAmazon(link.url);
      } else if (link.service === 'apple_tv') {
        result = await openAppleTV(link.url);
      } else {
        result = await openURL(link.url, link.service);
      }

      if (!result.success) {
        showLinkError(link.label);
      }
    } catch (error) {
      console.error('[MovieDetail] Error opening link:', error);
      showLinkError(link.label);
    }
  }, [movie]);

  // Handle info button press
  const handleLinkPress = useCallback(async (link) => {
    // Track analytics
    if (movie) {
      trackInfoButtonTap(movie, link.type);
    }

    try {
      // For trailers, use the trailer-specific opener (YouTube deep linking)
      if (link.type === 'trailer') {
        const result = await openTrailer(link.url);
        if (!result.success) {
          showLinkError(link.label);
        }
        return;
      }

      const result = await openURL(link.url);

      if (!result.success) {
        showLinkError(link.label);
      }
    } catch (error) {
      console.error('[MovieDetail] Error opening link:', error);
      showLinkError(link.label);
    }
  }, [movie]);

  // Toggle synopsis expansion
  const toggleSynopsis = useCallback(() => {
    setSynopsisExpanded((prev) => !prev);
  }, []);

  // Show loading state when fetching movie from id
  if (isLoadingMovie) {
    return (
      <View style={styles.container}>
        <View style={styles.errorContainer}>
          <ActivityIndicator size="large" color={Colors.primary} />
          <Text style={[styles.errorText, { marginTop: Spacing.tvos.lg }]}>
            Loading movie...
          </Text>
        </View>
      </View>
    );
  }

  // Show error state
  if (!movie || loadError) {
    return (
      <View style={styles.container}>
        <View style={styles.errorContainer}>
          <Text style={styles.errorText}>{loadError || 'Movie not found'}</Text>
          <Text style={styles.errorHint}>Press Menu to go back</Text>
        </View>
      </View>
    );
  }

  const posterUrl = getPosterUrl(movie, 'w780');
  const backdropUrl = getBackdropUrl(movie);
  const metadataString = getMetadataString(movie);
  const accessibilityLabel = getAccessibilityLabel(movie);

  return (
    <Animated.View style={[styles.container, { opacity: fadeAnim }]}>
      {/* Backdrop image (blurred background) */}
      {backdropUrl && (
        <Image
          source={{ uri: backdropUrl }}
          style={styles.backdrop}
          blurRadius={20}
        />
      )}
      <View style={styles.backdropOverlay} />

      <View style={styles.content}>
        {/* Left side - Poster */}
        <View style={styles.posterContainer}>
          <Image
            source={{ uri: posterUrl }}
            style={styles.poster}
            resizeMode="cover"
            accessible={true}
            accessibilityLabel={`Movie poster for ${movie.title}`}
          />

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

          {/* RT Score badge */}
          {rtScore && (
            <View
              style={[
                styles.rtBadge,
                { backgroundColor: rtScore.isFresh ? Colors.green : Colors.red },
              ]}
            >
              <Text style={styles.rtScore}>{rtScore.label}</Text>
              <Text style={styles.rtLabel}>
                {rtScore.isFresh ? 'Fresh' : 'Rotten'}
              </Text>
            </View>
          )}
        </View>

        {/* Right side - Details */}
        <View style={styles.detailsContainer}>
          <ScrollView
            ref={scrollViewRef}
            style={styles.detailsScroll}
            showsVerticalScrollIndicator={true}
            contentContainerStyle={styles.detailsScrollContent}
          >
            {/* Title row with date */}
            <View style={styles.titleRow}>
              <Text
                style={styles.title}
                accessible={true}
                accessibilityLabel={accessibilityLabel}
                accessibilityRole="header"
              >
                {movie.title}
              </Text>
              {movie.digital_date && (
                <Text style={styles.titleDate}>{formatShortDate(movie.digital_date)}</Text>
              )}
            </View>

            {/* Metadata row */}
            <View style={styles.metadataRow}>
              {movie.year && (
                <Text style={styles.metadataText}>{movie.year}</Text>
              )}
              {formattedRuntime && (
                <>
                  <Text style={styles.metadataDot}>•</Text>
                  <Text style={styles.metadataText}>{formattedRuntime}</Text>
                </>
              )}
              {movie.rating && (
                <>
                  <Text style={styles.metadataDot}>•</Text>
                  <View style={styles.ratingBadge}>
                    <Text style={styles.ratingText}>{movie.rating}</Text>
                  </View>
                </>
              )}
            </View>

            {/* Genres */}
            {formattedGenres && (
              <Text style={styles.genres}>{formattedGenres}</Text>
            )}

            {/* Director */}
            {movie.director && (
              <View style={styles.creditRow}>
                <Text style={styles.creditLabel}>Directed by</Text>
                <Text style={styles.creditValue}>{movie.director}</Text>
              </View>
            )}

            {/* Countries */}
            {formattedCountries && (
              <View style={styles.creditRow}>
                <Text style={styles.creditLabel}>Country</Text>
                <Text style={styles.creditValue}>{formattedCountries}</Text>
              </View>
            )}

            {/* Cast */}
            {movie.crew?.cast?.length > 0 && (
              <View style={styles.creditRow}>
                <Text style={styles.creditLabel}>Starring</Text>
                <Text style={styles.creditValue}>{movie.crew.cast.slice(0, 2).join(', ')}</Text>
              </View>
            )}

            {/* Language (only if not English) */}
            {movie.original_language && movie.original_language !== 'en' && (
              <View style={styles.creditRow}>
                <Text style={styles.creditLabel}>Language</Text>
                <Text style={styles.creditValue}>{movie.original_language.toUpperCase()}</Text>
              </View>
            )}

            {/* Action buttons - single row, equal sizing (above synopsis) */}
            {(hasWatchOptions || hasInfoLinks) && (
              <View style={styles.actionButtonRow}>
                {/* TRAILER button */}
                {infoLinks.find(l => l.type === 'trailer') && (
                  <ActionButton
                    label="TRAILER"
                    color="#E50914"
                    onPress={() => handleLinkPress(infoLinks.find(l => l.type === 'trailer'))}
                    hasTVPreferredFocus={true}
                    testID="action-btn-trailer"
                  />
                )}

                {/* RENT/BUY button - first purchase option */}
                {purchaseLinks.length > 0 && (
                  <ActionButton
                    label="RENT / BUY"
                    color="#ff9500"
                    onPress={() => handleWatchPress(purchaseLinks[0])}
                    hasTVPreferredFocus={!infoLinks.find(l => l.type === 'trailer')}
                    testID="action-btn-purchase"
                  />
                )}

                {/* STREAM button - first streaming option, shows service name */}
                {streamingLinks.length > 0 && (
                  <ActionButton
                    label={streamingLinks[0].service.toUpperCase()}
                    color={getServiceColor(streamingLinks[0].service)}
                    onPress={() => handleWatchPress(streamingLinks[0])}
                    hasTVPreferredFocus={!infoLinks.find(l => l.type === 'trailer') && purchaseLinks.length === 0}
                    testID="action-btn-stream"
                  />
                )}

                {/* PLEX button if available */}
                {plexLinks.length > 0 && (
                  <ActionButton
                    label="PLEX"
                    color="#E5A00D"
                    onPress={() => handleWatchPress(plexLinks[0])}
                    testID="action-btn-plex"
                  />
                )}
              </View>
            )}

            {/* Synopsis (no header) */}
            {movie.synopsis && (
              <View style={styles.synopsisContainer}>
                <Text style={styles.synopsis} numberOfLines={synopsisExpanded ? undefined : 6}>
                  {movie.synopsis}
                </Text>
              </View>
            )}
          </ScrollView>
        </View>
      </View>

      {/* Navigation arrow indicators */}
      <View style={styles.navArrowLeft}>
        <Animated.Text style={[styles.navArrowText, { opacity: leftArrowOpacity }]}>‹</Animated.Text>
      </View>
      <View style={styles.navArrowRight}>
        <Animated.Text style={[styles.navArrowText, { opacity: rightArrowOpacity }]}>›</Animated.Text>
      </View>

    </Animated.View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  backdrop: {
    ...StyleSheet.absoluteFillObject,
    width: SCREEN_WIDTH,
    height: SCREEN_HEIGHT,
  },
  backdropOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(10, 10, 10, 0.85)',
  },
  content: {
    flex: 1,
    flexDirection: 'row',
    paddingHorizontal: Spacing.tvos.screenPadding,
    paddingTop: Spacing.tvos.xl,
  },
  posterContainer: {
    width: POSTER_WIDTH,
    marginRight: Spacing.tvos.xl,
    position: 'relative',
  },
  poster: {
    width: POSTER_WIDTH,
    height: POSTER_WIDTH * 1.5,
    borderRadius: 16,
    backgroundColor: Colors.backgroundSecondary,
  },
  staffPickBadge: {
    position: 'absolute',
    top: Spacing.tvos.md,
    left: Spacing.tvos.md,
    backgroundColor: Colors.staffPick,
    paddingHorizontal: Spacing.tvos.md,
    paddingVertical: Spacing.tvos.xs,
    borderRadius: 6,
  },
  staffPickText: {
    color: Colors.staffPickText,
    fontSize: Typography.tvos.caption,
    fontWeight: '700',
    letterSpacing: 1,
  },
  restorationBadge: {
    position: 'absolute',
    top: Spacing.tvos.md,
    right: Spacing.tvos.md,
    backgroundColor: Colors.restoration,
    paddingHorizontal: Spacing.tvos.md,
    paddingVertical: Spacing.tvos.xs,
    borderRadius: 6,
  },
  restorationBadgeText: {
    color: Colors.restorationText,
    fontSize: Typography.tvos.caption,
    fontWeight: '700',
    letterSpacing: 1,
  },
  rtBadge: {
    position: 'absolute',
    bottom: Spacing.tvos.md,
    right: Spacing.tvos.md,
    paddingHorizontal: Spacing.tvos.md,
    paddingVertical: Spacing.tvos.sm,
    borderRadius: 8,
    alignItems: 'center',
  },
  rtScore: {
    color: Colors.textPrimary,
    fontSize: Typography.tvos.body,
    fontWeight: '800',
  },
  rtLabel: {
    color: Colors.textPrimary,
    fontSize: Typography.tvos.caption - 2,
    fontWeight: '500',
    marginTop: 2,
  },
  detailsContainer: {
    flex: 1,
    maxWidth: CONTENT_WIDTH,
  },
  detailsScroll: {
    flex: 1,
  },
  detailsScrollContent: {
    paddingBottom: Spacing.tvos.xl,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderBottomWidth: 2,
    borderBottomColor: 'rgba(0, 212, 170, 0.4)',
    paddingBottom: Spacing.tvos.sm,
    marginBottom: Spacing.tvos.md,
  },
  title: {
    color: Colors.textPrimary,
    fontSize: Typography.tvos.title,
    fontWeight: '700',
    lineHeight: Typography.tvos.title * 1.2,
    flex: 1,
  },
  titleDate: {
    color: Colors.primary,
    fontSize: Typography.tvos.title - 8,
    fontWeight: '700',
    marginLeft: Spacing.tvos.md,
  },
  metadataRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: Spacing.tvos.sm,
  },
  metadataText: {
    color: Colors.textSecondary,
    fontSize: Typography.tvos.body,
  },
  metadataDot: {
    color: Colors.textMuted,
    fontSize: Typography.tvos.body,
    marginHorizontal: Spacing.tvos.sm,
  },
  ratingBadge: {
    borderWidth: 1,
    borderColor: Colors.textSecondary,
    paddingHorizontal: Spacing.tvos.sm,
    paddingVertical: 2,
    borderRadius: 4,
  },
  ratingText: {
    color: Colors.textSecondary,
    fontSize: Typography.tvos.caption,
    fontWeight: '600',
  },
  genres: {
    color: Colors.primary,
    fontSize: Typography.tvos.body,
    marginBottom: Spacing.tvos.md,
  },
  creditRow: {
    flexDirection: 'row',
    marginBottom: Spacing.tvos.xs,
  },
  creditLabel: {
    color: Colors.textMuted,
    fontSize: Typography.tvos.body,
    marginRight: Spacing.tvos.sm,
  },
  creditValue: {
    color: Colors.textPrimary,
    fontSize: Typography.tvos.body,
    fontWeight: '500',
  },
  synopsisContainer: {
    marginTop: Spacing.tvos.lg,
  },
  sectionTitle: {
    color: Colors.textPrimary,
    fontSize: Typography.tvos.subtitle,
    fontWeight: '600',
    marginBottom: Spacing.tvos.sm,
  },
  synopsis: {
    color: Colors.textSecondary,
    fontSize: Typography.tvos.body,
    lineHeight: Typography.tvos.body * 1.5,
  },
  section: {
    marginTop: Spacing.tvos.lg,
  },
  buttonRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: Spacing.tvos.sm,
  },
  actionButtonRow: {
    flexDirection: 'row',
    marginTop: Spacing.tvos.lg,
    alignItems: 'center',
    paddingLeft: Spacing.tvos.md,  // Add clearance from poster edge
  },
  navArrowLeft: {
    position: 'absolute',
    left: 20,
    top: 0,
    bottom: 0,
    justifyContent: 'center',
    zIndex: 10,
  },
  navArrowRight: {
    position: 'absolute',
    right: 20,
    top: 0,
    bottom: 0,
    justifyContent: 'center',
    zIndex: 10,
  },
  navArrowText: {
    color: 'rgba(0, 212, 170, 0.6)',  // Teal at 60%
    fontSize: 80,
    fontWeight: '300',
  },
  errorContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  errorText: {
    color: Colors.textPrimary,
    fontSize: Typography.tvos.subtitle,
    marginBottom: Spacing.tvos.md,
  },
  errorHint: {
    color: Colors.textMuted,
    fontSize: Typography.tvos.caption,
  },
});

export default MovieDetailTvOS;
