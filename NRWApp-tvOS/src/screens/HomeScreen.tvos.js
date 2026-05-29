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
  { id: 'foreign', label: 'Foreign' },
  { id: 'documentary', label: 'Docs' },
  { id: 'restorations', label: 'Reissues' },
];

// Filter Button Component - forwardRef to allow focus navigation from grid
const FilterButton = forwardRef(({ filter, isActive, onPress, onFocus }, ref) => {
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
      onPress={onPress}
      onFocus={handleFocus}
      onBlur={handleBlur}
      activeOpacity={1}
      accessible={true}
      accessibilityLabel={`Filter by ${filter.label}`}
      accessibilityRole="button"
      accessibilityState={{ selected: isActive }}
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
const MetaToggle = forwardRef(({ isActive, offLabel, onLabel, accessibilityLabel, onPress, nextFocusUp }, ref) => {
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
    outputRange: [0, 36],
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
    >
      <Animated.View style={[styles.metaToggleWrap, { transform: [{ scale: scaleAnim }] }]}>
        <Text style={[styles.metaToggleLabel, isActive && styles.metaToggleLabelActive]}>
          {isActive ? onLabel : offLabel}
        </Text>
        <View style={[
          styles.metaToggleTrack,
          isActive && styles.metaToggleTrackActive,
          isFocused && styles.metaToggleTrackFocused,
        ]}>
          <Animated.View style={[styles.metaToggleThumb, { transform: [{ translateX: thumbTranslate }] }]} />
        </View>
      </Animated.View>
    </TouchableOpacity>
  );
});

// Date Card Component - non-focusable visual divider
const DateCard = ({ dateParts }) => {
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
      <View style={styles.dateCard}>
        {/* Top bar */}
        <View style={[styles.dateBar, { backgroundColor: barColor }]}>
          <Text style={styles.dateBarText}>
            {isPreOrder ? 'PRE-ORDER' : isFest ? 'FEST' : dateParts.dayName}
          </Text>
        </View>

        {/* Body */}
        <View style={styles.dateBody}>
          <Text style={[styles.dateNumber, { color: (isPreOrder || isFest) ? accentColor : '#fff' }]}>
            {isPreOrder ? 'SOON' : isFest ? 'NOW' : dateParts.day}
          </Text>
          {!isPreOrder && !isFest && dateParts.month ? (
            <Text style={styles.dateMonth}>{dateParts.month}</Text>
          ) : null}
          {/* Cascading chevrons */}
          <View style={styles.dateChevrons}>
            {[1, 0.6, 0.3].map((opacity, i) => (
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

const HomeScreenTvOS = () => {
  const navigation = useNavigation();
  const flatListRef = useRef(null);
  const initialFocusDone = useRef(false);  // Prevents hasTVPreferredFocus re-firing on listData changes
  const [headerNodeHandle, setHeaderNodeHandle] = useState(null);
  const [toggleNodeHandle, setToggleNodeHandle] = useState(null);

  // Callback ref for first filter button
  const setFirstFilterRef = useCallback((ref) => {
    if (ref) {
      const handle = findNodeHandle(ref);
      setHeaderNodeHandle(handle);
    }
  }, []);

  // Callback ref for slop toggle — this is what movie cards navigate UP to
  const setFirstToggleRef = useCallback((ref) => {
    if (ref) {
      const handle = findNodeHandle(ref);
      setToggleNodeHandle(handle);
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
  const [slopFree, setSlopFree] = useState(true);
  const [hideFest, setHideFest] = useState(false);
  const [showPreorders, setShowPreorders] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [searchFocused, setSearchFocused] = useState(false);

  // Fullscreen poster modal state
  const [fullscreenVisible, setFullscreenVisible] = useState(false);
  const [fullscreenIndex, setFullscreenIndex] = useState(0);

  // Grid item refs for wrap-around navigation
  const itemRefsMap = useRef(new Map());  // Map of index -> ref
  const [itemNodeHandles, setItemNodeHandles] = useState(new Map());  // Map of index -> node handle

  // Register item ref for wrap-around navigation
  const registerItemRef = useCallback((index, ref) => {
    if (ref) {
      itemRefsMap.current.set(index, ref);
    } else {
      itemRefsMap.current.delete(index);
    }
  }, []);

  // Update node handles after layout is complete using InteractionManager
  useEffect(() => {
    const handle = InteractionManager.runAfterInteractions(() => {
      const newHandles = new Map();
      itemRefsMap.current.forEach((ref, index) => {
        const nodeHandle = findNodeHandle(ref);
        if (nodeHandle) {
          newHandles.set(index, nodeHandle);
        }
      });
      setItemNodeHandles(newHandles);
    });
    return () => handle.cancel();
  }, [filteredMovies]);

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

    // Slop-free mode: hide flagged films
    if (slopFree) {
      movies = movies.filter(m => !m.is_slop && !m._is_slop_guess);
    }

    // Hide-fest mode: hide virtual screenings
    if (hideFest) {
      movies = movies.filter(m => !m.categories?.is_virtual_screening);
    }

    // Pre-orders: only show when toggle is ON or search is active
    if (!showPreorders && !searchQuery) {
      movies = movies.filter(m => !m._is_preorder);
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
            if (movie.categories?.is_indie || movie.categories?.tier === 'indie') return true;
            break;
          case 'staff-picks':
            if (movie.categories?.is_staff_pick || movie.featured) return true;
            break;
          case 'foreign': {
            const isForeign = movie.categories?.is_foreign ??
              (movie.original_language && movie.original_language !== 'en');
            if (isForeign) return true;
            break;
          }
          case 'documentary':
            if (movie.categories?.is_documentary === true) return true;
            break;
          case 'restorations':
            if (movie.categories?.is_restoration) return true;
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
        }
      }
      return false;
    });
  }, [filteredMovies, activeFilters, slopFree, hideFest, showPreorders, searchQuery]);

  // Build flat list data with date markers interspersed
  // Each date marker takes one grid cell (same size as movie card)
  const listData = useMemo(() => {
    if (!displayMovies || displayMovies.length === 0) return [];

    // Split into three buckets: fest (virtual screenings), pre-orders, regular
    const festMovies = displayMovies.filter(m => !m._is_preorder && m.categories?.is_virtual_screening);
    const preorderMovies = displayMovies.filter(m => m._is_preorder);
    const regularMovies = displayMovies.filter(m => !m._is_preorder && !m.categories?.is_virtual_screening);

    // Sort each bucket
    const byDateDesc = (a, b) => (b.digital_date || '0000-00-00').localeCompare(a.digital_date || '0000-00-00');
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
    let currentDate = null;
    let trailersPushed = false;
    sortedRegular.forEach((movie, index) => {
      const movieDate = movie.digital_date || 'Unknown';
      if (movieDate !== currentDate) {
        currentDate = movieDate;
        if (!trailersPushed && SHOW_TRAILERS_CARD) {
          items.push({ type: 'trailers', id: 'new-trailers-button', playlistUrl: latestPlaylistUrl });
          trailersPushed = true;
        }
        items.push({ type: 'date', id: `date-${movieDate}-${index}`, date: movieDate });
      }
      items.push({ type: 'movie', id: movie.tmdb_id || movie.id || `movie-${index}`, movie });
    });

    return items;
  }, [displayMovies, latestPlaylistUrl]);

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

  // Handle movie focus
  const handleMovieFocus = useCallback((movie, index) => {
    trackMovieFocus(movie, 0, index);
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
      // Items in first row should navigate up to slop toggle (then up again → filter chips)
      const isFirstRow = index < NUM_COLUMNS;
      const focusUpTarget = isFirstRow ? toggleNodeHandle : undefined;

      // NEW TRAILERS button
      if (item.type === 'trailers') {
        return (
          <View style={styles.cardWrapper}>
            <TrailersCard playlistUrl={item.playlistUrl} nextFocusUp={focusUpTarget} />
          </View>
        );
      }

      // Date marker
      if (item.type === 'date') {
        const dateParts = formatDateParts(item.date);
        return (
          <View style={styles.cardWrapper}>
            <DateCard dateParts={dateParts} />
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

      // Find nearest focusable handle within the same row as pivotIndex,
      // scanning right from pivot first, then left — produces the "slide" effect
      const findNearestInRow = (pivotIndex) => {
        const rowStart = Math.floor(pivotIndex / NUM_COLUMNS) * NUM_COLUMNS;
        const rowEnd = Math.min(rowStart + NUM_COLUMNS - 1, listData.length - 1);
        for (let i = pivotIndex; i <= rowEnd; i++) {
          const handle = itemNodeHandles.get(i);
          if (handle) return handle;
        }
        for (let i = pivotIndex - 1; i >= rowStart; i--) {
          const handle = itemNodeHandles.get(i);
          if (handle) return handle;
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

      // LEFT: wrap at row start, or skip a date card in the previous cell
      const nextFocusLeft = isRowStart
        ? (index > 0 ? findNearestHandle(index - 1, -1) : undefined)
        : (leftNeighbor && leftNeighbor.type === 'date' ? findNearestHandle(index - 2, -1) : undefined);

      // DOWN: if date card is directly below, slide into that row at the nearest movie
      const nextFocusDown = (belowItem && belowItem.type === 'date')
        ? findNearestInRow(index + NUM_COLUMNS)
        : undefined;

      // UP: if date card is directly above, slide into that row at the nearest movie;
      //     fall back to toggle when the date card is in the first row (nothing above it)
      const nextFocusUpVertical = (!isFirstRow && aboveItem && aboveItem.type === 'date')
        ? (findNearestInRow(index - NUM_COLUMNS) || toggleNodeHandle)
        : undefined;

      // Movie card
      return (
        <View style={styles.cardWrapper}>
          <MovieCard
            ref={(ref) => registerItemRef(index, ref)}
            movie={item.movie}
            onSelect={() => handleMovieSelect(item.movie)}
            onLongPress={() => handleOpenFullscreen(item.movie)}
            onFocus={() => handleMovieFocus(item.movie, index)}
            hasTVPreferredFocus={giveInitialFocus && index === (SHOW_TRAILERS_CARD ? 2 : 1)}
            testID={`movie-card-${index}`}
            nextFocusUp={isFirstRow ? toggleNodeHandle : nextFocusUpVertical}
            nextFocusDown={nextFocusDown}
            nextFocusLeft={nextFocusLeft}
            nextFocusRight={nextFocusRight}
          />
        </View>
      );
    },
    [formatDateParts, handleMovieSelect, handleMovieFocus, handleOpenFullscreen, headerNodeHandle, toggleNodeHandle, itemNodeHandles, listData, registerItemRef, giveInitialFocus]
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
      {/* Header: two rows — top has title/filters/search, bottom has toggles (closest to movies) */}
      <View style={styles.header}>
        {/* Top row */}
        <View style={styles.headerTopRow}>
          <Text style={styles.headerTitle}>THE NEW RELEASE WALL</Text>
          <View style={styles.filterRow}>
            {FILTERS.map((filter, index) => (
              <FilterButton
                key={filter.id}
                ref={index === 0 ? setFirstFilterRef : undefined}
                filter={filter}
                isActive={activeFilters.has(filter.id)}
                onPress={() => handleFilterChange(filter.id)}
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
        {/* Toggle row — sits directly above movies, gets focus first on up-press */}
        <View style={styles.toggleRow}>
          <MetaToggle
            ref={setFirstToggleRef}
            isActive={slopFree}
            offLabel="WITH SLOP"
            onLabel="SLOP FREE"
            accessibilityLabel={slopFree ? 'Slop Free active' : 'Showing all films'}
            onPress={() => setSlopFree(v => !v)}
            nextFocusUp={headerNodeHandle}
          />
          <MetaToggle
            isActive={hideFest}
            offLabel="WITH FEST"
            onLabel="NO FEST"
            accessibilityLabel={hideFest ? 'Virtual screenings hidden' : 'Showing virtual screenings'}
            onPress={() => setHideFest(v => !v)}
            nextFocusUp={headerNodeHandle}
          />
          <MetaToggle
            isActive={showPreorders}
            offLabel="NO PRE-ORDERS"
            onLabel="PRE-ORDERS"
            accessibilityLabel={showPreorders ? 'Showing pre-orders' : 'Pre-orders hidden'}
            onPress={() => setShowPreorders(v => !v)}
            nextFocusUp={headerNodeHandle}
          />
        </View>
      </View>

      {/* Vertical scrolling grid - the wall */}
      <FlatList
        ref={flatListRef}
        data={listData}
        renderItem={renderItem}
        keyExtractor={keyExtractor}
        numColumns={NUM_COLUMNS}
        showsVerticalScrollIndicator={false}
        contentContainerStyle={styles.listContent}
        columnWrapperStyle={styles.row}
        removeClippedSubviews={true}
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
    marginBottom: 10,
  },
  headerTitle: {
    color: Colors.textPrimary,
    fontSize: 44,
    fontWeight: '100',
    letterSpacing: 8,
  },
  filterRow: {
    flexDirection: 'row',
    gap: 12,
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
    paddingHorizontal: 16,
    paddingVertical: 6,
    borderRadius: 20,
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.2)',
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
    fontSize: 16,
    fontWeight: '500',
  },
  filterButtonTextActive: {
    color: Colors.background,
    fontWeight: '600',
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
    gap: 32,
    paddingBottom: 4,
  },
  metaToggleWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
  },
  metaToggleLabel: {
    fontSize: 16,
    fontWeight: '700',
    letterSpacing: 1.5,
    color: 'rgba(0,212,170,0.45)',
  },
  metaToggleLabelActive: {
    color: '#00d4aa',
  },
  metaToggleTrack: {
    width: 80,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#1a1a1a',
    borderWidth: 1,
    borderColor: 'rgba(0,212,170,0.3)',
    justifyContent: 'center',
    paddingHorizontal: 5,
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
