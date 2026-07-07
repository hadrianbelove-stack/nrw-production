/**
 * New Release Wall - Home Screen (Shared Logic)
 * Contains business logic shared between iOS and tvOS
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { AppState } from 'react-native';
import {
  fetchMovies,
  getFeaturedMovies,
  getMoviesByReleaseDate,
  filterMovies,
  searchMovies,
} from '../services/api';
import {
  saveLastFocusedIndex,
  getLastFocusedIndex,
  saveUserPreferences,
  getUserPreferences,
} from '../utils/cache';

/**
 * Custom hook for Home Screen state management
 * Shared between iOS and tvOS implementations
 */
export function useHomeScreen() {
  // State
  const [movies, setMovies] = useState([]);
  const [featuredMovies, setFeaturedMovies] = useState([]);
  const [featuredIds, setFeaturedIds] = useState([]);
  const [latestPlaylistUrl, setLatestPlaylistUrl] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeFilter, setActiveFilter] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [lastFocusedPosition, setLastFocusedPosition] = useState(null);

  // Load movies on mount
  useEffect(() => {
    loadMovies();
    loadPreferences();
  }, []);

  // Load user preferences
  const loadPreferences = useCallback(async () => {
    try {
      const prefs = await getUserPreferences();
      if (prefs.filter) {
        setActiveFilter(prefs.filter);
      }
    } catch (err) {
      console.error('[HomeScreen] Error loading preferences:', err);
    }
  }, []);

  // Fetch movies from API
  const loadMovies = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      // Do NOT clear the cache before fetching (audit #5): fetchMovies always
      // fetches fresh first anyway, and keeping the cache means the offline
      // fallback can actually fire on a flaky network instead of erroring.
      const { movies: moviesArray, featured: featuredIdsList, latestPlaylistUrl: playlistUrl } = await fetchMovies();
      setMovies(moviesArray);
      setFeaturedIds(featuredIdsList);
      setLatestPlaylistUrl(playlistUrl);

      // Build featured movies list using the root featured IDs or movie.featured flag
      let featured = [];
      if (featuredIdsList && featuredIdsList.length > 0) {
        // Use the root featured list to find movies by ID
        const featuredSet = new Set(featuredIdsList.map(String));
        featured = moviesArray.filter(movie => featuredSet.has(String(movie.id)));
      } else {
        // Fallback to movie.featured flag
        featured = getFeaturedMovies(moviesArray);
      }
      setFeaturedMovies(featured);

      // Restore last focused position
      const lastFocus = await getLastFocusedIndex();
      if (lastFocus) {
        setLastFocusedPosition(lastFocus);
      }
    } catch (err) {
      console.error('[HomeScreen] Error loading movies:', err);
      setError(err.message || 'Failed to load movies');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Refresh movies
  const refreshMovies = useCallback(async () => {
    await loadMovies();
  }, [loadMovies]);

  // Refetch when the app returns to the foreground (e.g. reopened from suspend),
  // so data updates without needing a force-quit / cold launch. AppState 'change'
  // only fires on transitions, so this does not double-fetch on initial mount.
  useEffect(() => {
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') {
        loadMovies();
      }
    });
    return () => sub.remove();
  }, [loadMovies]);

  // Change filter
  const changeFilter = useCallback(
    async (filter) => {
      setActiveFilter(filter);
      await saveUserPreferences({ filter });
    },
    []
  );

  // Search movies
  const updateSearchQuery = useCallback((query) => {
    setSearchQuery(query);
  }, []);

  // Save focused position (for returning from detail screen)
  const saveFocusedPosition = useCallback(async (shelfIndex, movieIndex) => {
    await saveLastFocusedIndex(shelfIndex, movieIndex);
    setLastFocusedPosition({ shelfIndex, movieIndex });
  }, []);

  // Clear focused position
  const clearFocusedPosition = useCallback(() => {
    setLastFocusedPosition(null);
  }, []);

  // Filtered movies — an active search runs over ALL movies (filters are
  // view modes; search bypasses them, matching the other NRW devices)
  const filteredMovies = useMemo(() => {
    if (searchQuery.trim()) {
      return searchMovies(movies, searchQuery);
    }
    return filterMovies(movies, activeFilter);
  }, [movies, activeFilter, searchQuery]);

  // Movies grouped by release date (for tvOS shelves)
  const moviesByDate = useMemo(() => {
    return getMoviesByReleaseDate(filteredMovies);
  }, [filteredMovies]);

  // Shelves data for tvOS
  const shelves = useMemo(() => {
    const shelvesArray = [];

    // Add featured shelf if showing all movies
    if (!activeFilter && featuredMovies.length > 0) {
      shelvesArray.push({
        id: 'featured',
        title: "What's New This Week",
        movies: featuredMovies,
        isFeatured: true,
      });
    }

    // Add date-grouped shelves
    Object.entries(moviesByDate).forEach(([date, dateMovies]) => {
      const formattedDate = formatReleaseDate(date);
      shelvesArray.push({
        id: `date-${date}`,
        title: formattedDate,
        movies: dateMovies,
        isFeatured: false,
      });
    });

    return shelvesArray;
  }, [activeFilter, featuredMovies, moviesByDate]);

  return {
    // State
    movies,
    featuredMovies,
    filteredMovies,
    shelves,
    isLoading,
    error,
    activeFilter,
    searchQuery,
    lastFocusedPosition,
    latestPlaylistUrl,

    // Actions
    refreshMovies,
    changeFilter,
    updateSearchQuery,
    saveFocusedPosition,
    clearFocusedPosition,
  };
}

/**
 * Format release date for shelf title
 */
function formatReleaseDate(dateString) {
  if (!dateString || dateString === 'Unknown') {
    return 'Unknown Release Date';
  }

  try {
    const date = new Date(dateString);
    const now = new Date();
    const diffDays = Math.floor((now - date) / (1000 * 60 * 60 * 24));

    if (diffDays < 0) {
      // Future release
      const absDays = Math.abs(diffDays);
      if (absDays === 1) {
        return 'Coming Tomorrow';
      } else if (absDays <= 7) {
        return `Coming in ${absDays} days`;
      } else {
        const options = { month: 'short', day: 'numeric' };
        return `Coming ${date.toLocaleDateString('en-US', options)}`;
      }
    } else if (diffDays === 0) {
      return 'Released Today';
    } else if (diffDays === 1) {
      return 'Released Yesterday';
    } else if (diffDays < 7) {
      return `Released ${diffDays} days ago`;
    } else {
      const options = { month: 'short', day: 'numeric' };
      return `Released ${date.toLocaleDateString('en-US', options)}`;
    }
  } catch {
    return dateString;
  }
}

/**
 * Movie selection handler factory
 * Creates navigation handler for movie selection
 */
export function createMovieSelectHandler(navigation) {
  return (movie) => {
    if (movie && navigation) {
      navigation.navigate('MovieDetail', { movie });
    }
  };
}

export default {
  useHomeScreen,
  createMovieSelectHandler,
};
