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
export function filterMovies(movies, filter = null) {
  if (!movies || !Array.isArray(movies)) return [];

  // Exclude reverted movies (failed JustWatch verification, no watch links)
  movies = movies.filter(m => m._enrichment_status !== 'reverted');

  if (!filter) return movies.filter(movie => !movie.hidden);

  switch (filter) {
    case 'featured':
    case 'indie':
      return movies.filter(
        movie => !movie.hidden && (movie.filters?.is_indie),
      );
    case 'foreign':
      return movies.filter(
        movie =>
          !movie.hidden &&
          (movie.filters?.is_foreign ||
            (movie.original_language && movie.original_language !== 'en')),
      );
    case 'restorations':
      return movies.filter(
        movie => !movie.hidden && movie.filters?.is_restoration === true,
      );
    case 'documentary':
      return movies.filter(
        movie => !movie.hidden && movie.filters?.is_documentary === true,
      );
    case 'pre-orders':
      return movies.filter(
        movie => !movie.hidden && movie._is_preorder === true,
      );
    case 'horror':
      return movies.filter(
        movie => !movie.hidden && (movie.genres || []).some(g => g.toLowerCase().includes('horror')),
      );
    case 'action':
      return movies.filter(
        movie => !movie.hidden && (movie.genres || []).some(g => g.toLowerCase().includes('action')),
      );
    case 'comedy':
      return movies.filter(
        movie => !movie.hidden && (movie.genres || []).some(g => g.toLowerCase().includes('comedy')),
      );
    case 'family':
      return movies.filter(
        movie => !movie.hidden && (movie.genres || []).some(g => g.toLowerCase().includes('family')),
      );
    case 'thriller':
      return movies.filter(
        movie => !movie.hidden && (movie.genres || []).some(g => g.toLowerCase().includes('thriller')),
      );
    case 'hidden':
      return movies.filter(movie => movie.hidden === true);
    default:
      return movies.filter(movie => !movie.hidden);
  }
}

/**
 * Filter movies by multiple categories (OR logic - cumulative)
 */
export function filterMoviesMulti(movies, activeFilters, searchQuery = '', slopMode = 'free', hideFest = false, showPreorders = false) {
  if (!movies || !Array.isArray(movies)) return [];
  // Exclude reverted movies (failed JustWatch verification, no watch links)
  movies = movies.filter(m => m._enrichment_status !== 'reverted');
  // Toggles are view modes — an active search bypasses them all
  if (!searchQuery) {
    // Slop mode: free = hide slop, all = show everything, only = show only slop
    if (slopMode === 'free') {
      movies = movies.filter(m => !m.is_slop && !m._is_slop_guess);
    } else if (slopMode === 'only') {
      movies = movies.filter(m => m.is_slop || m._is_slop_guess);
    }
    // Hide-fest mode: hide virtual screenings
    if (hideFest) {
      movies = movies.filter(m => !m.filters?.is_virtual_screening);
    }
  }
  // Pre-orders only appear when toggle is ON or search is active
  if (!showPreorders && !searchQuery) {
    movies = movies.filter(m => !m._is_preorder);
  }
  if (!activeFilters || activeFilters.size === 0 || searchQuery) {
    return movies.filter(movie => !movie.hidden);
  }

  return movies.filter(movie => {
    if (movie.hidden) return false;

    for (const filter of activeFilters) {
      switch (filter) {
        case 'indie':
          if (movie.filters?.is_indie) return true;
          break;
        case 'foreign':
          if (movie.filters?.is_foreign ||
            (movie.original_language && movie.original_language !== 'en')) return true;
          break;
        case 'restorations':
          if (movie.filters?.is_restoration === true) return true;
          break;
        case 'documentary':
          if (movie.filters?.is_documentary === true) return true;
          break;
        case 'horror':
          if ((movie.genres || []).some(g => g.toLowerCase().includes('horror'))) return true;
          break;
        case 'action':
          if ((movie.genres || []).some(g => g.toLowerCase().includes('action'))) return true;
          break;
        case 'comedy':
          if ((movie.genres || []).some(g => g.toLowerCase().includes('comedy'))) return true;
          break;
        case 'family':
          if ((movie.genres || []).some(g => g.toLowerCase().includes('family'))) return true;
          break;
        case 'thriller':
          if ((movie.genres || []).some(g => g.toLowerCase().includes('thriller'))) return true;
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

  const norm = s => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const nq = norm(query.trim());

  return movies.filter(movie => {
    const title = norm(movie.title || '');
    const director = norm(movie.crew?.director || movie.director || '');
    const genres = (movie.genres || []).map(g => norm(g));
    const country = norm(movie.country || '');
    const synopsis = norm(movie.capsule || movie.synopsis || '');
    const year = String(movie.year || '');

    return (
      title.includes(nq) ||
      director.includes(nq) ||
      genres.some(g => g.includes(nq)) ||
      country.includes(nq) ||
      synopsis.includes(nq) ||
      year.includes(nq)
    );
  });
}

/**
 * Sort movies by digital date (newest first)
 */
export function sortByDate(movies) {
  if (!movies || !Array.isArray(movies)) return [];

  return [...movies].sort((a, b) => {
    // Pre-orders sort to the end
    if (a._is_preorder && !b._is_preorder) return 1;
    if (!a._is_preorder && b._is_preorder) return -1;
    if (a._is_preorder && b._is_preorder)
      return (a.digital_date || '').localeCompare(b.digital_date || '');

    // Fest (virtual screening) movies group at the top, under the FEST strip
    const aFest = !!a.filters?.is_virtual_screening;
    const bFest = !!b.filters?.is_virtual_screening;
    if (aFest && !bFest) return -1;
    if (!aFest && bFest) return 1;

    // Virtual screenings: sort by tier (active → upcoming → expired)
    const screeningTier = m => {
      if (!m.filters?.is_virtual_screening) return -1;
      const s = m.virtual_screening_info?.status;
      return s === 'active' ? 0 : s === 'expired' ? 2 : 1;
    };
    const ta = screeningTier(a), tb = screeningTier(b);
    if (ta >= 0 && tb >= 0 && ta !== tb) return ta - tb;

    const dateA = a.digital_date || a.premiere_date || a.release_date || '';
    const dateB = b.digital_date || b.premiere_date || b.release_date || '';
    if (dateB !== dateA) return dateB.localeCompare(dateA);

    // Same date: staff picks first
    const aStaff = a.filters?.is_staff_pick || a.featured;
    const bStaff = b.filters?.is_staff_pick || b.featured;
    if (aStaff && !bStaff) return -1;
    if (!aStaff && bStaff) return 1;
    return 0;
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

  // Plex link (personal library — highest priority)
  if (movie.plex && movie.plex.deep_link) {
    links.push({
      service: 'plex',
      label: 'Play on Plex',
      url: movie.plex.deep_link,
      type: 'plex',
      icon: 'plex',
    });
  }

  // Handle VOD (purchase/rent) — only recognized services
  const vod = watchLinks.vod;
  if (Array.isArray(vod)) {
    vod.forEach(item => {
      if (item && item.link && isValidVodService(item.service)) {
        const isEventive = isEventiveLink(item.service, item.link);
        links.push({
          service: normalizeServiceId(item.service),
          label: isEventive ? 'Buy Ticket' : `Rent on ${item.service || 'VOD'}`,
          url: item.link,
          type: 'purchase',
          rentPrice: item.rent_price || null,
          buyPrice: item.buy_price || null,
        });
      }
    });
  } else if (vod && vod.link && isValidVodService(vod.service)) {
    const isEventive = isEventiveLink(vod.service, vod.link);
    links.push({
      service: normalizeServiceId(vod.service),
      label: isEventive ? 'Buy Ticket' : `Rent on ${vod.service || 'VOD'}`,
      url: vod.link,
      type: 'purchase',
      rentPrice: vod.rent_price || null,
      buyPrice: vod.buy_price || null,
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

  // Pre-order links (JustWatch buy offers for pre-order movies)
  if (links.length === 0) {
    const preOrderLinks = Array.isArray(movie.pre_order_links) ? movie.pre_order_links : [];
    const poDateStr = movie.digital_date
      ? new Date(movie.digital_date + 'T12:00:00').toLocaleDateString('en-US', {month: 'short', day: 'numeric'})
      : null;
    preOrderLinks.forEach(pl => {
      if (pl && pl.link) {
        links.push({
          service: normalizeServiceId(pl.service),
          label: `Pre-Order on ${pl.service || 'VOD'}`,
          sublabel: poDateStr ? `Available ${poDateStr}` : 'Available TBD',
          url: pl.link,
          type: 'purchase',
        });
      }
    });
  }

  return links;
}

/**
 * Check if a VOD service is one we want to display
 */
function isValidVodService(serviceName) {
  if (!serviceName) return false;
  const lower = serviceName.toLowerCase();
  return lower.includes('amazon') ||
         lower.includes('apple') ||
         lower.includes('itunes') ||
         lower.includes('fandango') ||
         lower.includes('youtube') ||
         lower.includes('vudu') ||
         lower.includes('eventive');
}

/**
 * Check if a link is an Eventive/festival screening link
 */
function isEventiveLink(serviceName, link) {
  const s = (serviceName || '').toLowerCase();
  const l = link || '';
  return s.includes('eventive') ||
         l.includes('eventive.org') ||
         l.includes('festivalplayer') ||
         l.includes('shift72.com');
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
  if (lower.includes('tubi')) return 'tubi';
  if (lower.includes('kanopy')) return 'kanopy';
  if (lower.includes('hoopla')) return 'hoopla';
  if (lower.includes('roku')) return 'roku';
  if (lower.includes('pluto')) return 'pluto';
  if (lower.includes('crackle')) return 'crackle';
  if (lower.includes('shudder')) return 'shudder';
  if (lower.includes('fandango')) return 'fandango';
  if (lower.includes('youtube')) return 'youtube';
  if (lower.includes('plex')) return 'plex';
  if (lower.includes('fawesome')) return 'fawesome';
  if (lower.includes('eventive')) return 'eventive';
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
