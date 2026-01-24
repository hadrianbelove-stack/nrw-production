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
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { useHomeScreen } from './useHomeScreen';
import MovieCard from '../components/MovieCard.tvos';
import FilterSidebar from '../components/FilterSidebar.tvos';
import { Colors, Typography, Spacing, Dimensions } from '../constants/colors';
import { useTVEventHandler, TV_EVENTS } from '../utils/focusManager.tvos';
import {
  trackScreenView,
  trackMovieFocus,
  trackMovieSelect,
  trackFilterChange,
} from '../services/analytics.tvos';

// Grid configuration - 7 columns for 1920px width
const NUM_COLUMNS = 7;
const CARD_WIDTH = Dimensions.tvos.cardWidth;
const CARD_HEIGHT = Dimensions.tvos.cardHeight;
const CARD_GAP = 16;

const HomeScreenTvOS = () => {
  const navigation = useNavigation();
  const flatListRef = useRef(null);

  // Get shared state and actions
  const {
    filteredMovies,
    isLoading,
    error,
    activeFilter,
    refreshMovies,
    changeFilter,
  } = useHomeScreen();

  // Local state
  const [isSidebarVisible, setIsSidebarVisible] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const previousFilterRef = useRef(activeFilter);

  // Track screen view on mount
  useEffect(() => {
    trackScreenView('Home', { filter: activeFilter });
  }, []);

  // Build flat list data with date markers interspersed
  // Each date marker takes one grid cell (same size as movie card)
  const listData = useMemo(() => {
    if (!filteredMovies || filteredMovies.length === 0) return [];

    // Sort movies by digital_date descending (newest first)
    const sorted = [...filteredMovies].sort((a, b) => {
      const dateA = a.digital_date || '0000-00-00';
      const dateB = b.digital_date || '0000-00-00';
      return dateB.localeCompare(dateA);
    });

    const items = [];
    let currentDate = null;

    sorted.forEach((movie, index) => {
      const movieDate = movie.digital_date || 'Unknown';

      // Insert date marker when date changes
      if (movieDate !== currentDate) {
        currentDate = movieDate;
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
  }, [filteredMovies]);

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
    [TV_EVENTS.MENU]: () => {
      if (!isSidebarVisible) {
        setIsSidebarVisible(true);
      }
    },
    [TV_EVENTS.SWIPE_UP]: () => {
      if (!isSidebarVisible) {
        setIsSidebarVisible(true);
      }
    },
    [TV_EVENTS.PLAY_PAUSE]: () => {
      handleRefresh();
    },
  });

  // Handle filter change with analytics
  const handleFilterChange = useCallback(
    (filter) => {
      trackFilterChange(filter, previousFilterRef.current);
      previousFilterRef.current = filter;
      changeFilter(filter);
    },
    [changeFilter]
  );

  // Handle sidebar close
  const handleSidebarClose = useCallback(() => {
    setIsSidebarVisible(false);
  }, []);

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

  // Render item (date marker or movie card)
  const renderItem = useCallback(
    ({ item, index }) => {
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
            hasTVPreferredFocus={index === 1} // First movie after first date marker
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
            {activeFilter !== 'all'
              ? `No ${activeFilter} movies. Press Menu to change filter.`
              : 'No movies available. Press Play/Pause to refresh.'}
          </Text>
        </View>
        <FilterSidebar
          isVisible={isSidebarVisible}
          activeFilter={activeFilter}
          onFilterChange={handleFilterChange}
          onClose={handleSidebarClose}
        />
      </View>
    );
  }

  return (
    <View style={styles.container}>
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

      {/* Filter Sidebar */}
      <FilterSidebar
        isVisible={isSidebarVisible}
        activeFilter={activeFilter}
        onFilterChange={handleFilterChange}
        onClose={handleSidebarClose}
      />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  listContent: {
    paddingHorizontal: 40,
    paddingTop: 40,
    paddingBottom: 60,
  },
  row: {
    justifyContent: 'flex-start',
    marginBottom: CARD_GAP,
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
    fontSize: 18,
    letterSpacing: 3,
    marginBottom: 8,
  },
  dateNumber: {
    color: Colors.primary,
    fontSize: 72,
    fontWeight: 'bold',
    lineHeight: 80,
  },
  dateMonth: {
    color: Colors.primary,
    fontSize: 28,
    fontWeight: 'bold',
    letterSpacing: 4,
    marginTop: 8,
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
