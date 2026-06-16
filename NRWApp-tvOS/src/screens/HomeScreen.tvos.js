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
  { id: 'indie', label: 'Indie' },
  { id: 'horror', label: 'Horror' },
  { id: 'action', label: 'Action' },
  { id: 'comedy', label: 'Comedy' },
  { id: 'family', label: 'Family' },
  { id: 'thriller', label: 'Thriller' },
  { id: 'foreign', label: 'Foreign' },
  { id: 'documentary', label: 'Docs' },
  { id: 'restorations', label: 'Reissues' },
];

// Filter descriptions — shown below filter row when a single filter is active (matches web)
// Date strips adopt the active filter's color when exactly one filter is on
const STRIP_COLORS = {
  'indie': '#00d4aa',
  'horror': '#ff5e57',
  'action': '#ff9500',
  'comedy': '#ffd32a',
  'family': '#2ed573',
  'thriller': '#d63031',
  'foreign': '#e84393',
  'documentary': '#4A90D9',
  'restorations': '#C8A951',
};

const FILTER_DESCRIPTIONS = {
  'staff-picks': { title: 'Selects', text: "The ones we're vouching for. Out of everything on the wall, these are the movies we think are genuinely worth your time. Not a popularity contest, just honest recommendations." },
  'indie':       { title: 'Indie', text: "The smaller films, the independents, the ones without a billboard campaign. These movies flew under the radar theatrically but are worth knowing about now that they're available to stream at home." },
  'horror':      { title: 'Horror', text: "The stuff that goes bump. Horror films now streaming — from slow-burn dread to full-on splatter." },
  'action':      { title: 'Action', text: "High-octane, kinetic filmmaking. Action movies now available to watch at home." },
  'comedy':      { title: 'Comedy', text: "Films that are actually funny. Comedies — broad and subtle — now streaming." },
  'family':      { title: 'Family', text: "Films for all ages. Family movies now available to watch at home." },
  'thriller':    { title: 'Thriller', text: "Suspense, dread, and unease. Thrillers now streaming — from psychological slow-burns to pulse-pounding crime." },
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
const MetaToggle = forwardRef(({ isActive, label, accessibilityLabel, onPress, nextFocusUp, nextFocusDown, accentColor }, ref) => {
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
          isActive && accentColor && { backgroundColor: accentColor, borderColor: accentColor },
          isFocused && styles.metaToggleTrackFocused,
        ]}>
          <Animated.View style={[styles.metaToggleThumb, { transform: [{ translateX: thumbTranslate }] }]} />
        </View>
        <Text style={[styles.metaToggleLabel, isActive && styles.metaToggleLabelActive, isActive && accentColor && { color: accentColor }]}>
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

// Date Row Strip — full-width, non-focusable neon banner between date groups
// (glowing top/bottom borders, colored day + white date, centered)
const DateRowStrip = ({ stripKey, stripColor }) => {
  let day, rest = '', color;
  if (stripKey === 'PRE-ORDER') {
    day = 'PRE-ORDER'; rest = 'COMING SOON'; color = '#7c3aed';
  } else if (stripKey === 'SCREENING') {
    day = 'FEST'; rest = 'NOW SCREENING'; color = '#f59e0b';
  } else if (stripKey === 'HIGHLIGHTS') {
    day = 'SELECTS'; rest = 'OUR PICKS'; color = '#dc143c';
  } else if (stripKey === 'SLOP') {
    day = 'SLOP'; rest = 'THE CONTENT RIVER'; color = '#ff9500';
  } else {
    const d = new Date(stripKey + 'T12:00:00');
    if (isNaN(d.getTime())) {
      day = 'DATE TBD';
    } else {
      day = d.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase();
      rest = `${d.toLocaleDateString('en-US', { month: 'short' })} ${d.getDate()}`.toUpperCase();
    }
    color = stripColor || Colors.primary;
  }

  // Section banners (the active view) render ~2x the per-date strips
  const isSection = ['PRE-ORDER', 'SCREENING', 'HIGHLIGHTS', 'SLOP'].includes(stripKey);

  return (
    <View
      accessible={false}
      focusable={false}
      isTVSelectable={false}
      style={[styles.dateStripRow, isSection && styles.dateStripRowSection, { borderColor: color, shadowColor: color }]}
    >
      <Text style={[styles.dateStripDay, isSection && styles.dateStripDaySection, { color, textShadowColor: color }]}>{day}</Text>
      {rest ? <Text style={[styles.dateStripRest, isSection && styles.dateStripRestSection]}>{rest}</Text> : null}
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
  const [searchNodeHandle, setSearchNodeHandle] = useState(null);
  // Ref to first rendered movie card — used by the boundary TVFocusGuideView for DOWN from filters
  const [firstMovieRefState, setFirstMovieRefState] = useState(null);

  // First filter button — no longer the wall's UP target (the toggle module is, now
  // that toggles sit in the lower-left directly above the wall).
  const setFirstFilterRef = useCallback((ref) => {}, []);

  // Callback ref for last filter button (Reissues)
  const setLastFilterRef = useCallback((ref) => {
    if (ref) {
      const handle = findNodeHandle(ref);
      if (handle) setLastFilterNodeHandle(handle);
    }
  }, []);

  // Slop toggle (first toggle) — the wall's UP target AND the toggle handle, so a
  // poster pressing UP lands on the toggles.
  const setFirstToggleRef = useCallback((ref) => {
    if (ref) {
      headerRefObject.current = ref;
      const handle = findNodeHandle(ref);
      setHeaderNodeHandle(handle);
      setToggleNodeHandle(handle);
    }
  }, []);

  // Search box — toggles/filters navigate UP to here; search goes DOWN to the toggles.
  const setSearchRef = useCallback((ref) => {
    if (ref) setSearchNodeHandle(findNodeHandle(ref));
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
  const [showHighlightsOnly, setShowHighlightsOnly] = useState(false);

  // View toggles (Selects / Fests / Pre-Orders) are mutually exclusive: at most
  // one is active. Each toggle maps to the single winning view, or 'none' when
  // toggled off. (hideFest is inverted — fests are shown only when view==='fests'.)
  const showExclusiveView = useCallback(view => {
    setShowHighlightsOnly(view === 'selects');
    setHideFest(view !== 'fests');
    setShowPreorders(view === 'preorders');
    setSlopMode('free'); // slop is part of the same exclusive group (matches desktop)
  }, []);
  const toggleShowHighlights = useCallback(() => showExclusiveView(showHighlightsOnly ? 'none' : 'selects'), [showHighlightsOnly, showExclusiveView]);
  const toggleHideFest = useCallback(() => showExclusiveView(hideFest ? 'fests' : 'none'), [hideFest, showExclusiveView]);
  const toggleShowPreorders = useCallback(() => showExclusiveView(showPreorders ? 'none' : 'preorders'), [showPreorders, showExclusiveView]);
  // Slop toggle cycles free → all → only → free. Entering a non-free state clears
  // the Selects/Fests/Pre-Orders views so only one thing is ever active (matches desktop).
  const cycleSlopMode = useCallback(() => {
    const next = slopMode === 'free' ? 'all' : slopMode === 'all' ? 'only' : 'free';
    setSlopMode(next);
    if (next !== 'free') {
      setShowHighlightsOnly(false);
      setHideFest(true);
      setShowPreorders(false);
    }
  }, [slopMode]);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [searchFocused, setSearchFocused] = useState(false);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  // Reset to first page whenever filters change
  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [activeFilters, slopMode, hideFest, showPreorders, showHighlightsOnly, searchQuery]);

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

  // Reset first-movie ref when listData changes so the boundary guide doesn't hold a stale ref
  // between filter changes (the new first movie will re-set it when it mounts).
  useEffect(() => {
    setFirstMovieRefState(null);
  }, [listData]);

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

    // Pre-orders only show in the Pre-Order view (or search). Hide them everywhere
    // else — including ones also flagged as screenings — so they never bleed into
    // the Fests view (matches desktop).
    if (!showPreorders && !searchQuery) {
      movies = movies.filter(m => !m._is_preorder);
    }

    // Highlights mode: only staff picks
    if (showHighlightsOnly) {
      movies = movies.filter(m => m.filters?.is_staff_pick || m.featured);
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
          case 'thriller':
            if ((movie.genres || []).some(g => g.toLowerCase().includes('thriller'))) return true;
            break;
        }
      }
      return false;
    });
  }, [filteredMovies, activeFilters, slopMode, hideFest, showPreorders, showHighlightsOnly, searchQuery]);

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
    let mIdx = 0;  // global movie ordinal — drives focus refs and row/col math

    // 0. HIGHLIGHTS strip at the top when the toggle is on
    if (showHighlightsOnly) {
      items.push({ type: 'date', id: 'date-highlights-top', date: 'HIGHLIGHTS' });
    }
    // SLOP strip at the top when slop-only mode is on
    if (slopMode === 'only') {
      items.push({ type: 'date', id: 'date-slop-top', date: 'SLOP' });
    }

    // 1. FEST section — active screenings under a "NOW SCREENING" banner, then
    //    upcoming ones grouped by date so they flow into the future (matches site).
    if (sortedFest.length > 0) {
      items.push({ type: 'date', id: 'date-fest-top', date: 'SCREENING' });
      let festDate = null;
      sortedFest.forEach((movie, index) => {
        const isActive = movie.virtual_screening_info?.status === 'active';
        if (isActive) {
          items.push({ type: 'movie', id: movie.tmdb_id || movie.id || `fest-${index}`, movie, mIdx: mIdx++, stripKey: 'SCREENING' });
        } else {
          const d = movie.digital_date || 'Unknown';
          if (d !== festDate) {
            festDate = d;
            items.push({ type: 'date', id: `date-fest-${d}-${index}`, date: d });
          }
          items.push({ type: 'movie', id: movie.tmdb_id || movie.id || `fest-${index}`, movie, mIdx: mIdx++, stripKey: d });
        }
      });
    }

    // 2. PRE-ORDERS section — a "PRE-ORDER" banner, then upcoming releases grouped
    //    by date (ascending) so each future drop date gets its own strip (matches site).
    if (sortedPreorders.length > 0) {
      items.push({ type: 'date', id: 'date-preorder-top', date: 'PRE-ORDER' });
      let poDate = null;
      sortedPreorders.forEach((movie, index) => {
        const d = movie.digital_date || 'Unknown';
        if (d !== poDate) {
          poDate = d;
          items.push({ type: 'date', id: `date-po-${d}-${index}`, date: d });
        }
        items.push({ type: 'movie', id: movie.tmdb_id || movie.id || `preorder-${index}`, movie, mIdx: mIdx++, stripKey: d });
      });
    }

    // 3. Regular movies with date strips (optional trailers card before first date)
    const hasMore = sortedRegular.length > visibleCount;
    const paginatedRegular = sortedRegular.slice(0, visibleCount);

    // SELECTS is a single curated section (like FEST / PRE-ORDER): one
    // "SELECTS · OUR PICKS" strip at the top, no per-date strips. Movies carry
    // stripKey 'HIGHLIGHTS' so the focus HUD shows the section, not a date.
    let currentDate = null;
    let trailersPushed = false;
    paginatedRegular.forEach((movie, index) => {
      const movieDate = movie.digital_date || 'Unknown';
      if (!showHighlightsOnly && movieDate !== currentDate) {
        currentDate = movieDate;
        if (!trailersPushed && SHOW_TRAILERS_CARD) {
          items.push({ type: 'trailers', id: 'new-trailers-button', playlistUrl: latestPlaylistUrl });
          trailersPushed = true;
        }
        items.push({ type: 'date', id: `date-${movieDate}-${index}`, date: movieDate, isBootstrap: !!movie.bootstrap_date });
      }
      items.push({ type: 'movie', id: movie.tmdb_id || movie.id || `movie-${index}`, movie, mIdx: mIdx++, stripKey: showHighlightsOnly ? 'HIGHLIGHTS' : movieDate });
    });

    if (hasMore) {
      items.push({ type: 'load_more', id: 'load-more', remaining: sortedRegular.length - visibleCount });
    }

    return items;
  }, [displayMovies, latestPlaylistUrl, visibleCount, showHighlightsOnly, slopMode]);

  // Group the flat list into rows: strips/trailers/load-more are full-width rows,
  // movies chunk into rows of NUM_COLUMNS. Focus math works on (row, col) of movie rows.
  const rowData = useMemo(() => {
    const rows = [];
    let movieRow = [];
    const flushRow = () => {
      if (movieRow.length > 0) {
        rows.push({ type: 'movieRow', id: 'mrow-' + movieRow[0].mIdx, items: movieRow });
        movieRow = [];
      }
    };
    for (const item of listData) {
      if (item.type === 'movie') {
        movieRow.push(item);
        if (movieRow.length === NUM_COLUMNS) flushRow();
      } else {
        flushRow();
        rows.push(item);
      }
    }
    flushRow();
    return rows;
  }, [listData]);

  // mIdx -> { movieRowOrdinal, col }, plus the mIdx grid of movie rows for neighbor lookup
  const movieGrid = useMemo(() => {
    const rowsOfIdx = [];
    const posByIdx = new Map();
    for (const row of rowData) {
      if (row.type !== 'movieRow') continue;
      const idxRow = row.items.map(it => it.mIdx);
      idxRow.forEach((mi, col) => posByIdx.set(mi, { row: rowsOfIdx.length, col }));
      rowsOfIdx.push(idxRow);
    }
    return { rowsOfIdx, posByIdx };
  }, [rowData]);

  // Heads-up date banner: always shows the focused row's date group.
  // (Sticky banners collide with focus-driven scrolling on tvOS, so the date
  // lives in a fixed banner above the grid instead.)
  const stripKeyByIdx = useMemo(() => {
    const arr = [];
    for (const it of listData) {
      if (it.type === 'movie') arr[it.mIdx] = it.stripKey;
    }
    return arr;
  }, [listData]);
  const [hudStrip, setHudStrip] = useState(null);
  const [hudVisible, setHudVisible] = useState(false);
  const hudStripRef = useRef(null);
  // First group's strip key — used to seed the HUD.
  const firstStrip = useMemo(() => stripKeyByIdx.find(k => k != null) ?? null, [stripKeyByIdx]);

  // First movie ordinal (mIdx) of each consecutive strip group. Lets us tell
  // whether the focused card is still in the group's first row — if so, the
  // in-grid date strip is on screen and the heads-up banner must stay hidden so
  // the same date never shows twice.
  const groupFirstIdx = useMemo(() => {
    const arr = [];
    let curKey = null, first = 0;
    for (let i = 0; i < stripKeyByIdx.length; i++) {
      if (stripKeyByIdx[i] == null) continue;
      if (stripKeyByIdx[i] !== curKey) { curKey = stripKeyByIdx[i]; first = i; }
      arr[i] = first;
    }
    return arr;
  }, [stripKeyByIdx]);

  useEffect(() => {
    hudStripRef.current = firstStrip;
    setHudStrip(firstStrip);
    setHudVisible(false);
  }, [firstStrip]);

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
      String(m.id || m.tmdb_id) === String(movie.id || movie.tmdb_id)
    );
    if (index !== -1) {
      setFullscreenIndex(index);
      setFullscreenVisible(true);
    }
  }, [displayMovies]);

  // Handle movie focus — also elevates wrapper z-index so focus ring isn't clipped by right sibling
  const handleMovieFocus = useCallback((movie, index) => {
    trackMovieFocus(movie, 0, index);
    const strip = stripKeyByIdx[index];
    if (strip && strip !== hudStripRef.current) {
      hudStripRef.current = strip;
      setHudStrip(strip);
    }
    // Reveal the heads-up banner only once focus has moved past the group's first
    // row — by then the in-grid date strip has scrolled off the top, so the banner
    // replaces it instead of doubling it.
    const firstOfGroup = groupFirstIdx[index] ?? index;
    setHudVisible((index - firstOfGroup) >= NUM_COLUMNS);
    if (prevFocusedWrapper.current) {
      prevFocusedWrapper.current.setNativeProps({ style: { zIndex: 1 } });
    }
    const wrapper = wrapperRefsMap.current.get(index);
    if (wrapper) {
      wrapper.setNativeProps({ style: { zIndex: 100 } });
      prevFocusedWrapper.current = wrapper;
    }
  }, [stripKeyByIdx, groupFirstIdx]);

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


  // Only fire hasTVPreferredFocus on first data load — prevents re-triggering on filter changes
  const giveInitialFocus = !initialFocusDone.current;
  if (giveInitialFocus) initialFocusDone.current = true;

  // Date strips adopt the active view toggle's color (SELECTS crimson, FESTS amber,
  // SLOP ONLY orange); otherwise a single active category filter; otherwise teal
  const singleFilter = activeFilters.size === 1 ? Array.from(activeFilters)[0] : null;
  const dateStripColor = showHighlightsOnly
    ? '#dc143c'
    : showPreorders
    ? '#7c3aed'
    : !hideFest
    ? '#f59e0b'
    : slopMode === 'only'
    ? '#ff9500'
    : (singleFilter && STRIP_COLORS[singleFilter]) || Colors.primary;


  // Render row (date strip, trailers, load-more, or a row of movie cards)
  const renderRow = useCallback(
    ({ item }) => {
      // Full-width date strip — non-focusable; the focus engine never sees it
      if (item.type === 'date') {
        return (
          <DateRowStrip
            stripKey={item.date}
            stripColor={dateStripColor}
          />
        );
      }

      // NEW TRAILERS button (own row)
      if (item.type === 'trailers') {
        return (
          <View style={styles.cardWrapper}>
            <TrailersCard playlistUrl={item.playlistUrl} nextFocusUp={headerNodeHandle} />
          </View>
        );
      }

      // Load more button (own row)
      if (item.type === 'load_more') {
        // UP from load-more goes to the last rendered movie card
        const lastRow = movieGrid.rowsOfIdx[movieGrid.rowsOfIdx.length - 1];
        const loadMoreUpHandle = lastRow ? itemNodeHandles.get(lastRow[0]) : headerNodeHandle;
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

      // Row of movie cards — focus neighbors derived from (row, col) in movieGrid
      return (
        <View style={styles.movieRow}>
          {item.items.map(({ movie, mIdx, id }) => {
            const pos = movieGrid.posByIdx.get(mIdx) || { row: 0, col: 0 };
            const { rowsOfIdx } = movieGrid;
            const rowIdx = pos.row;
            const colIdx = pos.col;
            const thisRow = rowsOfIdx[rowIdx] || [];
            const prevRow = rowsOfIdx[rowIdx - 1];
            const nextRow = rowsOfIdx[rowIdx + 1];
            const isFirstMovieRow = rowIdx === 0;
            const isRowEnd = colIdx === thisRow.length - 1;
            const isRowStart = colIdx === 0;

            // RIGHT at row end wraps to the next row's first card
            const nextFocusRight = isRowEnd && nextRow
              ? itemNodeHandles.get(nextRow[0])
              : undefined;

            // LEFT at row start: first row goes to the last filter chip; deeper rows wrap
            // to the previous row's last card
            const nextFocusLeft = isRowStart
              ? (isFirstMovieRow
                  ? lastFilterNodeHandle
                  : (prevRow ? itemNodeHandles.get(prevRow[prevRow.length - 1]) : undefined))
              : undefined;

            // UP: column-preserving into the previous row (clamped to its width);
            // first row lets spatial focus find the header naturally
            const nextFocusUp = isFirstMovieRow
              ? undefined
              : (prevRow ? itemNodeHandles.get(prevRow[Math.min(colIdx, prevRow.length - 1)]) : headerNodeHandle);

            // DOWN: column-preserving into the next row (clamped)
            const nextFocusDown = nextRow
              ? itemNodeHandles.get(nextRow[Math.min(colIdx, nextRow.length - 1)])
              : undefined;

            const isFirstMovie = mIdx === 0;

            return (
              <View key={id} ref={(ref) => registerWrapperRef(mIdx, ref)} style={styles.cardWrapper}>
                <MovieCard
                  ref={(ref) => { registerItemRef(mIdx, ref); if (isFirstMovie) setFirstMovieRefState(ref); }}
                  movie={movie}
                  onSelect={() => handleMovieSelect(movie)}
                  onLongPress={() => handleOpenFullscreen(movie)}
                  onFocus={() => handleMovieFocus(movie, mIdx)}
                  onBlur={() => handleMovieBlur(mIdx)}
                  hasTVPreferredFocus={giveInitialFocus && isFirstMovie}
                  testID={`movie-card-${mIdx}`}
                  nextFocusUp={nextFocusUp}
                  nextFocusDown={nextFocusDown}
                  nextFocusLeft={nextFocusLeft}
                  nextFocusRight={nextFocusRight}
                />
              </View>
            );
          })}
        </View>
      );
    },
    [movieGrid, dateStripColor, handleMovieSelect, handleMovieFocus, handleMovieBlur, handleOpenFullscreen, headerNodeHandle, lastFilterNodeHandle, itemNodeHandles, registerItemRef, registerWrapperRef, giveInitialFocus]
  );

  // Key extractor
  const keyExtractor = useCallback((item) => item.id, []);

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
      {/* Header: top row = title + search; bottom row = 2x2 toggle module (lower-left) + filters (two rows) */}
      <View style={styles.header}>
        {/* Top row: title left, search right */}
        <View style={styles.headerTopRow}>
          <Text style={styles.headerTitle}>THE NEW RELEASE WALL</Text>
          <View ref={setSearchRef} style={[styles.searchContainer, styles.searchGrow, searchFocused && styles.searchContainerFocused]}>
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
              nextFocusDown={toggleNodeHandle}
            />
            {searchQuery.length > 0 && (
              <TouchableOpacity style={styles.searchClear} onPress={() => updateSearchQuery('')}>
                <Text style={styles.searchClearText}>✕</Text>
              </TouchableOpacity>
            )}
          </View>
        </View>
        {/* Bottom row: 2x2 toggle module (lower-left) + filters as two rows filling the rest */}
        <View style={styles.bottomRow}>
          <View style={styles.toggleModule}>
            <View style={styles.toggleModuleRow}>
              <SlopToggle
                ref={setFirstToggleRef}
                slopMode={slopMode}
                onPress={cycleSlopMode}
                nextFocusUp={searchNodeHandle}
              />
              <MetaToggle
                isActive={showHighlightsOnly}
                label="SELECTS"
                accentColor="#dc143c"
                accessibilityLabel={showHighlightsOnly ? 'Showing selects only' : 'Showing all movies'}
                onPress={toggleShowHighlights}
                nextFocusUp={searchNodeHandle}
              />
            </View>
            <View style={styles.toggleModuleRow}>
              <MetaToggle
                isActive={!hideFest}
                label="FESTS"
                accentColor="#f59e0b"
                accessibilityLabel={hideFest ? 'Virtual screenings hidden' : 'Showing virtual screenings'}
                onPress={toggleHideFest}
              />
              <MetaToggle
                ref={setLastToggleRef}
                isActive={showPreorders}
                label="PRE-ORDER"
                accentColor="#7c3aed"
                accessibilityLabel={showPreorders ? 'Showing pre-orders' : 'Pre-orders hidden'}
                onPress={toggleShowPreorders}
              />
            </View>
          </View>
          <View style={styles.filterColumn}>
            <View style={styles.filterRow}>
              {FILTERS.slice(0, 5).map((filter, idx) => (
                <FilterButton
                  key={filter.id}
                  ref={idx === 0 ? setFirstFilterRef : undefined}
                  filter={filter}
                  isActive={activeFilters.has(filter.id)}
                  onPress={() => handleFilterChange(filter.id)}
                  nextFocusUp={searchNodeHandle}
                  style={{ flex: 1 }}
                />
              ))}
            </View>
            <View style={styles.filterRow}>
              {FILTERS.slice(5).map((filter, idx, arr) => (
                <FilterButton
                  key={filter.id}
                  ref={idx === arr.length - 1 ? setLastFilterRef : undefined}
                  filter={filter}
                  isActive={activeFilters.has(filter.id)}
                  onPress={() => handleFilterChange(filter.id)}
                  style={{ flex: 1 }}
                />
              ))}
            </View>
          </View>
        </View>
      </View>

      {/* Filter description — only for exactly one active genre filter (matches web;
          the Selects / Slop / Fests / Pre-Order views show no description blurb). */}
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

      {/* Heads-up date banner — tracks the focused row's date group.
          Hidden while focus is in the first group: its in-grid strip is
          already at the top of the river, so showing both doubles the header. */}
      {hudStrip != null && hudVisible && (
        <View style={styles.hudWrap}>
          <DateRowStrip stripKey={hudStrip} stripColor={dateStripColor} />
        </View>
      )}

      {/* DOWN boundary: intercepts focus falling downward from filter chips and redirects
          to the first movie card via TVFocusGuideView (addUIBlock — reliable main-thread path).
          Height 2 ensures the focus engine sees it; invisible to the user. */}
      <TVFocusGuideView
        destinations={firstMovieRefState ? [firstMovieRefState] : []}
        style={styles.boundaryGuide}
      />

      {/* Vertical scrolling grid - the wall */}
      <FlatList
        ref={flatListRef}
        data={rowData}
        renderItem={renderRow}
        keyExtractor={keyExtractor}
        extraData={itemNodeHandles}
        showsVerticalScrollIndicator={false}
        contentContainerStyle={styles.listContent}
        // removeClippedSubviews intentionally omitted — it destroys native view registrations
        // used for focus navigation, causing nextFocusUp/Down handles to go stale off-screen.
        maxToRenderPerBatch={8}
        windowSize={5}
        initialNumToRender={8}
        // UP boundary: when focus exits the top of the scroll view it crosses this 1px guide,
        // which redirects to the filter chips. Insurance alongside natural spatial focus.
        ListHeaderComponent={
          headerRefObject.current
            ? <TVFocusGuideView destinations={[headerRefObject.current]} style={styles.listHeaderGuide} />
            : null
        }
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
  // Lower-left layout: bottom row holds the 2x2 toggle module (left) + filters (two rows, right)
  bottomRow: {
    flexDirection: 'row',
    alignItems: 'stretch',
    gap: 28,
    paddingBottom: 4,
  },
  toggleModule: {
    flexDirection: 'column',
    gap: 14,
    justifyContent: 'center',
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.16)',
    borderRadius: 16,
    paddingVertical: 16,
    paddingHorizontal: 24,
  },
  toggleModuleRow: {
    flexDirection: 'row',
    gap: 28,
    alignItems: 'center',
  },
  filterColumn: {
    flex: 1,
    flexDirection: 'column',
    gap: 8,
    justifyContent: 'center',
  },
  searchGrow: {
    flex: 1,
    marginLeft: 28,
    maxWidth: 560,
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
  // Invisible 2px strip between header and FlatList — DOWN from filter chips lands here
  // and TVFocusGuideView redirects to the first movie card.
  boundaryGuide: {
    height: 2,
    marginHorizontal: 68,
  },
  // Invisible 1px strip at the top of the FlatList scroll content — UP from first-row
  // movies exits the scroll view and this guide redirects back to the filter chips.
  listHeaderGuide: {
    height: 1,
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
  movieRow: {
    flexDirection: 'row',
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
  hudWrap: {
    paddingHorizontal: 68,
  },
  // Date row strip — full-width neon banner between date groups
  dateStripRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'baseline',
    gap: 18,
    backgroundColor: 'rgba(8,8,12,0.96)',
    borderTopWidth: 2,
    borderBottomWidth: 2,
    borderRadius: 6,
    paddingVertical: 12,
    paddingHorizontal: 16,
    marginTop: 10,
    marginBottom: 6,
    shadowOpacity: 0.55,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 0 },
  },
  dateStripDay: {
    fontSize: 30,
    fontWeight: '900',
    letterSpacing: 8,
    textTransform: 'uppercase',
    textShadowRadius: 12,
    textShadowOffset: { width: 0, height: 0 },
  },
  dateStripRest: {
    fontSize: 30,
    fontWeight: '300',
    letterSpacing: 8,
    color: '#fff',
    textTransform: 'uppercase',
  },
  // Section banner (SLOP / SELECTS / FESTS / PRE-ORDER) — ~2x the date strips
  dateStripRowSection: {
    borderTopWidth: 3,
    borderBottomWidth: 3,
    paddingVertical: 24,
    shadowOpacity: 0.7,
    shadowRadius: 30,
  },
  dateStripDaySection: { fontSize: 54 },
  dateStripRestSection: { fontSize: 34, fontWeight: '400' },
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
