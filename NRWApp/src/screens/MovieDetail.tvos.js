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
} from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import {
  useMovieDetail,
  getPosterUrl,
  getBackdropUrl,
  formatSynopsis,
  getMetadataString,
  getAccessibilityLabel,
} from './MovieDetail';
import WatchButton, { InfoButton } from '../components/WatchButton.tvos';
import { Colors, Typography, Spacing } from '../constants/colors';
import { useTVEventHandler, TV_EVENTS } from '../utils/focusManager.tvos';
import {
  openAmazon,
  openAppleTV,
  openURL,
  openTrailer,
  showLinkError,
} from '../utils/links.tvos';
import { fetchMovies } from '../services/api';
import { trackWatchButtonTap, trackInfoButtonTap } from '../services/analytics.tvos';

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');
const POSTER_WIDTH = SCREEN_WIDTH * 0.35;
const CONTENT_WIDTH = SCREEN_WIDTH * 0.55;

const MovieDetailTvOS = () => {
  const navigation = useNavigation();
  const route = useRoute();
  const { movie: passedMovie, id: movieId } = route.params || {};
  const scrollViewRef = useRef(null);
  const fadeAnim = useRef(new Animated.Value(0)).current;

  // Local state for loading movie from id
  const [movie, setMovie] = useState(passedMovie || null);
  const [isLoadingMovie, setIsLoadingMovie] = useState(!passedMovie && !!movieId);
  const [loadError, setLoadError] = useState(null);

  // Load movie from id if not passed directly (deep link case)
  useEffect(() => {
    if (passedMovie) {
      setMovie(passedMovie);
      return;
    }

    if (!movieId) return;

    const loadMovie = async () => {
      setIsLoadingMovie(true);
      setLoadError(null);

      try {
        const { movies } = await fetchMovies();
        const foundMovie = movies.find(m => String(m.id) === String(movieId));

        if (foundMovie) {
          setMovie(foundMovie);
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

    loadMovie();
  }, [passedMovie, movieId]);

  // Get shared state
  const {
    watchLinks,
    infoLinks,
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
  });

  // Handle watch button press
  const handleWatchPress = useCallback(async (link) => {
    // Track analytics
    if (movie) {
      trackWatchButtonTap(movie, link.service, link.type);
    }

    try {
      let result;

      if (link.service === 'amazon') {
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
      let result;

      if (link.type === 'trailer') {
        result = await openTrailer(link.url);
      } else {
        result = await openURL(link.url);
      }

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

          {/* Featured badge */}
          {movie.featured && (
            <View style={styles.featuredBadge}>
              <Text style={styles.featuredText}>FEATURED</Text>
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
            {/* Title */}
            <Text
              style={styles.title}
              accessible={true}
              accessibilityLabel={accessibilityLabel}
              accessibilityRole="header"
            >
              {movie.title}
            </Text>

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

            {/* Synopsis */}
            {movie.synopsis && (
              <View style={styles.synopsisContainer}>
                <Text style={styles.sectionTitle}>Synopsis</Text>
                <Text style={styles.synopsis} numberOfLines={synopsisExpanded ? undefined : 6}>
                  {movie.synopsis}
                </Text>
              </View>
            )}

            {/* Watch buttons */}
            {hasWatchOptions && (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>Where to Watch</Text>

                {/* Purchase/Rent options */}
                {purchaseLinks.length > 0 && (
                  <View style={styles.buttonRow}>
                    {purchaseLinks.map((link, index) => (
                      <WatchButton
                        key={link.service}
                        service={link.service}
                        label={link.label}
                        type="purchase"
                        onPress={() => handleWatchPress(link)}
                        hasTVPreferredFocus={index === 0}
                        testID={`watch-btn-${link.service}`}
                      />
                    ))}
                  </View>
                )}

                {/* Streaming options */}
                {streamingLinks.length > 0 && (
                  <View style={styles.buttonRow}>
                    {streamingLinks.map((link) => (
                      <WatchButton
                        key={link.service}
                        service={link.service}
                        label={link.label}
                        type="streaming"
                        onPress={() => handleWatchPress(link)}
                        testID={`watch-btn-${link.service}`}
                      />
                    ))}
                  </View>
                )}
              </View>
            )}

            {/* Info buttons */}
            {hasInfoLinks && (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>More Info</Text>
                <View style={styles.buttonRow}>
                  {infoLinks.map((link) => (
                    <InfoButton
                      key={link.type}
                      type={link.type}
                      label={link.label}
                      onPress={() => handleLinkPress(link)}
                      testID={`info-btn-${link.type}`}
                    />
                  ))}
                </View>
              </View>
            )}
          </ScrollView>
        </View>
      </View>

      {/* Footer hint */}
      <View style={styles.footer}>
        <Text style={styles.footerText}>
          Menu to go back • Play/Pause for trailer
        </Text>
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
  featuredBadge: {
    position: 'absolute',
    top: Spacing.tvos.md,
    left: Spacing.tvos.md,
    backgroundColor: Colors.primary,
    paddingHorizontal: Spacing.tvos.md,
    paddingVertical: Spacing.tvos.xs,
    borderRadius: 6,
  },
  featuredText: {
    color: Colors.background,
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
  title: {
    color: Colors.textPrimary,
    fontSize: Typography.tvos.title,
    fontWeight: '700',
    marginBottom: Spacing.tvos.md,
    lineHeight: Typography.tvos.title * 1.2,
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
  footer: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    paddingVertical: Spacing.tvos.md,
    alignItems: 'center',
    backgroundColor: 'rgba(10, 10, 10, 0.8)',
  },
  footerText: {
    color: Colors.textMuted,
    fontSize: Typography.tvos.caption,
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
