/**
 * New Release Wall - tvOS Home Screen
 * Horizontal scrolling layout with inline date markers (mimics web layout)
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
        id: movie.id || `movie-${index}`,
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

  // Format date for display
  const formatDate = useCallback((dateString) => {
    if (!dateString || dateString === 'Unknown') {
      return 'Unknown';
    }
    try {
      const date = new Date(dateString);
      const options = { month: 'short', day: 'numeric' };
      return date.toLocaleDateString('en-US', options);
    } catch {
      return dateString;
    }
  }, []);

  // Render item (date marker or movie card)
  const renderItem = useCallback(
    ({ item, index }) => {
      if (item.type === 'date') {
        return (
          <View style={styles.dateMarker}>
            <Text style={styles.dateText}>{formatDate(item.date)}</Text>
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
    [formatDate, handleMovieSelect, handleMovieFocus]
  );

  // Key extractor
  const keyExtractor = useCallback((item) => item.id, []);

  // Get item layout for optimized scrolling
  const getItemLayout = useCallback((data, index) => {
    const item = data[index];
    const movieWidth = Dimensions.tvos.cardWidth + Spacing.tvos.cardGap;
    const dateWidth = 100 + Spacing.tvos.cardGap; // Date marker width

    // Calculate offset by summing widths of all previous items
    let offset = Spacing.tvos.screenPadding;
    for (let i = 0; i < index; i++) {
      offset += data[i].type === 'date' ? dateWidth : movieWidth;
    }

    const length = item.type === 'date' ? dateWidth : movieWidth;

    return { length, offset, index };
  }, []);

  // Render loading state
  if (isLoading && listData.length === 0) {
    return (
      <View style={styles.container}>
        <View style={styles.header}>
          <Text style={styles.title}>The New Release Wall</Text>
          <Text style={styles.subtitle}>Loading...</Text>
        </View>
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
        <View style={styles.header}>
          <Text style={styles.title}>The New Release Wall</Text>
        </View>
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
        <View style={styles.header}>
          <Text style={styles.title}>The New Release Wall</Text>
          <FilterIndicator filter={activeFilter} />
        </View>
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
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>The New Release Wall</Text>
        <View style={styles.headerRight}>
          <Text style={styles.movieCount}>{filteredMovies.length} films</Text>
          <FilterIndicator filter={activeFilter} />
          {isRefreshing && (
            <ActivityIndicator
              color={Colors.primary}
              style={styles.refreshIndicator}
            />
          )}
        </View>
      </View>

      {/* Horizontal scrolling list with date markers and movies */}
      <FlatList
        ref={flatListRef}
        data={listData}
        renderItem={renderItem}
        keyExtractor={keyExtractor}
        horizontal={true}
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.listContent}
        removeClippedSubviews={true}
        maxToRenderPerBatch={15}
        windowSize={7}
        initialNumToRender={10}
        decelerationRate="fast"
      />

      {/* Footer hint */}
      <View style={styles.footer}>
        <Text style={styles.footerText}>
          Press Menu to filter • Play/Pause to refresh
        </Text>
      </View>

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

// Filter indicator badge
const FilterIndicator = ({ filter }) => {
  if (filter === 'all') return null;

  const filterLabels = {
    featured: 'Featured',
    hidden: 'Hidden',
  };

  return (
    <View style={styles.filterBadge}>
      <Text style={styles.filterBadgeText}>
        {filterLabels[filter] || filter}
      </Text>
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
    paddingHorizontal: Spacing.tvos.screenPadding,
    paddingTop: Spacing.tvos.xl,
    paddingBottom: Spacing.tvos.md,
  },
  title: {
    color: Colors.primary,
    fontSize: Typography.tvos.title,
    fontWeight: '800',
    letterSpacing: 2,
  },
  subtitle: {
    color: Colors.textMuted,
    fontSize: Typography.tvos.body,
    marginTop: Spacing.tvos.xs,
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  movieCount: {
    color: Colors.textMuted,
    fontSize: Typography.tvos.caption,
    marginRight: Spacing.tvos.md,
  },
  filterBadge: {
    backgroundColor: Colors.primary,
    paddingHorizontal: Spacing.tvos.md,
    paddingVertical: Spacing.tvos.xs,
    borderRadius: 8,
  },
  filterBadgeText: {
    color: Colors.background,
    fontSize: Typography.tvos.caption,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  refreshIndicator: {
    marginLeft: Spacing.tvos.md,
  },
  listContent: {
    paddingHorizontal: Spacing.tvos.screenPadding,
    paddingVertical: 40, // Room for scale animation
    alignItems: 'center',
  },
  dateMarker: {
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: Spacing.tvos.md,
    marginRight: Spacing.tvos.cardGap,
  },
  dateText: {
    color: Colors.primary,
    fontSize: Typography.tvos.subtitle,
    fontWeight: '700',
    textAlign: 'center',
    writingDirection: 'ltr',
  },
  cardWrapper: {
    marginRight: Spacing.tvos.cardGap,
  },
  footer: {
    paddingVertical: Spacing.tvos.md,
    alignItems: 'center',
  },
  footerText: {
    color: Colors.textMuted,
    fontSize: Typography.tvos.caption,
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
    paddingHorizontal: Spacing.tvos.screenPadding,
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
    paddingHorizontal: Spacing.tvos.screenPadding,
  },
  emptyText: {
    color: Colors.textMuted,
    fontSize: Typography.tvos.body,
    textAlign: 'center',
  },
});

export default HomeScreenTvOS;
