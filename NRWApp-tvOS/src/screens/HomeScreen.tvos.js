/**
 * New Release Wall - tvOS Home Screen
 * Vertical scrolling grid layout matching web design
 */

import React, { useState, useCallback, useRef, useEffect, useMemo, forwardRef } from 'react';
import {
  View,
  Text,
  TextInput,
  FlatList,
  StyleSheet,
  ActivityIndicator,
  TouchableOpacity,
  Linking,
  Animated,
  Alert,
  findNodeHandle,
  InteractionManager,
  TVFocusGuideView,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { useHomeScreen } from './useHomeScreen';
import MovieCard from '../components/MovieCard.tvos';
import FullscreenPosterModal from '../components/FullscreenPosterModal.tvos';
import { Colors, Typography, Spacing, Dimensions } from '../constants/colors';
import { useTVEventHandler, TV_EVENTS } from '../utils/focusManager.tvos';
import {
  trackScreenView,
  trackMovieFocus,
  trackMovieSelect,
  trackFilterChange,
} from '../services/analytics.tvos';
import { setSharedMovieList } from './sharedMovieList';

// Filter options - matches web categories
const FILTERS = [
  { id: 'staff-picks', label: 'Picks' },
  { id: 'indie', label: 'Indie' },
  { id: 'horror', label: 'Horror' },
  { id: 'action', label: 'Action' },
  { id: 'comedy', label: 'Comedy' },
  { id: 'family', label: 'Family' },
  { id: 'foreign', label: 'Foreign' },
  { id: 'documentary', label: 'Docs' },
  { id: 'restorations', label: 'Reissues' },
];

// Filter descriptions — shown below filter row when a single filter is active (matches web)
const FILTER_DESCRIPTIONS = {
  'staff-picks': { title: 'Picks', text: "The ones we're vouching for. Out of everything on the wall, these are the movies we think are genuinely worth your time. Not a popularity contest, just honest recommendations." },
  'indie':       { title: 'Indie', text: "The smaller films, the independents, the ones without a billboard campaign. These movies flew under the radar theatrically but are worth knowing about now that they're available to stream at home." },
  'horror':      { title: 'Horror', text: "The stuff that goes bump. Horror films now streaming — from slow-burn dread to full-on splatter." },
  'action':      { title: 'Action', text: "High-octane, kinetic filmmaking. Action movies now available to watch at home." },
  'comedy':      { title: 'Comedy', text: "Films that are actually funny. Comedies — broad and subtle — now streaming." },
  'family':      { title: 'Family', text: "Films for all ages. Family movies now available to watch at home." },
  'foreign':     { title: 'Foreign', text: "Non-English language films from around the world. Some are massive in their home countries, some are intimate art-house pieces. The only thing they have in common is subtitles and the fact that they're streaming now." },
  'documentary': { title: 'Documentary', text: "Non-fiction filmmaking. Documentaries covering real stories, real people, and real events — now available to stream at home." },
  'restorations':{ title: 'Reissues', text: "Classic and catalog titles with new digital life. These are films that have been restored, remastered, or newly reissued on streaming platforms. Old movies, fresh transfers." },
};

// Filter Button Component - forwardRef to allow focus navigation from grid
const FilterButton = forwardRef(({ filter, isActive, onPress, onFocus, nextFocusDown, nextFocusUp, style }, ref) => {
  const [isFocused, setIsFocused] = useState(false);
  const scaleAnim = useRef(new Animated.Value(1)).current;

  const handleFocus = useCallback(() => {
    setIsFocused(true);
    onFocus?.();
    Animated.timing(scaleAnim, {
      toValue: 1.1,
      duration: 150,
      useNativeDriver: true,
    }).start();
  }, [scaleAnim, onFocus]);

  const handleBlur = useCallback(() => {
    setIsFocused(false);
    Animated.timing(scaleAnim, {
      toValue: 1,
      duration: 150,
      useNativeDriver: true,
    }).start();
  }, [scaleAnim]);

  return (
    <TouchableOpacity
      ref={ref}
      style={style}
      onPress={onPress}
      onFocus={handleFocus}
      onBlur={handleBlur}
      activeOpacity={1}
      accessible={true}
      accessibilityLabel={`Filter by ${filter.label}`}
      accessibilityRole="button"
      accessibilityState={{ selected: isActive }}
      nextFocusDown={nextFocusDown}
      nextFocusUp={nextFocusUp}
    >
      <Animated.View
        style={[
          styles.filterButton,
          isActive && styles.filterButtonActive,
          isFocused && styles.filterButtonFocused,
          { transform: [{ scale: scaleAnim }] },
        ]}
      >
        <Text
          style={[
            styles.filterButtonText,
            isActive && styles.filterButtonTextActive,
          ]}
        >
          {filter.label}
        </Text>
      </Animated.View>
    </TouchableOpacity>
  );
});

// Slop Toggle Button - TV remote focusable
// iOS-style track+thumb toggle — matches the website design
const MetaToggle = forwardRef(({ isActive, label, accessibilityLabel, onPress, nextFocusUp, nextFocusDown }, ref) => {
  const [isFocused, setIsFocused] = useState(false);
  const thumbAnim = useRef(new Animated.Value(isActive ? 1 : 0)).current;
  const scaleAnim = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    Animated.timing(thumbAnim, {
      toValue: isActive ? 1 : 0,
      duration: 220,
      useNativeDriver: true,
    }).start();
  }, [isActive, thumbAnim]);

  const handleFocus = useCallback(() => {
    setIsFocused(true);
    Animated.timing(scaleAnim, { toValue: 1.08, duration: 150, useNativeDriver: true }).start();
  }, [scaleAnim]);

  const handleBlur = useCallback(() => {
    setIsFocused(false);
    Animated.timing(scaleAnim, { toValue: 1, duration: 150, useNativeDriver: true }).start();
  }, [scaleAnim]);

  const thumbTranslate = thumbAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0, 42],
  });

  return (
    <TouchableOpacity
      ref={ref}
      onPress={onPress}
      onFocus={handleFocus}
      onBlur={handleBlur}
      activeOpacity={1}
      accessible={true}
      accessibilityLabel={accessibilityLabel}
      accessibilityRole="button"
      nextFocusUp={nextFocusUp}
      nextFocusDown={nextFocusDown}
    >
      <Animated.View style={[styles.metaToggleWrap, { transform: [{ scale: scaleAnim }] }]}>
        <View style={[
          styles.metaToggleTrack,
          isActive && styles.metaToggleTrackActive,
          isFocused && styles.metaToggleTrackFocused,
        ]}>
          <Animated.View style={[styles.metaToggleThumb, { transform: [{ translateX: thumbTranslate }] }]} />
        </View>
        <Text style={[styles.metaToggleLabel, isActive && styles.metaToggleLabelActive]}>
          {label}
        </Text>
      </Animated.View>
    </TouchableOpacity>
  );
});

// 3-state Slop Toggle — cycles: SLOP FREE → ALL → SLOP ONLY (matches desktop 3-state)
const SlopToggle = forwardRef(({ slopMode, onPress, nextFocusUp, nextFocusLeft, nextFocusDown }, ref) => {
  const [isFocused, setIsFocused] = useState(false);
  const scaleAnim = useRef(new Animated.Value(1)).current;
  const thumbAnim = useRef(new Animated.Value(slopMode === 'free' ? 0 : slopMode === 'all' ? 1 : 2)).current;

  useEffect(() => {
    const target = slopMode === 'free' ? 0 : slopMode === 'all' ? 1 : 2;
    Animated.timing(thumbAnim, { toValue: target, duration: 220, useNativeDriver: true }).start();
  }, [slopMode, thumbAnim]);

  const handleFocus = useCallback(() => {
    setIsFocused(true);
    Animated.timing(scaleAnim, { toValue: 1.08, duration: 150, useNativeDriver: true }).start();
  }, [scaleAnim]);

  const handleBlur = useCallback(() => {
    setIsFocused(false);
    Animated.timing(scaleAnim, { toValue: 1, duration: 150, useNativeDriver: true }).start();
  }, [scaleAnim]);

  // Thumb travels across 108px track with 20px thumb, 4px padding each side
  const thumbTranslate = thumbAnim.interpolate({
    inputRange: [0, 1, 2],
    outputRange: [0, 40, 80],
  });

  const LABELS = { free: 'SLOP FREE', all: 'ALL', only: 'SLOP ONLY' };
  const labelColor = slopMode === 'only' ? '#ff9500' : slopMode === 'free' ? '#00d4aa' : 'rgba(0,212,170,0.45)';
  const trackStyle = slopMode === 'free'
    ? { backgroundColor: '#00d4aa', borderColor: '#00d4aa' }
    : slopMode === 'only'
    ? { backgroundColor: '#ff9500', borderColor: '#ff9500' }
    : { backgroundColor: 'rgba(0,212,170,0.1)', borderColor: '#00d4aa' };
  const thumbColor = slopMode === 'all' ? '#00d4aa' : '#ffffff';

  return (
    <TouchableOpacity
      ref={ref}
      onPress={onPress}
      onFocus={handleFocus}
      onBlur={handleBlur}
      activeOpacity={1}
      accessible={true}
      accessibilityLabel={`Slop filter: ${LABELS[slopMode]}`}
      accessibilityRole="button"
      nextFocusUp={nextFocusUp}
      nextFocusLeft={nextFocusLeft}
      nextFocusDown={nextFocusDown}
    >
      <Animated.View style={[styles.metaToggleWrap, { transform: [{ scale: scaleAnim }] }]}>
        <View style={[styles.slopToggleTrack, trackStyle, isFocused && styles.metaToggleTrackFocused]}>
          <Animated.View style={[styles.slopToggleThumb, { backgroundColor: thumbColor, transform: [{ translateX: thumbTranslate }] }]} />
        </View>
        <Text style={[styles.metaToggleLabel, { color: labelColor }]}>{LABELS[slopMode]}</Text>
      </Animated.View>
    </TouchableOpacity>
  );
});

// Date Card Component - non-focusable visual divider
const DateCard = ({ dateParts, isBootstrap }) => {
  const isPreOrder = dateParts.dayName === 'PRE-' || dateParts.dayName === 'PRE-ORDER';
  const isFest = dateParts.dayName === 'FEST';
  const barColor = isPreOrder ? '#7c3aed' : isFest ? '#b45309' : Colors.primary;
  const accentColor = isPreOrder ? '#7c3aed' : isFest ? '#f59e0b' : Colors.primary;

  return (
    <View
      accessible={false}
      focusable={false}
      isTVSelectable={false}
    >
      <View style={[styles.dateCard, isBootstrap && styles.dateCardApproximate]}>
        {/* Top bar */}
        <View style={[styles.dateBar, { backgroundColor: barColor }]}>
          <Text style={styles.dateBarText}>
            {isPreOrder ? 'PRE-ORDER' : isFest ? 'FEST' : dateParts.dayName}
          </Text>
        </View>

        {/* Body */}
        <View style={styles.dateBody}>
          <Text style={[styles.dateNumber, { color: (isPreOrder || isFest) ? accentColor : '#fff', fontStyle: isBootstrap ? 'italic' : 'normal' }]}>
            {isPreOrder ? 'SOON' : isFest ? 'NOW' : (isBootstrap ? '~' : '') + dateParts.day}
          </Text>
          {!isPreOrder && !isFest && dateParts.month ? (
            <Text style={styles.dateMonth}>{dateParts.month}</Text>
          ) : null}
          {/* Cascading chevrons — 5 levels matching desktop */}
          <View style={styles.dateChevrons}>
            {[0.9, 0.7, 0.5, 0.3, 0.15].map((opacity, i) => (
              <Text key={i} style={[styles.dateChevron, {color: accentColor, opacity}]}>
                {'›'}
              </Text>
            ))}
          </View>
        </View>
      </View>
    </View>
  );
};

// Grid configuration - 5 columns for 1920px width
const NUM_COLUMNS = 5;
const CARD_WIDTH = Dimensions.tvos.cardWidth;
const CARD_HEIGHT = Dimensions.tvos.cardHeight;
const CARD_GAP = 16;
const SHOW_TRAILERS_CARD = false; // Trailers card temporarily disabled — set true to restore
const PAGE_SIZE = 60; // Movies rendered per page; more load on demand

// Trailers Card Component with focus animations
const TrailersCard = ({ playlistUrl, nextFocusUp }) => {
  const [isFocused, setIsFocused] = useState(false);
  const scaleAnim = useRef(new Animated.Value(1)).current;

  const handleFocus = useCallback(() => {
    setIsFocused(true);
    Animated.timing(scaleAnim, {
      toValue: 1.08,
      duration: 150,
      useNativeDriver: true,
    }).start();
  }, [scaleAnim]);

  const handleBlur = useCallback(() => {
    setIsFocused(false);
    Animated.timing(scaleAnim, {
      toValue: 1,
      duration: 150,
      useNativeDriver: true,
    }).start();
  }, [scaleAnim]);

  const handlePress = useCallback(() => {
    // Extract playlist ID from URL
    let playlistId = null;
    const url = playlistUrl || '';

    const match = url.match(/[?&]list=([a-zA-Z0-9_-]+)/);
    if (match) {
      playlistId = match[1];
    }

    console.log('[Trailers] Playlist URL:', url);
    console.log('[Trailers] Playlist ID:', playlistId);

    if (!playlistId) {
      Alert.alert(
        'No Playlist Available',
        'Please open YouTube and search for "New Release Wall" to find our trailers.'
      );
      return;
    }

    // Try multiple URL formats for tvOS YouTube deep linking
    // Format 1: youtube:// with full path (works on some tvOS versions)
    const tryUrls = [
      `youtube://www.youtube.com/playlist?list=${playlistId}`,
      `youtube://playlist?list=${playlistId}`,
      `vnd.youtube://www.youtube.com/playlist?list=${playlistId}`,
    ];

    const tryNextUrl = (index) => {
      if (index >= tryUrls.length) {
        // All formats failed - show manual instructions
        Alert.alert(
          'YouTube Playlist',
          `Playlist ID: ${playlistId}\n\nThe YouTube app couldn't open the playlist directly. Please open YouTube and search for "New Release Wall".`
        );
        return;
      }

      const urlToTry = tryUrls[index];
      console.log(`[Trailers] Trying format ${index + 1}:`, urlToTry);

      Linking.openURL(urlToTry).catch((err) => {
        console.error(`[Trailers] Format ${index + 1} failed:`, err);
        tryNextUrl(index + 1);
      });
    };

    tryNextUrl(0);
  }, [playlistUrl]);

  return (
    <TouchableOpacity
      onPress={handlePress}
      onFocus={handleFocus}
      onBlur={handleBlur}
      activeOpacity={1}
      accessible={true}
      accessibilityLabel="This Week's Trailers - Opens YouTube playlist"
      accessibilityRole="button"
      nextFocusUp={nextFocusUp}
    >
      <Animated.View
        style={[
          styles.trailersCard,
          {
            transform: [{ scale: scaleAnim }],
            zIndex: isFocused ? 1000 : 1,
            elevation: isFocused ? 10 : 0,
          },
        ]}
      >
        <Text style={styles.trailersTextSmall}>THIS WEEK'S</Text>
        <Text style={styles.trailersTextLarge}>TRAILERS</Text>
        {/* YouTube-style play button */}
        <View style={styles.youtubeButton}>
          <Text style={styles.youtubePlayIcon}>▶</Text>
        </View>
        {isFocused && <View style={styles.trailersFocusBorder} />}
      </Animated.View>
    </TouchableOpacity>
  );
};

// Load More Card — appears at bottom of grid when more movies remain
const LoadMoreCard = ({ remaining, onPress, nextFocusUp }) => {
  const [isFocused, setIsFocused] = useState(false);
  const scaleAnim = useRef(new Animated.Value(1)).current;

  const handleFocus = useCallback(() => {
    setIsFocused(true);
    Animated.timing(scaleAnim, { toValue: 1.05, duration: 150, useNativeDriver: true }).start();
  }, [scaleAnim]);

  const handleBlur = useCallback(() => {
    setIsFocused(false);
    Animated.timing(scaleAnim, { toValue: 1, duration: 150, useNativeDriver: true }).start();
  }, [scaleAnim]);

  return (
    <TouchableOpacity
      onPress={onPress}
      onFocus={handleFocus}
      onBlur={handleBlur}
      activeOpacity={1}
      accessible={true}
      accessibilityLabel={`Load ${remaining} more movies`}
      accessibilityRole="button"
      nextFocusUp={nextFocusUp}
    >
      <Animated.View style={[styles.loadMoreCard, isFocused && styles.loadMoreCardFocused, { transform: [{ scale: scaleAnim }] }]}>
        <Text style={styles.loadMoreArrow}>↓</Text>
        <Text style={styles.loadMoreLabel}>MORE</Text>
        <Text style={styles.loadMoreCount}>{remaining} films</Text>
      </Animated.View>
    </TouchableOpacity>
  );
};

const HomeScreenTvOS = () => {
  const navigation = useNavigation();
  const flatListRef = useRef(null);
  const initialFocusDone = useRef(false);  // Prevents hasTVPreferredFocus re-firing on listData changes
  const [headerNodeHandle, setHeaderNodeHandle] = useState(null);
  const headerRefObject = useRef(null);
  const [toggleNodeHandle, setToggleNodeHandle] = useState(null);
  const [lastFilterNodeHandle, setLastFilterNodeHandle] = useState(null);
  const [lastToggleNodeHandle, setLastToggleNodeHandle] = useState(null);

  // Callback ref for first filter button
  const setFirstFilterRef = useCallback((ref) => {
    if (ref) {
      headerRefObject.current = ref;
      const handle = findNodeHandle(ref);
      setHeaderNodeHandle(handle);
    }
  }, []);

  // Callback ref for last filter button (Reissues) — slop toggle LEFT target
  const setLastFilterRef = useCallback((ref) => {
    if (ref) {
      const handle = findNodeHandle(ref);
      if (handle) setLastFilterNodeHandle(handle);
    }
  }, []);

  // Callback ref for slop toggle — this is what movie cards navigate UP to
  const setFirstToggleRef = useCallback((ref) => {
    if (ref) {
      const handle = findNodeHandle(ref);
      setToggleNodeHandle(handle);
    }
  }, []);

  // Callback ref for last toggle (pre-order) — leftmost first-row poster LEFT target
  const setLastToggleRef = useCallback((ref) => {
    if (ref) {
      const handle = findNodeHandle(ref);
      if (handle) setLastToggleNodeHandle(handle);
    }
  }, []);

  // Get shared state and actions
  const {
    filteredMovies,
    isLoading,
    error,
    refreshMovies,
    latestPlaylistUrl,
    searchQuery,
    updateSearchQuery,
  } = useHomeScreen();

  // Local state - multi-select filters (Set of active filter IDs)
  const [activeFilters, setActiveFilters] = useState(new Set());
  const [slopMode, setSlopMode] = useState('free'); // 'free' | 'all' | 'only' — matches desktop 3-state
  const [hideFest, setHideFest] = useState(true); // default: hide fests (matches desktop default)
  const [showPreorders, setShowPreorders] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [searchFocused, setSearchFocused] = useState(false);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  // Reset to first page whenever filters change
  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [activeFilters, slopMode, hideFest, showPreorders, searchQuery]);

  // Fullscreen poster modal state
  const [fullscreenVisible, setFullscreenVisible] = useState(false);
  const [fullscreenIndex, setFullscreenIndex] = useState(0);

  // Grid item refs for wrap-around navigation
  const itemRefsMap = useRef(new Map());  // Map of index -> ref
  const [itemNodeHandles, setItemNodeHandles] = useState(new Map());  // Map of index -> node handle

  // Register item ref for wrap-around navigation.
  // Also updates itemNodeHandles immediately — bail-out prevents re-renders when handle unchanged.
  const registerItemRef = useCallback((index, ref) => {
    if (ref) {
      itemRefsMap.current.set(index, ref);
      const handle = findNodeHandle(ref);
      if (handle) {
        setItemNodeHandles(prev => {
          if (prev.get(index) === handle) return prev;
          const next = new Map(prev);
          next.set(index, handle);
          return next;
        });
      }
    } else {
      itemRefsMap.current.delete(index);
    }
  }, []);

  // Full handle refresh after listData changes (initial load + filter changes).
  // Backstop that catches anything registerItemRef missed (e.g. refs set before InteractionManager fires).
  useEffect(() => {
    const task = InteractionManager.runAfterInteractions(() => {
      setItemNodeHandles(prev => {
        const next = new Map(prev);
        let changed = false;
        itemRefsMap.current.forEach((ref, index) => {
          const handle = findNodeHandle(ref);
          if (handle && next.get(index) !== handle) {
            next.set(index, handle);
            changed = true;
          }
        });
        return changed ? next : prev;
      });
    });
    return () => task.cancel();
  }, [listData]);

  // Wrapper refs for z-index elevation on focus — imperative, avoids re-renders
  const wrapperRefsMap = useRef(new Map());
  const prevFocusedWrapper = useRef(null);

  const registerWrapperRef = useCallback((index, ref) => {
    if (ref) wrapperRefsMap.current.set(index, ref);
    else wrapperRefsMap.current.delete(index);
  }, []);

  // Track screen view on mount
  useEffect(() => {
    trackScreenView('Home', { filters: Array.from(activeFilters) });
  }, []);

  // Handle filter change - multi-select toggle behavior
  const handleFilterChange = useCallback((filterId) => {
    setActiveFilters(prev => {
      const newFilters = new Set(prev);

      // Toggle this filter on/off
      if (newFilters.has(filterId)) {
        newFilters.delete(filterId);
      } else {
        newFilters.add(filterId);
      }

      trackFilterChange(filterId, Array.from(prev).join(','));
      return newFilters;
    });
  }, []);

  // Get movies based on active filters (multi-select with OR logic - cumulative)
  const displayMovies = useMemo(() => {
    let movies = filteredMovies;

    // Slop mode: free=hide slop, all=show all, only=show only slop (matches desktop 3-state)
    // Fests and pre-orders are always exempt — if you turned them on, you want all of them
    if (slopMode === 'free') {
      movies = movies.filter(m =>
        (!m.is_slop && !m._is_slop_guess) ||
        (!hideFest && m.filters?.is_virtual_screening) ||
        (showPreorders && m._is_preorder)
      );
    } else if (slopMode === 'only') {
      movies = movies.filter(m =>
        (m.is_slop || m._is_slop_guess) ||
        (!hideFest && m.filters?.is_virtual_screening) ||
        (showPreorders && m._is_preorder)
      );
    }

    // Hide-fest mode: hide virtual screenings
    if (hideFest) {
      movies = movies.filter(m => !m.filters?.is_virtual_screening);
    }

    // Pre-orders: only show when toggle is ON or search is active
    // Virtual screenings are exempt — their visibility is controlled by hideFest, not showPreorders
    if (!showPreorders && !searchQuery) {
      movies = movies.filter(m => !m._is_preorder || m.filters?.is_virtual_screening);
    }

    // If no filters selected OR search is active, show all (search bypasses category filters — matches desktop)
    if (activeFilters.size === 0 || searchQuery) {
      return movies;
    }

    // Filter movies - must pass ANY selected filter (OR logic)
    return movies.filter(movie => {
      for (const filter of activeFilters) {
        switch (filter) {
          case 'indie':
            if (movie.filters?.is_indie) return true;
            break;
          case 'staff-picks':
            if (movie.filters?.is_staff_pick || movie.featured) return true;
            break;
          case 'foreign': {
            const isForeign = movie.filters?.is_foreign ??
              (movie.original_language && movie.original_language !== 'en');
            if (isForeign) return true;
            break;
          }
          case 'documentary':
            if (movie.filters?.is_documentary === true) return true;
            break;
          case 'restorations':
            if (movie.filters?.is_restoration) return true;
            break;
          case 'horror':
            if ((movie.genres || []).some(g => g.toLowerCase().includes('horror'))) return true;
            break;
          case 'action':
            if ((movie.genres || []).some(g => g.toLowerCase().includes('action'))) return true;
            break;
          case 'comedy':
            if ((movie.genres || []).some(g => g.toLowerCase().includes('comedy'))) return true;
            break;
          case 'family':
            if ((movie.genres || []).some(g => g.toLowerCase().includes('family'))) return true;
            break;
        }
      }
      return false;
    });
  }, [filteredMovies, activeFilters, slopMode, hideFest, showPreorders, searchQuery]);

  // Build flat list data with date markers interspersed
  // Each date marker takes one grid cell (same size as movie card)
  const listData = useMemo(() => {
    if (!displayMovies || displayMovies.length === 0) return [];

    // Split into three buckets: fest (virtual screenings), pre-orders, regular
    const festMovies = displayMovies.filter(m => !m._is_preorder && m.filters?.is_virtual_screening);
    const preorderMovies = displayMovies.filter(m => m._is_preorder);
    const regularMovies = displayMovies.filter(m => !m._is_preorder && !m.filters?.is_virtual_screening);

    // Sort each bucket
    // Sort by date desc, staff picks first within same date (matches desktop)
    const byDateDesc = (a, b) => {
      const da = a.digital_date || '0000-00-00';
      const db = b.digital_date || '0000-00-00';
      if (db !== da) return db.localeCompare(da);
      const aStaff = a.filters?.is_staff_pick || a.featured;
      const bStaff = b.filters?.is_staff_pick || b.featured;
      if (aStaff && !bStaff) return -1;
      if (!aStaff && bStaff) return 1;
      return 0;
    };
    // Fest: active (NOW) first by soonest expiry, then upcoming (FUTURE) ascending, then expired
    const today = new Date().toISOString().slice(0, 10);
    const festTier = m => {
      if (m.virtual_screening_info?.status === 'active') return 0;
      if ((m.digital_date || '') > today) return 1;
      return 2;
    };
    const sortedFest = [...festMovies].sort((a, b) => {
      const ta = festTier(a), tb = festTier(b);
      if (ta !== tb) return ta - tb;
      if (ta === 0) return (a.virtual_screening_info?.available_end || '').localeCompare(b.virtual_screening_info?.available_end || '');
      if (ta === 1) return (a.digital_date || '').localeCompare(b.digital_date || '');
      return (b.digital_date || '').localeCompare(a.digital_date || '');
    });
    const sortedPreorders = [...preorderMovies].sort((a, b) => (a.digital_date || '').localeCompare(b.digital_date || ''));
    const sortedRegular = [...regularMovies].sort(byDateDesc);

    const items = [];

    // 1. FEST section at top (amber card)
    if (sortedFest.length > 0) {
      items.push({ type: 'date', id: 'date-fest-top', date: 'SCREENING' });
      sortedFest.forEach((movie, index) => {
        items.push({ type: 'movie', id: movie.tmdb_id || movie.id || `fest-${index}`, movie });
      });
    }

    // 2. PRE-ORDERS section (purple card)
    if (sortedPreorders.length > 0) {
      items.push({ type: 'date', id: 'date-preorder-top', date: 'PRE-ORDER' });
      sortedPreorders.forEach((movie, index) => {
        items.push({ type: 'movie', id: movie.tmdb_id || movie.id || `preorder-${index}`, movie });
      });
    }

    // 3. Regular movies with date dividers (optional trailers card before first date)
    const hasMore = sortedRegular.length > visibleCount;
    const paginatedRegular = sortedRegular.slice(0, visibleCount);

    let currentDate = null;
    let trailersPushed = false;
    paginatedRegular.forEach((movie, index) => {
      const movieDate = movie.digital_date || 'Unknown';
      if (movieDate !== currentDate) {
        currentDate = movieDate;
        if (!trailersPushed && SHOW_TRAILERS_CARD) {
          items.push({ type: 'trailers', id: 'new-trailers-button', playlistUrl: latestPlaylistUrl });
          trailersPushed = true;
        }
        items.push({ type: 'date', id: `date-${movieDate}-${index}`, date: movieDate, isBootstrap: !!movie.bootstrap_date });
      }
      items.push({ type: 'movie', id: movie.tmdb_id || movie.id || `movie-${index}`, movie });
    });

    if (hasMore) {
      items.push({ type: 'load_more', id: 'load-more', remaining: sortedRegular.length - visibleCount });
    }

    return items;
  }, [displayMovies, latestPlaylistUrl, visibleCount]);

  // Handle movie selection - navigate to detail with analytics
  const handleMovieSelect = useCallback(
    (movie) => {
      trackMovieSelect(movie);
      // Store sorted movie list in module-level ref (avoids 1.6MB route params serialization).
      // DetailScreen reads from sharedMovieList instead of route params.
      const sortedList = listData.filter(item => item.type === 'movie').map(item => item.movie);
      setSharedMovieList(sortedList);
      const movieIndex = sortedList.findIndex(m => String(m.id) === String(movie.id));
      navigation.navigate('MovieDetail', { movie, movieIndex: movieIndex >= 0 ? movieIndex : 0 });
    },
    [navigation, listData]
  );

  // Handle opening fullscreen poster view
  const handleOpenFullscreen = useCallback((movie) => {
    // Find index of this movie in displayMovies
    const index = displayMovies.findIndex(m =>
      (m.id || m.tmdb_id) === (movie.id || movie.tmdb_id)
    );
    if (index !== -1) {
      setFullscreenIndex(index);
      setFullscreenVisible(true);
    }
  }, [displayMovies]);

  // Handle movie focus — also elevates wrapper z-index so focus ring isn't clipped by right sibling
  const handleMovieFocus = useCallback((movie, index) => {
    trackMovieFocus(movie, 0, index);
    if (prevFocusedWrapper.current) {
      prevFocusedWrapper.current.setNativeProps({ style: { zIndex: 1 } });
    }
    const wrapper = wrapperRefsMap.current.get(index);
    if (wrapper) {
      wrapper.setNativeProps({ style: { zIndex: 100 } });
      prevFocusedWrapper.current = wrapper;
    }
  }, []);

  const handleMovieBlur = useCallback((index) => {
    const wrapper = wrapperRefsMap.current.get(index);
    if (wrapper) {
      wrapper.setNativeProps({ style: { zIndex: 1 } });
    }
    prevFocusedWrapper.current = null;
  }, []);

  // Handle TV remote events
  useTVEventHandler({
    [TV_EVENTS.PLAY_PAUSE]: () => {
      handleRefresh();
    },
  });

  // Handle refresh
  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    await refreshMovies();
    setIsRefreshing(false);
  }, [refreshMovies]);


  // Format date for display (matches web date divider style)
  const formatDateParts = useCallback((dateString) => {
    if (!dateString || dateString === 'Unknown') {
      return { day: '?', dayName: '', month: 'Unknown' };
    }
    if (dateString === 'PRE-ORDER') {
      return { dayName: 'PRE-', day: 'ORDER', month: '' };
    }
    if (dateString === 'SCREENING') {
      return { dayName: 'FEST', day: 'NOW', month: '' };
    }
    try {
      const date = new Date(dateString + 'T12:00:00'); // Noon to avoid timezone issues
      return {
        dayName: date.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase(),
        day: date.getDate().toString(),
        month: date.toLocaleDateString('en-US', { month: 'short' }).toUpperCase(),
      };
    } catch {
      return { day: '?', dayName: '', month: dateString };
    }
  }, []);

  // Only fire hasTVPreferredFocus on first data load — prevents re-triggering on filter changes
  const giveInitialFocus = !initialFocusDone.current;
  if (giveInitialFocus) initialFocusDone.current = true;

  // Render item (date marker, trailers button, or movie card)
  const renderItem = useCallback(
    ({ item, index }) => {
      // Items in first row should navigate up to filter chips (bottom header row)
      const isFirstRow = index < NUM_COLUMNS;
      const focusUpTarget = isFirstRow ? headerNodeHandle : undefined;

      // NEW TRAILERS button
      if (item.type === 'trailers') {
        return (
          <View style={styles.cardWrapper}>
            <TrailersCard playlistUrl={item.playlistUrl} nextFocusUp={focusUpTarget} />
          </View>
        );
      }

      // Date marker — wrapped in TVFocusGuideView so the tvOS focus engine
      // redirects focus THROUGH the non-focusable date cell to an adjacent movie.
      if (item.type === 'date') {
        const dateParts = formatDateParts(item.date);
        // Find nearest movie ref above and below in same column
        const findMovieRef = (startIdx, step) => {
          let i = startIdx;
          while (i >= 0 && i < listData.length) {
            if (listData[i]?.type === 'movie') {
              const r = itemRefsMap.current.get(i);
              if (r) return r;
            }
            i += step;
          }
          return null;
        };
        const refAbove = findMovieRef(index - NUM_COLUMNS, -NUM_COLUMNS);
        const refBelow = findMovieRef(index + NUM_COLUMNS, NUM_COLUMNS);
        // Use header as up-fallback when nothing above in column
        const upFallback = refAbove ?? headerRefObject.current;
        const guideDests = [upFallback, refBelow].filter(Boolean);
        return (
          <TVFocusGuideView destinations={guideDests} style={styles.cardWrapper}>
            <DateCard dateParts={dateParts} isBootstrap={item.isBootstrap} />
          </TVFocusGuideView>
        );
      }

      // Load more button
      if (item.type === 'load_more') {
        // Scan backward for the nearest registered movie card handle to use as UP target
        let loadMoreUpHandle = headerNodeHandle;
        for (let i = index - 1; i >= 0; i--) {
          const h = itemNodeHandles.get(i);
          if (h) { loadMoreUpHandle = h; break; }
        }
        return (
          <View style={styles.cardWrapper}>
            <LoadMoreCard
              remaining={item.remaining}
              onPress={() => setVisibleCount(prev => prev + PAGE_SIZE)}
              nextFocusUp={loadMoreUpHandle}
            />
          </View>
        );
      }

      // Calculate wrap-around navigation for grid
      // At row end (rightmost column), RIGHT should go to next row's first item
      // At row start (leftmost column), LEFT should go to previous row's last item
      const columnIndex = index % NUM_COLUMNS;
      const isRowEnd = columnIndex === NUM_COLUMNS - 1;
      const isRowStart = columnIndex === 0;

      // Scan linearly for nearest focusable handle (skips date cards which have no handle)
      const findNearestHandle = (start, step) => {
        for (let i = start; i >= 0 && i < listData.length; i += step) {
          const handle = itemNodeHandles.get(i);
          if (handle) return handle;
        }
        return undefined;
      };

      // Scan strictly within the same column going up, skipping date cards and unregistered handles
      const findSameColumnAbove = (idx) => {
        let i = idx - NUM_COLUMNS;
        while (i >= 0) {
          if (listData[i]?.type !== 'date') {
            const handle = itemNodeHandles.get(i);
            if (handle) return handle;
          }
          i -= NUM_COLUMNS;
        }
        return undefined;
      };

      // Scan strictly within the same column going down, skipping date cards and unregistered handles
      const findSameColumnBelow = (idx) => {
        let i = idx + NUM_COLUMNS;
        while (i < listData.length) {
          if (listData[i]?.type !== 'date') {
            const handle = itemNodeHandles.get(i);
            if (handle) return handle;
          }
          i += NUM_COLUMNS;
        }
        return undefined;
      };

      const rightNeighbor = listData[index + 1];
      const leftNeighbor = index > 0 ? listData[index - 1] : undefined;
      const belowItem = listData[index + NUM_COLUMNS];
      const aboveItem = index >= NUM_COLUMNS ? listData[index - NUM_COLUMNS] : undefined;

      // RIGHT: wrap at row end, or skip a date card in the next cell
      const nextFocusRight = isRowEnd
        ? findNearestHandle(index + 1, 1)
        : (rightNeighbor && rightNeighbor.type === 'date' ? findNearestHandle(index + 2, 1) : undefined);

      // LEFT: at row start → last filter chip (first poster row) or far right of previous poster row.
      // Skip date cards in the previous cell; guard index-2 going negative (date at col 0, first row).
      const nextFocusLeft = isRowStart
        ? (isFirstRow ? lastFilterNodeHandle : findNearestHandle(index - 1, -1))
        : (leftNeighbor && leftNeighbor.type === 'date'
            ? (index === 1 ? lastFilterNodeHandle : findNearestHandle(index - 2, -1))
            : undefined);

      // DOWN: always column-preserving (skips dates + unregistered handles); undefined if nothing below
      const nextFocusDown = findSameColumnBelow(index);

      // UP: always explicit — column-preserving (skips dates), fall back to header when nothing above
      const nextFocusUp = isFirstRow
        ? headerNodeHandle
        : (findSameColumnAbove(index) ?? headerNodeHandle);

      // Movie card
      return (
        <View ref={(ref) => registerWrapperRef(index, ref)} style={styles.cardWrapper}>
          <MovieCard
            ref={(ref) => registerItemRef(index, ref)}
            movie={item.movie}
            onSelect={() => handleMovieSelect(item.movie)}
            onLongPress={() => handleOpenFullscreen(item.movie)}
            onFocus={() => handleMovieFocus(item.movie, index)}
            onBlur={() => handleMovieBlur(index)}
            hasTVPreferredFocus={giveInitialFocus && index === (SHOW_TRAILERS_CARD ? 2 : 1)}
            testID={`movie-card-${index}`}
            nextFocusUp={nextFocusUp}
            nextFocusDown={nextFocusDown}
            nextFocusLeft={nextFocusLeft}
            nextFocusRight={nextFocusRight}
          />
        </View>
      );
    },
    [formatDateParts, handleMovieSelect, handleMovieFocus, handleMovieBlur, handleOpenFullscreen, headerNodeHandle, lastFilterNodeHandle, itemNodeHandles, listData, registerItemRef, registerWrapperRef, giveInitialFocus]
  );

  // Key extractor
  const keyExtractor = useCallback((item) => item.id, []);

  // Get item layout for optimized scrolling (vertical grid)
  const getItemLayout = useCallback((data, index) => {
    const rowHeight = CARD_HEIGHT + CARD_GAP;
    const rowIndex = Math.floor(index / NUM_COLUMNS);
    return {
      length: rowHeight,
      offset: rowIndex * rowHeight,
      index,
    };
  }, []);

  // Render loading state
  if (isLoading && listData.length === 0) {
    return (
      <View style={styles.container}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={Colors.primary} />
        </View>
      </View>
    );
  }

  // Render error state
  if (error && listData.length === 0) {
    return (
      <View style={styles.container}>
        <View style={styles.errorContainer}>
          <Text style={styles.errorTitle}>Unable to Load Movies</Text>
          <Text style={styles.errorMessage}>{error}</Text>
          <Text style={styles.errorHint}>
            Press Play/Pause on your remote to retry
          </Text>
        </View>
      </View>
    );
  }

  // Render empty state
  if (!isLoading && listData.length === 0) {
    return (
      <View style={styles.container}>
        <View style={styles.emptyContainer}>
          <Text style={styles.emptyText}>
            No movies available. Press Play/Pause to refresh.
          </Text>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Header: top row = title + toggles; bottom row = filters + search */}
      <View style={styles.header}>
        {/* Top row: title left, toggles right */}
        <View style={styles.headerTopRow}>
          <Text style={styles.headerTitle}>THE NEW RELEASE WALL</Text>
          <View style={styles.toggleRow}>
            <SlopToggle
              ref={setFirstToggleRef}
              slopMode={slopMode}
              onPress={() => setSlopMode(m => m === 'free' ? 'all' : m === 'all' ? 'only' : 'free')}
              nextFocusDown={headerNodeHandle}
            />
            <MetaToggle
              isActive={!hideFest}
              label="FESTS"
              accessibilityLabel={hideFest ? 'Virtual screenings hidden' : 'Showing virtual screenings'}
              onPress={() => setHideFest(v => !v)}
              nextFocusDown={headerNodeHandle}
            />
            <MetaToggle
              ref={setLastToggleRef}
              isActive={showPreorders}
              label="PRE-ORDER"
              accessibilityLabel={showPreorders ? 'Showing pre-orders' : 'Pre-orders hidden'}
              onPress={() => setShowPreorders(v => !v)}
              nextFocusDown={headerNodeHandle}
            />
          </View>
        </View>
        {/* Bottom row: filter chips left, search right */}
        <View style={styles.filterSearchRow}>
          <View style={styles.filterRow}>
            {FILTERS.map((filter, idx) => (
              <FilterButton
                key={filter.id}
                ref={idx === 0 ? setFirstFilterRef : idx === FILTERS.length - 1 ? setLastFilterRef : undefined}
                filter={filter}
                isActive={activeFilters.has(filter.id)}
                onPress={() => handleFilterChange(filter.id)}
                nextFocusUp={toggleNodeHandle}
                style={{ flex: 1 }}
              />
            ))}
          </View>
          <View style={[styles.searchContainer, searchFocused && styles.searchContainerFocused]}>
            <Text style={styles.searchIcon}>⌕</Text>
            <TextInput
              style={styles.searchInput}
              placeholder="Search..."
              placeholderTextColor="rgba(255,255,255,0.4)"
              value={searchQuery}
              onChangeText={updateSearchQuery}
              onFocus={() => setSearchFocused(true)}
              onBlur={() => setSearchFocused(false)}
              autoCapitalize="none"
              autoCorrect={false}
              returnKeyType="search"
            />
            {searchQuery.length > 0 && (
              <TouchableOpacity style={styles.searchClear} onPress={() => updateSearchQuery('')}>
                <Text style={styles.searchClearText}>✕</Text>
              </TouchableOpacity>
            )}
          </View>
        </View>
      </View>

      {/* Filter description — shown when exactly one filter is active (matches web) */}
      {activeFilters.size === 1 && (() => {
        const filterId = Array.from(activeFilters)[0];
        const desc = FILTER_DESCRIPTIONS[filterId];
        if (!desc) return null;
        return (
          <View style={styles.filterDescriptionRow}>
            <Text style={styles.filterDescriptionTitle}>{desc.title}</Text>
            <Text style={styles.filterDescriptionText}>{desc.text}</Text>
          </View>
        );
      })()}

      {/* Vertical scrolling grid - the wall */}
      <FlatList
        ref={flatListRef}
        data={listData}
        renderItem={renderItem}
        keyExtractor={keyExtractor}
        numColumns={NUM_COLUMNS}
        extraData={itemNodeHandles}
        showsVerticalScrollIndicator={false}
        contentContainerStyle={styles.listContent}
        columnWrapperStyle={styles.row}
        maxToRenderPerBatch={21}
        windowSize={5}
        initialNumToRender={21}
        getItemLayout={getItemLayout}
      />

      {/* Refresh indicator overlay */}
      {isRefreshing && (
        <View style={styles.refreshOverlay}>
          <ActivityIndicator color={Colors.primary} size="large" />
        </View>
      )}

      {/* Fullscreen poster modal */}
      <FullscreenPosterModal
        visible={fullscreenVisible}
        movies={displayMovies}
        initialIndex={fullscreenIndex}
        onClose={() => setFullscreenVisible(false)}
        plexLibrary={{}}
      />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  header: {
    flexDirection: 'column',
    paddingHorizontal: 68,
    paddingTop: 20,
    paddingBottom: 8,
  },
  headerTopRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  headerTitle: {
    color: Colors.textPrimary,
    fontSize: 90,
    fontWeight: '100',
    letterSpacing: 9,
  },
  filterRow: {
    flexDirection: 'row',
    flex: 1,
    alignItems: 'center',
    gap: 8,
  },
  filterSearchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingBottom: 4,
    gap: 20,
  },
  searchContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    borderRadius: 20,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.2)',
    paddingHorizontal: 12,
    width: 250,
    height: 36,
  },
  searchContainerFocused: {
    borderColor: Colors.primary,
    borderWidth: 2,
  },
  searchIcon: {
    color: 'rgba(255, 255, 255, 0.6)',
    fontSize: 18,
    marginRight: 8,
  },
  searchInput: {
    flex: 1,
    color: Colors.textPrimary,
    fontSize: 16,
    padding: 0,
  },
  searchClear: {
    paddingLeft: 8,
  },
  searchClearText: {
    color: 'rgba(255, 255, 255, 0.6)',
    fontSize: 16,
  },
  filterButton: {
    alignSelf: 'stretch',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 16,
    borderRadius: 22,
    backgroundColor: 'rgba(255, 255, 255, 0.08)',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.35)',
  },
  filterButtonActive: {
    backgroundColor: Colors.primary,
    borderColor: Colors.primary,
  },
  filterButtonFocused: {
    borderColor: Colors.primary,
    borderWidth: 2,
  },
  filterButtonText: {
    color: Colors.textPrimary,
    fontSize: 20,
    fontWeight: '500',
  },
  filterButtonTextActive: {
    color: '#ffffff', // white on teal — matches desktop (body color: #fff)
    fontWeight: '700',
  },
  filterDivider: {
    width: 1,
    height: 20,
    backgroundColor: 'rgba(255,255,255,0.2)',
    alignSelf: 'center',
    marginHorizontal: 4,
  },
  toggleRow: {
    flexDirection: 'row',
    gap: 20,
    alignItems: 'center',
  },
  metaToggleWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  metaToggleLabel: {
    fontSize: 16,
    fontWeight: '700',
    letterSpacing: 1.2,
    color: 'rgba(0,212,170,0.45)',
  },
  metaToggleLabelActive: {
    color: '#00d4aa',
  },
  slopToggleTrack: {
    width: 108,
    height: 28,
    borderRadius: 14,
    backgroundColor: '#1a1a1a',
    borderWidth: 1,
    borderColor: 'rgba(0,212,170,0.45)',
    justifyContent: 'center',
    paddingHorizontal: 4,
  },
  slopToggleThumb: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: 'rgba(0,212,170,0.55)',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.4,
    shadowRadius: 3,
  },
  metaToggleTrack: {
    width: 80,
    height: 38,
    borderRadius: 19,
    backgroundColor: '#1a1a1a',
    borderWidth: 1,
    borderColor: 'rgba(0,212,170,0.3)',
    justifyContent: 'center',
    paddingHorizontal: 4,
  },
  metaToggleTrackActive: {
    backgroundColor: '#00d4aa',
    borderColor: '#00d4aa',
  },
  metaToggleTrackFocused: {
    borderColor: 'rgba(255,255,255,0.85)',
    borderWidth: 2.5,
  },
  metaToggleThumb: {
    width: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: '#fff',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.4,
    shadowRadius: 3,
  },
  listContent: {
    // Center the 5-column grid: (1920 - 5*344 - 4*16) / 2 = 68px
    paddingHorizontal: 68,
    paddingTop: 30,
    paddingBottom: 20,
    overflow: 'visible',
  },
  row: {
    justifyContent: 'flex-start',
    marginBottom: CARD_GAP,
    overflow: 'visible',
    zIndex: 1,
  },
  // THIS WEEK'S TRAILERS button - same size as movie cards
  trailersCard: {
    width: CARD_WIDTH,
    height: CARD_HEIGHT,
    borderRadius: 12,
    backgroundColor: Colors.background,
    borderWidth: 3,
    borderColor: Colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
    overflow: 'hidden',
  },
  trailersTextSmall: {
    color: '#ffffff',
    fontSize: 20,
    fontWeight: '600',
    letterSpacing: 1,
    textAlign: 'center',
  },
  trailersTextLarge: {
    color: '#ffffff',
    fontSize: 28,
    fontWeight: '800',
    letterSpacing: 2,
    textAlign: 'center',
    marginTop: 4,
  },
  youtubeButton: {
    width: 70,
    height: 50,
    backgroundColor: '#FF0000',
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 16,
  },
  youtubePlayIcon: {
    color: '#ffffff',
    fontSize: 24,
    marginLeft: 4,
  },
  trailersFocusBorder: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    borderRadius: 12,
    borderWidth: 4,
    borderColor: '#00ffcc',
  },
  // Date card - same size as movie cards
  dateCard: {
    width: CARD_WIDTH,
    height: CARD_HEIGHT,
    borderRadius: 12,
    backgroundColor: '#0a0a0a',
    overflow: 'hidden',
  },
  dateCardApproximate: {
    opacity: 0.8,
  },
  dateBar: {
    paddingVertical: 6,
    paddingHorizontal: 10,
  },
  dateBarText: {
    fontSize: 12,
    fontWeight: '800',
    color: '#000',
    letterSpacing: 0.5,
  },
  dateBody: {
    flex: 1,
    paddingLeft: 10,
    justifyContent: 'center',
  },
  dateNumber: {
    fontSize: 64,
    fontWeight: '800',
    lineHeight: 64,
  },
  dateMonth: {
    fontSize: 14,
    color: '#888',
    letterSpacing: 2,
    marginTop: 4,
  },
  dateChevrons: {
    flexDirection: 'row',
    marginTop: 14,
  },
  dateChevron: {
    fontSize: 80,
    lineHeight: 80,
  },
  cardWrapper: {
    marginRight: CARD_GAP,
    overflow: 'visible',
    zIndex: 1,
  },
  loadMoreCard: {
    width: CARD_WIDTH,
    height: CARD_HEIGHT,
    borderRadius: 12,
    backgroundColor: '#0a0a0a',
    borderWidth: 2,
    borderColor: 'rgba(0,212,170,0.3)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadMoreCardFocused: {
    borderColor: Colors.primary,
    borderWidth: 3,
  },
  loadMoreArrow: {
    fontSize: 44,
    color: Colors.primary,
  },
  loadMoreLabel: {
    fontSize: 22,
    fontWeight: '800',
    color: Colors.textPrimary,
    letterSpacing: 3,
    marginTop: 10,
  },
  loadMoreCount: {
    fontSize: 16,
    color: Colors.textMuted,
    marginTop: 6,
  },
  refreshOverlay: {
    position: 'absolute',
    top: 40,
    right: 40,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  errorContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 60,
  },
  errorTitle: {
    color: Colors.textPrimary,
    fontSize: Typography.tvos.subtitle,
    fontWeight: '600',
    marginBottom: Spacing.tvos.md,
  },
  errorMessage: {
    color: Colors.red,
    fontSize: Typography.tvos.body,
    marginBottom: Spacing.tvos.lg,
    textAlign: 'center',
  },
  errorHint: {
    color: Colors.textMuted,
    fontSize: Typography.tvos.caption,
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 60,
  },
  emptyText: {
    color: Colors.textMuted,
    fontSize: Typography.tvos.body,
    textAlign: 'center',
  },
  // Filter description panel — shown when exactly 1 filter active (matches web)
  filterDescriptionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 40,
    paddingHorizontal: 68,
    paddingVertical: 14,
    borderTopWidth: 1,
    borderTopColor: 'rgba(255,255,255,0.08)',
  },
  filterDescriptionTitle: {
    fontSize: 36,
    fontWeight: '800',
    letterSpacing: 4,
    color: Colors.primary,
    flexShrink: 0,
    textTransform: 'uppercase',
  },
  filterDescriptionText: {
    fontSize: 20,
    color: Colors.textMuted,
    lineHeight: 30,
    flex: 1,
  },
});

export default HomeScreenTvOS;
