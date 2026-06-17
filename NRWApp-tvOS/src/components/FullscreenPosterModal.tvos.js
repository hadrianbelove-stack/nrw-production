/**
 * New Release Wall - tvOS Fullscreen Poster Modal
 * Side-by-side layout: large poster + info panel
 *
 * Navigation:
 *   Row 1: [ < ]  [ TRAILER ]  [ > ]   — default focus on TRAILER
 *   Row 2: [Stream] [VOD1] [VOD2] ...  — all services side by side
 *
 *   < and > auto-fire on focus (navigate prev/next movie).
 *   TRAILER always gets default focus on each new movie.
 *   DOWN enters watch row, LEFT/RIGHT between services, UP back to nav row.
 */

import React, { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import {
  View,
  Text,
  Image,
  StyleSheet,
  Modal,
  TouchableOpacity,
  Animated,
  ScrollView,
  Linking,
} from 'react-native';
import { Colors, getServiceColor, isVirtualScreeningPlatform } from '../constants/colors';
import { useTVEventHandler, TV_EVENTS } from '../utils/focusManager.tvos';
import TrailerPlayer from './TrailerPlayer.tvos';
import { renderMarkdownSpans } from '../utils/markdown';

const FullscreenPosterModal = ({
  visible,
  movies,
  initialIndex,
  onClose,
  plexLibrary = {},
}) => {
  const [currentIndex, setCurrentIndex] = useState(initialIndex || 0);
  const [trailerVisible, setTrailerVisible] = useState(false);
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const [imageError, setImageError] = useState(false);
  // Visual-only ‹ › cues at the screen edges; they flash when you swipe to a new movie.
  const leftArrowOpacity = useRef(new Animated.Value(0.4)).current;
  const rightArrowOpacity = useRef(new Animated.Value(0.4)).current;
  const flashArrow = useCallback((anim) => {
    Animated.sequence([
      Animated.timing(anim, { toValue: 1, duration: 100, useNativeDriver: true }),
      Animated.timing(anim, { toValue: 0.4, duration: 200, useNativeDriver: true }),
    ]).start();
  }, []);

  // Update index when initialIndex changes
  useEffect(() => {
    if (visible) {
      setCurrentIndex(initialIndex || 0);
      setImageError(false);
      Animated.timing(fadeAnim, {
        toValue: 1,
        duration: 300,
        useNativeDriver: true,
      }).start();
    }
  }, [visible, initialIndex, fadeAnim]);

  // Current movie
  const movie = movies[currentIndex] || {};

  // Navigate to previous/next movie, flashing the matching edge arrow as a cue.
  const navigate = useCallback((direction) => {
    if (movies.length < 2) return;
    flashArrow(direction < 0 ? leftArrowOpacity : rightArrowOpacity);
    const newIndex = (currentIndex + direction + movies.length) % movies.length;
    setCurrentIndex(newIndex);
    setImageError(false);
  }, [currentIndex, movies.length, flashArrow, leftArrowOpacity, rightArrowOpacity]);

  // SWIPE left/right changes movie (arrows flash); d-pad LEFT/RIGHT is left alone so it
  // still moves focus between the watch-service buttons. MENU closes.
  useTVEventHandler(trailerVisible ? {} : {
    [TV_EVENTS.MENU]: () => onClose(),
    [TV_EVENTS.SWIPE_LEFT]: () => navigate(-1),
    [TV_EVENTS.SWIPE_RIGHT]: () => navigate(1),
  });

  // Get poster URL
  const posterUrl = movie.poster_url || movie.posterUrl || movie.poster;

  // Get director
  const director = movie.crew?.director || movie.director;

  // Format country
  const formatCountry = (country) => {
    if (!country) return null;
    const shortNames = {
      'united states of america': 'USA', 'united states': 'USA', 'usa': 'USA',
      'united kingdom': 'UK', 'great britain': 'UK',
      'south korea': 'S. Korea', 'south africa': 'S. Africa',
      'new zealand': 'N. Zealand', 'bosnia and herzegovina': 'Bosnia',
      'saudi arabia': 'S. Arabia',
    };
    const shortened = shortNames[country.toLowerCase()];
    if (shortened) return shortened;
    if (country !== country[0].toUpperCase() + country.slice(1).toLowerCase()) {
      return country[0].toUpperCase() + country.slice(1).toLowerCase();
    }
    return country;
  };

  // Build meta text
  const buildMeta = () => {
    const parts = [];
    if (movie.year) parts.push(movie.year);
    if (movie.genres?.length) parts.push(movie.genres.slice(0, 2).join(', '));
    if (movie.runtime) parts.push(`${movie.runtime} min`);
    if (director) parts.push(`Director: ${director}`);
    if (movie.country) parts.push(formatCountry(movie.country));
    return parts.join(' • ');
  };

  // Get streaming info
  const getStreamingInfo = () => {
    const watchLinks = movie.watch_links || {};
    const providers = movie.providers || {};

    if (watchLinks.streaming?.service) {
      return { service: watchLinks.streaming.service, link: watchLinks.streaming.link };
    }
    if (providers.streaming?.length) {
      const service = providers.streaming.find(p => !p.includes('with Ads')) || providers.streaming[0];
      return { service, link: null };
    }
    return null;
  };

  const streamingInfo = getStreamingInfo();

  // Open link
  const openLink = useCallback((url) => {
    if (url) {
      Linking.openURL(url).catch(err => console.error('Failed to open URL:', err));
    }
  }, []);

  // Get ALL VOD links
  const vodLinks = useMemo(() => {
    const watchLinks = movie.watch_links || {};
    const vodArray = watchLinks.vod || [];
    if (!Array.isArray(vodArray) || vodArray.length === 0) return [];
    return vodArray.slice(0, 3).map(vod => ({
      ...vod,
      isVirtualScreening: isVirtualScreeningPlatform(vod.service, vod.link || vod.url),
    }));
  }, [movie]);

  const hasTrailer = !!movie.links?.trailer_hosted;
  const hasWatchButtons = vodLinks.length > 0 || streamingInfo || plexLibrary[String(movie.id)]?.deep_link;

  // --- Sub-components ---

  // Action button (trailer / service)
  const ActionButton = ({ label, onPress, color, borderColor, textColor, isPreferred = false, disabled = false, size = 'lg' }) => {
    const [isFocused, setIsFocused] = useState(false);
    const scaleAnim = useRef(new Animated.Value(1)).current;

    const handleFocus = () => {
      setIsFocused(true);
      Animated.timing(scaleAnim, {
        toValue: 1.05,
        duration: 150,
        useNativeDriver: true,
      }).start();
    };

    const handleBlur = () => {
      setIsFocused(false);
      Animated.timing(scaleAnim, {
        toValue: 1,
        duration: 150,
        useNativeDriver: true,
      }).start();
    };

    const bgColor = color || '#333';

    return (
      <TouchableOpacity
        onPress={onPress}
        onFocus={handleFocus}
        onBlur={handleBlur}
        hasTVPreferredFocus={isPreferred}
        disabled={disabled}
        activeOpacity={1}
        style={size === 'sm' ? styles.btnTouchSm : styles.btnTouchLg}
      >
        <Animated.View
          style={[
            size === 'sm' ? styles.btnSm : styles.btnLg,
            { backgroundColor: bgColor },
            borderColor && { borderWidth: 2, borderColor },
            isFocused && styles.btnFocused,
            disabled && styles.btnDisabled,
            { transform: [{ scale: scaleAnim }] },
          ]}
        >
          <Text style={[styles.btnText, size === 'sm' && styles.btnTextSm, textColor && { color: textColor }]}>
            {label}
          </Text>
        </Animated.View>
      </TouchableOpacity>
    );
  };

  if (!visible) return null;

  return (
    <Modal
      visible={visible}
      transparent={true}
      animationType="none"
      onRequestClose={() => { if (!trailerVisible) onClose(); }}
    >
      <Animated.View style={[styles.container, { opacity: fadeAnim }]}>
        {/* Main content - side by side */}
        <View style={styles.content}>
          {/* Large poster */}
          <View style={styles.posterContainer}>
            {posterUrl && !imageError ? (
              <Image
                source={{ uri: posterUrl }}
                style={styles.poster}
                resizeMode="cover"
                onError={() => setImageError(true)}
              />
            ) : (
              <View style={styles.posterPlaceholder}>
                <Text style={styles.placeholderText}>{movie.display_title || movie.title}</Text>
              </View>
            )}
          </View>

          {/* Info panel */}
          <View style={styles.infoPanel}>
            <Text style={styles.title}>{movie.display_title || movie.title}</Text>
            <Text style={styles.meta}>{buildMeta()}</Text>

            <ScrollView style={styles.synopsisContainer} showsVerticalScrollIndicator={false}>
              <Text style={styles.synopsis}>
                {(movie.capsule || movie.synopsis) ? renderMarkdownSpans(movie.capsule || movie.synopsis) : 'Synopsis coming soon.'}
              </Text>
            </ScrollView>

            {/* Buttons — key forces full remount so hasTVPreferredFocus re-fires */}
            <View key={`btns-${currentIndex}`} style={styles.buttonArea}>

              {/* Row 1: TRAILER (swipe left/right changes movie; ‹ › cues sit at the screen edges) */}
              <View style={styles.navRow}>
                {hasTrailer && (
                  <ActionButton
                    label="TRAILER"
                    onPress={() => setTrailerVisible(true)}
                    color="#E50914"
                    isPreferred={true}
                    size="lg"
                  />
                )}
              </View>

              {/* Row 2: all watch services side by side */}
              {hasWatchButtons && (
                <View style={styles.watchRow}>
                  {/* Streaming buttons first */}
                  {streamingInfo && (
                    <ActionButton
                      label={streamingInfo.service.toUpperCase()}
                      onPress={() => openLink(streamingInfo.link)}
                      color={getServiceColor(streamingInfo.service)}
                      isPreferred={!hasTrailer}
                      disabled={!streamingInfo.link}
                      size="lg"
                    />
                  )}

                  {/* VOD buttons */}
                  {vodLinks.map((vod, i) => (
                    <ActionButton
                      key={`vod-${i}`}
                      label={vod.isVirtualScreening ? 'TICKET' : (vod.service || 'RENT/BUY').toUpperCase()}
                      onPress={() => openLink(vod.link || vod.url)}
                      color={vod.isVirtualScreening ? 'transparent' : getServiceColor(vod.service)}
                      borderColor={vod.isVirtualScreening ? Colors.screeningGold : undefined}
                      textColor={vod.isVirtualScreening ? Colors.screeningGold : undefined}
                      isPreferred={!hasTrailer && !streamingInfo && i === 0}
                      disabled={!(vod.link || vod.url)}
                      size="sm"
                    />
                  ))}

                  {/* Plex button */}
                  {plexLibrary[String(movie.id)]?.deep_link && (
                    <ActionButton
                      label="PLEX"
                      onPress={() => openLink(plexLibrary[String(movie.id)].deep_link)}
                      color="#E5A00D"
                      isPreferred={!hasTrailer && !streamingInfo && vodLinks.length === 0}
                      size="lg"
                    />
                  )}
                </View>
              )}
            </View>
          </View>
        </View>

        {/* Visual-only ‹ › edge cues — flash on swipe, never focusable */}
        {movies.length > 1 && (
          <View style={styles.arrowLeft} pointerEvents="none">
            <Animated.Text style={[styles.arrowText, { opacity: leftArrowOpacity }]}>‹</Animated.Text>
          </View>
        )}
        {movies.length > 1 && (
          <View style={styles.arrowRight} pointerEvents="none">
            <Animated.Text style={[styles.arrowText, { opacity: rightArrowOpacity }]}>›</Animated.Text>
          </View>
        )}

        {/* Counter */}
        <Text style={styles.counter}>
          {currentIndex + 1} / {movies.length}
        </Text>

        {/* Trailer player overlay */}
        {trailerVisible && movies.length > 0 && (
          <TrailerPlayer
            movieList={movies}
            initialIndex={currentIndex}
            onClose={(lastIndex) => {
              setTrailerVisible(false);
              if (lastIndex !== currentIndex && lastIndex >= 0 && lastIndex < movies.length) {
                setCurrentIndex(lastIndex);
                setImageError(false);
              }
            }}
          />
        )}
      </Animated.View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.95)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  content: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 40,
    paddingHorizontal: 120,
  },
  posterContainer: {
    width: 450,
    height: 675,
    borderRadius: 16,
    overflow: 'hidden',
    backgroundColor: Colors.backgroundSecondary,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 20 },
    shadowOpacity: 0.5,
    shadowRadius: 40,
  },
  poster: {
    width: '100%',
    height: '100%',
  },
  posterPlaceholder: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 40,
  },
  placeholderText: {
    color: Colors.textMuted,
    fontSize: 28,
    textAlign: 'center',
  },
  infoPanel: {
    width: 500,
    maxHeight: 675,
    backgroundColor: 'rgba(26, 26, 46, 0.95)',
    borderRadius: 16,
    padding: 32,
  },
  title: {
    color: '#fff',
    fontSize: 36,
    fontWeight: '700',
    marginBottom: 8,
  },
  meta: {
    color: '#888',
    fontSize: 20,
    marginBottom: 20,
  },
  synopsisContainer: {
    maxHeight: 200,
    marginBottom: 24,
  },
  synopsis: {
    color: '#ccc',
    fontSize: 22,
    lineHeight: 32,
  },
  buttonArea: {
    gap: 14,
  },
  // Row 1: < TRAILER >
  navRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  arrowLeft: {
    position: 'absolute',
    left: 40,
    top: 0,
    bottom: 0,
    justifyContent: 'center',
  },
  arrowRight: {
    position: 'absolute',
    right: 40,
    top: 0,
    bottom: 0,
    justifyContent: 'center',
  },
  arrowText: {
    color: Colors.primary,
    fontSize: 70,
    fontWeight: '300',
  },
  // Row 2: services
  watchRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  // Large button (trailer, streaming, plex)
  btnTouchLg: {
    width: 180,
    height: 54,
  },
  btnLg: {
    flex: 1,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  // Small button (VOD)
  btnTouchSm: {
    width: 160,
    height: 48,
  },
  btnSm: {
    flex: 1,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  btnFocused: {
    borderWidth: 3,
    borderColor: Colors.focusBorderHighlight,
  },
  btnDisabled: {
    opacity: 0.5,
  },
  btnText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '700',
    letterSpacing: 1,
  },
  btnTextSm: {
    fontSize: 15,
  },
  counter: {
    position: 'absolute',
    bottom: 40,
    color: '#888',
    fontSize: 20,
  },
});

export default FullscreenPosterModal;
