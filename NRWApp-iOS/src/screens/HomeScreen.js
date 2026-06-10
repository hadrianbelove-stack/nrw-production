/**
 * New Release Wall - Home Screen
 * Movie grid with filters and search
 */

import React, {useState, useEffect, useCallback, useMemo} from 'react';
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
import DateDividerCard from '../components/DateDividerCard';
import FilterBar from '../components/FilterBar';
import {Colors, Typography, Spacing, Dimensions} from '../constants/colors';
import {
  fetchMovies,
  refreshMovies,
  filterMoviesMulti,
  searchMovies,
  sortByDate,
  getNewThisWeek,
} from '../services/api';
import {trackFilterChange, trackSearch} from '../services/analytics';

const screenWidth = RNDimensions.get('window').width;

const FILTER_DESCRIPTIONS = {
  'staff-picks': { title: 'Picks', text: "The ones we're vouching for. Out of everything on the wall, these are the movies we think are genuinely worth your time. Not a popularity contest, just honest recommendations." },
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
  const [activeFilters, setActiveFilters] = useState(new Set());
  const [slopMode, setSlopMode] = useState('free');
  const [hideFest, setHideFest] = useState(true);
  const [showPreorders, setShowPreorders] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  // Initial load
  useEffect(() => {
    loadMovies();
  }, []);

  // Apply filters and search
  useEffect(() => {
    let result = filterMoviesMulti(movies, activeFilters, searchQuery, slopMode, hideFest, showPreorders);
    if (searchQuery.trim()) {
      result = searchMovies(result, searchQuery);
    }
    result = sortByDate(result);
    setDisplayedMovies(result);
  }, [movies, activeFilters, slopMode, hideFest, searchQuery, showPreorders]);

  // Build grid items with date dividers inserted
  const gridItems = useMemo(() => {
    if (searchQuery.trim()) return displayedMovies; // no dividers during search
    const items = [];
    const today = new Date().toISOString().split('T')[0];
    let lastDate = null;
    let addedPreOrder = false;

    for (const movie of displayedMovies) {
      const date = movie.digital_date || movie.premiere_date || '';
      const isPreOrder = movie._is_preorder || date > today;

      if (isPreOrder && !addedPreOrder) {
        items.push({_type: 'date-divider', _key: 'div-preorder', dateString: 'pre-order'});
        addedPreOrder = true;
      } else if (!isPreOrder && date && date !== lastDate) {
        items.push({_type: 'date-divider', _key: 'div-' + date, dateString: date});
        lastDate = date;
      }
      items.push(movie);
    }
    return items;
  }, [displayedMovies, searchQuery]);

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

  const handleFilterChange = useCallback(filterId => {
    setActiveFilters(prev => {
      const newFilters = new Set(prev);
      if (newFilters.has(filterId)) {
        newFilters.delete(filterId);
      } else {
        newFilters.add(filterId);
      }
      trackFilterChange(filterId);
      return newFilters;
    });
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

  const renderGridItem = ({item}) => {
    if (item._type === 'date-divider') {
      return (
        <View style={styles.cardWrapper}>
          <DateDividerCard dateString={item.dateString} />
        </View>
      );
    }
    return (
      <View style={styles.cardWrapper}>
        <MovieCard
          movie={item}
          onPress={handleMoviePress}
          isFeatured={item.featured || item.filters?.is_staff_pick}
        />
      </View>
    );
  };

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
      {newThisWeek.length > 0 && !searchQuery && activeFilters.size === 0 && (
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

  const activeFilterDesc = activeFilters.size === 1
    ? FILTER_DESCRIPTIONS[Array.from(activeFilters)[0]]
    : null;

  return (
    <View style={[styles.container, {paddingBottom: insets.bottom}]}>
      <FilterBar activeFilters={activeFilters} onFilterChange={handleFilterChange} slopMode={slopMode} onSlopModeChange={setSlopMode} hideFest={hideFest} onHideFestChange={setHideFest} showPreorders={showPreorders} onShowPreordersChange={setShowPreorders} />

      {activeFilterDesc && (
        <View style={styles.filterDescRow}>
          <Text style={styles.filterDescTitle}>{activeFilterDesc.title}</Text>
          <Text style={styles.filterDescText}>{activeFilterDesc.text}</Text>
        </View>
      )}

      <FlatList
        data={gridItems}
        renderItem={renderGridItem}
        keyExtractor={item => item._key || String(item.id)}
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
  filterDescRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
    paddingHorizontal: Spacing.screenPadding,
    paddingVertical: 10,
    borderTopWidth: 1,
    borderTopColor: 'rgba(255,255,255,0.08)',
    backgroundColor: Colors.background,
  },
  filterDescTitle: {
    fontSize: 13,
    fontWeight: '800',
    letterSpacing: 1.5,
    color: Colors.primary,
    textTransform: 'uppercase',
    flexShrink: 0,
    paddingTop: 1,
  },
  filterDescText: {
    fontSize: 12,
    color: Colors.textMuted,
    lineHeight: 17,
    flex: 1,
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
