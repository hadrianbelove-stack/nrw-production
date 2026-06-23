/**
 * New Release Wall - tvOS Search Screen
 * Allows searching movies by title, director, or country
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  FlatList,
  StyleSheet,
  TouchableOpacity,
  Animated,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Colors, Dimensions } from '../constants/colors';
import MovieCard from '../components/MovieCard.tvos';

const CARD_WIDTH = Dimensions.tvos.cardWidth;
const CARD_HEIGHT = Dimensions.tvos.cardHeight;
const CARD_GAP = 16;
const NUM_COLUMNS = 5;

const SearchScreen = ({ route }) => {
  const navigation = useNavigation();
  const { movies = [] } = route.params || {};
  const [searchQuery, setSearchQuery] = useState('');
  const [results, setResults] = useState([]);
  const inputRef = useRef(null);

  // Focus input on mount
  useEffect(() => {
    setTimeout(() => {
      inputRef.current?.focus();
    }, 100);
  }, []);

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

  // Handle movie selection
  const handleMovieSelect = useCallback((movie) => {
    navigation.navigate('MovieDetail', { movie });
  }, [navigation]);

  // Handle back button
  const handleBack = useCallback(() => {
    navigation.goBack();
  }, [navigation]);

  // Render movie item
  const renderItem = useCallback(({ item, index }) => (
    <View style={styles.cardWrapper}>
      <MovieCard
        movie={item}
        onSelect={() => handleMovieSelect(item)}
        testID={`search-result-${index}`}
      />
    </View>
  ), [handleMovieSelect]);

  const keyExtractor = useCallback((item) => item.id || item.tmdb_id || String(Math.random()), []);

  return (
    <View style={styles.container}>
      {/* Header with back button and search input */}
      <View style={styles.header}>
        <TouchableOpacity
          style={styles.backButton}
          onPress={handleBack}
          accessible={true}
          accessibilityLabel="Go back"
          accessibilityRole="button"
        >
          <Text style={styles.backIcon}>←</Text>
        </TouchableOpacity>

        <View style={styles.searchContainer}>
          <Text style={styles.searchIcon}>⌕</Text>
          <TextInput
            ref={inputRef}
            style={styles.searchInput}
            placeholder="Search movies, directors, countries..."
            placeholderTextColor="#666"
            value={searchQuery}
            onChangeText={handleSearchChange}
            autoCapitalize="none"
            autoCorrect={false}
            returnKeyType="search"
          />
          {searchQuery.length > 0 && (
            <TouchableOpacity
              style={styles.clearButton}
              onPress={() => handleSearchChange('')}
              accessible={true}
              accessibilityLabel="Clear search"
            >
              <Text style={styles.clearIcon}>✕</Text>
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
          <Text style={styles.emptyText}>No movies found</Text>
          <Text style={styles.emptyHint}>Try a different search term</Text>
        </View>
      ) : (
        <View style={styles.emptyContainer}>
          <Text style={styles.emptyText}>Search for movies</Text>
          <Text style={styles.emptyHint}>Enter a title, director, or country</Text>
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
    paddingHorizontal: 60,
    paddingTop: 28,
    paddingBottom: 16,
    gap: 20,
  },
  backButton: {
    width: 50,
    height: 50,
    borderRadius: 25,
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  backIcon: {
    color: Colors.textPrimary,
    fontSize: 28,
  },
  searchContainer: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    borderRadius: 12,
    paddingHorizontal: 20,
    height: 60,
  },
  searchIcon: {
    color: '#666',
    fontSize: 24,
    marginRight: 12,
  },
  searchInput: {
    flex: 1,
    color: Colors.textPrimary,
    fontSize: 24,
    height: '100%',
  },
  clearButton: {
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
  },
  clearIcon: {
    color: '#666',
    fontSize: 20,
  },
  resultsInfo: {
    paddingHorizontal: 68,
    paddingBottom: 10,
  },
  resultsText: {
    color: Colors.textSecondary,
    fontSize: 18,
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
  },
  emptyText: {
    color: Colors.textPrimary,
    fontSize: 28,
    marginBottom: 10,
  },
  emptyHint: {
    color: Colors.textMuted,
    fontSize: 20,
  },
});

export default SearchScreen;
