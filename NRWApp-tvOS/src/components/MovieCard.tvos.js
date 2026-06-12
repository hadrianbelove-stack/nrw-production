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
import { FOCUS_STYLES } from '../utils/focusManager.tvos';

// Decode HTML entities (e.g. &#x27; → ')
const decodeHtml = (str) => str.replace(/&#x27;/g, "'").replace(/&amp;/g, '&').replace(/&quot;/g, '"');

// 3-letter Olympic country codes (UK stays UK)
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
  nextFocusDown,
  nextFocusLeft,
  nextFocusRight,
}, ref) => {
  const [isFocused, setIsFocused] = useState(false);
  const [imageError, setImageError] = useState(false);
  const scaleAnim = useRef(new Animated.Value(1)).current;

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

    Animated.timing(scaleAnim, {
      toValue: FOCUS_STYLES.movieCard.scale,
      duration: 150,
      useNativeDriver: true,
    }).start();

    if (onFocus) {
      onFocus(movie);
    }
  }, [movie, onFocus, scaleAnim]);

  // Handle blur event
  const handleBlur = useCallback(() => {
    setIsFocused(false);

    Animated.timing(scaleAnim, {
      toValue: 1,
      duration: 150,
      useNativeDriver: true,
    }).start();

    if (onBlur) {
      onBlur(movie);
    }
  }, [movie, onBlur, scaleAnim]);

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

  // Get poster URL
  const posterUrl = movie.poster_url || movie.posterUrl || movie.poster;
  const hasPoster = !!posterUrl;

  // Get streaming service badge
  const getStreamingBadge = () => {
    const watchLinks = movie.watch_links || {};
    const providers = movie.providers || {};

    // Pre-order: pipeline sets _is_preorder flag during enrichment
    if (movie._is_preorder) {
      const poDate = movie.digital_date
        ? new Date(movie.digital_date + 'T12:00:00').toLocaleDateString('en-US', {month: 'short', day: 'numeric'})
        : 'TBD';
      return { name: 'PRE-ORDER', subtext: poDate, color: '#7c3aed' };
    }

    // watch_links.streaming is an array of {service, link} (legacy: a single object).
    // Prefer a non-"with Ads" entry, then fall back to providers.streaming (plain strings).
    let service;
    const wlStreaming = watchLinks.streaming;
    if (Array.isArray(wlStreaming) && wlStreaming.length > 0) {
      const pick = wlStreaming.find(s => !(s?.service || '').includes('with Ads')) || wlStreaming[0];
      service = pick?.service;
    } else if (wlStreaming && typeof wlStreaming === 'object') {
      service = wlStreaming.service; // legacy single-object form
    }
    if (!service && providers.streaming?.length > 0) {
      service = providers.streaming.find(p => !p.includes('with Ads')) || providers.streaming[0];
    }
    if (!service) return null;
    // Channel storefronts ("Shudder Amazon Channel", "Britbox Apple TV Channel") are the
    // brand sold through Amazon/Apple/Roku — name the brand, not the storefront.
    service = service.replace(/\s+(Amazon|Apple TV|Roku Premium)\s+Channel\s*$/i, '').trim() || service;

    const s = service.toLowerCase();
    const frame = (name, color) => ({ name, color, isFrame: true });
    if (s.includes('netflix')) return frame('NETFLIX', '#E50914');
    if (s.includes('disney')) return frame('DISNEY+', '#113CCF');
    if (s.includes('max') || s.includes('hbo')) return frame('MAX', Colors.maxPurple);
    if (s.includes('amazon') || s.includes('prime')) return frame('PRIME', '#00A8E1');
    if (s.includes('hulu')) return frame('HULU', '#1CE783');
    if (s.includes('peacock')) return frame('PEACOCK', '#000000');
    if (s.includes('mubi')) return frame('MUBI', '#DA2128');
    if (s.includes('shudder')) return frame('SHUDDER', '#E31B23');
    if (s.includes('criterion')) return frame('CRITERION', '#000000');
    if (s.includes('paramount')) return frame('PARAMOUNT+', '#0064FF');
    if (s.includes('apple')) return frame('APPLE TV+', '#000000');
    return frame(service.toUpperCase().slice(0, 8), '#666666');
  };

  const isFest = !!movie.filters?.is_virtual_screening;
  const streamingBadge = isFest ? null : getStreamingBadge();
  const isStaffPick = !!(movie.filters?.is_staff_pick || movie.featured);
  // Light-background services need black text on the frame header
  const frameTextColor = streamingBadge?.name && ['HULU', 'PRIME'].includes(streamingBadge.name) ? '#000' : '#fff';

  // Get director - can be in crew.director or movie.director
  const director = movie.crew?.director || movie.director;

  // Get country - can be country (string) or countries (array)
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
  const genre = movie.genres?.[0];
  const metaText = [director, genre, countryText].filter(Boolean).join(' • ');

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
      nextFocusDown={nextFocusDown}
      nextFocusLeft={nextFocusLeft}
      nextFocusRight={nextFocusRight}
    >
      <View style={[styles.cardContainer, { width: cardWidth }]}>
        {/* Scale + shadow layer — no overflow clipping so shadow glows outside */}
        <Animated.View
          style={[
            styles.scaleLayer,
            {
              width: cardWidth,
              height: cardHeight,
              transform: [{ scale: scaleAnim }],
              zIndex: isFocused ? 1000 : 1,
              elevation: isFocused ? 10 : 0,
            },
            isStaffPick && styles.scaleLayerStaffPick,
            isFocused && styles.scaleLayerFocused,
          ]}
        >
          {/* Clip container — overflow:hidden keeps image and overlays inside rounded corners */}
          {isFest ? (
            /* === Festival Frame — dark navy, gold text, framed poster === */
            <View style={[styles.posterContainer, { width: cardWidth, height: cardHeight, backgroundColor: '#0d1117', justifyContent: 'flex-start' }]}>
              {/* Dark header: festival name in gold, abbreviated */}
              <View style={[styles.streamingFrameHeader, styles.festFrameHeader]}>
                <Text style={styles.festFrameName} numberOfLines={2}>{decodeHtml((movie.virtual_screening_info?.screening_name || 'FESTIVAL').replace(/\b(19|20)\d{2}\b/g, '').replace(/\bInternational\b/gi, 'Intl.').replace(/\bFilm Festival\b/gi, 'Film Fest').replace(/\s+/g, ' ').trim())}</Text>
              </View>
              {/* Poster framed inside with padding — dark navy shows as border on sides/bottom */}
              {hasPoster && !imageError ? (
                <View style={styles.festPosterWrap}>
                  <Image source={{ uri: posterUrl }} style={styles.festPosterImg} resizeMode="contain" onError={() => setImageError(true)} />
                </View>
              ) : (
                <View style={[styles.posterPlaceholder, { flex: 1, height: undefined, borderRadius: 0 }]}>
                  <Text style={styles.placeholderText} numberOfLines={3}>{movie.display_title || movie.title}</Text>
                </View>
              )}
              {(movie.filters?.is_restoration || movie.reissue_label) && (
                <View style={[styles.restorationCardBadge, { top: 60 }]}>
                  <Text style={styles.restorationCardBadgeText}>{movie.reissue_label?.toUpperCase() || 'RESTORED'}</Text>
                </View>
              )}
              {isStaffPick && <View style={styles.featuredStrip}><Text style={styles.featuredStripText}>★ HIGHLIGHT</Text></View>}
              <View style={[styles.screeningBorder, { borderColor: 'rgba(255,215,0,0.55)' }]} />
            </View>
          ) : streamingBadge?.isFrame ? (
            /* === Gallery Label Frame (service-colored card) === */
            <View style={[styles.posterContainer, { width: cardWidth, height: cardHeight, backgroundColor: streamingBadge.color, justifyContent: 'flex-start' }]}>
              {/* 52px header strip: SERVICE NAME + NOW STREAMING */}
              <View style={styles.streamingFrameHeader}>
                <Text style={[styles.streamingFrameName, { color: frameTextColor }]}>{streamingBadge.name}</Text>
                <Text style={[styles.streamingFrameSuper, { color: frameTextColor }]}>NOW STREAMING</Text>
              </View>
              {/* Poster fills remaining space */}
              {hasPoster && !imageError ? (
                <Image source={{ uri: posterUrl }} style={styles.streamingFramePoster} resizeMode="cover" onError={() => setImageError(true)} />
              ) : (
                <View style={[styles.posterPlaceholder, { flex: 1, height: undefined, borderRadius: 0 }]}>
                  <Text style={styles.placeholderText} numberOfLines={3}>{movie.display_title || movie.title}</Text>
                </View>
              )}
              {/* Overlays still apply */}
              {(movie.filters?.is_restoration || movie.reissue_label) && (
                <View style={[styles.restorationCardBadge, { top: 60 }]}>
                  <Text style={styles.restorationCardBadgeText}>{movie.reissue_label?.toUpperCase() || 'RESTORED'}</Text>
                </View>
              )}
              {isStaffPick && <View style={styles.featuredStrip}><Text style={styles.featuredStripText}>★ HIGHLIGHT</Text></View>}
              {movie.filters?.is_virtual_screening && !isStaffPick && movie.virtual_screening_info?.screening_name && (
                <View style={styles.screeningRibbon}><Text style={styles.screeningRibbonText} numberOfLines={2}>{decodeHtml(movie.virtual_screening_info.screening_name)}</Text></View>
              )}
              {movie.filters?.is_virtual_screening && !isStaffPick && <View style={styles.screeningBorder} />}
              {/* Score badges overlay */}
              {(movie.rt_score || movie.imdb_rating) && (
                <View style={styles.cardScoreOverlay}>
                  {movie.rt_score && <View style={[styles.cardScoreBadge, styles.cardScoreBadgeRt]}><Text style={styles.cardScoreBadgeText}>{movie.rt_score}</Text></View>}
                  {movie.imdb_rating && <View style={[styles.cardScoreBadge, styles.cardScoreBadgeImdb]}><Text style={[styles.cardScoreBadgeText, { color: '#000' }]}>{parseFloat(movie.imdb_rating).toFixed(1)}</Text></View>}
                </View>
              )}
            </View>
          ) : (
            /* === Standard poster card === */
            <View style={[styles.posterContainer, { width: cardWidth, height: cardHeight }]}>
              {hasPoster && !imageError ? (
                <Image source={{ uri: posterUrl }} style={styles.poster} resizeMode="cover" onError={() => setImageError(true)} />
              ) : (
                <View style={styles.posterPlaceholder}>
                  <Text style={styles.placeholderText} numberOfLines={3}>{movie.display_title || movie.title}</Text>
                </View>
              )}
              {/* Pre-order badge (streamingBadge without isFrame) */}
              {streamingBadge && (
                <View style={[styles.streamingBadge, { backgroundColor: streamingBadge.color }, streamingBadge.subtext && { flexDirection: 'row', gap: 8 }]}>
                  <Text style={styles.streamingBadgeText}>{streamingBadge.name}</Text>
                  <Text style={styles.streamingBadgeSubtext}>{streamingBadge.subtext || 'NOW STREAMING'}</Text>
                </View>
              )}
              {(movie.filters?.is_restoration || movie.reissue_label) && (
                <View style={styles.restorationCardBadge}>
                  <Text style={styles.restorationCardBadgeText}>{movie.reissue_label?.toUpperCase() || 'RESTORED'}</Text>
                </View>
              )}
              {isStaffPick && <View style={styles.featuredStrip}><Text style={styles.featuredStripText}>★ HIGHLIGHT</Text></View>}
              {movie.filters?.is_virtual_screening && !isStaffPick && movie.virtual_screening_info?.screening_name && (
                <View style={styles.screeningRibbon}><Text style={styles.screeningRibbonText} numberOfLines={2}>{decodeHtml(movie.virtual_screening_info.screening_name)}</Text></View>
              )}
              {movie.filters?.is_virtual_screening && !isStaffPick && <View style={styles.screeningBorder} />}
              {/* Score badges overlay — bottom-left, matches desktop card */}
              {(movie.rt_score || movie.imdb_rating) && (
                <View style={styles.cardScoreOverlay}>
                  {movie.rt_score && <View style={[styles.cardScoreBadge, styles.cardScoreBadgeRt]}><Text style={styles.cardScoreBadgeText}>{movie.rt_score}</Text></View>}
                  {movie.imdb_rating && <View style={[styles.cardScoreBadge, styles.cardScoreBadgeImdb]}><Text style={[styles.cardScoreBadgeText, { color: '#000' }]}>{parseFloat(movie.imdb_rating).toFixed(1)}</Text></View>}
                </View>
              )}
            </View>
          )}

          {/* Staff pick permanent border overlay (outside clip container so it glows) */}
          {isStaffPick && !isFocused && <View style={styles.staffPickBorder} />}
          {/* Double-border focus ring: black halo behind teal ring */}
          {isFocused && <View style={styles.focusBorderOuter} />}
          {isFocused && <View style={styles.focusBorder} />}
        </Animated.View>

        {/* Info below poster - always visible */}
        <View style={styles.infoContainer}>
          {metaText !== '' && (
            <Text style={styles.infoText} numberOfLines={1}>
              {metaText}
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
  scaleLayer: {
    borderRadius: 12,
    position: 'relative',
  },
  scaleLayerFocused: {
    shadowColor: FOCUS_STYLES.movieCard.shadowColor,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: FOCUS_STYLES.movieCard.shadowOpacity,
    shadowRadius: FOCUS_STYLES.movieCard.shadowRadius,
  },
  scaleLayerStaffPick: {
    shadowColor: Colors.staffPick,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.55,
    shadowRadius: 14,
  },
  posterContainer: {
    borderRadius: 12,
    overflow: 'hidden',
    backgroundColor: Colors.backgroundSecondary,
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
  restorationCardBadge: {
    position: 'absolute',
    top: 8,
    left: 8,
    backgroundColor: Colors.restoration,
    paddingHorizontal: 6,
    paddingVertical: 3,
    borderRadius: 8,
    zIndex: 6,
  },
  restorationCardBadgeText: {
    color: Colors.restorationText,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  streamingBadge: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    paddingVertical: Spacing.tvos.xs,
    alignItems: 'center',
    justifyContent: 'center',
    borderTopLeftRadius: 12,
    borderTopRightRadius: 12,
  },
  streamingBadgeText: {
    color: '#FFFFFF',
    fontSize: Typography.tvos.caption - 4,
    fontWeight: '800',
    letterSpacing: 0.8,
  },
  streamingBadgeSubtext: {
    color: '#FFFFFF',
    fontSize: Typography.tvos.caption - 2,
    fontWeight: '600',
  },
  featuredStrip: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: Colors.staffPick,
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
    paddingVertical: 5,
    paddingHorizontal: 8,
    borderBottomLeftRadius: 12,
    borderBottomRightRadius: 12,
    alignItems: 'center',
  },
  screeningRibbonText: {
    color: Colors.screeningGoldText,
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 0.5,
    textAlign: 'center',
    textTransform: 'uppercase',
  },
  screeningBorder: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: 12,
    borderWidth: 2,
    borderColor: '#FFD700',
  },
  focusBorderOuter: {
    position: 'absolute',
    top: -4,
    left: -4,
    right: -4,
    bottom: -4,
    borderRadius: 16,
    borderWidth: 4,
    borderColor: '#000',
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
    fontWeight: '700',
    textAlign: 'center',
  },
  staffPickBorder: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: 12,
    borderWidth: 2,
    borderColor: Colors.staffPick,
  },
  streamingFrameHeader: {
    height: 52,
    width: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 8,
  },
  streamingFrameName: {
    fontSize: 15,
    fontWeight: '800',
    letterSpacing: 1.4,
    textTransform: 'uppercase',
    lineHeight: 17,
  },
  streamingFrameSuper: {
    fontSize: 8,
    fontWeight: '500',
    letterSpacing: 2,
    textTransform: 'uppercase',
    opacity: 0.75,
    lineHeight: 10,
    marginTop: 3,
  },
  streamingFramePoster: {
    flex: 1,
    width: '100%',
  },
  festFrameHeader: {
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,215,0,0.25)',
  },
  festFrameName: {
    fontSize: 13,
    fontWeight: '800',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
    color: '#FFD700',
    lineHeight: 15,
    textAlign: 'center',
  },
  festPosterWrap: {
    flex: 1,
    paddingHorizontal: 12,
    paddingBottom: 12,
  },
  festPosterImg: {
    flex: 1,
  },
  cardScoreOverlay: {
    position: 'absolute',
    bottom: 8,
    left: 8,
    flexDirection: 'row',
    gap: 4,
  },
  cardScoreBadge: {
    paddingHorizontal: 6,
    paddingVertical: 3,
    borderRadius: 4,
  },
  cardScoreBadgeRt: {
    backgroundColor: 'rgba(250,50,50,0.85)',
  },
  cardScoreBadgeImdb: {
    backgroundColor: 'rgba(245,197,24,0.9)',
  },
  cardScoreBadgeText: {
    fontSize: 14,
    fontWeight: '800',
    color: '#fff',
  },
});

export default MovieCard;
