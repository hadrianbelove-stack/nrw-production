/**
 * New Release Wall - API Service
 * Fetches movie data from GitHub
 */

import {getCachedData, setCachedData, CACHE_KEYS} from '../utils/cache';

// GitHub raw content URL for data.json
const DATA_URL =
  'https://raw.githubusercontent.com/hadrianbelove-stack/nrw-production/main/data.json';

// Cache duration: 1 hour in milliseconds
const CACHE_DURATION = 60 * 60 * 1000;

/**
 * Fetch movie data from GitHub
 * Returns cached data if available and not expired
 */
export async function fetchMovies() {
  try {
    // Check cache first
    const cached = await getCachedData(CACHE_KEYS.MOVIES);
    if (cached && !isCacheExpired(cached.timestamp)) {
      console.log('[API] Returning cached data');
      return extractMoviesData(cached.data);
    }

    console.log('[API] Fetching fresh data from GitHub');

    // Add timeout to prevent indefinite hang
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000);

    const response = await fetch(DATA_URL, {signal: controller.signal});
    clearTimeout(timeoutId);

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();

    // Cache the fresh data
    await setCachedData(CACHE_KEYS.MOVIES, {
      data,
      timestamp: Date.now(),
    });

    return extractMoviesData(data);
  } catch (error) {
    console.error('[API] Error fetching movies:', error);

    // If fetch fails, try to return stale cached data
    const cached = await getCachedData(CACHE_KEYS.MOVIES);
    if (cached) {
      console.log('[API] Returning stale cached data due to network error');
      return extractMoviesData(cached.data);
    }

    throw error;
  }
}

/**
 * Force refresh data (bypass cache)
 */
export async function refreshMovies() {
  try {
    console.log('[API] Force refreshing data');

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000);

    const response = await fetch(DATA_URL, {signal: controller.signal});
    clearTimeout(timeoutId);

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();

    await setCachedData(CACHE_KEYS.MOVIES, {
      data,
      timestamp: Date.now(),
    });

    return extractMoviesData(data);
  } catch (error) {
    console.error('[API] Error refreshing movies:', error);
    throw error;
  }
}

/**
 * Extract movies array and featured list from data.json structure
 */
function extractMoviesData(data) {
  if (data && typeof data === 'object' && !Array.isArray(data)) {
    return {
      movies: data.movies || [],
      featured: data.featured || [],
      latestPlaylistUrl: data.latest_playlist_url || null,
    };
  } else if (Array.isArray(data)) {
    return {
      movies: data,
      featured: [],
      latestPlaylistUrl: null,
    };
  } else {
    return {movies: [], featured: [], latestPlaylistUrl: null};
  }
}

/**
 * Check if cached data has expired
 */
function isCacheExpired(timestamp) {
  return Date.now() - timestamp > CACHE_DURATION;
}

/**
 * Filter movies by category
 */
export function filterMovies(movies, filter = 'all') {
  if (!movies || !Array.isArray(movies)) return [];

  switch (filter) {
    case 'all':
      return movies.filter(movie => !movie.hidden);
    case 'featured':
    case 'staff-picks':
      return movies.filter(
        movie =>
          !movie.hidden &&
          (movie.categories?.is_staff_pick || movie.featured === true),
      );
    case 'big-time':
      return movies.filter(
        movie => !movie.hidden && movie.categories?.tier === 'big_time',
      );
    case 'niche':
      return movies.filter(
        movie => !movie.hidden && movie.categories?.tier === 'niche',
      );
    case 'foreign':
      return movies.filter(
        movie =>
          !movie.hidden &&
          (movie.categories?.is_foreign ||
            (movie.original_language && movie.original_language !== 'en')),
      );
    case 'restorations':
      return movies.filter(
        movie => !movie.hidden && movie.categories?.is_restoration === true,
      );
    case 'hidden':
      return movies.filter(movie => movie.hidden === true);
    default:
      return movies.filter(movie => !movie.hidden);
  }
}

/**
 * Search movies by title, director, or genre
 */
export function searchMovies(movies, query) {
  if (!movies || !Array.isArray(movies) || !query) return movies;

  const lowerQuery = query.toLowerCase().trim();

  return movies.filter(movie => {
    const title = (movie.title || '').toLowerCase();
    const director = (movie.director || '').toLowerCase();
    const genres = (movie.genres || []).map(g => g.toLowerCase());

    return (
      title.includes(lowerQuery) ||
      director.includes(lowerQuery) ||
      genres.some(g => g.includes(lowerQuery))
    );
  });
}

/**
 * Sort movies by digital date (newest first)
 */
export function sortByDate(movies) {
  if (!movies || !Array.isArray(movies)) return [];

  return [...movies].sort((a, b) => {
    const dateA = a.digital_date || a.premiere_date || a.release_date || '';
    const dateB = b.digital_date || b.premiere_date || b.release_date || '';
    return dateB.localeCompare(dateA);
  });
}

/**
 * Get movies released in last 7 days
 */
export function getNewThisWeek(movies) {
  if (!movies || !Array.isArray(movies)) return [];

  const weekAgo = new Date();
  weekAgo.setDate(weekAgo.getDate() - 7);
  const weekAgoStr = weekAgo.toISOString().split('T')[0];

  return movies.filter(movie => {
    const date = movie.digital_date || movie.premiere_date;
    return date && date >= weekAgoStr && !movie.hidden;
  });
}

/**
 * Get watch links for a movie
 */
export function getWatchLinks(movie) {
  if (!movie) return [];

  const links = [];
  const watchLinks = movie.watch_links || {};

  // Handle VOD (purchase/rent)
  const vod = watchLinks.vod;
  if (Array.isArray(vod)) {
    vod.forEach(item => {
      if (item && item.link) {
        links.push({
          service: normalizeServiceId(item.service),
          label: `Rent on ${item.service || 'VOD'}`,
          url: item.link,
          type: 'purchase',
        });
      }
    });
  } else if (vod && vod.link) {
    links.push({
      service: normalizeServiceId(vod.service),
      label: `Rent on ${vod.service || 'VOD'}`,
      url: vod.link,
      type: 'purchase',
    });
  }

  // Handle streaming
  const streaming = watchLinks.streaming;
  if (Array.isArray(streaming)) {
    streaming.forEach(item => {
      if (item && item.link) {
        links.push({
          service: normalizeServiceId(item.service),
          label: `Watch on ${item.service || 'Streaming'}`,
          url: item.link,
          type: 'streaming',
        });
      }
    });
  } else if (streaming && streaming.link) {
    links.push({
      service: normalizeServiceId(streaming.service),
      label: `Watch on ${streaming.service || 'Streaming'}`,
      url: streaming.link,
      type: 'streaming',
    });
  }

  return links;
}

/**
 * Normalize service name to ID
 */
function normalizeServiceId(serviceName) {
  if (!serviceName) return 'vod';
  const lower = serviceName.toLowerCase();
  if (lower.includes('amazon') || lower.includes('prime')) return 'amazon';
  if (lower.includes('apple') || lower.includes('itunes')) return 'apple_tv';
  if (lower.includes('netflix')) return 'netflix';
  if (lower.includes('hulu')) return 'hulu';
  if (lower.includes('max') || lower.includes('hbo')) return 'max';
  if (lower.includes('disney')) return 'disney_plus';
  if (lower.includes('peacock')) return 'peacock';
  if (lower.includes('paramount')) return 'paramount_plus';
  if (lower.includes('mubi')) return 'mubi';
  if (lower.includes('criterion')) return 'criterion';
  return serviceName.toLowerCase().replace(/\s+/g, '_');
}

export default {
  fetchMovies,
  refreshMovies,
  filterMovies,
  searchMovies,
  sortByDate,
  getNewThisWeek,
  getWatchLinks,
};
