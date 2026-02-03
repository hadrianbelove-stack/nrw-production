/**
 * New Release Wall - tvOS Fullscreen Poster Modal
 * Side-by-side layout: large poster + info panel
 * Navigate between movies with left/right on remote
 */

import React, { useState, useRef, useCallback, useEffect } from 'react';
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
import { Colors, Typography, Spacing } from '../constants/colors';
import { useTVEventHandler, TV_EVENTS } from '../utils/focusManager.tvos';

const FullscreenPosterModal = ({
  visible,
  movies,
  initialIndex,
  onClose,
  plexLibrary = {},
}) => {
  const [currentIndex, setCurrentIndex] = useState(initialIndex || 0);
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

  // Handle TV remote events
  useTVEventHandler({
    [TV_EVENTS.LEFT]: () => navigate(-1),
    [TV_EVENTS.RIGHT]: () => navigate(1),
    [TV_EVENTS.BACK]: () => onClose(),
  });

  // Get poster URL
  const posterUrl = movie.poster_url || movie.posterUrl || movie.poster;

  // Get director
  const director = movie.crew?.director || movie.director;

  // Format country
  const formatCountry = (country) => {
    const abbrev = {
      'United States of America': 'USA',
      'United Kingdom': 'UK',
    };
    return abbrev[country] || country;
  };

  // Build meta text
  const buildMeta = () => {
    const parts = [];
    if (movie.year) parts.push(movie.year);
    if (movie.genres?.length) parts.push(movie.genres.slice(0, 2).join(', '));
    if (movie.runtime) parts.push(`${movie.runtime} min`);
    if (director) parts.push(`Dir: ${director}`);
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

  // Button component with focus handling
  const ActionButton = ({ label, onPress, isPrimary = false, disabled = false }) => {
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

    return (
      <TouchableOpacity
        onPress={onPress}
        onFocus={handleFocus}
        onBlur={handleBlur}
        disabled={disabled}
        activeOpacity={1}
      >
        <Animated.View
          style={[
            styles.button,
            isPrimary ? styles.buttonPrimary : styles.buttonSecondary,
            isFocused && styles.buttonFocused,
            disabled && styles.buttonDisabled,
            { transform: [{ scale: scaleAnim }] },
          ]}
        >
          <Text style={[styles.buttonText, isPrimary && styles.buttonTextPrimary]}>
            {label}
          </Text>
        </Animated.View>
      </TouchableOpacity>
    );
  };

  // Navigation arrow component
  const NavArrow = ({ direction, onPress }) => {
    const [isFocused, setIsFocused] = useState(false);
    const isLeft = direction === 'left';

    return (
      <TouchableOpacity
        onPress={onPress}
        onFocus={() => setIsFocused(true)}
        onBlur={() => setIsFocused(false)}
        style={[
          styles.navArrow,
          isLeft ? styles.navArrowLeft : styles.navArrowRight,
          isFocused && styles.navArrowFocused,
        ]}
        activeOpacity={1}
      >
        <Text style={styles.navArrowText}>{isLeft ? '‹' : '›'}</Text>
      </TouchableOpacity>
    );
  };

  if (!visible) return null;

  return (
    <Modal
      visible={visible}
      transparent={true}
      animationType="none"
      onRequestClose={onClose}
    >
      <Animated.View style={[styles.container, { opacity: fadeAnim }]}>
        {/* Navigation arrows */}
        <NavArrow direction="left" onPress={() => navigate(-1)} />
        <NavArrow direction="right" onPress={() => navigate(1)} />

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
                <Text style={styles.placeholderText}>{movie.title}</Text>
              </View>
            )}
          </View>

          {/* Info panel */}
          <View style={styles.infoPanel}>
            <Text style={styles.title}>{movie.title}</Text>
            <Text style={styles.meta}>{buildMeta()}</Text>

            <ScrollView style={styles.synopsisContainer} showsVerticalScrollIndicator={false}>
              <Text style={styles.synopsis}>
                {movie.synopsis || 'Synopsis coming soon.'}
              </Text>
            </ScrollView>

            {/* Action buttons */}
            <View style={styles.buttons}>
              {streamingInfo && (
                <ActionButton
                  label={`Watch on ${streamingInfo.service}`}
                  onPress={() => openLink(streamingInfo.link)}
                  isPrimary={true}
                  disabled={!streamingInfo.link}
                />
              )}

              {plexLibrary[String(movie.id)]?.deep_link && (
                <ActionButton
                  label="Play on Plex"
                  onPress={() => openLink(plexLibrary[String(movie.id)].deep_link)}
                />
              )}

              {movie.links?.trailer && (
                <ActionButton
                  label="Watch Trailer"
                  onPress={() => openLink(movie.links.trailer)}
                />
              )}

              {movie.rt_score && (
                <ActionButton
                  label={`Rotten Tomatoes: ${movie.rt_score}`}
                  onPress={() => openLink(movie.links?.rt)}
                  disabled={!movie.links?.rt}
                />
              )}
            </View>
          </View>
        </View>

        {/* Counter */}
        <Text style={styles.counter}>
          {currentIndex + 1} / {movies.length}
        </Text>

        {/* Hint */}
        <Text style={styles.hint}>
          Swipe left/right to navigate • Menu to close
        </Text>
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
  button: {
    paddingVertical: 16,
    paddingHorizontal: 24,
    borderRadius: 10,
    alignItems: 'center',
  },
  buttonPrimary: {
    backgroundColor: '#E50914',
  },
  buttonSecondary: {
    backgroundColor: '#333',
  },
  buttonFocused: {
    borderWidth: 3,
    borderColor: '#00ffcc',
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  buttonText: {
    color: '#fff',
    fontSize: 22,
    fontWeight: '600',
  },
  buttonTextPrimary: {
    fontWeight: '700',
  },
  navArrow: {
    position: 'absolute',
    top: '50%',
    marginTop: -40,
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  navArrowLeft: {
    left: 30,
  },
  navArrowRight: {
    right: 30,
  },
  navArrowFocused: {
    backgroundColor: 'rgba(255, 255, 255, 0.3)',
    borderWidth: 2,
    borderColor: '#00ffcc',
  },
  navArrowText: {
    color: '#fff',
    fontSize: 48,
    fontWeight: '300',
  },
  counter: {
    position: 'absolute',
    bottom: 40,
    color: '#888',
    fontSize: 20,
  },
  hint: {
    position: 'absolute',
    bottom: 20,
    color: '#555',
    fontSize: 16,
  },
});

export default FullscreenPosterModal;
