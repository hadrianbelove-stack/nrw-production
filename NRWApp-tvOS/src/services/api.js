/**
 * New Release Wall - API Service
 * Shared data fetching logic for iOS and tvOS
 */

import { getCachedData, setCachedData, CACHE_KEYS } from '../utils/cache';

// GitHub raw content URL for data.json
const DATA_URL = 'https://raw.githubusercontent.com/hadrianbelove-stack/nrw-production/main/data.json';

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
 * Filter movies by category filters (OR logic - cumulative)
 * @param {Array} movies - Array of movie objects
 * @param {Array|string} filters - Array of filter IDs or single filter string (for backwards compatibility)
 * @returns {Array} Filtered movies that match ANY selected filter
 */
export function filterMovies(movies, filters = 'all') {
  if (!movies || !Array.isArray(movies)) return [];

  // Convert string to array for backwards compatibility
  const filterArray = Array.isArray(filters) ? filters : [filters];

  // If 'all' is in filters or no filters, show all non-hidden
  if (filterArray.includes('all') || filterArray.length === 0) {
    return movies.filter(movie => !movie.hidden);
  }

  return movies.filter(movie => {
    if (movie.hidden) return false;

    // Must pass ANY selected filter (OR logic - cumulative)
    for (const filter of filterArray) {
      switch (filter) {
        case 'big-time':
          if (movie.categories?.is_big_time || movie.categories?.tier === 'big_time') return true;
          break;
        case 'indie':
          if (movie.categories?.is_indie || movie.categories?.tier === 'indie') return true;
          break;
        case 'staff-picks': {
          const isStaffPick = movie.categories?.is_staff_pick || movie.featured === true;
          if (isStaffPick) return true;
          break;
        }
        case 'foreign': {
          const isForeign = movie.categories?.is_foreign ??
            (movie.original_language && movie.original_language !== 'en');
          if (isForeign) return true;
          break;
        }
        case 'series':
          if (movie.content_type === 'limited_series') return true;
          break;
        case 'plex':
          if (movie.plex && movie.plex.deep_link) return true;
          break;
        case 'restorations':
          if (movie.categories?.is_restoration) return true;
          break;
        case 'documentary':
          if (movie.categories?.is_documentary === true) return true;
          break;
        case 'virtual-screenings':
          if (movie.categories?.is_virtual_screening) return true;
          break;
        case 'featured': {
          const isFeatured = movie.categories?.is_staff_pick || movie.featured === true;
          if (isFeatured) return true;
          break;
        }
        case 'hidden':
          if (movie.hidden === true) return true;
          break;
      }
    }
    return false;
  });
}

/**
 * Search movies by title, director, genre, country, synopsis, or year
 */
export function searchMovies(movies, query) {
  if (!movies || !Array.isArray(movies) || !query) return movies;

  const lowerQuery = query.toLowerCase().trim();

  return movies.filter(movie => {
    const title = (movie.title || '').toLowerCase();
    const director = (movie.director || movie.crew?.director || '').toLowerCase();
    const genres = (movie.genres || []).map(g => g.toLowerCase());
    const country = (movie.country || '').toLowerCase();
    const synopsis = (movie.synopsis || '').toLowerCase();
    const year = String(movie.year || '');

    return (
      title.includes(lowerQuery) ||
      director.includes(lowerQuery) ||
      genres.some(g => g.includes(lowerQuery)) ||
      country.includes(lowerQuery) ||
      synopsis.includes(lowerQuery) ||
      year.includes(lowerQuery)
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
  'eventive': 'eventive',
  'fawesome': 'fawesome',
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
 * Check if a service should be shown for VOD (purchase/rent)
 * Includes major VOD platforms that work on Apple TV
 */
function isValidVodService(serviceName) {
  if (!serviceName) return false;
  const lower = serviceName.toLowerCase();
  // Include Amazon, Apple, Fandango, and specialty platforms like Eventive
  return lower.includes('amazon') ||
         lower.includes('apple') ||
         lower.includes('itunes') ||
         lower.includes('fandango') ||
         lower.includes('vudu') ||
         lower.includes('eventive');
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

  // Handle VOD (purchase/rent) links - filter to supported platforms
  for (const vodItem of watchLinks.vod) {
    if (vodItem && vodItem.link && isValidVodService(vodItem.service)) {
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

  // Pre-order links (JustWatch buy offers for pre-order movies)
  if (links.length === 0) {
    const preOrderLinks = Array.isArray(movie.pre_order_links) ? movie.pre_order_links : [];
    for (const pl of preOrderLinks) {
      if (pl && pl.link) {
        const serviceId = normalizeServiceId(pl.service);
        links.push({
          service: serviceId || 'vod',
          label: `Pre-Order on ${pl.service || 'VOD'}`,
          url: pl.link,
          type: 'purchase',
          icon: serviceId || 'vod',
        });
      }
    }
  }

  return links;
}

/**
 * Get info links for a movie (trailer only - RT not useful on tvOS)
 */
export function getInfoLinks(movie) {
  if (!movie || !movie.links) return [];

  const links = [];
  const movieLinks = movie.links;

  const trailerUrl = movieLinks.trailer_hosted || movieLinks.trailer;
  if (trailerUrl) {
    links.push({
      type: 'trailer',
      label: 'TRAILER',
      url: trailerUrl,
      icon: 'play',
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
