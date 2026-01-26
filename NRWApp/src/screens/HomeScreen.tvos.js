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

    // Try different YouTube URL formats for tvOS
    // Format 1: Simple playlist URL
    const youtubeUrl = playlistId
      ? `https://www.youtube.com/playlist?list=${playlistId}`
      : 'https://www.youtube.com/@New-Release-Wall/playlists';

    console.log('[Trailers] Opening YouTube playlist:', youtubeUrl);
    console.log('[Trailers] Playlist ID:', playlistId);

    // Use the https URL - tvOS should open it in YouTube app if installed
    Linking.openURL(youtubeUrl).catch((err) => {
      console.error('[Trailers] Error opening YouTube:', err);
      Alert.alert(
        'YouTube Not Available',
        'Please install the YouTube app from the App Store to view trailers.'
      );
    });
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
    refreshMovies,
    changeFilter,
    latestPlaylistUrl,
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
  }, [filteredMovies, latestPlaylistUrl]);

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
      {/* Header with title */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>THE NEW RELEASE WALL</Text>
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
  header: {
    paddingHorizontal: 40,
    paddingTop: 20,
    paddingBottom: CARD_GAP,
  },
  headerTitle: {
    color: Colors.textPrimary,
    fontSize: 38,
    fontWeight: '800',
    letterSpacing: 4,
    textAlign: 'center',
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
