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

// Simple action button with equal sizing
const ActionButton = ({ label, color, onPress, hasTVPreferredFocus = false, testID, borderColor, textColor, icon, iconTintColor }) => {
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

// Focusable navigation arrow at screen edge.
// When the user presses RIGHT past the last button, Apple's focus engine
// lands on this arrow. It auto-navigates on focus (no SELECT needed).
// These are only rendered after a delay so they can't steal initial focus.
const NavArrow = ({ direction, onNavigate }) => {
  const [isFocused, setIsFocused] = useState(false);
  const isLeft = direction === 'left';

  return (
    <TouchableOpacity
      onPress={() => {
        console.log(`[NavArrow] ${direction} PRESSED`);
        onNavigate();
      }}
      onFocus={() => {
        setIsFocused(true);
        console.log(`[NavArrow] ${direction} FOCUSED — auto-navigating`);
        onNavigate();
      }}
      onBlur={() => setIsFocused(false)}
      style={[
        navArrowStyles.arrow,
        isLeft ? navArrowStyles.left : navArrowStyles.right,
        isFocused && navArrowStyles.focused,
      ]}
      activeOpacity={1}
    >
      <Text style={navArrowStyles.text}>{isLeft ? '\u2039' : '\u203A'}</Text>
    </TouchableOpacity>
  );
};

const navArrowStyles = StyleSheet.create({
  arrow: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    width: 60,
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 10,
    backgroundColor: 'rgba(0, 212, 170, 0.05)',
    borderWidth: 2,
    borderColor: 'transparent',
  },
  left: {
    left: 0,
  },
  right: {
    right: 0,
  },
  focused: {
    backgroundColor: 'rgba(0, 212, 170, 0.25)',
    borderColor: Colors.focusBorderHighlight,
  },
  text: {
    color: 'rgba(0, 212, 170, 0.6)',
    fontSize: 80,
    fontWeight: '300',
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

  // NavArrows hidden on mount and after navigation — prevents focus steal.
  // Arrows only appear after 800ms, by which time buttons have claimed focus.
  const [showArrows, setShowArrows] = useState(false);
  const showArrowsTimer = useRef(null);
  useEffect(() => {
    showArrowsTimer.current = setTimeout(() => setShowArrows(true), 800);
    return () => clearTimeout(showArrowsTimer.current);
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

  // Navigate to next movie (cycles to first if at end)
  const navigateNext = useCallback(() => {
    console.log(`[Nav] navigateNext — list=${movieList.length}, idx=${currentIndex}`);
    if (movieList.length === 0) return;
    const nextIndex = (currentIndex + 1) % movieList.length;
    console.log(`[Nav] → ${nextIndex}: ${movieList[nextIndex]?.title}`);
    setCurrentIndex(nextIndex);
    setMovie(movieList[nextIndex]);
    // Hide arrows briefly to force focus back to buttons
    setShowArrows(false);
    clearTimeout(showArrowsTimer.current);
    showArrowsTimer.current = setTimeout(() => setShowArrows(true), 800);
  }, [movieList, currentIndex]);

  // Navigate to previous movie (cycles to last if at start)
  const navigatePrevious = useCallback(() => {
    console.log(`[Nav] navigatePrev — list=${movieList.length}, idx=${currentIndex}`);
    if (movieList.length === 0) return;
    const prevIndex = currentIndex === 0 ? movieList.length - 1 : currentIndex - 1;
    console.log(`[Nav] → ${prevIndex}: ${movieList[prevIndex]?.title}`);
    setCurrentIndex(prevIndex);
    setMovie(movieList[prevIndex]);
    // Hide arrows briefly to force focus back to buttons
    setShowArrows(false);
    clearTimeout(showArrowsTimer.current);
    showArrowsTimer.current = setTimeout(() => setShowArrows(true), 800);
  }, [movieList, currentIndex]);

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
    mcScore,
    imdbScore,
    formattedCountries,
    hasWatchOptions,
    hasInfoLinks,
  } = useMovieDetail(movie);

  // Trailer player state
  const [trailerVisible, setTrailerVisible] = useState(false);

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

  // Handle TV remote events (disabled while trailer player is active)
  // LEFT/RIGHT navigation is handled by focusable NavArrow buttons at screen edges
  useTVEventHandler(trailerVisible ? {} : {
    [TV_EVENTS.MENU]: () => {
      navigation.goBack();
    },
    [TV_EVENTS.PLAY_PAUSE]: () => {
      if (movie?.links?.trailer_hosted) {
        setTrailerVisible(true);
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
                <Text style={styles.titleDate}>{formatShortDate(movie.digital_date)}</Text>
              )}
            </View>

            {/* Virtual screening badge */}
            {movie.categories?.is_virtual_screening && (
              <Text style={styles.screeningName}>
                {movie.virtual_screening_info?.screening_name || 'VIRTUAL SCREENING'}
              </Text>
            )}

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

            {/* Trailer — its own row above watch buttons */}
            {movie?.links?.trailer_hosted && (
              <View style={styles.watchButtonRow}>
                <ActionButton
                  label="TRAILER"
                  color="#E50914"
                  onPress={() => setTrailerVisible(true)}
                  hasTVPreferredFocus={true}
                  testID="action-btn-trailer"
                />
              </View>
            )}

            {/* Watch buttons row (streaming + VOD + plex) */}
            {hasWatchOptions && (() => {
              const nonVsLinks = purchaseLinks.slice(0, 2).filter(l => !isVirtualScreeningPlatform(l.service, l.url));
              const totalButtons = (streamingLinks.length > 0 ? 1 : 0) + nonVsLinks.length + (plexLinks.length > 0 ? 1 : 0);
              if (totalButtons === 0) return null;
              return (
              <View style={styles.watchButtonRow}>
                {/* STREAM button */}
                {streamingLinks.length > 0 && (() => {
                  const svcKey = normalizeService(streamingLinks[0].service);
                  return (
                  <ActionButton
                    label={getStreamDisplayName(streamingLinks[0].service)}
                    color={getServiceColor(streamingLinks[0].service)}
                    icon={getServiceLogo(streamingLinks[0].service)}
                    iconTintColor="#ffffff"
                    borderColor={NEEDS_BORDER.includes(svcKey) ? '#444' : undefined}
                    onPress={() => handleWatchPress(streamingLinks[0])}
                    hasTVPreferredFocus={!movie?.links?.trailer_hosted}
                    testID="action-btn-stream"
                  />
                  );
                })()}

                {/* VOD buttons (non-virtual-screening only) */}
                {nonVsLinks.map((link, idx) => {
                  const label = movie?._is_preorder ? 'PRE-ORDER'
                    : getVodDisplayName(link.service);
                  const buttonColor = movie?._is_preorder ? '#7c3aed'
                    : getServiceColor(link.service);
                  const vodKey = normalizeService(link.service);
                  const vodBorder = (!movie?._is_preorder && NEEDS_BORDER.includes(vodKey)) ? '#444'
                    : undefined;
                  return (
                    <View key={`purchase-${idx}`}>
                      <ActionButton
                        label={label}
                        color={buttonColor}
                        icon={!movie?._is_preorder ? getServiceLogo(link.service) : null}
                        iconTintColor="#ffffff"
                        borderColor={vodBorder}
                        onPress={() => handleWatchPress(link)}
                        hasTVPreferredFocus={!movie?.links?.trailer_hosted && streamingLinks.length === 0 && idx === 0}
                        testID={`action-btn-purchase-${idx}`}
                      />
                      {movie?._is_preorder && link.sublabel && (
                        <Text style={styles.preOrderDateLabel}>{link.sublabel}</Text>
                      )}
                    </View>
                  );
                })}

                {/* PLEX button */}
                {plexLinks.length > 0 && (
                  <ActionButton
                    label="PLEX"
                    color="#E5A00D"
                    icon={getServiceLogo('plex')}
                    iconTintColor="#ffffff"
                    onPress={() => handleWatchPress(plexLinks[0])}
                    testID="action-btn-plex"
                  />
                )}
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

            {/* Synopsis — tap to expand/collapse */}
            {movie.synopsis && (
              <TouchableOpacity
                style={styles.synopsisContainer}
                onPress={toggleSynopsis}
                activeOpacity={0.8}
                accessible={true}
                accessibilityLabel={synopsisExpanded ? 'Collapse synopsis' : 'Expand synopsis'}
                accessibilityRole="button"
              >
                <Text style={styles.synopsis} numberOfLines={synopsisExpanded ? undefined : 6}>
                  {movie.synopsis}
                  {movie.categories?.is_virtual_screening && movie.virtual_screening_info?.screening_name && (
                    <Text style={styles.screeningCallout}>
                      {` Virtual screening available as part of the ${movie.virtual_screening_info.screening_name}.${movie.virtual_screening_info?.available_end ? ` Ends ${formatShortDate(movie.virtual_screening_info.available_end)}.` : ''}`}
                    </Text>
                  )}
                </Text>
                {!synopsisExpanded && movie.synopsis.length > 300 && (
                  <Text style={styles.synopsisMore}>Select to read more</Text>
                )}
              </TouchableOpacity>
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
          </ScrollView>
        </View>
      </View>

      {/* Navigation arrows — focusable buttons at screen edges.
         Hidden for 800ms on mount and after each navigation so buttons claim focus first.
         Once visible, focus landing here auto-navigates to next/prev movie. */}
      {showArrows && movieList.length > 1 && (
        <NavArrow direction="left" onNavigate={navigatePrevious} />
      )}
      {showArrows && movieList.length > 1 && (
        <NavArrow direction="right" onNavigate={navigateNext} />
      )}

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
    fontSize: Typography.tvos.body - 2,
    fontWeight: '800',
    letterSpacing: 1.5,
    textAlign: 'center',
    paddingVertical: 8,
    paddingHorizontal: 12,
    marginBottom: Spacing.tvos.sm,
    overflow: 'hidden',
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
  synopsisMore: {
    color: Colors.primary,
    fontSize: Typography.tvos.caption,
    marginTop: Spacing.tvos.xs,
    fontWeight: '500',
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
