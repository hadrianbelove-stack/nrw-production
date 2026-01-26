/**
 * New Release Wall - tvOS Movie Card Component
 * Focusable card with parallax effects and focus animations
 */

import React, { useState, useRef, useCallback } from 'react';
import {
  View,
  Text,
  Image,
  StyleSheet,
  TouchableOpacity,
  Animated,
  AccessibilityInfo,
} from 'react-native';
import { Colors, Typography, Spacing, Dimensions } from '../constants/colors';
import { PARALLAX_PROPERTIES, FOCUS_STYLES } from '../utils/focusManager.tvos';

const MovieCard = ({
  movie,
  onSelect,
  onFocus,
  onBlur,
  isFeatured = false,
  hasTVPreferredFocus = false,
  testID,
}) => {
  const [isFocused, setIsFocused] = useState(false);
  const [imageError, setImageError] = useState(false);
  const scaleAnim = useRef(new Animated.Value(1)).current;
  const shadowAnim = useRef(new Animated.Value(0)).current;

  // Get card dimensions based on featured status
  const cardWidth = isFeatured
    ? Dimensions.tvos.featuredCardWidth
    : Dimensions.tvos.cardWidth;
  const cardHeight = isFeatured
    ? Dimensions.tvos.featuredCardHeight
    : Dimensions.tvos.cardHeight;

  // Handle focus event
  const handleFocus = useCallback(() => {
    setIsFocused(true);

    // Animate scale and shadow with smooth timing (no spring bounce)
    Animated.parallel([
      Animated.timing(scaleAnim, {
        toValue: FOCUS_STYLES.movieCard.scale,
        duration: 150,
        useNativeDriver: true,
      }),
      Animated.timing(shadowAnim, {
        toValue: 1,
        duration: 150,
        useNativeDriver: false,
      }),
    ]).start();

    if (onFocus) {
      onFocus(movie);
    }
  }, [movie, onFocus, scaleAnim, shadowAnim]);

  // Handle blur event
  const handleBlur = useCallback(() => {
    setIsFocused(false);

    // Animate scale and shadow back
    Animated.parallel([
      Animated.timing(scaleAnim, {
        toValue: 1,
        duration: 150,
        useNativeDriver: true,
      }),
      Animated.timing(shadowAnim, {
        toValue: 0,
        duration: 150,
        useNativeDriver: false,
      }),
    ]).start();

    if (onBlur) {
      onBlur(movie);
    }
  }, [movie, onBlur, scaleAnim, shadowAnim]);

  // Handle selection (remote click)
  const handleSelect = useCallback(() => {
    if (onSelect) {
      onSelect(movie);
    }
  }, [movie, onSelect]);

  // Interpolate shadow opacity
  const shadowOpacity = shadowAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0, FOCUS_STYLES.movieCard.shadowOpacity],
  });

  // Get poster URL
  const posterUrl = movie.poster_url || movie.posterUrl || movie.poster;
  const hasPoster = !!posterUrl;

  // Get streaming service badge
  const getStreamingBadge = () => {
    const watchLinks = movie.watch_links || {};
    const providers = movie.providers || {};

    let service = watchLinks.streaming?.service;
    if (!service && providers.streaming?.length > 0) {
      service = providers.streaming.find(p => !p.includes('with Ads')) || providers.streaming[0];
    }
    if (!service) return null;

    const s = service.toLowerCase();
    if (s.includes('netflix')) return { name: 'NETFLIX', color: '#E50914' };
    if (s.includes('disney')) return { name: 'DISNEY+', color: '#113CCF' };
    if (s.includes('max') || s.includes('hbo')) return { name: 'MAX', color: '#002BE7' };
    if (s.includes('amazon') || s.includes('prime')) return { name: 'PRIME', color: '#00A8E1' };
    if (s.includes('hulu')) return { name: 'HULU', color: '#1CE783' };
    if (s.includes('peacock')) return { name: 'PEACOCK', color: '#000000' };
    if (s.includes('mubi')) return { name: 'MUBI', color: '#DA2128' };
    if (s.includes('shudder')) return { name: 'SHUDDER', color: '#E31B23' };
    if (s.includes('criterion')) return { name: 'CRITERION', color: '#000000' };
    if (s.includes('paramount')) return { name: 'PARAMOUNT+', color: '#0064FF' };
    if (s.includes('apple')) return { name: 'APPLE TV+', color: '#000000' };
    return { name: service.toUpperCase().slice(0, 8), color: '#666666' };
  };

  const streamingBadge = getStreamingBadge();

  return (
    <TouchableOpacity
      onPress={handleSelect}
      onFocus={handleFocus}
      onBlur={handleBlur}
      hasTVPreferredFocus={hasTVPreferredFocus}
      activeOpacity={1}
      accessible={true}
      accessibilityLabel={`${movie.title}, ${movie.year || ''}, directed by ${movie.director || 'Unknown'}`}
      accessibilityRole="button"
      accessibilityHint="Press to view movie details"
      testID={testID}
    >
      <Animated.View
        style={[
          styles.container,
          {
            width: cardWidth,
            height: cardHeight,
            transform: [{ scale: scaleAnim }],
          },
        ]}
      >
        {/* Shadow layer (only visible when focused) */}
        <Animated.View
          style={[
            styles.shadowLayer,
            {
              opacity: shadowOpacity,
              shadowColor: FOCUS_STYLES.movieCard.shadowColor,
              shadowRadius: FOCUS_STYLES.movieCard.shadowRadius,
            },
          ]}
        />

        {/* Poster image or placeholder */}
        {hasPoster && !imageError ? (
          <Image
            source={{ uri: posterUrl }}
            style={styles.poster}
            resizeMode="cover"
            onError={() => setImageError(true)}
          />
        ) : (
          <View style={styles.posterPlaceholder}>
            <Text style={styles.placeholderText} numberOfLines={3}>
              {movie.title}
            </Text>
          </View>
        )}

        {/* Streaming service badge - upper right */}
        {streamingBadge && (
          <View style={[styles.streamingBadge, { backgroundColor: streamingBadge.color }]}>
            <Text style={styles.streamingBadgeText}>{streamingBadge.name}</Text>
          </View>
        )}

        {/* Featured border - red box around poster */}
        {movie.featured && <View style={styles.featuredBorder} />}

        {/* Featured strip - bottom red banner */}
        {movie.featured && (
          <View style={styles.featuredStrip}>
            <Text style={styles.featuredStripText}>FEATURED</Text>
          </View>
        )}

        {/* Focus border */}
        {isFocused && <View style={styles.focusBorder} />}

        {/* Metadata overlay (visible when focused) */}
        {isFocused && (
          <View style={styles.metadataOverlay}>
            <View style={styles.gradientOverlay} />
            <View style={styles.metadataContent}>
              <Text style={styles.title} numberOfLines={2}>
                {movie.title}
              </Text>
              <Text style={styles.subtitle} numberOfLines={1}>
                {movie.director && `Dir. ${movie.director}`}
                {movie.year && ` • ${movie.year}`}
              </Text>
              {movie.countries && movie.countries.length > 0 && (
                <Text style={styles.country} numberOfLines={1}>
                  {movie.countries.join(', ')}
                </Text>
              )}
            </View>
          </View>
        )}
      </Animated.View>
    </TouchableOpacity>
  );
};

const styles = StyleSheet.create({
  container: {
    borderRadius: 12,
    overflow: 'hidden',
    backgroundColor: Colors.backgroundSecondary,
    position: 'relative',
  },
  shadowLayer: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: 12,
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.5,
    backgroundColor: 'transparent',
  },
  poster: {
    width: '100%',
    height: '100%',
    borderRadius: 12,
  },
  posterPlaceholder: {
    width: '100%',
    height: '100%',
    borderRadius: 12,
    backgroundColor: Colors.backgroundSecondary,
    borderWidth: 1,
    borderColor: Colors.border || '#333',
    justifyContent: 'center',
    alignItems: 'center',
    padding: Spacing.tvos.md,
  },
  placeholderText: {
    color: Colors.textMuted,
    fontSize: Typography.tvos.body,
    textAlign: 'center',
    fontWeight: '500',
  },
  streamingBadge: {
    position: 'absolute',
    top: Spacing.tvos.xs,
    right: Spacing.tvos.xs,
    paddingHorizontal: Spacing.tvos.xs + 2,
    paddingVertical: Spacing.tvos.xs - 2,
    borderRadius: 6,
  },
  streamingBadgeText: {
    color: '#FFFFFF',
    fontSize: Typography.tvos.caption - 4,
    fontWeight: '800',
    letterSpacing: 0.3,
  },
  featuredBorder: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: 12,
    borderWidth: 3,
    borderColor: '#E50914',
  },
  featuredStrip: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: '#E50914',
    paddingVertical: Spacing.tvos.xs,
    borderBottomLeftRadius: 12,
    borderBottomRightRadius: 12,
    alignItems: 'center',
  },
  featuredStripText: {
    color: '#FFFFFF',
    fontSize: Typography.tvos.caption - 2,
    fontWeight: '800',
    letterSpacing: 1.5,
  },
  focusBorder: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: 12,
    borderWidth: FOCUS_STYLES.movieCard.borderWidth,
    borderColor: FOCUS_STYLES.movieCard.borderColor,
  },
  metadataOverlay: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    height: '40%',
  },
  gradientOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0, 0, 0, 0.8)',
    borderBottomLeftRadius: 12,
    borderBottomRightRadius: 12,
  },
  metadataContent: {
    flex: 1,
    justifyContent: 'flex-end',
    padding: Spacing.tvos.md,
  },
  title: {
    color: Colors.textPrimary,
    fontSize: Typography.tvos.body,
    fontWeight: '600',
    marginBottom: Spacing.tvos.xs,
  },
  subtitle: {
    color: Colors.textSecondary,
    fontSize: Typography.tvos.caption,
  },
  country: {
    color: Colors.textMuted,
    fontSize: Typography.tvos.caption - 2,
    marginTop: Spacing.tvos.xs / 2,
  },
});

export default MovieCard;
