/**
 * New Release Wall - tvOS Home Screen
 * Horizontal shelf layout with focus-based navigation
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { useHomeScreen } from './HomeScreen';
import MovieShelf, { LoadingShelf, EmptyShelf } from '../components/MovieShelf.tvos';
import FilterSidebar from '../components/FilterSidebar.tvos';
import { Colors, Typography, Spacing } from '../constants/colors';
import { useTVEventHandler, TV_EVENTS } from '../utils/focusManager.tvos';
import {
  trackScreenView,
  trackMovieFocus,
  trackMovieSelect,
  trackFilterChange,
} from '../services/analytics.tvos';

const HomeScreenTvOS = () => {
  const navigation = useNavigation();
  const scrollViewRef = useRef(null);

  // Get shared state and actions
  const {
    shelves,
    isLoading,
    error,
    activeFilter,
    lastFocusedPosition,
    refreshMovies,
    changeFilter,
    saveFocusedPosition,
  } = useHomeScreen();

  // Local state
  const [isSidebarVisible, setIsSidebarVisible] = useState(false);
  const [focusedShelfIndex, setFocusedShelfIndex] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const previousFilterRef = useRef(activeFilter);

  // Track screen view on mount
  useEffect(() => {
    trackScreenView('Home', { filter: activeFilter });
  }, []);

  // Handle movie selection - navigate to detail with analytics
  const handleMovieSelectWithTracking = useCallback(
    (movie) => {
      trackMovieSelect(movie);
      navigation.navigate('MovieDetail', { movie });
    },
    [navigation]
  );

  // Handle movie focus - save position and track
  const handleMovieFocus = useCallback(
    (movie, shelfIndex, movieIndex) => {
      saveFocusedPosition(shelfIndex, movieIndex);
      trackMovieFocus(movie, shelfIndex, movieIndex);
    },
    [saveFocusedPosition]
  );

  // Handle shelf focus
  const handleShelfFocus = useCallback((shelfIndex) => {
    setFocusedShelfIndex(shelfIndex);
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
      // Refresh on play/pause when nothing is playing
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

  // Handle pull-to-refresh (tvOS style - press play/pause)
  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    await refreshMovies();
    setIsRefreshing(false);
  }, [refreshMovies]);

  // Render loading state
  if (isLoading && shelves.length === 0) {
    return (
      <View style={styles.container}>
        <View style={styles.header}>
          <Text style={styles.title}>NEW RELEASE WALL</Text>
          <Text style={styles.subtitle}>Loading...</Text>
        </View>
        <LoadingShelf title="Featured" />
        <LoadingShelf title="Recent Releases" />
        <LoadingShelf title="More Films" />
      </View>
    );
  }

  // Render error state
  if (error && shelves.length === 0) {
    return (
      <View style={styles.container}>
        <View style={styles.header}>
          <Text style={styles.title}>NEW RELEASE WALL</Text>
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
  if (!isLoading && shelves.length === 0) {
    return (
      <View style={styles.container}>
        <View style={styles.header}>
          <Text style={styles.title}>NEW RELEASE WALL</Text>
          <FilterIndicator filter={activeFilter} />
        </View>
        <EmptyShelf
          title="No Movies Found"
          message={
            activeFilter !== 'all'
              ? `No ${activeFilter} movies to display. Press Menu to change filter.`
              : 'No movies available. Press Play/Pause to refresh.'
          }
        />
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
        <Text style={styles.title}>NEW RELEASE WALL</Text>
        <View style={styles.headerRight}>
          <FilterIndicator filter={activeFilter} />
          {isRefreshing && (
            <ActivityIndicator
              color={Colors.primary}
              style={styles.refreshIndicator}
            />
          )}
        </View>
      </View>

      {/* Shelves */}
      <ScrollView
        ref={scrollViewRef}
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
        removeClippedSubviews={true}
      >
        {shelves.map((shelf, index) => {
          // Determine which shelf should have preferred focus
          // If we have a last focused position, use that shelf; otherwise default to first shelf
          const isPreferredFocusShelf = lastFocusedPosition
            ? lastFocusedPosition.shelfIndex === index
            : index === 0;

          return (
            <MovieShelf
              key={shelf.id}
              title={shelf.title}
              movies={shelf.movies}
              isFeatured={shelf.isFeatured}
              shelfIndex={index}
              initialFocusIndex={
                lastFocusedPosition?.shelfIndex === index
                  ? lastFocusedPosition.movieIndex
                  : 0
              }
              hasPreferredFocus={isPreferredFocusShelf}
              onMovieSelect={handleMovieSelectWithTracking}
              onMovieFocus={handleMovieFocus}
              onShelfFocus={handleShelfFocus}
            />
          );
        })}

        {/* Footer hint */}
        <View style={styles.footer}>
          <Text style={styles.footerText}>
            Press Menu to filter • Play/Pause to refresh
          </Text>
        </View>
      </ScrollView>

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
    paddingBottom: Spacing.tvos.lg,
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
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    paddingBottom: Spacing.tvos.xl,
  },
  footer: {
    paddingVertical: Spacing.tvos.xl,
    alignItems: 'center',
  },
  footerText: {
    color: Colors.textMuted,
    fontSize: Typography.tvos.caption,
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
});

export default HomeScreenTvOS;
