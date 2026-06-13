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

const FILTER_DESCRIPTIONS = {
  'staff-picks': { title: 'Selects', text: "The ones we're vouching for. Out of everything on the wall, these are the movies we think are genuinely worth your time. Not a popularity contest, just honest recommendations." },
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
  const [slopMode, setSlopMode] = useState('free');
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

  // Strip color: active view toggle recolors date strips (SELECTS crimson, FESTS amber,
  // SLOP ONLY orange); otherwise a single active category filter; otherwise teal
  const singleFilter = activeFilters.size === 1 ? Array.from(activeFilters)[0] : null;
  const dateStripColor = showHighlightsOnly
    ? '#dc143c'
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

  // View toggles are mutually exclusive — turning one on turns the others off
  const handleShowHighlightsChange = useCallback(value => {
    setShowHighlightsOnly(value);
    if (value) {
      setHideFest(true);
      setShowPreorders(false);
    }
  }, []);

  const handleHideFestChange = useCallback(value => {
    setHideFest(value);
    if (!value) {
      setShowHighlightsOnly(false);
      setShowPreorders(false);
    }
  }, []);

  const handleShowPreordersChange = useCallback(value => {
    setShowPreorders(value);
    if (value) {
      setShowHighlightsOnly(false);
      setHideFest(true);
    }
  }, []);

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

  const activeFilterDesc = showHighlightsOnly
    ? FILTER_DESCRIPTIONS['staff-picks']
    : activeFilters.size === 1
    ? FILTER_DESCRIPTIONS[Array.from(activeFilters)[0]]
    : null;

  return (
    <View style={[styles.container, {paddingBottom: insets.bottom}]}>
      <FilterBar activeFilters={activeFilters} onFilterChange={handleFilterChange} slopMode={slopMode} onSlopModeChange={setSlopMode} hideFest={hideFest} onHideFestChange={handleHideFestChange} showPreorders={showPreorders} onShowPreordersChange={handleShowPreordersChange} showHighlightsOnly={showHighlightsOnly} onShowHighlightsChange={handleShowHighlightsChange} />

      {activeFilterDesc && (
        <View style={styles.filterDescRow}>
          <Text style={styles.filterDescTitle}>{activeFilterDesc.title}</Text>
          <Text style={styles.filterDescText}>{activeFilterDesc.text}</Text>
        </View>
      )}

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
