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

// Filter options - matches web categories
const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'big-time', label: 'Big Time Stuff' },
  { id: 'niche', label: 'Niche Notables' },
  { id: 'staff-picks', label: 'Staff Picks' },
  { id: 'foreign', label: 'Foreign' },
  { id: 'series', label: 'Limited Series' },
  { id: 'festivals', label: 'Festivals' },
  { id: 'restorations', label: 'Restorations' },
  { id: 'plex', label: 'Plex' },
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

// Date Card Component - non-focusable visual divider
const DateCard = ({ dateParts }) => {
  return (
    <View
      accessible={true}
      accessibilityLabel={`${dateParts.dayName} ${dateParts.month} ${dateParts.day}`}
      accessibilityRole="text"
    >
      <View style={styles.dateCard}>
        <View style={styles.dateCardInner}>
          <Text style={styles.dateDayName}>{dateParts.dayName}</Text>
          <Text style={styles.dateNumber}>{dateParts.day}</Text>
          <Text style={styles.dateMonth}>{dateParts.month}</Text>
        </View>
      </View>
    </View>
  );
};

// Grid configuration - 8 columns for 1920px width
const NUM_COLUMNS = 8;
const CARD_WIDTH = Dimensions.tvos.cardWidth;
const CARD_HEIGHT = Dimensions.tvos.cardHeight;
const CARD_GAP = 16;

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
  const [headerNodeHandle, setHeaderNodeHandle] = useState(null);

  // Callback ref for "All" filter button - sets node handle immediately when ref is populated
  const setAllFilterRef = useCallback((ref) => {
    if (ref) {
      const handle = findNodeHandle(ref);
      setHeaderNodeHandle(handle);
    }
  }, []);

  // Get shared state and actions
  const {
    filteredMovies,
    isLoading,
    error,
    refreshMovies,
    latestPlaylistUrl,
  } = useHomeScreen();

  // Local state - multi-select filters (Set of active filter IDs)
  const [activeFilters, setActiveFilters] = useState(new Set());
  const [isRefreshing, setIsRefreshing] = useState(false);

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

      if (filterId === 'all') {
        // "All" clears all other filters
        newFilters.clear();
      } else {
        // Toggle this filter on/off
        if (newFilters.has(filterId)) {
          newFilters.delete(filterId);
        } else {
          newFilters.add(filterId);
        }
      }

      trackFilterChange(filterId, Array.from(prev).join(','));
      return newFilters;
    });
  }, []);

  // Get movies based on active filters (multi-select with OR logic - cumulative)
  const displayMovies = useMemo(() => {
    // If no filters selected, show all
    if (activeFilters.size === 0) {
      return filteredMovies;
    }

    // Filter movies - must pass ANY selected filter (OR logic)
    return filteredMovies.filter(movie => {
      for (const filter of activeFilters) {
        switch (filter) {
          case 'big-time':
            if (movie.categories?.tier === 'big_time') return true;
            break;
          case 'niche':
            if (movie.categories?.tier === 'niche') return true;
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
          case 'series':
            if (movie.content_type === 'limited_series') return true;
            break;
          case 'plex':
            if (movie.plex && movie.plex.deep_link) return true;
            break;
          case 'festivals':
            if (movie.categories?.is_festival) return true;
            break;
          case 'restorations':
            if (movie.categories?.is_restoration) return true;
            break;
        }
      }
      return false;
    });
  }, [filteredMovies, activeFilters]);

  // Build flat list data with date markers interspersed
  // Each date marker takes one grid cell (same size as movie card)
  const listData = useMemo(() => {
    if (!displayMovies || displayMovies.length === 0) return [];

    // Sort movies by digital_date descending (newest first)
    const sorted = [...displayMovies].sort((a, b) => {
      const dateA = a.digital_date || '0000-00-00';
      const dateB = b.digital_date || '0000-00-00';
      return dateB.localeCompare(dateA);
    });

    const items = [];
    let currentDate = null;
    let isFirstDate = true;

    sorted.forEach((movie, index) => {
      const movieDate = movie.digital_date || 'Unknown';

      // Insert date marker when date changes
      if (movieDate !== currentDate) {
        currentDate = movieDate;

        // Add NEW TRAILERS button before the first date
        if (isFirstDate) {
          items.push({
            type: 'trailers',
            id: 'new-trailers-button',
            playlistUrl: latestPlaylistUrl,
          });
          isFirstDate = false;
        }

        items.push({
          type: 'date',
          id: `date-${movieDate}-${index}`,
          date: movieDate,
        });
      }

      items.push({
        type: 'movie',
        id: movie.tmdb_id || movie.id || `movie-${index}`,
        movie: movie,
      });
    });

    return items;
  }, [displayMovies, latestPlaylistUrl]);

  // Handle movie selection - navigate to detail with analytics
  const handleMovieSelect = useCallback(
    (movie) => {
      trackMovieSelect(movie);
      navigation.navigate('MovieDetail', { movie });
    },
    [navigation]
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

  // Render item (date marker, trailers button, or movie card)
  const renderItem = useCallback(
    ({ item, index }) => {
      // Items in first row should navigate up to header buttons
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

      // Get node handles for wrap-around targets
      const nextFocusRight = isRowEnd ? itemNodeHandles.get(index + 1) : undefined;
      const nextFocusLeft = isRowStart && index > 0 ? itemNodeHandles.get(index - 1) : undefined;

      // Movie card
      return (
        <View style={styles.cardWrapper}>
          <MovieCard
            ref={(ref) => registerItemRef(index, ref)}
            movie={item.movie}
            onSelect={() => handleMovieSelect(item.movie)}
            onLongPress={() => handleOpenFullscreen(item.movie)}
            onFocus={() => handleMovieFocus(item.movie, index)}
            hasTVPreferredFocus={index === 2} // First movie after trailers + first date marker
            testID={`movie-card-${index}`}
            nextFocusUp={focusUpTarget}
            nextFocusLeft={nextFocusLeft}
            nextFocusRight={nextFocusRight}
          />
        </View>
      );
    },
    [formatDateParts, handleMovieSelect, handleMovieFocus, handleOpenFullscreen, headerNodeHandle, itemNodeHandles, registerItemRef]
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
      {/* Header with title on left, filters and search on right */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>THE NEW RELEASE WALL</Text>
        <View style={styles.filterRow}>
            {FILTERS.map((filter, index) => (
              <FilterButton
                key={filter.id}
                ref={index === 0 ? setAllFilterRef : undefined}  // First button ("All") gets callback ref
                filter={filter}
                isActive={filter.id === 'all' ? activeFilters.size === 0 : activeFilters.has(filter.id)}
                onPress={() => handleFilterChange(filter.id)}
              />
            ))}
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
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 64,
    paddingTop: 28,
    paddingBottom: 16,
  },
  headerTitle: {
    color: Colors.primary,
    fontSize: 44,
    fontWeight: '600',
    letterSpacing: 8,
  },
  filterRow: {
    flexDirection: 'row',
    gap: 12,
  },
  searchIcon: {
    color: 'rgba(255, 255, 255, 0.6)',
    fontSize: 24,
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
  listContent: {
    // Center the 8-column grid: (1920 - 8*210 - 7*16) / 2 = 64px
    paddingHorizontal: 64,
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
    borderWidth: 3,
    borderColor: Colors.primary,
    backgroundColor: Colors.background,
    justifyContent: 'center',
    alignItems: 'center',
    overflow: 'hidden',
  },
  dateCardFocused: {
    borderColor: '#00ffcc',
    borderWidth: 4,
    backgroundColor: 'rgba(0, 212, 170, 0.1)',
  },
  dateCardInner: {
    alignItems: 'center',
  },
  dateDayName: {
    color: '#999999',
    fontSize: 14,
    letterSpacing: 2,
    marginBottom: 4,
  },
  dateNumber: {
    color: Colors.primary,
    fontSize: 64,
    fontWeight: 'bold',
    lineHeight: 72,
  },
  dateMonth: {
    color: Colors.primary,
    fontSize: 24,
    fontWeight: 'bold',
    letterSpacing: 4,
    marginTop: 6,
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
