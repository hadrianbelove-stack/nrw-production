/**
 * New Release Wall - tvOS Fullscreen Poster Modal
 * Side-by-side layout: large poster + info panel
 * Navigation: UP/DOWN between button rows, LEFT/RIGHT within rows,
 * edge triggers (< >) navigate to prev/next movie on focus.
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

  // Update index when initialIndex changes
  useEffect(() => {
    if (visible) {
      setCurrentIndex(initialIndex || 0);
      setImageError(false);
      // Fade in
      Animated.timing(fadeAnim, {
        toValue: 1,
        duration: 300,
        useNativeDriver: true,
      }).start();
    }
  }, [visible, initialIndex, fadeAnim]);

  // Current movie
  const movie = movies[currentIndex] || {};

  // Navigate to previous/next movie
  const navigate = useCallback((direction) => {
    const newIndex = (currentIndex + direction + movies.length) % movies.length;
    setCurrentIndex(newIndex);
    setImageError(false);
  }, [currentIndex, movies.length]);

  // Handle TV remote events — only MENU to dismiss
  useTVEventHandler(trailerVisible ? {} : {
    [TV_EVENTS.MENU]: () => onClose(),
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

  // Get VOD/rental info with virtual screening platform detection (memoized)
  const vodInfo = useMemo(() => {
    const watchLinks = movie.watch_links || {};
    const vodLinks = watchLinks.vod || [];
    if (!Array.isArray(vodLinks) || vodLinks.length === 0) return null;
    const vod = vodLinks[0];
    const isVirtualScreening = isVirtualScreeningPlatform(vod.service, vod.link || vod.url);
    return { ...vod, isVirtualScreening };
  }, [movie]);

  // Edge trigger — navigates to prev/next movie the moment focus lands on it
  const EdgeTrigger = ({ direction }) => (
    <TouchableOpacity
      onFocus={() => navigate(direction === 'left' ? -1 : 1)}
      style={[styles.edgeTrigger, direction === 'left' ? styles.edgeLeft : styles.edgeRight]}
      activeOpacity={1}
    >
      <Text style={styles.edgeText}>{direction === 'left' ? '‹' : '›'}</Text>
    </TouchableOpacity>
  );

  // Action button with focus handling
  const ActionButton = ({ label, onPress, color, borderColor, textColor, isFirst = false, disabled = false }) => {
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
        hasTVPreferredFocus={isFirst}
        disabled={disabled}
        activeOpacity={1}
      >
        <Animated.View
          style={[
            styles.button,
            { backgroundColor: bgColor },
            borderColor && { borderWidth: 2, borderColor },
            isFocused && styles.buttonFocused,
            disabled && styles.buttonDisabled,
            { transform: [{ scale: scaleAnim }] },
          ]}
        >
          <Text style={[styles.buttonText, textColor && { color: textColor }]}>
            {label}
          </Text>
        </Animated.View>
      </TouchableOpacity>
    );
  };

  if (!visible) return null;

  // Determine which button gets initial focus (first available)
  let firstButtonAssigned = false;
  const getIsFirst = () => {
    if (!firstButtonAssigned) {
      firstButtonAssigned = true;
      return true;
    }
    return false;
  };

  return (
    <Modal
      visible={visible}
      transparent={true}
      animationType="none"
      onRequestClose={onClose}
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
                {movie.synopsis || 'Synopsis coming soon.'}
              </Text>
            </ScrollView>

            {/* Action buttons with edge triggers */}
            {/* key forces remount on movie change so hasTVPreferredFocus re-fires */}
            <View key={`buttons-${currentIndex}`} style={styles.buttons}>

              {/* Trailer row */}
              {movie.links?.trailer_hosted && (
                <View style={styles.buttonRow}>
                  <EdgeTrigger direction="left" />
                  <ActionButton
                    label="Watch Trailer"
                    onPress={() => setTrailerVisible(true)}
                    color="#E50914"
                    isFirst={getIsFirst()}
                  />
                  <EdgeTrigger direction="right" />
                </View>
              )}

              {/* VOD row (may have multiple) */}
              {vodInfo && (
                <View style={styles.buttonRow}>
                  <EdgeTrigger direction="left" />
                  <ActionButton
                    label={vodInfo.isVirtualScreening ? 'Buy Ticket' : 'Rent / Buy'}
                    onPress={() => openLink(vodInfo.link || vodInfo.url)}
                    color={vodInfo.isVirtualScreening ? 'transparent' : '#ff9500'}
                    borderColor={vodInfo.isVirtualScreening ? Colors.screeningGold : undefined}
                    textColor={vodInfo.isVirtualScreening ? Colors.screeningGold : undefined}
                    isFirst={getIsFirst()}
                    disabled={!(vodInfo.link || vodInfo.url)}
                  />
                  <EdgeTrigger direction="right" />
                </View>
              )}

              {/* Streaming row */}
              {streamingInfo && (
                <View style={styles.buttonRow}>
                  <EdgeTrigger direction="left" />
                  <ActionButton
                    label={`Watch on ${streamingInfo.service}`}
                    onPress={() => openLink(streamingInfo.link)}
                    color={getServiceColor(streamingInfo.service)}
                    isFirst={getIsFirst()}
                    disabled={!streamingInfo.link}
                  />
                  <EdgeTrigger direction="right" />
                </View>
              )}

              {/* Plex row */}
              {plexLibrary[String(movie.id)]?.deep_link && (
                <View style={styles.buttonRow}>
                  <EdgeTrigger direction="left" />
                  <ActionButton
                    label="Play on Plex"
                    onPress={() => openLink(plexLibrary[String(movie.id)].deep_link)}
                    color="#E5A00D"
                    isFirst={getIsFirst()}
                  />
                  <EdgeTrigger direction="right" />
                </View>
              )}

              {/* RT row */}
              {movie.rt_score && (
                <View style={styles.buttonRow}>
                  <EdgeTrigger direction="left" />
                  <ActionButton
                    label={`Rotten Tomatoes: ${movie.rt_score}`}
                    onPress={() => openLink(movie.links?.rt)}
                    isFirst={getIsFirst()}
                    disabled={!movie.links?.rt}
                  />
                  <EdgeTrigger direction="right" />
                </View>
              )}
            </View>
          </View>
        </View>

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
  buttons: {
    gap: 12,
  },
  buttonRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  button: {
    flex: 1,
    paddingVertical: 16,
    paddingHorizontal: 24,
    borderRadius: 10,
    alignItems: 'center',
  },
  buttonFocused: {
    borderWidth: 3,
    borderColor: Colors.focusBorderHighlight,
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  buttonText: {
    color: '#fff',
    fontSize: 22,
    fontWeight: '600',
  },
  edgeTrigger: {
    width: 50,
    height: 50,
    justifyContent: 'center',
    alignItems: 'center',
    opacity: 0.4,
  },
  edgeLeft: {
    marginRight: 8,
  },
  edgeRight: {
    marginLeft: 8,
  },
  edgeText: {
    color: 'rgba(0, 212, 170, 0.6)',
    fontSize: 36,
    fontWeight: '300',
  },
  counter: {
    position: 'absolute',
    bottom: 40,
    color: '#888',
    fontSize: 20,
  },
});

export default FullscreenPosterModal;
