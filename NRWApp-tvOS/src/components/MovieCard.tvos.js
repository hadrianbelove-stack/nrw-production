/**
 * New Release Wall - tvOS Movie Card Component
 * Focusable card with parallax effects and focus animations
 */

import React, { useState, useRef, useCallback, forwardRef } from 'react';
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

const MovieCard = forwardRef(({
  movie,
  onSelect,
  onLongPress,
  onFocus,
  onBlur,
  isFeatured = false,
  hasTVPreferredFocus = false,
  testID,
  nextFocusUp,
  nextFocusLeft,
  nextFocusRight,
}, ref) => {
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

  // Handle long press (opens fullscreen view)
  const handleLongPress = useCallback(() => {
    if (onLongPress) {
      onLongPress(movie);
    }
  }, [movie, onLongPress]);

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
    if (s.includes('max') || s.includes('hbo')) return { name: 'MAX', color: Colors.maxPurple };
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

  // Get director - can be in crew.director or movie.director
  const director = movie.crew?.director || movie.director;

  // Get country - can be country (string) or countries (array)
  // Use common abbreviations for long country names
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

  const getCountryText = () => {
    if (movie.country) {
      return formatCountry(movie.country);
    }
    if (movie.countries && movie.countries.length > 0) {
      return movie.countries.map(formatCountry).join(', ');
    }
    return null;
  };

  const countryText = getCountryText();

  return (
    <TouchableOpacity
      ref={ref}
      onPress={handleSelect}
      onLongPress={handleLongPress}
      delayLongPress={500}
      onFocus={handleFocus}
      onBlur={handleBlur}
      hasTVPreferredFocus={hasTVPreferredFocus}
      activeOpacity={1}
      accessible={true}
      accessibilityLabel={`${movie.title}, ${movie.year || ''}, directed by ${director || 'Unknown'}`}
      accessibilityRole="button"
      accessibilityHint="Press to view details, long press for fullscreen"
      testID={testID}
      style={styles.touchable}
      nextFocusUp={nextFocusUp}
      nextFocusLeft={nextFocusLeft}
      nextFocusRight={nextFocusRight}
    >
      <View style={[styles.cardContainer, { width: cardWidth }]}>
        <Animated.View
          style={[
            styles.posterContainer,
            {
              width: cardWidth,
              height: cardHeight,
              transform: [{ scale: scaleAnim }],
              zIndex: isFocused ? 1000 : 1,
              elevation: isFocused ? 10 : 0,
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

          {/* Staff Pick border - red box around poster */}
          {movie.featured && <View style={styles.featuredBorder} />}

          {/* Staff Pick strip - bottom red banner */}
          {movie.featured && (
            <View style={styles.featuredStrip}>
              <Text style={styles.featuredStripText}>STAFF PICK</Text>
            </View>
          )}

          {/* Virtual screening ribbon - shows actual screening name */}
          {movie.categories?.is_virtual_screening && !movie.featured && (
            <View style={styles.screeningRibbon}>
              <Text style={styles.screeningRibbonText} numberOfLines={2}>
                {movie.virtual_screening_info?.screening_name || 'VIRTUAL SCREENING'}
              </Text>
            </View>
          )}

          {/* Focus border */}
          {isFocused && <View style={styles.focusBorder} />}
        </Animated.View>

        {/* Info below poster - always visible */}
        <View style={styles.infoContainer}>
          {(director || countryText) && (
            <Text style={styles.infoText} numberOfLines={1}>
              {director}{director && countryText ? ' • ' : ''}{countryText}
            </Text>
          )}
        </View>
      </View>
    </TouchableOpacity>
  );
});

const styles = StyleSheet.create({
  touchable: {
    overflow: 'visible',
  },
  cardContainer: {
    overflow: 'visible',
  },
  posterContainer: {
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
  screeningRibbon: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: Colors.screeningGold,
    paddingVertical: Spacing.tvos.xs,
    paddingHorizontal: 10,
    borderBottomLeftRadius: 12,
    borderBottomRightRadius: 12,
    alignItems: 'center',
  },
  screeningRibbonText: {
    color: Colors.screeningGoldText,
    fontSize: Typography.tvos.caption,
    fontWeight: '900',
    letterSpacing: 0.3,
    textAlign: 'center',
    textTransform: 'uppercase',
  },
  focusBorder: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: 12,
    borderWidth: FOCUS_STYLES.movieCard.borderWidth,
    borderColor: FOCUS_STYLES.movieCard.borderColor,
  },
  // Info section below poster
  infoContainer: {
    paddingTop: 6,
    paddingHorizontal: 2,
  },
  infoText: {
    color: Colors.primary,
    fontSize: 20,
    textAlign: 'center',
  },
});

export default MovieCard;
