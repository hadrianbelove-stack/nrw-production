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

    // Animate scale and shadow
    Animated.parallel([
      Animated.spring(scaleAnim, {
        toValue: FOCUS_STYLES.movieCard.scale,
        friction: 8,
        tension: 100,
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
      Animated.spring(scaleAnim, {
        toValue: 1,
        friction: 8,
        tension: 100,
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

        {/* Poster image with parallax */}
        <Image
          source={{ uri: posterUrl }}
          style={styles.poster}
          resizeMode="cover"
          tvParallaxProperties={PARALLAX_PROPERTIES}
        />

        {/* Featured badge */}
        {movie.featured && (
          <View style={styles.featuredBadge}>
            <Text style={styles.featuredText}>FEATURED</Text>
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
  featuredBadge: {
    position: 'absolute',
    top: Spacing.tvos.sm,
    right: Spacing.tvos.sm,
    backgroundColor: Colors.featuredBadge,
    paddingHorizontal: Spacing.tvos.sm,
    paddingVertical: Spacing.tvos.xs,
    borderRadius: 4,
  },
  featuredText: {
    color: Colors.featuredBadgeText,
    fontSize: Typography.tvos.caption,
    fontWeight: '700',
    letterSpacing: 1,
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
