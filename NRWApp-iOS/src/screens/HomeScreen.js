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
import DateRowHeader from '../components/DateRowHeader';
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

// 3-column grid matching mobile web
const numColumns = 3;
const cardMargin = Spacing.cardGap;
const cardWidth = (screenWidth - Spacing.screenPadding * 2 - cardMargin * (numColumns - 1)) / numColumns;

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

export default function HomeScreen({navigation}) {
  const insets = useSafeAreaInsets();

  const [movies, setMovies] = useState([]);
  const [displayedMovies, setDisplayedMovies] = useState([]);
  const [newThisWeek, setNewThisWeek] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [activeFilters, setActiveFilters] = useState(new Set());
  const [slopMode, setSlopMode] = useState('all');
  const [hideFest, setHideFest] = useState(true);
  const [showPreorders, setShowPreorders] = useState(false);
  const [showHighlightsOnly, setShowHighlightsOnly] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  // Initial load
  useEffect(() => {
    loadMovies();
  }, []);

  // Apply filters and search
  useEffect(() => {
    let result = filterMoviesMulti(movies, activeFilters, searchQuery, slopMode, hideFest, showPreorders);
    if (showHighlightsOnly) {
      result = result.filter(m => m.filters?.is_staff_pick || m.featured);
    }
    if (searchQuery.trim()) {
      result = searchMovies(result, searchQuery);
    }
    result = sortByDate(result);
    setDisplayedMovies(result);
  }, [movies, activeFilters, slopMode, hideFest, searchQuery, showPreorders, showHighlightsOnly]);

  // Build grid rows: full-width date strips + rows of 3 posters (matches mobile web)
  const gridRows = useMemo(() => {
    const rows = [];
    let group = [];
    const flushGroup = () => {
      for (let i = 0; i < group.length; i += numColumns) {
        const chunk = group.slice(i, i + numColumns);
        rows.push({_type: 'row', _key: 'row-' + rows.length, movies: chunk});
      }
      group = [];
    };

    if (searchQuery.trim()) {
      // No strips during search
      group = displayedMovies.slice();
      flushGroup();
      return rows;
    }

    if (showHighlightsOnly && displayedMovies.length > 0) {
      rows.push({_type: 'strip', _key: 'strip-highlights', dateString: 'highlights'});
    }
    if (slopMode === 'only' && displayedMovies.length > 0) {
      rows.push({_type: 'strip', _key: 'strip-slop', dateString: 'slop'});
    }

    const today = new Date().toISOString().split('T')[0];
    // SELECTS is a single curated section (like FEST / PRE-ORDER): all regular
    // picks group under the one "SELECTS · OUR PICKS" strip — no per-date strips.
    let lastStrip = showHighlightsOnly ? 'highlights' : null;
    for (const movie of displayedMovies) {
      const date = movie.digital_date || movie.premiere_date || '';
      let stripKey;
      if (movie._is_preorder || (!movie.filters?.is_virtual_screening && date > today)) {
        stripKey = 'pre-order';
      } else if (movie.filters?.is_virtual_screening) {
        stripKey = 'fest';
      } else if (showHighlightsOnly) {
        stripKey = 'highlights';
      } else {
        stripKey = date || 'unknown';
      }
      if (stripKey !== lastStrip) {
        flushGroup();
        if (stripKey !== 'unknown') {
          rows.push({_type: 'strip', _key: 'strip-' + stripKey, dateString: stripKey});
        }
        lastStrip = stripKey;
      }
      group.push(movie);
    }
    flushGroup();
    return rows;
  }, [displayedMovies, searchQuery, showHighlightsOnly, slopMode]);

  // Strip color: active view toggle recolors date strips (SELECTS teal, FESTS amber,
  // SLOP ONLY orange); otherwise a single active category filter; otherwise teal
  const singleFilter = activeFilters.size === 1 ? Array.from(activeFilters)[0] : null;
  const dateStripColor = showHighlightsOnly
    ? '#00d4aa'
    : !hideFest
    ? '#f59e0b'
    : slopMode === 'only'
    ? '#ff9500'
    : (singleFilter && STRIP_COLORS[singleFilter]) || Colors.primary;

  // Strip rows stick below the list header while their day scrolls
  // (+1 offsets for the ListHeaderComponent, which occupies sticky index 0)
  const stickyIndices = useMemo(
    () => gridRows.reduce((acc, r, i) => (r._type === 'strip' ? (acc.push(i + 1), acc) : acc), []),
    [gridRows],
  );

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

  // Genres are single-select: a genre replaces any current genre (click again clears).
  // Picking a genre clears the view toggles — only one filter OR one toggle at a time (matches tvOS).
  const handleFilterChange = useCallback(filterId => {
    setActiveFilters(prev => {
      const isOnlyActive = prev.size === 1 && prev.has(filterId);
      trackFilterChange(filterId);
      return isOnlyActive ? new Set() : new Set([filterId]);
    });
    setShowHighlightsOnly(false);
    setHideFest(true);
    setShowPreorders(false);
    setSlopMode('all');
  }, []);

  // View toggles (Selects / Fests / Pre-Orders) are mutually exclusive: at most
  // one is active. Each handler maps to the single winning view, or 'none' when
  // toggled off. (hideFest is inverted — fests are shown only when view==='fests'.)
  // Toggles also clear genre filters + slop so only one thing is ever active.
  const showExclusiveView = useCallback(view => {
    setShowHighlightsOnly(view === 'selects');
    setHideFest(view !== 'fests');
    setShowPreorders(view === 'preorders');
    setSlopMode('all');
    setActiveFilters(new Set());
  }, []);

  // Slop toggle is part of the same exclusive group: clicking it ALWAYS makes it
  // the exclusive view (clears genre filters and the other view toggles) on every
  // click, regardless of the resulting state (matches web).
  const handleSlopModeChange = useCallback(next => {
    setSlopMode(next);
    setActiveFilters(new Set());
    setShowHighlightsOnly(false);
    setHideFest(true);
    setShowPreorders(false);
  }, []);

  const handleShowHighlightsChange = useCallback(v => showExclusiveView(v ? 'selects' : 'none'), [showExclusiveView]);
  const handleHideFestChange = useCallback(v => showExclusiveView(v ? 'none' : 'fests'), [showExclusiveView]);
  const handleShowPreordersChange = useCallback(v => showExclusiveView(v ? 'preorders' : 'none'), [showExclusiveView]);

  const handleSearch = useCallback(query => {
    setSearchQuery(query);
    if (query.trim()) {
      trackSearch(query);
    }
  }, []);

  // Grid tap opens the poster close-up (View 1), matching mobile web
  const handleMoviePress = useCallback(
    movie => {
      const currentIndex = displayedMovies.findIndex(m => String(m.id) === String(movie.id));
      navigation.navigate('PosterView', {
        movies: displayedMovies,
        index: currentIndex >= 0 ? currentIndex : 0,
      });
    },
    [navigation, displayedMovies],
  );

  const renderRow = ({item}) => {
    if (item._type === 'strip') {
      return (
        <DateRowHeader
          dateString={item.dateString}
          stripColor={dateStripColor}
        />
      );
    }
    return (
      <View style={styles.gridRow}>
        {item.movies.map(movie => (
          <MovieCard
            key={String(movie.id)}
            movie={movie}
            width={cardWidth}
            onPress={handleMoviePress}
            isFeatured={movie.featured || movie.filters?.is_staff_pick}
          />
        ))}
        {Array.from({length: numColumns - item.movies.length}).map((_, i) => (
          <View key={'pad-' + i} style={{width: cardWidth}} />
        ))}
      </View>
    );
  };

  // Sticky index 0 — empty spacer kept to preserve the strip-row sticky offset
  // math (strips are at gridRows index + 1). Search + selects live in the FilterBar.
  const renderHeader = () => <View style={styles.headerSpacer} />;

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
    <View style={[styles.container, {paddingTop: insets.top, paddingBottom: insets.bottom}]}>
      <View style={styles.appHeader}>
        <Text style={styles.appTitle}>THE NEW RELEASE WALL</Text>
        <Text style={styles.slogan}>What came out, every day. Bringing back browsing.</Text>
      </View>
      <FilterBar activeFilters={activeFilters} onFilterChange={handleFilterChange} slopMode={slopMode} onSlopModeChange={handleSlopModeChange} hideFest={hideFest} onHideFestChange={handleHideFestChange} showPreorders={showPreorders} onShowPreordersChange={handleShowPreordersChange} showHighlightsOnly={showHighlightsOnly} onShowHighlightsChange={handleShowHighlightsChange} searchQuery={searchQuery} onSearchChange={handleSearch} />

      <FlatList
        data={gridRows}
        renderItem={renderRow}
        keyExtractor={item => item._key}
        stickyHeaderIndices={stickyIndices}
        contentContainerStyle={styles.listContent}
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
  headerSpacer: {
    height: Spacing.sm,
    backgroundColor: Colors.background,
  },
  appHeader: {
    paddingHorizontal: Spacing.screenPadding,
    paddingTop: Spacing.sm,
    paddingBottom: Spacing.xs,
    alignItems: 'center',
  },
  appTitle: {
    color: Colors.primary,
    fontSize: 20,
    fontWeight: '200',
    letterSpacing: 5,
    textAlign: 'center',
  },
  slogan: {
    color: '#cfcfcf',
    fontSize: 12,
    fontWeight: '300',
    letterSpacing: 0.3,
    marginTop: 5,
    textAlign: 'center',
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
  gridRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
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
