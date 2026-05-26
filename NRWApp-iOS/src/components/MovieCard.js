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
  // Canonical 3-letter map (matches assets/shared-config.js). UK/USA kept; maps
  // both full names and 2-letter ISO codes. Keep in sync with the web map.
  'united states of america': 'USA', 'united states': 'USA', 'usa': 'USA', 'us': 'USA',
  'united kingdom': 'UK', 'great britain': 'UK', 'gb': 'UK', 'uk': 'UK',
  'india': 'IND', 'in': 'IND',
  'canada': 'CAN', 'ca': 'CAN',
  'france': 'FRA', 'fr': 'FRA',
  'mexico': 'MEX', 'mx': 'MEX',
  'australia': 'AUS', 'au': 'AUS',
  'germany': 'GER', 'de': 'GER',
  'italy': 'ITA', 'it': 'ITA',
  'japan': 'JPN', 'jp': 'JPN',
  'south korea': 'KOR', 'kr': 'KOR',
  'belgium': 'BEL', 'be': 'BEL',
  'spain': 'ESP', 'es': 'ESP',
  'indonesia': 'IDN', 'id': 'IDN',
  'brazil': 'BRA', 'br': 'BRA',
  'argentina': 'ARG', 'ar': 'ARG',
  'thailand': 'THA', 'th': 'THA',
  'new zealand': 'NZL', 'nz': 'NZL',
  'austria': 'AUT', 'at': 'AUT',
  'poland': 'POL', 'pl': 'POL',
  'china': 'CHN', 'cn': 'CHN',
  'taiwan': 'TWN', 'tw': 'TWN',
  'denmark': 'DEN', 'dk': 'DEN',
  'netherlands': 'NED', 'nl': 'NED',
  'ireland': 'IRL', 'ie': 'IRL',
  'turkey': 'TUR', 'tr': 'TUR',
  'nigeria': 'NGA', 'ng': 'NGA',
  'philippines': 'PHI', 'ph': 'PHI',
  'finland': 'FIN', 'fi': 'FIN',
  'colombia': 'COL', 'co': 'COL',
  'sweden': 'SWE', 'se': 'SWE',
  'russia': 'RUS', 'ru': 'RUS',
  'hong kong': 'HKG', 'hk': 'HKG',
  'ukraine': 'UKR', 'ua': 'UKR',
  'greece': 'GRE', 'gr': 'GRE',
  'israel': 'ISR', 'il': 'ISR',
  'georgia': 'GEO', 'ge': 'GEO',
  'saudi arabia': 'KSA', 'sa': 'KSA',
  'czech republic': 'CZE', 'cz': 'CZE',
  'cuba': 'CUB', 'cu': 'CUB',
  'switzerland': 'SUI', 'ch': 'SUI',
  'south africa': 'RSA', 'za': 'RSA',
  'venezuela': 'VEN', 've': 'VEN',
  'croatia': 'CRO', 'hr': 'CRO',
  'guatemala': 'GUA', 'gt': 'GUA',
  'kenya': 'KEN', 'ke': 'KEN',
  'iceland': 'ISL', 'is': 'ISL',
  'bulgaria': 'BUL', 'bg': 'BUL',
  'norway': 'NOR', 'no': 'NOR',
  'iraq': 'IRQ', 'iq': 'IRQ',
  'hungary': 'HUN', 'hu': 'HUN',
  'nepal': 'NEP', 'np': 'NEP',
  'slovenia': 'SLO', 'si': 'SLO',
  'cambodia': 'CAM', 'kh': 'CAM',
  'morocco': 'MAR', 'ma': 'MAR',
  'chile': 'CHL', 'cl': 'CHL',
  'singapore': 'SGP', 'sg': 'SGP',
  'armenia': 'ARM', 'am': 'ARM',
  'united arab emirates': 'UAE', 'ae': 'UAE',
  'palestinian territory': 'PLE', 'palestine': 'PLE', 'ps': 'PLE',
  'bosnia and herzegovina': 'BIH', 'ba': 'BIH',
  'unknown': '—',
};

const formatCountry = (country) => {
  if (!country) return null;
  const shortened = COUNTRY_SHORT_NAMES[country.toLowerCase()];
  if (shortened) return shortened;
  // Unmapped: fall back to first 3 letters, uppercased (stay 3-letter).
  return country.replace(/[^A-Za-z]/g, '').slice(0, 3).toUpperCase() || country;
};

// Get streaming service bar badge info
const getStreamingBadge = (movie) => {
  if (movie._is_preorder) return null; // pre-order badge handles this
  const watchLinks = movie.watch_links || {};
  const providers = movie.providers || {};
  let service = null;
  const streaming = watchLinks.streaming;
  if (Array.isArray(streaming) && streaming.length > 0) service = streaming[0].service;
  else if (streaming?.service) service = streaming.service;
  if (!service && providers.streaming?.length > 0) {
    service = providers.streaming.find(p => !p.includes('with Ads')) || providers.streaming[0];
  }
  if (!service) return null;
  // Channel storefronts ("Shudder Amazon Channel", "Britbox Apple TV Channel") are the
  // brand sold through Amazon/Apple/Roku — name the brand, not the storefront.
  service = service.replace(/\s+(Amazon|Apple TV|Roku Premium)\s+Channel\s*$/i, '').trim() || service;
  const s = service.toLowerCase();
  if (s.includes('netflix')) return {name: 'NETFLIX', color: '#E50914'};
  if (s.includes('disney')) return {name: 'DISNEY+', color: '#113CCF'};
  if (s.includes('max') || s.includes('hbo')) return {name: 'MAX', color: '#B537F2'};
  if (s.includes('amazon') || s.includes('prime')) return {name: 'PRIME', color: '#00A8E1'};
  if (s.includes('hulu')) return {name: 'HULU', color: '#1CE783', textColor: '#000'};
  if (s.includes('peacock')) return {name: 'PEACOCK', color: '#000'};
  if (s.includes('mubi')) return {name: 'MUBI', color: '#DA2128'};
  if (s.includes('shudder')) return {name: 'SHUDDER', color: '#8B0000'};
  if (s.includes('apple')) return {name: 'APPLE TV+', color: '#555'};
  if (s.includes('tubi')) return {name: 'TUBI', color: '#FA382F'};
  return {name: service.toUpperCase().slice(0, 8), color: '#444'};
};

export default function MovieCard({movie, onPress, isFeatured = false}) {
  if (!movie) return null;

  const posterUrl = movie.poster_url || movie.poster;
  const director = movie.director || movie.crew?.director;
  const metaText = [director, movie.genres?.[0], movie.country && formatCountry(movie.country)].filter(Boolean).join(' · ');
  const streamingBadge = getStreamingBadge(movie);

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

        {/* Streaming service bar badge (full-width top bar) */}
        {streamingBadge && (
          <View style={[styles.streamingBar, {backgroundColor: streamingBadge.color}]}>
            <Text style={[styles.streamingBarText, streamingBadge.textColor && {color: streamingBadge.textColor}]}>
              {streamingBadge.name}
            </Text>
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

        {/* Pre-order badge — pipeline sets _is_preorder flag */}
        {movie._is_preorder && (
          <View style={styles.preOrderBadge}>
            <Text style={styles.preOrderBadgeText}>PRE-ORDER</Text>
            <Text style={styles.preOrderDateText}>
              {movie.digital_date
                ? new Date(movie.digital_date + 'T12:00:00').toLocaleDateString('en-US', {month: 'short', day: 'numeric'})
                : 'TBD'}
            </Text>
          </View>
        )}

        {/* Virtual screening top banner */}
        {movie.categories?.is_virtual_screening && !isFeatured && !movie.featured && (
          <View style={styles.screeningTopBanner}>
            <Text style={styles.screeningTopBannerText}>VIRTUAL SCREENING</Text>
          </View>
        )}

        {/* Virtual screening festival name ribbon */}
        {movie.categories?.is_virtual_screening && !isFeatured && !movie.featured && movie.virtual_screening_info?.screening_name && (
          <View style={styles.screeningRibbon}>
            <Text style={styles.screeningRibbonText} numberOfLines={2}>
              {movie.virtual_screening_info.screening_name}
            </Text>
          </View>
        )}

        {/* Score badges (RT + MC + IMDb) */}
        {(movie.rt_score || (movie.metacritic_score && movie.metacritic_score !== "0") || movie.imdb_rating) && (
          <View style={styles.scoreBadgeRow}>
            {movie.rt_score && (
              <View style={styles.scoreBadge}>
                <View style={styles.scoreBadgeContent}>
                  <Image source={require('../assets/logos/rt.png')} style={styles.scoreBadgeLogo} />
                  <Text style={styles.rtScoreText}>{movie.rt_score}</Text>
                </View>
              </View>
            )}
            {movie.metacritic_score && movie.metacritic_score !== "0" && (
              <View style={styles.scoreBadge}>
                <View style={styles.scoreBadgeContent}>
                  <Image source={require('../assets/logos/metacritic.png')} style={[styles.scoreBadgeLogo, { tintColor: '#7ddf64' }]} />
                  <Text style={styles.mcScoreText}>{movie.metacritic_score}</Text>
                </View>
              </View>
            )}
            {movie.imdb_rating && (
              <View style={styles.scoreBadge}>
                <View style={styles.scoreBadgeContent}>
                  <Image source={require('../assets/logos/imdb.png')} style={styles.scoreBadgeLogo} />
                  <Text style={styles.imdbScoreText}>{movie.imdb_rating}</Text>
                </View>
              </View>
            )}
          </View>
        )}
      </View>

      <View style={styles.info}>
        <Text style={styles.title} numberOfLines={2}>
          {movie.display_title || movie.title}
        </Text>
        {metaText !== '' && (
          <Text style={styles.director} numberOfLines={1}>
            {metaText}
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
  streamingBar: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    paddingVertical: 5,
    alignItems: 'center',
    zIndex: 5,
  },
  streamingBarText: {
    color: '#fff',
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 0.8,
  },
  preOrderBadge: {
    position: 'absolute',
    top: 8,
    right: 8,
    backgroundColor: '#7c3aed',
    paddingHorizontal: 6,
    paddingVertical: 3,
    borderRadius: 4,
    alignItems: 'center',
  },
  preOrderBadgeText: {
    color: '#fff',
    fontSize: 8,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  preOrderDateText: {
    color: '#fff',
    fontSize: 11,
    fontWeight: '600',
  },
  screeningTopBanner: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    backgroundColor: 'rgba(255, 215, 0, 0.92)',
    paddingVertical: 3,
    paddingHorizontal: 6,
    alignItems: 'center',
  },
  screeningTopBannerText: {
    color: '#000',
    fontSize: 8,
    fontWeight: '800',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
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
    paddingHorizontal: 6,
    paddingVertical: 3,
    borderRadius: 6,
    backgroundColor: 'rgba(0,0,0,0.7)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.1)',
  },
  scoreBadgeContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
  },
  scoreBadgeLogo: {
    width: 16,
    height: 11,
    resizeMode: 'contain',
  },
  rtScoreText: {
    color: '#ff6b6b',
    fontSize: 9,
    fontWeight: '800',
  },
  mcScoreText: {
    color: '#7ddf64',
    fontSize: 9,
    fontWeight: '800',
  },
  imdbScoreText: {
    color: '#f5c518',
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
