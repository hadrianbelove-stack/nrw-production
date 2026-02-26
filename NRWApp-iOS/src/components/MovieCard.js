/**
 * New Release Wall - Movie Card Component
 * Displays movie poster with title and metadata
 */

import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Image,
} from 'react-native';
import {Colors, Typography, Spacing, Dimensions} from '../constants/colors';

const COUNTRY_SHORT_NAMES = {
  'united states of america': 'USA', 'united states': 'USA', 'usa': 'USA',
  'united kingdom': 'UK', 'great britain': 'UK',
  'south korea': 'S. Korea', 'south africa': 'S. Africa',
  'new zealand': 'N. Zealand', 'bosnia and herzegovina': 'Bosnia',
  'saudi arabia': 'S. Arabia',
};

const formatCountry = (country) => {
  if (!country) return null;
  const shortened = COUNTRY_SHORT_NAMES[country.toLowerCase()];
  if (shortened) return shortened;
  if (country !== country[0].toUpperCase() + country.slice(1).toLowerCase()) {
    return country[0].toUpperCase() + country.slice(1).toLowerCase();
  }
  return country;
};

export default function MovieCard({movie, onPress, isFeatured = false}) {
  if (!movie) return null;

  const posterUrl = movie.poster_url || movie.poster;
  const director = movie.director || movie.crew?.director;

  return (
    <TouchableOpacity
      style={styles.container}
      onPress={() => onPress?.(movie)}
      activeOpacity={0.8}>
      <View style={styles.posterContainer}>
        {posterUrl ? (
          <Image
            source={{uri: posterUrl}}
            style={styles.poster}
            resizeMode="cover"
          />
        ) : (
          <View style={styles.posterPlaceholder}>
            <Text style={styles.placeholderText}>No Poster</Text>
          </View>
        )}

        {/* Featured badge */}
        {(isFeatured || movie.featured || movie.categories?.is_staff_pick) && (
          <View style={styles.featuredBadge}>
            <Text style={styles.featuredText}>★ PICK</Text>
          </View>
        )}

        {/* Restoration badge */}
        {movie.categories?.is_restoration && (
          <View style={styles.restorationBadge}>
            <Text style={styles.restorationText}>RESTORED</Text>
          </View>
        )}

        {/* RT Score badge */}
        {movie.rt_score && (
          <View
            style={[
              styles.rtBadge,
              {
                backgroundColor:
                  parseInt(movie.rt_score, 10) >= 60 ? Colors.green : Colors.red,
              },
            ]}>
            <Text style={styles.rtText}>{movie.rt_score}</Text>
          </View>
        )}
      </View>

      <View style={styles.info}>
        <Text style={styles.title} numberOfLines={2}>
          {movie.title}
        </Text>
        {director && (
          <Text style={styles.director} numberOfLines={1}>
            {director}
          </Text>
        )}
        {movie.country && (
          <Text style={styles.country} numberOfLines={1}>
            {formatCountry(movie.country)}
          </Text>
        )}
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: {
    width: Dimensions.cardWidth,
    marginBottom: Spacing.md,
  },
  posterContainer: {
    width: Dimensions.cardWidth,
    height: Dimensions.cardHeight,
    borderRadius: 8,
    overflow: 'hidden',
    backgroundColor: Colors.backgroundSecondary,
  },
  poster: {
    width: '100%',
    height: '100%',
  },
  posterPlaceholder: {
    width: '100%',
    height: '100%',
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: Colors.backgroundTertiary,
  },
  placeholderText: {
    color: Colors.textMuted,
    fontSize: Typography.caption,
  },
  featuredBadge: {
    position: 'absolute',
    top: 8,
    left: 8,
    backgroundColor: Colors.featuredBadge,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  featuredText: {
    color: Colors.featuredBadgeText,
    fontSize: 10,
    fontWeight: '700',
  },
  restorationBadge: {
    position: 'absolute',
    bottom: 8,
    left: 8,
    backgroundColor: Colors.restoration,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  restorationText: {
    color: Colors.restorationText,
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  rtBadge: {
    position: 'absolute',
    top: 8,
    right: 8,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  rtText: {
    color: Colors.textPrimary,
    fontSize: 11,
    fontWeight: '700',
  },
  info: {
    paddingTop: Spacing.sm,
  },
  title: {
    color: Colors.textPrimary,
    fontSize: Typography.caption + 2,
    fontWeight: '600',
    lineHeight: 18,
  },
  director: {
    color: Colors.textSecondary,
    fontSize: Typography.caption,
    marginTop: 2,
  },
  country: {
    color: Colors.textMuted,
    fontSize: Typography.caption - 1,
    marginTop: 1,
  },
});
