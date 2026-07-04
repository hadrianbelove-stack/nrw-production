/**
 * New Release Wall - tvOS Search Screen
 * Full-screen search destination (Apple TV / Netflix pattern): big query field
 * up top, live-filtered results grid below, native tvOS keyboard.
 * Searches movies by title, original title, director, or country.
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  FlatList,
  StyleSheet,
  TouchableOpacity,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Colors } from '../constants/colors';
import MovieCard from '../components/MovieCard.tvos';
import SearchIcon from '../components/SearchIcon.tvos';
import { getSearchMovieList, setSharedMovieList } from './sharedMovieList';

const CARD_GAP = 16;
const NUM_COLUMNS = 5;

const SearchScreen = ({ route }) => {
  const navigation = useNavigation();
  // Full movie list seeded by HomeScreen via the shared store (route params can't
  // carry the ~1.6MB list). route.params kept as a fallback for older callers.
  const movies = getSearchMovieList().length
    ? getSearchMovieList()
    : (route.params?.movies || []);
  const [searchQuery, setSearchQuery] = useState('');
  const [results, setResults] = useState([]);
  const [inputFocused, setInputFocused] = useState(false);
  const [clearFocused, setClearFocused] = useState(false);
  const inputRef = useRef(null);

  // Focus input on mount
  useEffect(() => {
    setTimeout(() => {
      inputRef.current?.focus();
    }, 100);
  }, []);

  // Progressive back (standard TV search pattern): Menu with a query showing
  // clears the search back to its default state; Menu on an empty search exits
  // to the wall.
  //
  // The hardware Menu press pops the native stack BEFORE beforeRemove can veto
  // it (verified on-sim: preventDefault alone didn't hold), so while a query
  // exists we own the Menu key in JS — same TVEventControl pattern TrailerPlayer
  // proved out (its build-28/29 comments). Scoped tightly: enabled only while
  // this screen has a non-empty query, disabled the moment it clears/unmounts,
  // so Menu everywhere else keeps its native pop/suspend behavior.
  // Hardware Menu exits this screen via the native-stack pop. That pop fires at
  // the UIKit layer and is NOT interceptible (verified on-sim, three ways:
  // beforeRemove preventDefault, TVEventControl menu ownership, and
  // gestureEnabled:false all lost to it — TrailerPlayer's JS-menu trick only
  // works because that screen has no focusable views). Worse, a beforeRemove
  // preventDefault against the native pop DESYNCS react-navigation's JS state
  // from the native stack, and navigate('Search') becomes a no-op afterward —
  // the original "can't reselect search" bug. So: NO back-press interception of
  // any kind on this screen. The UX contract instead: exiting unmounts the
  // route (search always reopens fresh), HomeScreen re-seeds focus onto the
  // SEARCH button on return, and the ✕ button clears in place.

  // Search function
  const performSearch = useCallback((query) => {
    if (!query.trim()) {
      setResults([]);
      return;
    }

    const lowerQuery = query.toLowerCase();
    const filtered = movies.filter((movie) => {
      const title = (movie.title || '').toLowerCase();
      const origTitle = (movie.original_title || '').toLowerCase();
      const director = (movie.crew?.director || movie.director || '').toLowerCase();
      const country = (movie.country || '').toLowerCase();

      return (
        title.includes(lowerQuery) ||
        origTitle.includes(lowerQuery) ||
        director.includes(lowerQuery) ||
        country.includes(lowerQuery)
      );
    });

    setResults(filtered);
  }, [movies]);

  // Handle search input change
  const handleSearchChange = useCallback((text) => {
    setSearchQuery(text);
    performSearch(text);
  }, [performSearch]);

  // Handle movie selection — seed the shared list with the current results so
  // MovieDetail's left/right arrows browse within the search results.
  const handleMovieSelect = useCallback((movie, index) => {
    setSharedMovieList(results);
    navigation.navigate('MovieDetail', { movie, movieIndex: index });
  }, [navigation, results]);

  // Handle back button
  const handleBack = useCallback(() => {
    navigation.goBack();
  }, [navigation]);

  // Render movie item
  const renderItem = useCallback(({ item, index }) => (
    <View style={styles.cardWrapper}>
      <MovieCard
        movie={item}
        onSelect={() => handleMovieSelect(item, index)}
        testID={`search-result-${index}`}
      />
    </View>
  ), [handleMovieSelect]);

  const keyExtractor = useCallback((item, index) => String(item.id || item.tmdb_id || index), []);

  return (
    <View style={styles.container}>
      {/* Header with back button and the big query field */}
      <View style={styles.header}>
        <TouchableOpacity
          style={styles.backButton}
          onPress={handleBack}
          accessible={true}
          accessibilityLabel="Go back"
          accessibilityRole="button"
        >
          <Text style={styles.backIcon}>‹</Text>
        </TouchableOpacity>

        <View style={[styles.searchContainer, inputFocused && styles.searchContainerFocused]}>
          <View style={styles.searchIconWrap}>
            <SearchIcon size={34} color={inputFocused ? '#00d4aa' : 'rgba(255,255,255,0.55)'} strokeWidth={1.8} />
          </View>
          <TextInput
            ref={inputRef}
            style={styles.searchInput}
            placeholder="Search movies, directors, countries…"
            placeholderTextColor="rgba(255,255,255,0.35)"
            value={searchQuery}
            onChangeText={handleSearchChange}
            onFocus={() => setInputFocused(true)}
            onBlur={() => setInputFocused(false)}
            autoCapitalize="none"
            autoCorrect={false}
            returnKeyType="search"
          />
          {searchQuery.length > 0 && (
            <TouchableOpacity
              style={[styles.clearButton, clearFocused && styles.clearButtonFocused]}
              onPress={() => handleSearchChange('')}
              onFocus={() => setClearFocused(true)}
              onBlur={() => setClearFocused(false)}
              accessible={true}
              accessibilityLabel="Clear search"
            >
              <Text style={[styles.clearIcon, clearFocused && styles.clearIconFocused]}>✕</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>

      {/* Results count */}
      {searchQuery.length > 0 && (
        <View style={styles.resultsInfo}>
          <Text style={styles.resultsText}>
            {results.length} {results.length === 1 ? 'result' : 'results'} for "{searchQuery}"
          </Text>
        </View>
      )}

      {/* Results grid */}
      {results.length > 0 ? (
        <FlatList
          data={results}
          renderItem={renderItem}
          keyExtractor={keyExtractor}
          numColumns={NUM_COLUMNS}
          showsVerticalScrollIndicator={false}
          contentContainerStyle={styles.listContent}
          columnWrapperStyle={styles.row}
        />
      ) : searchQuery.length > 0 ? (
        <View style={styles.emptyContainer}>
          <SearchIcon size={72} color="rgba(255,255,255,0.18)" strokeWidth={1.4} />
          <Text style={styles.emptyText}>No movies found</Text>
          <Text style={styles.emptyHint}>Try a different title, director, or country</Text>
        </View>
      ) : (
        <View style={styles.emptyContainer}>
          <SearchIcon size={72} color="rgba(0,212,170,0.35)" strokeWidth={1.4} />
          <Text style={styles.emptyText}>Search the wall</Text>
          <Text style={styles.emptyHint}>Results appear as you type — title, director, or country</Text>
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
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 68,
    paddingTop: 40,
    paddingBottom: 18,
    gap: 24,
  },
  backButton: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  backIcon: {
    color: Colors.textPrimary,
    fontSize: 38,
    lineHeight: 44,
  },
  // Big query field — 10-foot sizing, teal focus treatment matching the app
  searchContainer: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    borderRadius: 18,
    borderWidth: 2,
    borderColor: 'rgba(255,255,255,0.16)',
    paddingHorizontal: 26,
    height: 88,
  },
  searchContainerFocused: {
    borderColor: Colors.primary,
    backgroundColor: 'rgba(0,212,170,0.06)',
    shadowColor: Colors.primary,
    shadowOpacity: 0.45,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 0 },
  },
  searchIconWrap: {
    marginRight: 18,
  },
  searchInput: {
    flex: 1,
    color: Colors.textPrimary,
    fontSize: 30,
    height: '100%',
  },
  clearButton: {
    width: 64,
    height: 64,
    borderRadius: 32,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.08)',
    borderWidth: 2,
    borderColor: 'transparent',
  },
  clearButtonFocused: {
    backgroundColor: 'rgba(0,212,170,0.15)',
    borderColor: Colors.primary,
  },
  clearIcon: {
    color: 'rgba(255,255,255,0.55)',
    fontSize: 30,
  },
  clearIconFocused: {
    color: Colors.primary,
  },
  resultsInfo: {
    paddingHorizontal: 68,
    paddingBottom: 10,
  },
  resultsText: {
    color: Colors.textSecondary,
    fontSize: 20,
  },
  listContent: {
    // Center the 5-column grid: (1920 - 5*344 - 4*16) / 2 = 68px
    paddingHorizontal: 68,
    paddingTop: 10,
    paddingBottom: 40,
  },
  row: {
    justifyContent: 'flex-start',
    marginBottom: CARD_GAP,
  },
  cardWrapper: {
    marginRight: CARD_GAP,
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 14,
  },
  emptyText: {
    color: Colors.textPrimary,
    fontSize: 30,
    marginTop: 8,
  },
  emptyHint: {
    color: Colors.textMuted,
    fontSize: 20,
  },
});

export default SearchScreen;
