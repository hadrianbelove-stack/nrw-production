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
  BackHandler,
} from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import {
  useMovieDetail,
  getPosterUrl,
  getBackdropUrl,
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
  openPlex,
  showLinkError,
} from '../utils/links.tvos';
import { fetchMovies } from '../services/api';
import { trackWatchButtonTap } from '../services/analytics.tvos';
import TrailerPlayer from '../components/TrailerPlayer.tvos';
import { getSharedMovieList } from './sharedMovieList';
import { renderMarkdownSpans } from '../utils/markdown';

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


// Full-width stream button matching site's .stream-btn — forwardRef for focus wiring
const StreamButton = forwardRef(({
  service, onPress, hasTVPreferredFocus = false, testID,
  nextFocusUp, nextFocusDown,
}, ref) => {
  const [isFocused, setIsFocused] = useState(false);
  const scaleAnim = useRef(new Animated.Value(1)).current;
  const svcKey = normalizeService(service);
  const logo = getServiceLogo(service);
  const displayName = getStreamDisplayName(service);

  const handleFocus = useCallback(() => {
    setIsFocused(true);
    Animated.spring(scaleAnim, { toValue: 1.05, useNativeDriver: true }).start();
  }, [scaleAnim]);

  const handleBlur = useCallback(() => {
    setIsFocused(false);
    Animated.spring(scaleAnim, { toValue: 1, useNativeDriver: true }).start();
  }, [scaleAnim]);

  return (
    <TouchableOpacity
      ref={ref}
      onPress={onPress}
      onFocus={handleFocus}
      onBlur={handleBlur}
      hasTVPreferredFocus={hasTVPreferredFocus}
      nextFocusUp={nextFocusUp}
      nextFocusDown={nextFocusDown}
      activeOpacity={0.9}
      accessible={true}
      accessibilityLabel={`Watch on ${displayName}`}
      accessibilityRole="button"
      testID={testID}
    >
      <Animated.View style={[
        streamBtnStyles.button,
        { backgroundColor: getServiceColor(service) },
        NEEDS_BORDER.includes(svcKey) && streamBtnStyles.darkServiceBorder,
        isFocused && streamBtnStyles.focused,
        { transform: [{ scale: scaleAnim }] },
      ]}>
        {logo ? (
          <Image source={logo} style={streamBtnStyles.logo} />
        ) : (
          <Text style={streamBtnStyles.label}>{displayName}</Text>
        )}
      </Animated.View>
    </TouchableOpacity>
  );
});

const streamBtnStyles = StyleSheet.create({
  button: {
    height: 64,
    borderRadius: 10,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: 'transparent',
  },
  focused: {
    borderColor: Colors.focusBorderHighlight,
    borderWidth: 4,
  },
  logo: {
    height: 28,
    width: 140,
    resizeMode: 'contain',
    tintColor: '#ffffff',
  },
  label: {
    color: '#ffffff',
    fontSize: 20,
    fontWeight: '700',
    letterSpacing: 1,
  },
  darkServiceBorder: {
    borderColor: 'rgba(255,255,255,0.2)',
  },
});

// VOD button — split layout (40% logo / 60% price) matching site's .vod-btn
const VodButton = ({
  service, color, onPress, hasTVPreferredFocus = false, testID,
  icon, label,
  rentPrice, buyPrice,
  nextFocusUp, nextFocusDown,
}) => {
  const [isFocused, setIsFocused] = useState(false);
  const scaleAnim = useRef(new Animated.Value(1)).current;
  const svcKey = normalizeService(service);

  const handleFocus = useCallback(() => {
    setIsFocused(true);
    Animated.spring(scaleAnim, { toValue: 1.05, useNativeDriver: true }).start();
  }, [scaleAnim]);

  const handleBlur = useCallback(() => {
    setIsFocused(false);
    Animated.spring(scaleAnim, { toValue: 1, useNativeDriver: true }).start();
  }, [scaleAnim]);

  const priceStr = [
    rentPrice && `Rent ${rentPrice}`,
    buyPrice && `Buy ${buyPrice}`,
  ].filter(Boolean).join(' / ');
  const a11yLabel = [label || getVodDisplayName(service), priceStr].filter(Boolean).join(', ');

  return (
    <TouchableOpacity
      onPress={onPress}
      onFocus={handleFocus}
      onBlur={handleBlur}
      hasTVPreferredFocus={hasTVPreferredFocus}
      nextFocusUp={nextFocusUp}
      nextFocusDown={nextFocusDown}
      activeOpacity={0.9}
      accessible={true}
      accessibilityLabel={a11yLabel}
      accessibilityRole="button"
      testID={testID}
      style={{ flex: 1 }}
    >
      <Animated.View style={[
        vodBtnStyles.button,
        NEEDS_BORDER.includes(svcKey) && { borderColor: 'rgba(255,255,255,0.2)' },
        isFocused && vodBtnStyles.focused,
        { transform: [{ scale: scaleAnim }] },
      ]}>
        {/* Left 40%: brand color + logo */}
        <View style={[vodBtnStyles.logoHalf, { backgroundColor: color }]}>
          {icon ? (
            <Image source={icon} style={vodBtnStyles.logo} />
          ) : (
            <Text style={vodBtnStyles.logoText}>{label || getVodDisplayName(service)}</Text>
          )}
        </View>
        {/* Right 60%: dark bg + prices */}
        <View style={vodBtnStyles.priceHalf}>
          <Text style={vodBtnStyles.priceText}>
            {priceStr || label || getVodDisplayName(service)}
          </Text>
        </View>
      </Animated.View>
    </TouchableOpacity>
  );
};

const vodBtnStyles = StyleSheet.create({
  button: {
    flexDirection: 'row',
    minHeight: 58,
    borderRadius: 10,
    overflow: 'hidden',
    borderWidth: 2,
    borderColor: 'transparent',
  },
  focused: {
    borderColor: Colors.focusBorderHighlight,
    borderWidth: 4,
  },
  logoHalf: {
    width: '40%',
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 8,
    paddingHorizontal: 8,
  },
  logo: {
    height: 22,
    width: 80,
    resizeMode: 'contain',
    tintColor: '#ffffff',
  },
  logoText: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '700',
    letterSpacing: 1,
  },
  priceHalf: {
    width: '60%',
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(0,0,0,0.4)',
    paddingVertical: 8,
    paddingHorizontal: 6,
  },
  priceText: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '700',
    textAlign: 'center',
  },
});

// Visual-only navigation arrow indicator (not focusable — d-pad LEFT/RIGHT navigates via useTVEventHandler)
const NavArrowIndicator = ({ direction, flash }) => {
  const opacity = useRef(new Animated.Value(0.5)).current;

  useEffect(() => {
    if (flash) {
      opacity.setValue(1);
      Animated.timing(opacity, { toValue: 0.5, duration: 400, useNativeDriver: true }).start();
    }
  }, [flash, opacity]);

  return (
    <Animated.View style={[navArrowStyles.circle, { opacity }]}>
      <Text style={navArrowStyles.symbol}>
        {direction === 'left' ? '\u2039' : '\u203A'}
      </Text>
    </Animated.View>
  );
};

const navArrowStyles = StyleSheet.create({
  circle: {
    width: 60,
    height: 60,
    borderRadius: 30,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(0, 212, 170, 0.1)',
  },
  symbol: {
    color: Colors.primary,
    fontSize: 36,
    fontWeight: '300',
    marginTop: -2,
  },
});

// Focusable trailer button matching site's .lb-trailer-btn
const TrailerButton = forwardRef(({
  onPress, hasTVPreferredFocus = false,
  nextFocusUp, nextFocusDown, nextFocusLeft, nextFocusRight,
}, ref) => {
  const [isFocused, setIsFocused] = useState(false);
  const scaleAnim = useRef(new Animated.Value(1)).current;

  const handleFocus = useCallback(() => {
    setIsFocused(true);
    Animated.spring(scaleAnim, { toValue: 1.05, useNativeDriver: true }).start();
  }, [scaleAnim]);

  const handleBlur = useCallback(() => {
    setIsFocused(false);
    Animated.spring(scaleAnim, { toValue: 1, useNativeDriver: true }).start();
  }, [scaleAnim]);

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
      accessibilityLabel="Play trailer"
      accessibilityRole="button"
      testID="action-btn-trailer"
      style={{ flex: 1 }}
    >
      <Animated.View style={[
        trailerBtnStyles.button,
        isFocused && trailerBtnStyles.focused,
        { transform: [{ scale: scaleAnim }] },
      ]}>
        <Text style={trailerBtnStyles.text}>TRAILER</Text>
      </Animated.View>
    </TouchableOpacity>
  );
});

const trailerBtnStyles = StyleSheet.create({
  button: {
    height: 60,
    backgroundColor: '#E50914',
    borderRadius: 10,
    borderWidth: 2,
    borderColor: 'rgba(255,255,255,0.3)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  focused: {
    borderColor: Colors.focusBorderHighlight,
    borderWidth: 4,
  },
  text: {
    color: '#ffffff',
    fontSize: 22,
    fontWeight: '800',
    letterSpacing: 3,
  },
});

// Compact score badge — small inline pill matching site's .score-badge (display-only)
const ScoreBadge = ({ logo, score, color, borderColor, bgColor, accessibilityLabel }) => (
  <View
    style={[badgeStyles.pill, borderColor && { borderColor, backgroundColor: bgColor }]}
    accessible={true}
    accessibilityLabel={accessibilityLabel}
  >
    <Image source={logo} style={[badgeStyles.logo, { tintColor: color }]} />
    <Text style={[badgeStyles.score, { color }]}>{score}</Text>
  </View>
);

const badgeStyles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: Spacing.tvos.sm,
  },
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 8,
    backgroundColor: 'rgba(255,255,255,0.06)',
    borderWidth: 1.5,
    borderColor: 'rgba(255,255,255,0.2)',
  },
  logo: {
    width: 24,
    height: 24,
    resizeMode: 'contain',
  },
  score: {
    fontSize: 18,
    fontWeight: '600',
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

  // Arrow flash state — briefly highlights the ‹/› indicator on navigation
  const [arrowFlash, setArrowFlash] = useState(null); // 'left' | 'right' | null

  // Navigate to next movie (cycles to first if at end)
  const navigateNext = useCallback(() => {
    if (movieList.length === 0) return;
    const nextIndex = (currentIndex + 1) % movieList.length;
    setArrowFlash('right');
    setCurrentIndex(nextIndex);
    setMovie(movieList[nextIndex]);
  }, [movieList, currentIndex]);

  // Navigate to previous movie (cycles to last if at start)
  const navigatePrevious = useCallback(() => {
    if (movieList.length === 0) return;
    const prevIndex = currentIndex === 0 ? movieList.length - 1 : currentIndex - 1;
    setArrowFlash('left');
    setCurrentIndex(prevIndex);
    setMovie(movieList[prevIndex]);
  }, [movieList, currentIndex]);

  // Get shared state
  const {
    watchLinks,
    plexLinks,
    purchaseLinks,
    streamingLinks,
    formattedRuntime,
    rtScore,
    mcScore,
    imdbScore,
    lbScore,
    formattedCountries,
    hasWatchOptions,
  } = useMovieDetail(movie);

  // Trailer player state
  const [trailerVisible, setTrailerVisible] = useState(false);

  // Trailer button ref → node handle for nextFocusUp on watch buttons
  // trailerButtonRef also used to restore focus after trailer closes (setNativeProps)
  const [trailerHandle, setTrailerHandle] = useState(null);
  const trailerButtonRef = useRef(null);
  const trailerRefCallback = useCallback((ref) => {
    trailerButtonRef.current = ref;
    if (ref) setTrailerHandle(findNodeHandle(ref));
  }, []);

  // Prevent MENU from popping MovieDetail while trailer is playing.
  // BackHandler intercepts at the native level (more reliable than beforeRemove on tvOS).
  // TrailerPlayer handles MENU via its own TVEventHandler to close the overlay.
  React.useEffect(() => {
    if (!trailerVisible) return;
    const sub = BackHandler.addEventListener('hardwareBackPress', () => true);
    return () => sub.remove();
  }, [trailerVisible]);

  // Fade in on mount
  React.useEffect(() => {
    Animated.timing(fadeAnim, {
      toValue: 1,
      duration: 300,
      useNativeDriver: true,
    }).start();
  }, [fadeAnim]);

  // Handle TV remote events (disabled while trailer player is active)
  // LEFT/RIGHT d-pad swipes navigate movies directly — no button press needed
  useTVEventHandler(trailerVisible ? {} : {
    [TV_EVENTS.MENU]: () => {
      navigation.goBack();
    },
    [TV_EVENTS.PLAY_PAUSE]: () => {
      if (movie?.links?.trailer_hosted) {
        setTrailerVisible(true);
      }
    },
    [TV_EVENTS.LEFT]: () => {
      if (movieList.length > 1) navigatePrevious();
    },
    [TV_EVENTS.RIGHT]: () => {
      if (movieList.length > 1) navigateNext();
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

      if (result && !result.success) {
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

        </View>

        {/* Right side - Details (reordered to match site lightbox) */}
        <View style={styles.detailsContainer}>
          <ScrollView
            ref={scrollViewRef}
            style={styles.detailsScroll}
            showsVerticalScrollIndicator={false}
            contentContainerStyle={styles.detailsScrollContent}
          >
            {/* 1. Title row with date */}
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

            {/* 2. Virtual screening badge */}
            {movie.categories?.is_virtual_screening && (
              <Text style={styles.screeningName}>
                {decodeHtml(movie.virtual_screening_info?.screening_name || 'VIRTUAL SCREENING')}
              </Text>
            )}

            {/* 3. Meta block — Director, Cast, details line */}
            {movie.director && (
              <Text style={styles.metadataCrewLine}><Text style={styles.metadataCrewLabel}>Director: </Text><Text style={styles.metadataCrewName}>{movie.director}</Text></Text>
            )}
            {movie.crew?.cast?.length > 0 && (
              <Text style={styles.metadataCrewLine}><Text style={styles.metadataCrewLabel}>Cast: </Text><Text style={styles.metadataCrewName}>{movie.crew.cast.slice(0, 3).join(', ')}</Text></Text>
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

            {/* 4. Language (only if not English) */}
            {movie.original_language && movie.original_language !== 'en' && (
              <View style={styles.creditRow}>
                <Text style={styles.creditLabel}>Language</Text>
                <Text style={styles.creditValue}>{movie.original_language.toUpperCase()}</Text>
              </View>
            )}

            {/* 5. Scores — compact inline badge pills (display-only, no Wiki) */}
            {(rtScore || mcScore || imdbScore || lbScore) && (
              <View style={badgeStyles.row}>
                {rtScore && (
                  <ScoreBadge
                    logo={require('../../assets/logos/rt.png')}
                    score={rtScore.label}
                    color="#ff6b6b"
                    borderColor="rgba(255,107,107,0.55)"
                    bgColor="rgba(255,107,107,0.08)"
                    accessibilityLabel={`Rotten Tomatoes ${rtScore.label}`}
                  />
                )}
                {imdbScore && (
                  <ScoreBadge
                    logo={require('../../assets/logos/imdb.png')}
                    score={imdbScore.label}
                    color="#f5c518"
                    borderColor="rgba(245,197,24,0.55)"
                    bgColor="rgba(245,197,24,0.08)"
                    accessibilityLabel={`IMDb rating ${imdbScore.label}`}
                  />
                )}
                {mcScore && (
                  <ScoreBadge
                    logo={require('../../assets/logos/metacritic.png')}
                    score={mcScore.label}
                    color="#7ddf64"
                    borderColor="rgba(125,223,100,0.55)"
                    bgColor="rgba(125,223,100,0.08)"
                    accessibilityLabel={`Metacritic score ${mcScore.label}`}
                  />
                )}
                {lbScore && (
                  <ScoreBadge
                    logo={require('../../assets/logos/letterboxd.png')}
                    score={lbScore.label}
                    color="#00E054"
                    borderColor="rgba(0,224,84,0.55)"
                    bgColor="rgba(0,224,84,0.08)"
                    accessibilityLabel={`Letterboxd rating ${lbScore.label}`}
                  />
                )}
              </View>
            )}

            {/* 6. Pull Quotes */}
            {movie.pull_quotes?.length > 0 && (
              <View style={styles.pullQuotesSection}>
                {movie.pull_quotes.slice(0, 2).map((pq, i) => (
                  <View key={i} style={styles.pullQuoteCard}>
                    <Text style={styles.pqText}>{'\u201C'}{pq.text}{'\u201D'}</Text>
                    {(pq.critic || pq.outlet) && (
                      <Text style={styles.pqAttribution}>{'\u2014'} {[pq.critic, pq.outlet].filter(Boolean).join(', ')}</Text>
                    )}
                  </View>
                ))}
              </View>
            )}

            {/* 7. Synopsis */}
            {movie.synopsis && (
              <View style={styles.synopsisContainer}>
                <Text style={styles.synopsis} numberOfLines={6} ellipsizeMode="tail">
                  {renderMarkdownSpans(movie.synopsis)}
                  {movie.categories?.is_virtual_screening && movie.virtual_screening_info?.screening_name && (
                    <Text style={styles.screeningCallout}>
                      {` Virtual screening available as part of the ${movie.virtual_screening_info.screening_name}.${movie.virtual_screening_info?.available_end ? ` Ends ${formatShortDate(movie.virtual_screening_info.available_end)}.` : ''}`}
                    </Text>
                  )}
                </Text>
              </View>
            )}

            {/* 8. Navigation + Trailer row: ‹ [TRAILER] › */}
            {/* Arrows are visual-only — LEFT/RIGHT d-pad navigates via useTVEventHandler */}
            <View style={styles.navTrailerRow}>
              {movieList.length > 1 && (
                <NavArrowIndicator direction="left" flash={arrowFlash === 'left'} />
              )}

              {movie?.links?.trailer_hosted ? (
                <TrailerButton
                  ref={trailerRefCallback}
                  onPress={() => setTrailerVisible(true)}
                  hasTVPreferredFocus={true}
                />
              ) : (
                <View style={{ flex: 1 }} />
              )}

              {movieList.length > 1 && (
                <NavArrowIndicator direction="right" flash={arrowFlash === 'right'} />
              )}
            </View>

            {/* 9. Stream button — full-width row (before VOD) */}
            {streamingLinks.length > 0 && (
              <View style={styles.streamRow}>
                <StreamButton
                  service={streamingLinks[0].service}
                  onPress={() => handleWatchPress(streamingLinks[0])}
                  hasTVPreferredFocus={!movie?.links?.trailer_hosted}
                  nextFocusUp={trailerHandle}
                  testID="action-btn-stream"
                />
              </View>
            )}

            {/* 10. VOD buttons — split layout, side by side */}
            {hasWatchOptions && (() => {
              const nonVsLinks = purchaseLinks.slice(0, 2).filter(l => !isVirtualScreeningPlatform(l.service, l.url));
              if (nonVsLinks.length === 0 && plexLinks.length === 0) return null;

              return (
                <View style={styles.vodRow}>
                  {nonVsLinks.map((link, i) => {
                    const buttonColor = movie?._is_preorder ? '#7c3aed'
                      : getServiceColor(link.service);
                    return (
                      <VodButton
                        key={`purchase-${i}`}
                        service={link.service}
                        nextFocusUp={trailerHandle}
                        color={buttonColor}
                        icon={!movie?._is_preorder ? getServiceLogo(link.service) : null}
                        label={movie?._is_preorder ? 'PRE-ORDER' : null}
                        rentPrice={link.rentPrice}
                        buyPrice={link.buyPrice}
                        onPress={() => handleWatchPress(link)}
                        hasTVPreferredFocus={!movie?.links?.trailer_hosted && streamingLinks.length === 0 && i === 0}
                        testID={`action-btn-purchase-${i}`}
                      />
                    );
                  })}

                  {/* PLEX button in VOD row */}
                  {plexLinks.length > 0 && (
                    <VodButton
                      service="plex"
                      nextFocusUp={trailerHandle}
                      color="#E5A00D"
                      icon={getServiceLogo('plex')}
                      onPress={() => handleWatchPress(plexLinks[0])}
                      testID="action-btn-plex"
                    />
                  )}
                </View>
              );
            })()}

            {/* 11. Virtual screening QR code */}
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

          </ScrollView>
        </View>
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
            // Restore TV remote focus to the trailer button after the overlay unmounts.
            // setNativeProps is the correct tvOS focus API; AccessibilityInfo is for VoiceOver.
            if (trailerButtonRef.current) {
              trailerButtonRef.current.setNativeProps({ hasTVPreferredFocus: true });
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
    backgroundColor: 'rgba(10, 10, 10, 0.65)',
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
  detailsContainer: {
    flex: 1,
    maxWidth: CONTENT_WIDTH,
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    overflow: 'hidden',
  },
  detailsScroll: {
    flex: 1,
  },
  detailsScrollContent: {
    padding: Spacing.tvos.md,
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
  metadataCrewLine: {
    fontSize: Typography.tvos.body,
  },
  metadataCrewLabel: {
    color: Colors.primary,
    fontWeight: 'bold',
  },
  metadataCrewName: {
    color: Colors.textPrimary,
    fontWeight: 'bold',
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
  navTrailerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginTop: Spacing.tvos.lg,
    marginBottom: 10,
  },
  streamRow: {
    marginBottom: 8,
  },
  vodRow: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 8,
  },
  preOrderDateLabel: {
    color: '#c4b5fd',
    fontSize: Typography.tvos.caption,
    fontWeight: '500',
    textAlign: 'center',
    marginTop: 4,
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
  pullQuoteCard: {
    marginBottom: Spacing.tvos.sm,
    paddingLeft: 12,
    paddingRight: 12,
    paddingVertical: 10,
    borderLeftWidth: 3,
    borderLeftColor: 'rgba(0, 212, 170, 0.6)',
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderRadius: 6,
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
