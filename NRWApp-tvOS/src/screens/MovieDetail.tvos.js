/**
 * New Release Wall - tvOS Movie Detail Screen
 * Full-screen layout optimized for 10-foot viewing
 */

import React, { useCallback, useRef, useState, useEffect, forwardRef } from 'react';
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
  findNodeHandle,
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
import { Colors, Typography, Spacing, getServiceColor, isVirtualScreeningPlatform } from '../constants/colors';
import QRCode from 'react-native-qrcode-svg';
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
import TrailerPlayer from '../components/TrailerPlayer.tvos';
import { getSharedMovieList } from './sharedMovieList';

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');
const POSTER_WIDTH = SCREEN_WIDTH * 0.35;
const CONTENT_WIDTH = SCREEN_WIDTH * 0.55;

const formatShortDate = (dateStr) => {
  const [y, m, d] = dateStr.split('-');
  const dt = new Date(y, m - 1, d);
  return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

// Decode HTML entities (e.g. &#x27; → ')
const decodeHtml = (str) => str.replace(/&#x27;/g, "'").replace(/&amp;/g, '&').replace(/&quot;/g, '"');

// Module-level edge navigation tracking.
// Track which watch button is focused by index. When the user presses RIGHT
// at the last watch button (or LEFT at the first), navigate to next/prev movie.
// No timers — deterministic index check.
let _totalButtonCount = 0;    // Total ActionButtons mounted (including trailer)
let _focusedWatchIndex = -1;  // Which watch-row button is focused (-1 = none)
let _watchButtonCount = 0;    // How many watch-row buttons are mounted
let _lastWatchBlurTime = 0;   // Timestamp of last watch-button blur (for edge detection)

// Simple action button with equal sizing — forwardRef for focus navigation wiring
const ActionButton = forwardRef(({
  label, color, onPress, hasTVPreferredFocus = false, testID,
  borderColor, textColor, icon, iconTintColor,
  nextFocusUp, nextFocusDown, nextFocusLeft, nextFocusRight,
  buttonIndex, isWatchButton = false,
}, ref) => {
  const [isFocused, setIsFocused] = useState(false);
  const scaleAnim = useRef(new Animated.Value(1)).current;

  // Track mounted buttons
  useEffect(() => {
    _totalButtonCount++;
    if (isWatchButton) _watchButtonCount++;
    return () => {
      _totalButtonCount--;
      if (isWatchButton) _watchButtonCount--;
    };
  }, []);

  const handleFocus = useCallback(() => {
    setIsFocused(true);
    if (isWatchButton) _focusedWatchIndex = buttonIndex;
    Animated.spring(scaleAnim, {
      toValue: 1.1,
      useNativeDriver: true,
    }).start();
  }, [scaleAnim, isWatchButton, buttonIndex]);

  const handleBlur = useCallback(() => {
    setIsFocused(false);
    if (isWatchButton) {
      if (_focusedWatchIndex === buttonIndex) _focusedWatchIndex = -1;
      _lastWatchBlurTime = Date.now();
    }
    Animated.spring(scaleAnim, {
      toValue: 1,
      useNativeDriver: true,
    }).start();
  }, [scaleAnim, isWatchButton, buttonIndex]);

  return (
    <TouchableOpacity
      ref={ref}
      onPress={onPress}
      onFocus={handleFocus}
      onBlur={handleBlur}
      hasTVPreferredFocus={hasTVPreferredFocus}
      nextFocusUp={nextFocusUp}
      nextFocusDown={nextFocusDown}
      nextFocusLeft={nextFocusLeft}
      nextFocusRight={nextFocusRight}
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
          borderColor && { borderWidth: 1, borderColor },
          isFocused && actionButtonStyles.buttonFocused,
          { transform: [{ scale: scaleAnim }] },
        ]}
      >
        {icon ? (
          <Image source={icon} style={[actionButtonStyles.logoFull, iconTintColor && { tintColor: iconTintColor }]} />
        ) : (
          <Text style={[actionButtonStyles.label, textColor && { color: textColor }]}>{label}</Text>
        )}
      </Animated.View>
    </TouchableOpacity>
  );
});

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
    borderColor: Colors.focusBorderHighlight,
  },
  label: {
    color: '#ffffff',
    fontSize: 20,
    fontWeight: '700',
    letterSpacing: 1,
  },
  logoFull: {
    width: 140,
    height: 32,
    resizeMode: 'contain',
  },
});

// Rotten Tomatoes display — freshness icon + score (display-only)
const RTDisplay = ({ score }) => {
  const isCertifiedFresh = score >= 75;
  const isFresh = score >= 60;
  const label = isCertifiedFresh ? 'CERTIFIED FRESH' : isFresh ? 'FRESH' : 'ROTTEN';
  const labelColor = isCertifiedFresh ? '#FFD700' : isFresh ? '#FA3232' : '#77B900';

  return (
    <View style={scoreStyles.container} accessible={true} accessibilityLabel={`Rotten Tomatoes ${score} percent ${label}`}>
      <View style={scoreStyles.iconWrap}>
        <Image
          source={require('../../assets/logos/rt.png')}
          style={[scoreStyles.rtIcon, !isFresh && { tintColor: '#77B900' }]}
        />
        {isCertifiedFresh && (
          <View style={scoreStyles.certifiedBadge}>
            <Text style={scoreStyles.certifiedCheck}>{'\u2713'}</Text>
          </View>
        )}
      </View>
      <View>
        <Text style={scoreStyles.scoreValue}>{score}%</Text>
        <Text style={[scoreStyles.freshnessLabel, { color: labelColor }]}>{label}</Text>
      </View>
    </View>
  );
};

// Metacritic display — colored score box + logo wordmark (display-only)
const MetacriticDisplay = ({ score }) => {
  if (!score || score === 0) return null;

  const getColor = (s) => {
    if (s >= 61) return '#66cc33';
    if (s >= 40) return '#ffcc33';
    return '#ff0000';
  };

  return (
    <View style={scoreStyles.container} accessible={true} accessibilityLabel={`Metacritic score ${score}`}>
      <Image source={require('../../assets/logos/metacritic.png')} style={scoreStyles.mcIcon} />
      <View style={[scoreStyles.mcBox, { backgroundColor: getColor(score) }]}>
        <Text style={scoreStyles.mcScore}>{score}</Text>
      </View>
    </View>
  );
};

const scoreStyles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    marginRight: 24,
  },
  iconWrap: {
    width: 40,
    height: 40,
    marginRight: 10,
  },
  rtIcon: {
    width: 40,
    height: 40,
    resizeMode: 'contain',
  },
  certifiedBadge: {
    position: 'absolute',
    bottom: -2,
    right: -4,
    width: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: '#FFD700',
    justifyContent: 'center',
    alignItems: 'center',
  },
  certifiedCheck: {
    color: '#000',
    fontSize: 12,
    fontWeight: '900',
  },
  scoreValue: {
    color: '#ffffff',
    fontSize: 22,
    fontWeight: '800',
  },
  freshnessLabel: {
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.5,
    marginTop: 1,
  },
  mcBox: {
    width: 48,
    height: 48,
    borderRadius: 6,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 10,
  },
  mcScore: {
    color: '#ffffff',
    fontSize: 24,
    fontWeight: '800',
  },
  mcIcon: {
    width: 40,
    height: 40,
    resizeMode: 'contain',
    marginRight: 10,
    tintColor: '#ffffff',
  },
  imdbLogo: {
    width: 48,
    height: 24,
    resizeMode: 'contain',
    marginRight: 8,
  },
});

// Service display names — matches web app's shared-config.js maps
const getStreamDisplayName = (service) => {
  const n = normalizeService(service);
  const map = { amazon: 'PRIME', prime_video: 'PRIME', apple_tv: 'APPLE TV+', disney_plus: 'DISNEY+', paramount_plus: 'PARAMOUNT+', amc: 'AMC+', netflix: 'NETFLIX', max: 'MAX', hulu: 'HULU', peacock: 'PEACOCK', mubi: 'MUBI', criterion: 'CRITERION', plex: 'PLEX' };
  return map[n] || service.toUpperCase();
};
const getVodDisplayName = (service) => {
  const n = normalizeService(service);
  const map = { amazon: 'AMAZON', apple_tv: 'APPLE TV', fandango: 'FANDANGO', youtube: 'YOUTUBE', plex: 'PLEX' };
  return map[n] || service.toUpperCase();
};

// Service logo images (white logos on brand-color backgrounds)
const SERVICE_LOGOS = {
  amazon: require('../../assets/logos/services/amazon.png'),
  apple_tv: require('../../assets/logos/services/apple_tv.png'),
  netflix: require('../../assets/logos/services/netflix.png'),
  hulu: require('../../assets/logos/services/hulu.png'),
  max: require('../../assets/logos/services/max.png'),
  disney_plus: require('../../assets/logos/services/disney_plus.png'),
  peacock: require('../../assets/logos/services/peacock.png'),
  paramount_plus: require('../../assets/logos/services/paramount_plus.png'),
  mubi: require('../../assets/logos/services/mubi.png'),
  criterion: require('../../assets/logos/services/criterion.png'),
  amc: require('../../assets/logos/services/amc.png'),
  fandango: require('../../assets/logos/services/fandango.png'),
  plex: require('../../assets/logos/services/plex.png'),
};
// Normalize service names to match logo keys
const normalizeService = (service) => {
  if (!service) return service;
  const s = service.toLowerCase();
  if (s.includes('apple')) return 'apple_tv';
  if (s === 'amazon_video' || s === 'prime_video') return 'amazon';
  if (s === 'hbo_max') return 'max';
  if (s === 'amc_plus') return 'amc';
  return s;
};
const getServiceLogo = (service) => SERVICE_LOGOS[normalizeService(service)] || null;

// Services that need a visible border on dark backgrounds (black bg buttons)
const NEEDS_BORDER = ['apple_tv', 'peacock', 'criterion'];

// Visual-only chevron indicator at screen edges.
// NOT focusable — purely decorative. Navigation is handled by the TV event handler
// detecting RIGHT/LEFT when focus can't move further.
const ChevronIndicator = ({ direction, active }) => {
  const isLeft = direction === 'left';
  return (
    <View style={[chevronStyles.container, isLeft ? chevronStyles.left : chevronStyles.right]}>
      <Animated.View style={[chevronStyles.circle, active && chevronStyles.active]}>
        <Text style={[chevronStyles.symbol, active && chevronStyles.symbolActive]}>
          {isLeft ? '\u2039' : '\u203A'}
        </Text>
      </Animated.View>
    </View>
  );
};

const chevronStyles = StyleSheet.create({
  container: {
    justifyContent: 'center',
    alignItems: 'center',
    alignSelf: 'center',
  },
  left: {
    marginLeft: -Spacing.tvos.screenPadding,
    marginRight: Spacing.tvos.md,
  },
  right: {
    marginRight: -Spacing.tvos.screenPadding,
    marginLeft: Spacing.tvos.md,
  },
  circle: {
    width: 50,
    height: 50,
    borderRadius: 25,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.06)',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.12)',
  },
  active: {
    backgroundColor: 'rgba(0, 212, 170, 0.3)',
    borderColor: Colors.focusBorderHighlight,
  },
  symbol: {
    color: 'rgba(255, 255, 255, 0.3)',
    fontSize: 32,
    fontWeight: '300',
    marginTop: -2,
  },
  symbolActive: {
    color: '#ffffff',
  },
});

const MovieDetailTvOS = () => {
  const navigation = useNavigation();
  const route = useRoute();
  const { movie: passedMovie, id: movieId, movieIndex } = route.params || {};
  const scrollViewRef = useRef(null);
  const fadeAnim = useRef(new Animated.Value(0)).current;

  // Local state for loading movie from id
  const [movie, setMovie] = useState(passedMovie || null);
  const [isLoadingMovie, setIsLoadingMovie] = useState(!passedMovie && !!movieId);
  const [loadError, setLoadError] = useState(null);

  // Movie list for left/right navigation — read from shared module-level store
  // (avoids serializing 1.6MB through React Navigation route params)
  const [movieList, setMovieList] = useState(() => getSharedMovieList());
  const [currentIndex, setCurrentIndex] = useState(() => {
    if (typeof movieIndex === 'number') return movieIndex;
    const shared = getSharedMovieList();
    if (shared.length > 0 && passedMovie) {
      const idx = shared.findIndex(m => String(m.id) === String(passedMovie.id));
      return idx >= 0 ? idx : 0;
    }
    return 0;
  });

  // Reset module-level tracking on unmount
  useEffect(() => {
    return () => { _focusedWatchIndex = -1; _watchButtonCount = 0; _totalButtonCount = 0; _lastWatchBlurTime = 0; };
  }, []);

  // Deep link fallback: fetch movies only if shared list is empty (e.g., deep link into app)
  useEffect(() => {
    if (movieList.length > 0) return;

    const loadMovies = async () => {
      try {
        const { movies } = await fetchMovies();
        setMovieList(movies);

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

  // Chevron flash state — briefly lights up when edge navigation fires
  const [chevronFlash, setChevronFlash] = useState(null); // 'left' | 'right' | null
  const flashTimer = useRef(null);

  // Navigate to next movie (cycles to first if at end)
  const navigateNext = useCallback(() => {
    if (movieList.length === 0) return;
    const nextIndex = (currentIndex + 1) % movieList.length;
    setPreferWatchFocus(_focusedWatchIndex >= 0);
    setCurrentIndex(nextIndex);
    setMovie(movieList[nextIndex]);
    // Flash the right chevron
    setChevronFlash('right');
    clearTimeout(flashTimer.current);
    flashTimer.current = setTimeout(() => setChevronFlash(null), 300);
  }, [movieList, currentIndex]);

  // Navigate to previous movie (cycles to last if at start)
  const navigatePrevious = useCallback(() => {
    if (movieList.length === 0) return;
    const prevIndex = currentIndex === 0 ? movieList.length - 1 : currentIndex - 1;
    setPreferWatchFocus(_focusedWatchIndex >= 0);
    setCurrentIndex(prevIndex);
    setMovie(movieList[prevIndex]);
    // Flash the left chevron
    setChevronFlash('left');
    clearTimeout(flashTimer.current);
    flashTimer.current = setTimeout(() => setChevronFlash(null), 300);
  }, [movieList, currentIndex]);

  // Get shared state
  const {
    watchLinks,
    infoLinks,
    plexLinks,
    purchaseLinks,
    streamingLinks,
    formattedRuntime,
    rtScore,
    mcScore,
    imdbScore,
    formattedCountries,
    hasWatchOptions,
    hasInfoLinks,
  } = useMovieDetail(movie);

  // Trailer player state
  const [trailerVisible, setTrailerVisible] = useState(false);

  // Trailer button ref → node handle for nextFocusUp on watch buttons
  const [trailerHandle, setTrailerHandle] = useState(null);
  const trailerRefCallback = useCallback((ref) => {
    if (ref) setTrailerHandle(findNodeHandle(ref));
  }, []);

  // Track whether to give initial focus to watch row (instead of trailer) after movie navigation.
  // When the user navigates LEFT/RIGHT from a watch button, focus should stay on the watch row.
  const [preferWatchFocus, setPreferWatchFocus] = useState(false);

  // Prevent MENU/Back from popping the detail screen while trailer is playing.
  // The TrailerPlayer handles MENU internally to close itself; without this guard
  // React Navigation's native back handler also fires and pops the whole screen.
  React.useEffect(() => {
    if (!trailerVisible) return;
    const unsubscribe = navigation.addListener('beforeRemove', (e) => {
      e.preventDefault();
    });
    return unsubscribe;
  }, [navigation, trailerVisible]);

  // Fade in on mount
  React.useEffect(() => {
    Animated.timing(fadeAnim, {
      toValue: 1,
      duration: 300,
      useNativeDriver: true,
    }).start();
  }, [fadeAnim]);

  // Handle TV remote events (disabled while trailer player is active)
  // RIGHT/LEFT edge navigation: deterministic index check, no timers.
  // Navigate only when the focused watch button is at the edge of the row.
  useTVEventHandler(trailerVisible ? {} : {
    [TV_EVENTS.MENU]: () => {
      navigation.goBack();
    },
    [TV_EVENTS.PLAY_PAUSE]: () => {
      if (movie?.links?.trailer_hosted) {
        setTrailerVisible(true);
      }
    },
    [TV_EVENTS.RIGHT]: () => {
      if (movieList.length <= 1) return;
      if (_totalButtonCount === 0) {
        navigateNext();
        return;
      }
      // If a watch button just blurred, focus moved between buttons — don't navigate.
      // tvOS moves focus BEFORE delivering the TV event, so by the time this handler
      // fires, _focusedWatchIndex already points to the NEW button. The blur timestamp
      // tells us whether focus actually moved (blur = moved) or stayed (no blur = edge).
      if (Date.now() - _lastWatchBlurTime < 150) return;
      // No recent blur → focus couldn't move → at right edge → navigate
      if (_focusedWatchIndex >= 0 && _focusedWatchIndex >= _watchButtonCount - 1) {
        navigateNext();
      }
    },
    [TV_EVENTS.LEFT]: () => {
      if (movieList.length <= 1) return;
      if (_totalButtonCount === 0) {
        navigatePrevious();
        return;
      }
      // Same blur-timestamp check as RIGHT (see comment above)
      if (Date.now() - _lastWatchBlurTime < 150) return;
      // No recent blur → focus couldn't move → at left edge → navigate
      if (_focusedWatchIndex === 0) {
        navigatePrevious();
      }
    },
  });

  // Clear flash timer on unmount
  useEffect(() => {
    return () => { clearTimeout(flashTimer.current); };
  }, []);

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

      if (result && !result.success) {
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
        {/* Left chevron indicator — visual only */}
        {movieList.length > 1 && (
          <ChevronIndicator direction="left" active={chevronFlash === 'left'} />
        )}

        {/* Left side - Poster */}
        <View style={styles.posterContainer}>
          <Image
            source={{ uri: posterUrl }}
            style={styles.poster}
            resizeMode="cover"
            accessible={true}
            accessibilityLabel={`Movie poster for ${movie.title}`}
          />

          {/* Trailer overlay on poster (#10: thick red border, dim, circle + text) */}
          {movie?.links?.trailer_hosted && (
            <TouchableOpacity
              ref={trailerRefCallback}
              style={styles.posterTrailerOverlay}
              onPress={() => setTrailerVisible(true)}
              hasTVPreferredFocus={!preferWatchFocus}
              activeOpacity={0.8}
              accessible={true}
              accessibilityLabel="Play trailer"
              accessibilityRole="button"
            >
              <View style={styles.posterTrailerCircle}>
                <View style={styles.posterTrailerTriangle} />
              </View>
              <Text style={styles.posterTrailerText}>TRAILER</Text>
            </TouchableOpacity>
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
                {movie.display_title || movie.title}
              </Text>
              {movie.digital_date && (
                <Text style={styles.titleDate}>
                  {formatShortDate(movie.digital_date)}
                  {movie.categories?.is_virtual_screening && movie.virtual_screening_info?.available_end
                    ? '\u2013' + formatShortDate(movie.virtual_screening_info.available_end)
                    : ''}
                </Text>
              )}
            </View>

            {/* Virtual screening badge */}
            {movie.categories?.is_virtual_screening && (
              <Text style={styles.screeningName}>
                {decodeHtml(movie.virtual_screening_info?.screening_name || 'VIRTUAL SCREENING')}
              </Text>
            )}

            {/* Meta block — 3 lines */}
            {movie.director && (
              <Text style={styles.metadataText}>Dir: {movie.director}</Text>
            )}
            {movie.crew?.cast?.length > 0 && (
              <Text style={styles.metadataText}>Cast: {movie.crew.cast.slice(0, 3).join(', ')}</Text>
            )}
            <View style={styles.metadataRow}>
              {formattedCountries && (
                <Text style={styles.metadataText}>{formattedCountries}</Text>
              )}
              {formattedCountries && movie.year && <Text style={styles.metadataDot}>•</Text>}
              {movie.year && (
                <Text style={styles.metadataText}>{movie.year}</Text>
              )}
              {formattedRuntime && (
                <>
                  <Text style={styles.metadataDot}>•</Text>
                  <Text style={styles.metadataText}>{formattedRuntime}</Text>
                </>
              )}
              {movie.studio && (
                <>
                  <Text style={styles.metadataDot}>•</Text>
                  <Text style={styles.metadataText}>{movie.studio}</Text>
                </>
              )}
            </View>

            {/* Language (only if not English) */}
            {movie.original_language && movie.original_language !== 'en' && (
              <View style={styles.creditRow}>
                <Text style={styles.creditLabel}>Language</Text>
                <Text style={styles.creditValue}>{movie.original_language.toUpperCase()}</Text>
              </View>
            )}

            {/* Trailer is now a poster overlay (see posterContainer above) */}

            {/* Watch buttons row (VOD first, then streaming) */}
            {hasWatchOptions && (() => {
              const nonVsLinks = purchaseLinks.slice(0, 2).filter(l => !isVirtualScreeningPlatform(l.service, l.url));
              const totalButtons = (streamingLinks.length > 0 ? 1 : 0) + nonVsLinks.length + (plexLinks.length > 0 ? 1 : 0);
              if (totalButtons === 0) return null;

              // Compute sequential button indices for edge navigation tracking
              let watchIdx = 0;

              return (
              <View style={styles.watchButtonRow}>
                {/* VOD buttons (rent/buy) — before streaming */}
                {nonVsLinks.length > 0 && (
                  <Text style={styles.watchSectionLabel}>Rent/Buy:</Text>
                )}
                {nonVsLinks.map((link, i) => {
                  const idx = watchIdx++;
                  const label = movie?._is_preorder ? 'PRE-ORDER'
                    : getVodDisplayName(link.service);
                  const buttonColor = movie?._is_preorder ? '#7c3aed'
                    : getServiceColor(link.service);
                  const vodKey = normalizeService(link.service);
                  const vodBorder = (!movie?._is_preorder && NEEDS_BORDER.includes(vodKey)) ? '#444'
                    : undefined;
                  return (
                    <View key={`purchase-${i}`}>
                      <ActionButton
                        buttonIndex={idx}
                        isWatchButton={true}
                        nextFocusUp={undefined}
                        label={label}
                        color={buttonColor}
                        icon={!movie?._is_preorder ? getServiceLogo(link.service) : null}
                        iconTintColor="#ffffff"
                        borderColor={vodBorder}
                        onPress={() => handleWatchPress(link)}
                        hasTVPreferredFocus={(preferWatchFocus || !movie?.links?.trailer_hosted) && i === 0}
                        testID={`action-btn-purchase-${i}`}
                      />
                      {movie?._is_preorder && link.sublabel && (
                        <Text style={styles.preOrderDateLabel}>{link.sublabel}</Text>
                      )}
                    </View>
                  );
                })}

                {/* STREAM button — after VOD */}
                {streamingLinks.length > 0 && (() => {
                  const idx = watchIdx++;
                  const svcKey = normalizeService(streamingLinks[0].service);
                  return (
                  <>
                    <Text style={styles.watchSectionLabel}>Stream:</Text>
                    <ActionButton
                      buttonIndex={idx}
                      isWatchButton={true}
                      nextFocusUp={undefined}
                      label={getStreamDisplayName(streamingLinks[0].service)}
                      color={getServiceColor(streamingLinks[0].service)}
                      icon={getServiceLogo(streamingLinks[0].service)}
                      iconTintColor="#ffffff"
                      borderColor={NEEDS_BORDER.includes(svcKey) ? '#444' : undefined}
                      onPress={() => handleWatchPress(streamingLinks[0])}
                      hasTVPreferredFocus={(preferWatchFocus || !movie?.links?.trailer_hosted) && nonVsLinks.length === 0}
                      testID="action-btn-stream"
                    />
                  </>
                  );
                })()}

                {/* PLEX button */}
                {plexLinks.length > 0 && (() => {
                  const idx = watchIdx++;
                  return (
                  <ActionButton
                    buttonIndex={idx}
                    isWatchButton={true}
                    nextFocusUp={undefined}
                    label="PLEX"
                    color="#E5A00D"
                    icon={getServiceLogo('plex')}
                    iconTintColor="#ffffff"
                    onPress={() => handleWatchPress(plexLinks[0])}
                    testID="action-btn-plex"
                  />
                  );
                })()}

              </View>
              );
            })()}

            {/* Virtual screening QR code — scan to buy ticket on phone */}
            {purchaseLinks.some(link => isVirtualScreeningPlatform(link.service, link.url)) && (() => {
              const vsLink = purchaseLinks.find(link => isVirtualScreeningPlatform(link.service, link.url));
              if (!vsLink?.url) return null;
              return (
                <View style={styles.qrBlock} accessible={true} accessibilityLabel="Scan QR code with your phone to buy a virtual screening ticket">
                  <Text style={styles.qrLabel}>BUY TICKET</Text>
                  <View style={styles.qrCodeWrap}>
                    <QRCode
                      value={vsLink.url}
                      size={160}
                      backgroundColor="#ffffff"
                      color="#000000"
                    />
                  </View>
                  <Text style={styles.qrNote}>Virtual Screenings only available on phone or computer</Text>
                </View>
              );
            })()}

            {/* Scores row — RT + MC + IMDb display-only badges */}
            {(rtScore || mcScore || imdbScore) && (
              <View style={styles.scoresRow}>
                {rtScore && <RTDisplay score={rtScore.value} />}
                {mcScore && <MetacriticDisplay score={mcScore.value} />}
                {imdbScore && (
                  <View style={scoreStyles.container} accessible={true} accessibilityLabel={`IMDb rating ${imdbScore.label}`}>
                    <Image source={require('../../assets/logos/imdb.png')} style={scoreStyles.imdbLogo} />
                    <Text style={[scoreStyles.scoreValue, { color: '#f5c518' }]}>{imdbScore.label}</Text>
                  </View>
                )}
              </View>
            )}

            {/* Pull Quotes */}
            {movie.pull_quotes?.length > 0 && (
              <View style={styles.pullQuotesSection}>
                {movie.pull_quotes.slice(0, 2).map((pq, i) => (
                  <View key={i} style={styles.pullQuoteRow}>
                    <View style={[styles.pqSourceBadge, { backgroundColor: pq.source === 'rotten_tomatoes' ? '#FA3232' : '#00E054' }]}>
                      <Text style={styles.pqSourceText}>{pq.source === 'rotten_tomatoes' ? 'RT' : 'LB'}</Text>
                    </View>
                    <View style={styles.pqContent}>
                      <Text style={styles.pqText}>{'\u201C'}{pq.text}{'\u201D'}</Text>
                      {(pq.critic || pq.outlet) && (
                        <Text style={styles.pqAttribution}>{'\u2014'} {[pq.critic, pq.outlet].filter(Boolean).join(', ')}</Text>
                      )}
                    </View>
                  </View>
                ))}
              </View>
            )}

            {/* Synopsis — plain text, not interactive */}
            {movie.synopsis && (
              <View style={styles.synopsisContainer}>
                <Text style={styles.synopsis} numberOfLines={6}>
                  {movie.synopsis}
                  {movie.categories?.is_virtual_screening && movie.virtual_screening_info?.screening_name && (
                    <Text style={styles.screeningCallout}>
                      {` Virtual screening available as part of the ${movie.virtual_screening_info.screening_name}.${movie.virtual_screening_info?.available_end ? ` Ends ${formatShortDate(movie.virtual_screening_info.available_end)}.` : ''}`}
                    </Text>
                  )}
                </Text>
              </View>
            )}
          </ScrollView>
        </View>

        {/* Right chevron indicator — visual only */}
        {movieList.length > 1 && (
          <ChevronIndicator direction="right" active={chevronFlash === 'right'} />
        )}
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
  posterTrailerOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    borderRadius: 16,
    backgroundColor: 'rgba(0,0,0,0.45)',
    borderWidth: 3,
    borderColor: '#E50914',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 12,
    zIndex: 5,
  },
  posterTrailerCircle: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#E50914',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#E50914',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.6,
    shadowRadius: 20,
  },
  posterTrailerTriangle: {
    width: 0,
    height: 0,
    borderLeftWidth: 24,
    borderTopWidth: 14,
    borderBottomWidth: 14,
    borderLeftColor: '#ffffff',
    borderTopColor: 'transparent',
    borderBottomColor: 'transparent',
    marginLeft: 6,
  },
  posterTrailerText: {
    color: '#ffffff',
    fontSize: 22,
    fontWeight: '800',
    letterSpacing: 6,
    textShadowColor: 'rgba(0,0,0,0.8)',
    textShadowOffset: { width: 0, height: 2 },
    textShadowRadius: 10,
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
  scoreRow: {
    flexDirection: 'row',
    gap: Spacing.tvos.md,
    marginTop: Spacing.tvos.sm,
    marginBottom: Spacing.tvos.sm,
  },
  scoreBadge: {
    paddingHorizontal: Spacing.tvos.md,
    paddingVertical: Spacing.tvos.sm,
    borderRadius: 8,
    alignItems: 'center',
  },
  scoreBadgeText: {
    color: Colors.textPrimary,
    fontSize: Typography.tvos.body,
    fontWeight: '800',
  },
  scoreBadgeLabel: {
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
  screeningName: {
    backgroundColor: Colors.screeningGold,
    color: Colors.screeningGoldText,
    fontSize: 16,
    fontWeight: '700',
    letterSpacing: 1,
    textAlign: 'center',
    paddingVertical: 5,
    paddingHorizontal: 10,
    marginBottom: Spacing.tvos.sm,
    overflow: 'hidden',
    alignSelf: 'flex-start',
    borderRadius: 4,
  },
  screeningCallout: {
    color: Colors.screeningGold,
    fontWeight: '700',
    fontStyle: 'italic',
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
  synopsis: {
    color: Colors.textSecondary,
    fontSize: Typography.tvos.body,
    lineHeight: Typography.tvos.body * 1.5,
  },
  watchButtonRow: {
    flexDirection: 'row',
    marginTop: Spacing.tvos.lg,
    alignItems: 'center',
    paddingLeft: Spacing.tvos.md,
    flexWrap: 'wrap',
  },
  watchSectionLabel: {
    color: '#00d4aa',
    fontSize: Typography.tvos.caption,
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginRight: 4,
  },
  preOrderDateLabel: {
    color: '#c4b5fd',
    fontSize: Typography.tvos.caption,
    fontWeight: '500',
    textAlign: 'center',
    marginTop: 4,
  },
  scoresRow: {
    flexDirection: 'row',
    marginTop: Spacing.tvos.lg,
    alignItems: 'center',
    paddingLeft: Spacing.tvos.md,
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
  pullQuotesSection: {
    marginTop: Spacing.tvos.lg,
  },
  pullQuoteRow: {
    flexDirection: 'row',
    marginBottom: Spacing.tvos.sm,
  },
  pqSourceBadge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 4,
    marginRight: 10,
    marginTop: 3,
  },
  pqSourceText: {
    color: '#fff',
    fontSize: Typography.tvos.caption - 2,
    fontWeight: '700',
  },
  pqContent: {
    flex: 1,
  },
  pqText: {
    color: Colors.textSecondary,
    fontSize: Typography.tvos.body - 2,
    fontStyle: 'italic',
    lineHeight: (Typography.tvos.body - 2) * 1.4,
  },
  pqAttribution: {
    color: Colors.textMuted,
    fontSize: Typography.tvos.caption,
    marginTop: 3,
  },
  qrBlock: {
    alignItems: 'center',
    marginTop: Spacing.tvos.lg,
    paddingVertical: Spacing.tvos.md,
    paddingHorizontal: Spacing.tvos.lg,
    borderWidth: 1,
    borderColor: Colors.screeningGold,
    borderRadius: 16,
    alignSelf: 'flex-start',
  },
  qrLabel: {
    color: Colors.screeningGold,
    fontSize: Typography.tvos.button,
    fontWeight: '800',
    letterSpacing: 1.5,
    marginBottom: Spacing.tvos.sm,
  },
  qrCodeWrap: {
    padding: 12,
    borderRadius: 8,
    backgroundColor: '#ffffff',
  },
  qrNote: {
    color: Colors.textMuted,
    fontSize: Typography.tvos.caption - 2,
    marginTop: Spacing.tvos.sm,
    textAlign: 'center',
    maxWidth: 220,
  },
});

// Error boundary — catches render crashes and shows the error instead of killing the app
class MovieDetailErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  componentDidCatch(error, info) {
    console.error('[MovieDetail] CRASH CAUGHT:', error.message, info.componentStack);
  }
  render() {
    if (this.state.hasError) {
      return (
        <View style={{ flex: 1, backgroundColor: '#1a1a2e', justifyContent: 'center', alignItems: 'center', padding: 60 }}>
          <Text style={{ color: '#ff4444', fontSize: 32, fontWeight: 'bold', marginBottom: 20 }}>
            Detail Screen Error
          </Text>
          <Text style={{ color: '#ffffff', fontSize: 22, textAlign: 'center', marginBottom: 16 }}>
            {this.state.error?.message || 'Unknown error'}
          </Text>
          <Text style={{ color: '#888888', fontSize: 16, textAlign: 'center' }}>
            Press Menu to go back. Check Xcode console for full stack trace.
          </Text>
        </View>
      );
    }
    return this.props.children;
  }
}

const MovieDetailWithErrorBoundary = () => (
  <MovieDetailErrorBoundary>
    <MovieDetailTvOS />
  </MovieDetailErrorBoundary>
);

export default MovieDetailWithErrorBoundary;
