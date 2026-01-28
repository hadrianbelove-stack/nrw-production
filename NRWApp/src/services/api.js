/**
 * New Release Wall - API Service
 * Shared data fetching logic for iOS and tvOS
 */

import { getCachedData, setCachedData, CACHE_KEYS } from '../utils/cache';

// GitHub raw content URL for data.json
const DATA_URL = 'https://raw.githubusercontent.com/hadrianbelove-stack/nrw-production/main/data.json';

// Cache duration: 24 hours in milliseconds
const CACHE_DURATION = 24 * 60 * 60 * 1000;

/**
 * Fetch movie data from GitHub
 * Returns cached data if available and not expired
 * @returns {Promise<{movies: Array, featured: Array}>} Object with movies array and featured IDs
 */
export async function fetchMovies() {
  try {
    // Always fetch fresh data to ensure posters are up to date
    // TODO: Re-enable caching once data is stable
    console.log('[API] Fetching fresh movie data from GitHub (cache bypassed)');

    // Add timeout to prevent indefinite hang on slow networks
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000); // 15 second timeout

    const response = await fetch(DATA_URL, { signal: controller.signal });
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
 * Extract movies array and featured list from data.json structure
 * Handles both root object format and legacy array format
 * Note: Plex data is now embedded directly in movie objects in data.json
 */
function extractMoviesData(data) {
  // Handle root object format: { movies: [...], featured: [...], latest_playlist_url: "..." }
  if (data && typeof data === 'object' && !Array.isArray(data)) {
    const plexCount = (data.movies || []).filter(m => m.plex).length;
    if (plexCount > 0) {
      console.log(`[API] ${plexCount} movies have Plex links`);
    }
    return {
      movies: data.movies || [],
      featured: data.featured || [],
      latestPlaylistUrl: data.latest_playlist_url || null,
    };
  } else if (Array.isArray(data)) {
    // Handle legacy array format (for backwards compatibility)
    return {
      movies: data,
      featured: [],
      latestPlaylistUrl: null,
    };
  } else {
    return { movies: [], featured: [], latestPlaylistUrl: null };
  }
}

/**
 * Check if cached data has expired
 */
function isCacheExpired(timestamp) {
  return Date.now() - timestamp > CACHE_DURATION;
}

/**
 * Get featured movies from data
 */
export function getFeaturedMovies(movies) {
  if (!movies || !Array.isArray(movies)) return [];
  return movies.filter(movie => movie.featured === true);
}

/**
 * Get the best available date for a movie
 * Priority: digital_date > premiere_date > release_date
 */
function getMovieDate(movie) {
  return movie.digital_date || movie.premiere_date || movie.release_date || null;
}

/**
 * Get movies by release date (for organizing into shelves)
 * Uses digital_date as primary key with fallbacks to premiere_date and release_date
 */
export function getMoviesByReleaseDate(movies) {
  if (!movies || !Array.isArray(movies)) return {};

  const grouped = {};

  movies.forEach(movie => {
    const date = getMovieDate(movie) || 'Unknown';
    if (!grouped[date]) {
      grouped[date] = [];
    }
    grouped[date].push(movie);
  });

  // Sort dates in descending order (most recent first)
  // Handle "Unknown" specially - put at the end
  const sortedDates = Object.keys(grouped).sort((a, b) => {
    if (a === 'Unknown') return 1;
    if (b === 'Unknown') return -1;
    const dateA = new Date(a);
    const dateB = new Date(b);
    // Handle invalid dates by putting them before "Unknown"
    if (isNaN(dateA.getTime())) return 1;
    if (isNaN(dateB.getTime())) return -1;
    return dateB - dateA;
  });

  const sortedGrouped = {};
  sortedDates.forEach(date => {
    sortedGrouped[date] = grouped[date];
  });

  return sortedGrouped;
}

/**
 * Filter movies by visibility status
 */
export function filterMovies(movies, filter = 'all') {
  if (!movies || !Array.isArray(movies)) return [];

  switch (filter) {
    case 'featured':
      return movies.filter(movie => movie.featured === true);
    case 'hidden':
      return movies.filter(movie => movie.hidden === true);
    case 'all':
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
 * Map provider/service names to internal service IDs
 */
const SERVICE_NAME_MAP = {
  'amazon': 'amazon',
  'amazon video': 'amazon',
  'amazon prime video': 'amazon',
  'prime video': 'amazon',
  'apple tv': 'apple_tv',
  'apple tv+': 'apple_tv',
  'apple itunes': 'apple_tv',
  'itunes': 'apple_tv',
  'netflix': 'netflix',
  'hulu': 'hulu',
  'max': 'max',
  'hbo max': 'max',
  'peacock': 'peacock',
  'paramount+': 'paramount_plus',
  'paramount plus': 'paramount_plus',
  'disney+': 'disney_plus',
  'disney plus': 'disney_plus',
  'mubi': 'mubi',
  'criterion': 'criterion',
  'criterion channel': 'criterion',
  'angel studios': 'angel_studios',
  'fandango at home': 'fandango',
  'vudu': 'fandango',
  'vix': 'vix',
  'shudder': 'shudder',
  'strand releasing amazon channel': 'strand_releasing',
};

/**
 * Normalize service name to internal service ID
 */
function normalizeServiceId(serviceName) {
  if (!serviceName) return null;
  const normalized = serviceName.toLowerCase().trim();
  return SERVICE_NAME_MAP[normalized] || normalized.replace(/\s+/g, '_');
}

/**
 * Check if a service is Amazon or Apple TV (for VOD filtering)
 */
function isAmazonOrAppleService(serviceName) {
  if (!serviceName) return false;
  const lower = serviceName.toLowerCase();
  return lower.includes('amazon') || lower.includes('apple') || lower.includes('itunes');
}

/**
 * Normalize watch_links to handle both array format (new) and single-object format (legacy)
 * Returns normalized structure with arrays for both streaming and vod
 */
function normalizeWatchLinks(watchLinks) {
  const normalized = { streaming: [], vod: [] };

  if (!watchLinks || typeof watchLinks !== 'object') {
    return normalized;
  }

  // Handle streaming
  const streaming = watchLinks.streaming;
  if (Array.isArray(streaming)) {
    normalized.streaming = streaming;
  } else if (streaming && typeof streaming === 'object') {
    normalized.streaming = [streaming];
  }

  // Handle vod
  const vod = watchLinks.vod;
  if (Array.isArray(vod)) {
    normalized.vod = vod;
  } else if (vod && typeof vod === 'object') {
    normalized.vod = [vod];
  }

  return normalized;
}

/**
 * Get watch links for a movie
 * Reads from movie.watch_links structure:
 * NEW format: { streaming: [{service, link}, ...], vod: [{service, link}, ...] }
 * Legacy format: { streaming: {service, link}, vod: {service, link} }
 * Also includes Plex link if movie.plex is present (from plex_library.json)
 */
export function getWatchLinks(movie) {
  if (!movie) return [];

  const links = [];

  // Add Plex link first if available (personal library takes priority)
  if (movie.plex && movie.plex.deep_link) {
    links.push({
      service: 'plex',
      label: 'Play on Plex',
      url: movie.plex.deep_link,
      type: 'plex',
      icon: 'plex',
    });
  }

  const watchLinks = normalizeWatchLinks(movie.watch_links);

  // Handle VOD (purchase/rent) links - filter to Amazon and Apple TV only
  for (const vodItem of watchLinks.vod) {
    if (vodItem && vodItem.link && isAmazonOrAppleService(vodItem.service)) {
      const serviceId = normalizeServiceId(vodItem.service);
      links.push({
        service: serviceId || 'vod',
        label: `Rent on ${vodItem.service || 'VOD'}`,
        url: vodItem.link,
        type: 'purchase',
        icon: serviceId || 'vod',
      });
    }
  }

  // Handle streaming links - include ALL services
  for (const streamingItem of watchLinks.streaming) {
    if (streamingItem && streamingItem.link) {
      const serviceId = normalizeServiceId(streamingItem.service);
      links.push({
        service: serviceId || 'streaming',
        label: `Watch on ${streamingItem.service || 'Streaming'}`,
        url: streamingItem.link,
        type: 'streaming',
        icon: serviceId || 'streaming',
      });
    }
  }

  return links;
}

/**
 * Get info links for a movie (trailer, RT, Wikipedia)
 * Reads from movie.links structure: { trailer, rt, wikipedia }
 */
export function getInfoLinks(movie) {
  if (!movie || !movie.links) return [];

  const links = [];
  const movieLinks = movie.links;

  if (movieLinks.trailer) {
    links.push({
      type: 'trailer',
      label: 'Watch Trailer',
      url: movieLinks.trailer,
      icon: 'play',
    });
  }

  // Handle both 'rt' and 'rotten_tomatoes' field names
  const rtUrl = movieLinks.rt || movieLinks.rotten_tomatoes;
  if (rtUrl) {
    links.push({
      type: 'rotten_tomatoes',
      label: 'Rotten Tomatoes',
      url: rtUrl,
      icon: 'tomato',
    });
  }

  if (movieLinks.wikipedia) {
    links.push({
      type: 'wikipedia',
      label: 'Wikipedia',
      url: movieLinks.wikipedia,
      icon: 'wiki',
    });
  }

  return links;
}

export default {
  fetchMovies,
  getFeaturedMovies,
  getMoviesByReleaseDate,
  filterMovies,
  searchMovies,
  getWatchLinks,
  getInfoLinks,
};
