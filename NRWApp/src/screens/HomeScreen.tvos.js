/**
 * New Release Wall - tvOS Home Screen
 * Vertical scrolling grid layout matching web design
 */

import React, { useState, useCallback, useRef, useEffect, useMemo } from 'react';
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
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { useHomeScreen } from './useHomeScreen';
import MovieCard from '../components/MovieCard.tvos';
import { Colors, Typography, Spacing, Dimensions } from '../constants/colors';
import { useTVEventHandler, TV_EVENTS } from '../utils/focusManager.tvos';
import {
  trackScreenView,
  trackMovieFocus,
  trackMovieSelect,
  trackFilterChange,
} from '../services/analytics.tvos';

// Filter options
const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'featured', label: 'Featured' },
  { id: 'foreign', label: 'Foreign' },
  { id: 'series', label: 'Mini-Series' },
];

// Filter Button Component
const FilterButton = ({ filter, isActive, onPress, onFocus }) => {
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
};

// Grid configuration - 7 columns for 1920px width
const NUM_COLUMNS = 7;
const CARD_WIDTH = Dimensions.tvos.cardWidth;
const CARD_HEIGHT = Dimensions.tvos.cardHeight;
const CARD_GAP = 16;

// Trailers Card Component with focus animations
const TrailersCard = ({ playlistUrl }) => {
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
      accessibilityLabel="New Trailers - Opens YouTube playlist"
      accessibilityRole="button"
    >
      <Animated.View
        style={[
          styles.trailersCard,
          { transform: [{ scale: scaleAnim }] },
        ]}
      >
        <Text style={styles.trailersText}>NEW</Text>
        <Text style={styles.trailersText}>TRAILERS</Text>
        {isFocused && <View style={styles.trailersFocusBorder} />}
      </Animated.View>
    </TouchableOpacity>
  );
};

const HomeScreenTvOS = () => {
  const navigation = useNavigation();
  const flatListRef = useRef(null);

  // Get shared state and actions
  const {
    filteredMovies,
    isLoading,
    error,
    activeFilter,
    changeFilter,
    refreshMovies,
    latestPlaylistUrl,
  } = useHomeScreen();

  // Local state
  const [isRefreshing, setIsRefreshing] = useState(false);
  const previousFilterRef = useRef(activeFilter);

  // Track screen view on mount
  useEffect(() => {
    trackScreenView('Home', { filter: activeFilter });
  }, []);

  // Handle filter change
  const handleFilterChange = useCallback((filterId) => {
    trackFilterChange(filterId, previousFilterRef.current);
    previousFilterRef.current = filterId;
    changeFilter(filterId);
  }, [changeFilter]);

  // Get movies based on active filter
  const displayMovies = useMemo(() => {
    if (activeFilter === 'featured') {
      return filteredMovies.filter(m => m.featured);
    }
    if (activeFilter === 'foreign') {
      // Foreign = non-English original language films
      return filteredMovies.filter(m => {
        const lang = m.original_language;
        // Include if original_language exists and is not English
        return lang && lang !== 'en';
      });
    }
    if (activeFilter === 'series') {
      // Limited series / miniseries only
      return filteredMovies.filter(m => m.content_type === 'limited_series');
    }
    return filteredMovies;
  }, [filteredMovies, activeFilter]);

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
      // NEW TRAILERS button
      if (item.type === 'trailers') {
        return (
          <View style={styles.cardWrapper}>
            <TrailersCard playlistUrl={item.playlistUrl} />
          </View>
        );
      }

      // Date marker
      if (item.type === 'date') {
        const dateParts = formatDateParts(item.date);
        return (
          <View style={styles.dateCard}>
            <View style={styles.dateCardInner}>
              <Text style={styles.dateDayName}>{dateParts.dayName}</Text>
              <Text style={styles.dateNumber}>{dateParts.day}</Text>
              <Text style={styles.dateMonth}>{dateParts.month}</Text>
            </View>
          </View>
        );
      }

      // Movie card
      return (
        <View style={styles.cardWrapper}>
          <MovieCard
            movie={item.movie}
            onSelect={() => handleMovieSelect(item.movie)}
            onFocus={() => handleMovieFocus(item.movie, index)}
            hasTVPreferredFocus={index === 2} // First movie after trailers + first date marker
            testID={`movie-card-${index}`}
          />
        </View>
      );
    },
    [formatDateParts, handleMovieSelect, handleMovieFocus]
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
      {/* Header with title and filters */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>THE NEW RELEASE WALL</Text>
        <View style={styles.filterRow}>
          {FILTERS.map((filter) => (
            <FilterButton
              key={filter.id}
              filter={filter}
              isActive={activeFilter === filter.id}
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
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  header: {
    paddingHorizontal: 40,
    paddingTop: 20,
    paddingBottom: 12,
    alignItems: 'center',
  },
  headerTitle: {
    color: Colors.primary,
    fontSize: 42,
    fontWeight: '100',
    letterSpacing: 12,
    textAlign: 'center',
    marginBottom: 16,
  },
  filterRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 16,
  },
  filterButton: {
    paddingHorizontal: 24,
    paddingVertical: 10,
    borderRadius: 25,
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
    fontSize: 20,
    fontWeight: '500',
  },
  filterButtonTextActive: {
    color: Colors.background,
    fontWeight: '600',
  },
  listContent: {
    // Center the 7-column grid: (1920 - 7*(210+16)) / 2 = 169px
    paddingHorizontal: 169,
    paddingTop: 0,
    paddingBottom: 20,
  },
  row: {
    justifyContent: 'flex-start',
    marginBottom: CARD_GAP,
  },
  // NEW TRAILERS button - same size as movie cards
  trailersCard: {
    width: CARD_WIDTH,
    height: CARD_HEIGHT,
    borderRadius: 12,
    backgroundColor: '#E50914',
    justifyContent: 'center',
    alignItems: 'center',
    overflow: 'hidden',
  },
  trailersText: {
    color: '#FFFFFF',
    fontSize: 28,
    fontWeight: '900',
    letterSpacing: 2,
    textAlign: 'center',
  },
  trailersFocusBorder: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    borderRadius: 12,
    borderWidth: 4,
    borderColor: Colors.primary,
  },
  // Date card - same size as movie cards, styled like web
  dateCard: {
    width: CARD_WIDTH,
    height: CARD_HEIGHT,
    marginRight: CARD_GAP,
    borderRadius: 12,
    borderWidth: 3,
    borderColor: Colors.primary,
    backgroundColor: Colors.background,
    justifyContent: 'center',
    alignItems: 'center',
    overflow: 'hidden',
  },
  dateCardInner: {
    alignItems: 'center',
  },
  dateDayName: {
    color: Colors.textMuted,
    fontSize: 16,
    letterSpacing: 3,
    marginBottom: 6,
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
