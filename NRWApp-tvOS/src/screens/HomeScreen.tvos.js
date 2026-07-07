/**
 * New Release Wall - tvOS Home Screen
 * Vertical scrolling grid layout matching web design
 */

import React, { useState, useCallback, useRef, useEffect, useMemo, forwardRef } from 'react';
import {
  View,
  Text,
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
  AppState,
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
import { setSharedMovieList, setSearchMovieList } from './sharedMovieList';
import SearchIcon from '../components/SearchIcon.tvos';

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

// Filter Button Component - forwardRef to allow focus navigation from grid
const FilterButton = forwardRef(({ filter, isActive, onPress, onFocus, nextFocusDown, nextFocusUp, style, hasTVPreferredFocus }, ref) => {
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
      hasTVPreferredFocus={hasTVPreferredFocus}
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

// GENRE pulldown control — quiet teal-outline pill with a caret (matches the
// desktop .genre-control). Focusable; opens the genre overlay on select.
const GenreControl = forwardRef(({ label, isActive, onPress, nextFocusUp }, ref) => {
  const [isFocused, setIsFocused] = useState(false);
  const scaleAnim = useRef(new Animated.Value(1)).current;
  const handleFocus = useCallback(() => {
    setIsFocused(true);
    Animated.timing(scaleAnim, { toValue: 1.08, duration: 150, useNativeDriver: true }).start();
  }, [scaleAnim]);
  const handleBlur = useCallback(() => {
    setIsFocused(false);
    Animated.timing(scaleAnim, { toValue: 1, duration: 150, useNativeDriver: true }).start();
  }, [scaleAnim]);
  return (
    <TouchableOpacity
      ref={ref}
      onPress={onPress}
      onFocus={handleFocus}
      onBlur={handleBlur}
      activeOpacity={1}
      accessible={true}
      accessibilityRole="button"
      accessibilityLabel="Filter by genre"
      nextFocusUp={nextFocusUp}
    >
      <Animated.View
        style={[
          styles.genreControl,
          isActive && styles.genreControlActive,
          isFocused && styles.genreControlFocused,
          { transform: [{ scale: scaleAnim }] },
        ]}
      >
        <Text style={[styles.genreControlText, isActive && styles.genreControlTextActive]}>{label}</Text>
        <Text style={[styles.genreControlCaret, isActive && styles.genreControlTextActive]}>▾</Text>
      </Animated.View>
    </TouchableOpacity>
  );
});

// SEARCH button — far right of the control bar. Real magnifying-glass icon +
// label, styled as a quiet teal pill like GenreControl. Select opens the
// full-screen Search route (search is a destination, like Apple TV / Netflix).
const SearchButton = forwardRef(({ onPress, hasTVPreferredFocus }, ref) => {
  const [isFocused, setIsFocused] = useState(false);
  const scaleAnim = useRef(new Animated.Value(1)).current;
  const handleFocus = useCallback(() => {
    setIsFocused(true);
    Animated.timing(scaleAnim, { toValue: 1.08, duration: 150, useNativeDriver: true }).start();
  }, [scaleAnim]);
  const handleBlur = useCallback(() => {
    setIsFocused(false);
    Animated.timing(scaleAnim, { toValue: 1, duration: 150, useNativeDriver: true }).start();
  }, [scaleAnim]);
  return (
    <TouchableOpacity
      ref={ref}
      onPress={onPress}
      onFocus={handleFocus}
      onBlur={handleBlur}
      activeOpacity={1}
      hasTVPreferredFocus={hasTVPreferredFocus}
      accessible={true}
      accessibilityRole="button"
      accessibilityLabel="Search movies"
    >
      <Animated.View
        style={[
          styles.searchControl,
          isFocused && styles.searchControlFocused,
          { transform: [{ scale: scaleAnim }] },
        ]}
      >
        <SearchIcon size={24} color={isFocused ? '#00d4aa' : 'rgba(0,212,170,0.75)'} strokeWidth={2} />
        <Text style={[styles.searchControlText, isFocused && styles.searchControlTextFocused]}>SEARCH</Text>
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
    outputRange: [0, 46],
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

  // Thumb travels across 122px track with 24px thumb, 4px padding each side
  const thumbTranslate = thumbAnim.interpolate({
    inputRange: [0, 1, 2],
    outputRange: [0, 45, 90],
  });

  const LABELS = { free: 'SLOP FREE', all: 'SLOP FILTER', only: 'SLOP ONLY' };
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
    day = 'FEST'; rest = 'NOW SCREENING'; color = Colors.screeningGold;
  } else if (stripKey === 'HIGHLIGHTS') {
    day = 'SELECTS'; rest = 'OF NOTE'; color = '#00d4aa';
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
  const [lastFilterNodeHandle, setLastFilterNodeHandle] = useState(null);
  const [lastToggleNodeHandle, setLastToggleNodeHandle] = useState(null);
  // GENRE pulldown overlay (collapses the genre chips behind one control)
  const [genreOverlay, setGenreOverlay] = useState(false);
  // Ref to first rendered movie card — used by the boundary TVFocusGuideView for DOWN from filters
  const [firstMovieRefState, setFirstMovieRefState] = useState(null);

  // First filter button — no longer the wall's UP target (the toggle module is, now
  // that toggles sit in the lower-left directly above the wall).
  const setFirstFilterRef = useCallback((ref) => {}, []);

  // Callback ref for the last control in the bar (SEARCH) — LEFT from the first
  // row's leftmost poster wraps up to it.
  const setLastFilterRef = useCallback((ref) => {
    if (ref) {
      const handle = findNodeHandle(ref);
      if (handle) setLastFilterNodeHandle(handle);
    }
  }, []);

  // Slop toggle (first toggle) — the wall's UP target, so a poster pressing UP
  // lands on the toggles.
  const setFirstToggleRef = useCallback((ref) => {
    if (ref) {
      headerRefObject.current = ref;
      setHeaderNodeHandle(findNodeHandle(ref));
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
    movies,
    filteredMovies,
    isLoading,
    error,
    refreshMovies,
    latestPlaylistUrl,
  } = useHomeScreen();

  // SEARCH opens the full-screen Search route over the FULL movie list
  // (search covers everything, bypassing wall view filters — matches desktop).
  const handleOpenSearch = useCallback(() => {
    returningFromSearchRef.current = true;
    setSearchMovieList(movies);
    navigation.navigate('Search');
  }, [navigation, movies]);

  // Returning from the Search route drops tvOS focus entirely (nothing on the
  // wall is focused, so the remote goes dead — "couldn't reselect search").
  // Re-seed focus onto the SEARCH button itself, one-shot like pendingFocusMIdx.
  const returningFromSearchRef = useRef(false);
  const [searchBtnPreferredFocus, setSearchBtnPreferredFocus] = useState(false);
  useEffect(() => {
    const unsubscribe = navigation.addListener('focus', () => {
      if (!returningFromSearchRef.current) return;
      returningFromSearchRef.current = false;
      setSearchBtnPreferredFocus(true);
    });
    return unsubscribe;
  }, [navigation]);
  useEffect(() => {
    if (!searchBtnPreferredFocus) return;
    const t = setTimeout(() => setSearchBtnPreferredFocus(false), 400);
    return () => clearTimeout(t);
  }, [searchBtnPreferredFocus]);

  // Local state - multi-select filters (Set of active filter IDs)
  const [activeFilters, setActiveFilters] = useState(new Set());
  const [slopMode, setSlopMode] = useState('all'); // 'all' (SLOP FILTER, resting) | 'free' | 'only' — matches desktop 3-state
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
    setSlopMode('all'); // slop resets to its resting default when another view wins (matches desktop)
    setActiveFilters(new Set()); // view toggles are mutually exclusive with genre filters
  }, []);
  const toggleShowHighlights = useCallback(() => showExclusiveView(showHighlightsOnly ? 'none' : 'selects'), [showHighlightsOnly, showExclusiveView]);
  const toggleHideFest = useCallback(() => showExclusiveView(hideFest ? 'fests' : 'none'), [hideFest, showExclusiveView]);
  const toggleShowPreorders = useCallback(() => showExclusiveView(showPreorders ? 'none' : 'preorders'), [showPreorders, showExclusiveView]);
  // Slop toggle cycles all → free → only → all. Every click makes slop the exclusive
  // view: it clears the active genre AND the Selects/Fests/Pre-Orders toggles on every
  // click, regardless of the resulting state (matches desktop setExclusiveView('slop')).
  const cycleSlopMode = useCallback(() => {
    const next = slopMode === 'all' ? 'free' : slopMode === 'free' ? 'only' : 'all';
    setSlopMode(next);
    setActiveFilters(new Set()); // slop toggle is mutually exclusive with genre filters
    setShowHighlightsOnly(false);
    setHideFest(true);
    setShowPreorders(false);
  }, [slopMode]);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  // When set, the movie card with this mIdx claims focus on its next render
  // (used by "MORE" to land on the first newly-loaded film, and by app re-entry
  // to land on the very first film). Cleared shortly after so it doesn't re-grab.
  const [pendingFocusMIdx, setPendingFocusMIdx] = useState(null);

  // Reset to first page whenever filters change
  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [activeFilters, slopMode, hideFest, showPreorders, showHighlightsOnly]);

  // Release the one-shot preferred-focus flag once the target card has had a
  // chance to claim focus, so it won't keep stealing focus on later re-renders.
  useEffect(() => {
    if (pendingFocusMIdx == null) return;
    const t = setTimeout(() => setPendingFocusMIdx(null), 350);
    return () => clearTimeout(t);
  }, [pendingFocusMIdx]);

  // When the app returns to the foreground, reset the wall to the top: first
  // page, scrolled to offset 0, cursor on the first film.
  useEffect(() => {
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') {
        setVisibleCount(PAGE_SIZE);
        flatListRef.current?.scrollToOffset({ offset: 0, animated: false });
        setPendingFocusMIdx(0);
      }
    });
    return () => sub.remove();
  }, []);

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

  // Single-select: a genre replaces any other active genre and is mutually exclusive
  // with the view toggles — only one filter OR one toggle is ever active. Tapping the
  // active filter again clears it (back to the default wall).
  const handleFilterChange = useCallback((filterId) => {
    setActiveFilters(prev => {
      const isOnlyActive = prev.size === 1 && prev.has(filterId);
      trackFilterChange(filterId, Array.from(prev).join(','));
      return isOnlyActive ? new Set() : new Set([filterId]);
    });
    // Picking a genre clears the view toggles.
    setShowHighlightsOnly(false);
    setHideFest(true);
    setShowPreorders(false);
    setSlopMode('all'); // slop resets to its resting default when a genre wins (matches desktop)
  }, []);

  // Get movies based on active filters (multi-select with OR logic - cumulative)
  const displayMovies = useMemo(() => {
    let movies = filteredMovies;

    // Slop mode: free=hide slop, all=show all, only=show only slop (matches desktop 3-state)
    // Fests and pre-orders are always exempt — if you turned them on, you want all of them
    if (slopMode === 'free') {
      movies = movies.filter(m =>
        (!m.is_slop) ||
        (!hideFest && m.filters?.is_virtual_screening) ||
        (showPreorders && m._is_preorder)
      );
    } else if (slopMode === 'only') {
      movies = movies.filter(m =>
        (m.is_slop) ||
        (!hideFest && m.filters?.is_virtual_screening) ||
        (showPreorders && m._is_preorder)
      );
    }

    // Fests view is exclusive: ON => only virtual screenings; OFF => hide them.
    if (hideFest) {
      movies = movies.filter(m => !m.filters?.is_virtual_screening);
    } else {
      movies = movies.filter(m => m.filters?.is_virtual_screening);
    }

    // Pre-order view is exclusive: ON => only pre-orders; OFF => hide them everywhere
    // else (incl. ones also flagged as screenings, so they never bleed into the Fests
    // view). Matches desktop.
    movies = showPreorders
      ? movies.filter(m => m._is_preorder)
      : movies.filter(m => !m._is_preorder);

    // Highlights mode: only staff picks
    if (showHighlightsOnly) {
      movies = movies.filter(m => m.filters?.is_staff_pick || m.featured);
    }

    // If no filters selected, show all
    if (activeFilters.size === 0) {
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
  }, [filteredMovies, activeFilters, slopMode, hideFest, showPreorders, showHighlightsOnly]);

  // Genre-filtered views pack into one continuous grid: no per-date strip rows
  // (a full-width strip over 1-2 filtered cards wastes a row). Each card shows
  // its own small date in the caption instead (MovieCard showDate). Picking a
  // genre clears every view toggle (handleFilterChange), so only the regular
  // bucket can be non-empty while this is true.
  const genrePacked = activeFilters.size > 0;

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
    // FEST availability uses the real screening window (available_start / available_end),
    // NOT the pipeline "active" flag — "active" only means "not expired yet" and wrongly
    // includes future-dated screenings. NOW = open today; UPCOMING = starts later.
    const today = new Date().toISOString().slice(0, 10);
    const vsStart = m => (m.virtual_screening_info?.available_start || '').slice(0, 10);
    const vsEnd = m => (m.virtual_screening_info?.available_end || '').slice(0, 10);
    const isExpired = m =>
      m.virtual_screening_info?.status === 'expired' || (vsEnd(m) && vsEnd(m) < today);
    // Drop screenings whose window has already closed.
    const liveFest = festMovies.filter(m => !isExpired(m));
    // Tier 0 = available now (started, or no start date as a safe fallback); 1 = upcoming.
    const festTier = m => (vsStart(m) && vsStart(m) > today ? 1 : 0);
    const sortedFest = [...liveFest].sort((a, b) => {
      const ta = festTier(a), tb = festTier(b);
      if (ta !== tb) return ta - tb;
      if (ta === 0) return vsEnd(a).localeCompare(vsEnd(b));   // now: soonest to close first
      return vsStart(a).localeCompare(vsStart(b));             // upcoming: soonest to open first
    });
    // Undated ("TBD") pre-orders sort to the end, not the top.
    const sortedPreorders = [...preorderMovies].sort((a, b) => (a.digital_date || '9999-99-99').localeCompare(b.digital_date || '9999-99-99'));
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
        if (festTier(movie) === 0) {
          // Available now → under the NOW SCREENING banner
          items.push({ type: 'movie', id: movie.tmdb_id || movie.id || `fest-${index}`, movie, mIdx: mIdx++, stripKey: 'SCREENING' });
        } else {
          // Upcoming → grouped by the screening's start date
          const d = vsStart(movie) || 'Unknown';
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
      if (!showHighlightsOnly && !genrePacked && movieDate !== currentDate) {
        currentDate = movieDate;
        if (!trailersPushed && SHOW_TRAILERS_CARD) {
          items.push({ type: 'trailers', id: 'new-trailers-button', playlistUrl: latestPlaylistUrl });
          trailersPushed = true;
        }
        items.push({ type: 'date', id: `date-${movieDate}-${index}`, date: movieDate, isBootstrap: !!movie.bootstrap_date });
      }
      items.push({ type: 'movie', id: movie.tmdb_id || movie.id || `movie-${index}`, movie, mIdx: mIdx++, stripKey: showHighlightsOnly ? 'HIGHLIGHTS' : movieDate, showDate: genrePacked });
    });

    if (hasMore) {
      items.push({ type: 'load_more', id: 'load-more', remaining: sortedRegular.length - visibleCount });
    }

    return items;
  }, [displayMovies, latestPlaylistUrl, visibleCount, showHighlightsOnly, slopMode, genrePacked]);

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
    // Back/Menu closes the GENRE overlay (HomeScreen is the stack root, so this
    // doesn't fight navigation — there's nothing to pop here).
    [TV_EVENTS.MENU]: () => {
      setGenreOverlay((open) => (open ? false : open));
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

  // Date strips adopt the active view toggle's color (SELECTS teal, FESTS gold,
  // SLOP ONLY orange); otherwise a single active category filter; otherwise teal
  const singleFilter = activeFilters.size === 1 ? Array.from(activeFilters)[0] : null;
  const dateStripColor = showHighlightsOnly
    ? '#00d4aa'
    : showPreorders
    ? '#7c3aed'
    : !hideFest
    ? Colors.screeningGold
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
              onPress={() => {
                // Films get sequential mIdx in list order, so the first new film
                // is one past the current highest mIdx. Focus it after expanding.
                const lastIdxRow = movieGrid.rowsOfIdx[movieGrid.rowsOfIdx.length - 1];
                const maxMIdx = lastIdxRow ? lastIdxRow[lastIdxRow.length - 1] : -1;
                setPendingFocusMIdx(maxMIdx + 1);
                setVisibleCount(prev => prev + PAGE_SIZE);
              }}
              nextFocusUp={loadMoreUpHandle}
            />
          </View>
        );
      }

      // Row of movie cards — focus neighbors derived from (row, col) in movieGrid
      return (
        <View style={styles.movieRow}>
          {item.items.map(({ movie, mIdx, id, showDate }) => {
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

            // Each day is its own navigation block. Within a day, up/down is
            // column-preserving (clamped to the row width). At a day's edge, down
            // lands on the next day's first poster (top-left) and up on the previous
            // day's last poster — a clean hop instead of a column-preserving vault.
            // Packed genre views have no day blocks (one continuous grid), so
            // navigation stays column-preserving throughout.
            const thisDay = thisRow.length ? stripKeyByIdx[thisRow[0]] : null;
            const rowStartsDay = !genrePacked && (!prevRow || stripKeyByIdx[prevRow[0]] !== thisDay);
            const rowEndsDay = !genrePacked && (!nextRow || stripKeyByIdx[nextRow[0]] !== thisDay);

            const nextFocusUp = isFirstMovieRow
              ? undefined
              : (prevRow
                  ? itemNodeHandles.get(rowStartsDay ? prevRow[prevRow.length - 1] : prevRow[Math.min(colIdx, prevRow.length - 1)])
                  : headerNodeHandle);

            const nextFocusDown = nextRow
              ? itemNodeHandles.get(rowEndsDay ? nextRow[0] : nextRow[Math.min(colIdx, nextRow.length - 1)])
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
                  hasTVPreferredFocus={(giveInitialFocus && isFirstMovie) || pendingFocusMIdx === mIdx}
                  showDate={showDate}
                  testID={`movie-card-${mIdx}`}
                  nextFocusUp={nextFocusUp}
                  nextFocusDown={nextFocusDown}
                  nextFocusLeft={nextFocusLeft}
                  nextFocusRight={nextFocusRight}
                />
              </View>
            );
          })}
          {/* Fill a partial row's trailing empty cells with focus guides that redirect into
              THIS row's posters. Stops DOWN from the row above spatial-skipping past a short
              day to a later date (tvOS ignores the cards' own nextFocusDown across rows). */}
          {item.items.length < NUM_COLUMNS && (() => {
            const lastMIdx = item.items[item.items.length - 1].mIdx;
            const dest = itemRefsMap.current.get(lastMIdx);
            return Array.from({ length: NUM_COLUMNS - item.items.length }).map((_, i) => (
              <TVFocusGuideView
                key={`fill-${item.items[0].mIdx}-${i}`}
                style={styles.cellFiller}
                destinations={dest ? [dest] : []}
              />
            ));
          })()}
        </View>
      );
    },
    [movieGrid, stripKeyByIdx, dateStripColor, genrePacked, handleMovieSelect, handleMovieFocus, handleMovieBlur, handleOpenFullscreen, headerNodeHandle, lastFilterNodeHandle, itemNodeHandles, registerItemRef, registerWrapperRef, giveInitialFocus, pendingFocusMIdx]
  );

  // Key extractor
  const keyExtractor = useCallback((item) => item.id, []);

  // GENRE pulldown: the single active genre (if any) and the control's label
  const activeGenreId = activeFilters.size ? [...activeFilters][0] : null;
  const genreControlLabel = activeGenreId
    ? (FILTERS.find((f) => f.id === activeGenreId)?.label || 'Genre').toUpperCase()
    : 'GENRE';

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

  // Render empty state (search lives on its own full-screen route now, so an
  // empty list here can only mean no data).
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
      {/* Header: masthead = wordmark + slogan only; below it one control bar:
          SLOP FILTER · SELECTS · FESTS · PRE-ORDER · GENRE · SEARCH (matches web) */}
      <View style={styles.header}>
        <View style={styles.headerTopRow}>
          <View>
            <Text style={styles.headerTitle}>THE NEW RELEASE WALL</Text>
            <Text style={styles.headerSlogan}>What came out, every day.</Text>
          </View>
        </View>
        <View style={styles.controlBar}>
          <View style={styles.barCell}>
            <SlopToggle ref={setFirstToggleRef} slopMode={slopMode} onPress={cycleSlopMode} />
          </View>
          <View style={styles.barDivider} />
          <View style={styles.barCell}>
            <MetaToggle
              isActive={showHighlightsOnly}
              label="SELECTS"
              accentColor="#00d4aa"
              accessibilityLabel={showHighlightsOnly ? 'Showing selects only' : 'Showing all movies'}
              onPress={toggleShowHighlights}
            />
          </View>
          <View style={styles.barDivider} />
          <View style={styles.barCell}>
            <MetaToggle
              isActive={!hideFest}
              label="FESTS"
              accentColor={Colors.screeningGold}
              accessibilityLabel={hideFest ? 'Virtual screenings hidden' : 'Showing virtual screenings'}
              onPress={toggleHideFest}
            />
          </View>
          <View style={styles.barDivider} />
          <View style={styles.barCell}>
            <MetaToggle
              ref={setLastToggleRef}
              isActive={showPreorders}
              label="PRE-ORDER"
              accentColor="#7c3aed"
              accessibilityLabel={showPreorders ? 'Showing pre-orders' : 'Pre-orders hidden'}
              onPress={toggleShowPreorders}
            />
          </View>
          <View style={styles.barDivider} />
          <View style={styles.barCell}>
            <GenreControl
              label={genreControlLabel}
              isActive={!!activeGenreId}
              onPress={() => setGenreOverlay(true)}
            />
          </View>
          <View style={styles.barDivider} />
          <View style={styles.barCell}>
            <SearchButton ref={setLastFilterRef} onPress={handleOpenSearch} hasTVPreferredFocus={searchBtnPreferredFocus} />
          </View>
        </View>
      </View>

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

      {/* Vertical scrolling grid - the wall. */}
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

      {/* GENRE pulldown overlay — chips for the genre filter (Back/Menu closes it) */}
      {genreOverlay && (
        <View style={styles.genreOverlayBackdrop}>
          <View style={styles.genrePanel}>
            {FILTERS.map((filter, idx) => (
              <FilterButton
                key={filter.id}
                filter={filter}
                isActive={activeFilters.has(filter.id)}
                hasTVPreferredFocus={idx === 0}
                onPress={() => { handleFilterChange(filter.id); setGenreOverlay(false); }}
                style={styles.genreChip}
              />
            ))}
            <FilterButton
              filter={{ id: '__clear', label: '✕ Clear' }}
              isActive={false}
              onPress={() => { if (activeGenreId) handleFilterChange(activeGenreId); setGenreOverlay(false); }}
              style={styles.genreClear}
            />
          </View>
        </View>
      )}
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
    paddingTop: 18,
    paddingBottom: 4,
  },
  headerTopRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  headerTitle: {
    color: Colors.textPrimary,
    fontSize: 90,
    fontWeight: '100',
    letterSpacing: 9,
  },
  headerSlogan: {
    // Tracked caps echoing the wordmark's rhythm (matches web fused-strip design)
    color: 'rgba(0,212,170,0.8)',
    fontSize: 22,
    fontWeight: '500',
    letterSpacing: 6,
    textTransform: 'uppercase',
    marginTop: 6,
  },
  filterRow: {
    flexDirection: 'row',
    flex: 1,
    alignItems: 'center',
    gap: 8,
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
    gap: 18,
    justifyContent: 'center',
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.16)',
    borderRadius: 16,
    paddingVertical: 18,
    paddingHorizontal: 32,
  },
  toggleModuleRow: {
    flexDirection: 'row',
    gap: 34,
    alignItems: 'center',
  },
  filterColumn: {
    flex: 1,
    flexDirection: 'column',
    gap: 8,
    justifyContent: 'center',
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
  // GENRE pulldown control (sits at the end of the one control row) — quiet teal
  // outline pill + caret, matching the desktop .genre-control.
  genreControl: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingVertical: 12,
    paddingHorizontal: 26,
    borderRadius: 24,
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: 'rgba(0,212,170,0.35)',
  },
  genreControlActive: { borderColor: 'rgba(0,212,170,0.55)' },
  genreControlFocused: { borderColor: '#00d4aa', borderWidth: 2 },
  genreControlText: { fontSize: 22, fontWeight: '700', letterSpacing: 2, color: 'rgba(0,212,170,0.75)' },
  genreControlTextActive: { color: '#00d4aa' },
  genreControlCaret: { fontSize: 16, color: 'rgba(0,212,170,0.75)' },
  // SEARCH button (far right of the control row) — glass icon + label, quiet teal
  // pill matching the GENRE control. Select opens the full-screen Search route.
  searchControl: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    paddingVertical: 12,
    paddingHorizontal: 26,
    borderRadius: 24,
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: 'rgba(0,212,170,0.35)',
  },
  searchControlFocused: {
    borderColor: '#00d4aa',
    borderWidth: 2,
    backgroundColor: 'rgba(0,212,170,0.08)',
  },
  searchControlText: { fontSize: 22, fontWeight: '700', letterSpacing: 2, color: 'rgba(0,212,170,0.75)' },
  searchControlTextFocused: { color: '#00d4aa' },
  // One filled control row (toggles + GENRE + SEARCH), distributed across the width
  controlBar: {
    // Open row (fused-strip design, matches web): no box — the first date
    // strip below acts as the row's bottom line
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: 'transparent',
    paddingVertical: 6,
    paddingHorizontal: 4,
    marginTop: 2,
  },
  barDivider: {
    width: 0,
    height: 36,
    backgroundColor: 'transparent',
  },
  // Each toggle/genre occupies an equal cell so they fill the bar evenly
  // (no clumped negative space between pills).
  barCell: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  // GENRE overlay — dropdown panel anchored under the GENRE control (top-right),
  // matching the desktop .genre-pop.
  genreOverlayBackdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.2)',
  },
  // Horizontal strip just below the bar — one row of chips, short, blocks
  // minimal posters.
  genrePanel: {
    position: 'absolute',
    top: 232,
    left: 60,
    right: 60,
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: 12,
    backgroundColor: '#14141f',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.16)',
    borderRadius: 16,
    paddingVertical: 16,
    paddingHorizontal: 22,
  },
  genreChip: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 11,
    paddingHorizontal: 22,
    borderRadius: 22,
    backgroundColor: 'rgba(255,255,255,0.08)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.35)',
  },
  genreClear: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 11,
    paddingHorizontal: 22,
    borderRadius: 22,
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.25)',
  },
  metaToggleWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  metaToggleLabel: {
    fontSize: 22,
    fontWeight: '700',
    letterSpacing: 1.4,
    color: 'rgba(0,212,170,0.75)',  // 0.45 was 2.8:1 — below the 3:1 large-text floor at 10ft
  },
  metaToggleLabelActive: {
    color: '#00d4aa',
  },
  slopToggleTrack: {
    width: 122,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#1a1a1a',
    borderWidth: 1,
    borderColor: 'rgba(0,212,170,0.45)',
    justifyContent: 'center',
    paddingHorizontal: 4,
  },
  slopToggleThumb: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: 'rgba(0,212,170,0.55)',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.4,
    shadowRadius: 3,
  },
  metaToggleTrack: {
    width: 88,
    height: 42,
    borderRadius: 21,
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
    width: 34,
    height: 34,
    borderRadius: 17,
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
  dateStripRestSection: { fontSize: 54, fontWeight: '400' },
  cardWrapper: {
    marginRight: CARD_GAP,
    overflow: 'visible',
    zIndex: 1,
  },
  // Invisible focus-redirect placeholder occupying an empty trailing cell of a partial row.
  cellFiller: {
    width: CARD_WIDTH,
    height: CARD_HEIGHT,
    marginRight: CARD_GAP,
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
});

export default HomeScreenTvOS;
