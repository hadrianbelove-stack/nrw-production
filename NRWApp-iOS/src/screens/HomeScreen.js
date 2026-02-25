/**
 * New Release Wall - Home Screen
 * Movie grid with filters and search
 */

import React, {useState, useEffect, useCallback} from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TextInput,
  RefreshControl,
  ActivityIndicator,
  Dimensions as RNDimensions,
} from 'react-native';
import {useSafeAreaInsets} from 'react-native-safe-area-context';

import MovieCard from '../components/MovieCard';
import FilterBar from '../components/FilterBar';
import {Colors, Typography, Spacing, Dimensions} from '../constants/colors';
import {
  fetchMovies,
  refreshMovies,
  filterMovies,
  searchMovies,
  sortByDate,
  getNewThisWeek,
} from '../services/api';
import {trackFilterChange, trackSearch} from '../services/analytics';

const screenWidth = RNDimensions.get('window').width;
const numColumns = 2;
const cardMargin = Spacing.cardGap;
const cardWidth = (screenWidth - Spacing.screenPadding * 2 - cardMargin) / numColumns;

export default function HomeScreen({navigation}) {
  const insets = useSafeAreaInsets();

  const [movies, setMovies] = useState([]);
  const [displayedMovies, setDisplayedMovies] = useState([]);
  const [newThisWeek, setNewThisWeek] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');

  // Initial load
  useEffect(() => {
    loadMovies();
  }, []);

  // Apply filters and search
  useEffect(() => {
    let result = filterMovies(movies, filter);
    if (searchQuery.trim()) {
      result = searchMovies(result, searchQuery);
    }
    result = sortByDate(result);
    setDisplayedMovies(result);
  }, [movies, filter, searchQuery]);

  const loadMovies = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await fetchMovies();
      setMovies(data.movies);
      setNewThisWeek(getNewThisWeek(data.movies));
    } catch (err) {
      console.error('[HomeScreen] Error loading movies:', err);
      setError('Failed to load movies. Pull to retry.');
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const data = await refreshMovies();
      setMovies(data.movies);
      setNewThisWeek(getNewThisWeek(data.movies));
      setError(null);
    } catch (err) {
      console.error('[HomeScreen] Error refreshing:', err);
    } finally {
      setRefreshing(false);
    }
  };

  const handleFilterChange = useCallback(newFilter => {
    setFilter(newFilter);
    trackFilterChange(newFilter);
  }, []);

  const handleSearch = useCallback(query => {
    setSearchQuery(query);
    if (query.trim()) {
      trackSearch(query);
    }
  }, []);

  const handleMoviePress = useCallback(
    movie => {
      // Find movie index in displayed list for navigation support
      const currentIndex = displayedMovies.findIndex(m => m.id === movie.id);
      navigation.navigate('MovieDetail', {
        movie,
        movieList: displayedMovies,
        currentIndex: currentIndex >= 0 ? currentIndex : 0,
      });
    },
    [navigation, displayedMovies],
  );

  const renderMovieCard = ({item}) => (
    <View style={styles.cardWrapper}>
      <MovieCard
        movie={item}
        onPress={handleMoviePress}
        isFeatured={item.featured || item.categories?.is_staff_pick}
      />
    </View>
  );

  const renderHeader = () => (
    <View style={styles.header}>
      {/* Search bar */}
      <View style={styles.searchContainer}>
        <TextInput
          style={styles.searchInput}
          placeholder="Search movies, directors, genres..."
          placeholderTextColor={Colors.textMuted}
          value={searchQuery}
          onChangeText={handleSearch}
          returnKeyType="search"
          autoCorrect={false}
        />
      </View>

      {/* New This Week section */}
      {newThisWeek.length > 0 && !searchQuery && filter === 'all' && (
        <View style={styles.newThisWeekSection}>
          <Text style={styles.sectionTitle}>🎬 New This Week</Text>
          <Text style={styles.sectionSubtitle}>
            Curated new releases you won't find elsewhere
          </Text>
          <FlatList
            horizontal
            data={newThisWeek.slice(0, 6)}
            renderItem={({item}) => (
              <View style={styles.horizontalCard}>
                <MovieCard movie={item} onPress={handleMoviePress} isFeatured />
              </View>
            )}
            keyExtractor={item => `new-${item.id}`}
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.horizontalList}
          />
        </View>
      )}

      {/* Results count */}
      <View style={styles.resultsHeader}>
        <Text style={styles.resultsCount}>
          {displayedMovies.length} {displayedMovies.length === 1 ? 'movie' : 'movies'}
          {searchQuery ? ` matching "${searchQuery}"` : ''}
        </Text>
      </View>
    </View>
  );

  if (loading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color={Colors.primary} />
        <Text style={styles.loadingText}>Loading movies...</Text>
      </View>
    );
  }

  if (error && movies.length === 0) {
    return (
      <View style={styles.centerContainer}>
        <Text style={styles.errorText}>{error}</Text>
      </View>
    );
  }

  return (
    <View style={[styles.container, {paddingBottom: insets.bottom}]}>
      <FilterBar selectedFilter={filter} onFilterChange={handleFilterChange} />

      <FlatList
        data={displayedMovies}
        renderItem={renderMovieCard}
        keyExtractor={item => String(item.id)}
        numColumns={numColumns}
        contentContainerStyle={styles.listContent}
        columnWrapperStyle={styles.row}
        ListHeaderComponent={renderHeader}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyText}>No movies found</Text>
          </View>
        }
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={handleRefresh}
            tintColor={Colors.primary}
          />
        }
        showsVerticalScrollIndicator={false}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: Colors.background,
    padding: Spacing.lg,
  },
  loadingText: {
    color: Colors.textSecondary,
    fontSize: Typography.body,
    marginTop: Spacing.md,
  },
  errorText: {
    color: Colors.red,
    fontSize: Typography.body,
    textAlign: 'center',
  },
  header: {
    paddingBottom: Spacing.md,
  },
  searchContainer: {
    paddingHorizontal: Spacing.screenPadding,
    paddingTop: Spacing.md,
    paddingBottom: Spacing.sm,
  },
  searchInput: {
    backgroundColor: Colors.backgroundSecondary,
    borderRadius: 10,
    paddingVertical: Spacing.sm + 2,
    paddingHorizontal: Spacing.md,
    color: Colors.textPrimary,
    fontSize: Typography.body,
  },
  newThisWeekSection: {
    paddingTop: Spacing.md,
    paddingBottom: Spacing.sm,
  },
  sectionTitle: {
    color: Colors.textPrimary,
    fontSize: Typography.subtitle,
    fontWeight: '700',
    paddingHorizontal: Spacing.screenPadding,
  },
  sectionSubtitle: {
    color: Colors.textSecondary,
    fontSize: Typography.caption,
    paddingHorizontal: Spacing.screenPadding,
    marginTop: 2,
    marginBottom: Spacing.sm,
  },
  horizontalList: {
    paddingHorizontal: Spacing.screenPadding,
  },
  horizontalCard: {
    marginRight: Spacing.cardGap,
  },
  resultsHeader: {
    paddingHorizontal: Spacing.screenPadding,
    paddingTop: Spacing.md,
  },
  resultsCount: {
    color: Colors.textMuted,
    fontSize: Typography.caption,
  },
  listContent: {
    paddingHorizontal: Spacing.screenPadding,
    paddingBottom: Spacing.xl,
  },
  row: {
    justifyContent: 'space-between',
  },
  cardWrapper: {
    width: cardWidth,
    marginBottom: Spacing.md,
  },
  emptyContainer: {
    padding: Spacing.xl,
    alignItems: 'center',
  },
  emptyText: {
    color: Colors.textMuted,
    fontSize: Typography.body,
  },
});
