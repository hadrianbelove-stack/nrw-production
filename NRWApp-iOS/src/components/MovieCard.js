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

        {/* Pre-order badge */}
        {(movie._is_preorder ||
          (movie.pre_order_links && Object.keys(movie.pre_order_links).length > 0 &&
           movie.digital_date > new Date().toISOString().split('T')[0])) && (
          <View style={styles.preOrderBadge}>
            <Text style={styles.preOrderBadgeText}>PRE-ORDER</Text>
          </View>
        )}

        {/* Virtual screening ribbon - shows actual screening name */}
        {movie.categories?.is_virtual_screening && (
          <View style={styles.screeningRibbon}>
            <Text style={styles.screeningRibbonText} numberOfLines={2}>
              {movie.virtual_screening_info?.screening_name || 'VIRTUAL SCREENING'}
            </Text>
          </View>
        )}

        {/* Score badges (RT + IMDb) */}
        {(movie.rt_score || movie.imdb_rating) && (
          <View style={styles.scoreBadgeRow}>
            {movie.rt_score && (
              <View style={[styles.scoreBadge, styles.rtScoreBadge]}>
                <Text style={styles.rtScoreText}>RT {movie.rt_score}</Text>
              </View>
            )}
            {movie.imdb_rating && (
              <View style={[styles.scoreBadge, styles.imdbScoreBadge]}>
                <Text style={styles.imdbScoreText}>{movie.imdb_rating}</Text>
              </View>
            )}
          </View>
        )}
      </View>

      <View style={styles.info}>
        <Text style={styles.title} numberOfLines={2}>
          {movie.display_title || movie.title}
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
  preOrderBadge: {
    position: 'absolute',
    top: 8,
    right: 8,
    backgroundColor: '#7c3aed',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  preOrderBadgeText: {
    color: '#fff',
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  screeningRibbon: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: '#FFD700',
    paddingHorizontal: 8,
    paddingVertical: 5,
  },
  screeningRibbonText: {
    color: '#000',
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.3,
    lineHeight: 12.5,
    textAlign: 'center',
    textTransform: 'uppercase',
  },
  scoreBadgeRow: {
    position: 'absolute',
    bottom: 8,
    left: 8,
    flexDirection: 'row',
    gap: 4,
  },
  scoreBadge: {
    paddingHorizontal: 5,
    paddingVertical: 2,
    borderRadius: 3,
  },
  rtScoreBadge: {
    backgroundColor: 'rgba(250, 50, 50, 0.85)',
  },
  rtScoreText: {
    color: '#fff',
    fontSize: 9,
    fontWeight: '800',
  },
  imdbScoreBadge: {
    backgroundColor: 'rgba(245, 197, 24, 0.9)',
  },
  imdbScoreText: {
    color: '#000',
    fontSize: 9,
    fontWeight: '800',
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
