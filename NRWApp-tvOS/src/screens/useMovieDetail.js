/**
 * New Release Wall - Movie Detail Screen (Shared Logic)
 * Contains business logic shared between iOS and tvOS
 */

import { useState, useMemo } from 'react';
import { getWatchLinks, getInfoLinks } from '../services/api';

const COUNTRY_ABBREV = {
  'United States of America': 'USA', 'United States': 'USA', 'US': 'USA', 'USA': 'USA',
  'United Kingdom': 'UK', 'Great Britain': 'UK', 'GB': 'UK',
  'Germany': 'GER', 'DE': 'GER',
  'France': 'FRA', 'FR': 'FRA',
  'South Korea': 'KOR', 'KR': 'KOR',
  'Netherlands': 'NED', 'NL': 'NED',
  'Switzerland': 'SUI', 'CH': 'SUI',
  'South Africa': 'RSA', 'ZA': 'RSA',
  'Chile': 'CHL', 'CL': 'CHL',
  'Japan': 'JPN', 'JP': 'JPN',
  'Italy': 'ITA', 'IT': 'ITA',
  'Spain': 'ESP', 'ES': 'ESP',
  'Sweden': 'SWE', 'SE': 'SWE',
  'Denmark': 'DEN', 'DK': 'DEN',
  'Norway': 'NOR', 'NO': 'NOR',
  'Poland': 'POL', 'PL': 'POL',
  'Australia': 'AUS', 'AU': 'AUS',
  'Canada': 'CAN', 'CA': 'CAN',
  'Mexico': 'MEX', 'MX': 'MEX',
  'Brazil': 'BRA', 'BR': 'BRA',
  'Argentina': 'ARG', 'AR': 'ARG',
  'Belgium': 'BEL', 'BE': 'BEL',
  'Portugal': 'POR', 'PT': 'POR',
  'Romania': 'ROM', 'RO': 'ROM',
  'Hungary': 'HUN', 'HU': 'HUN',
  'Czech Republic': 'CZE', 'CZ': 'CZE',
  'Austria': 'AUT', 'AT': 'AUT',
  'Ireland': 'IRL', 'IE': 'IRL',
  'China': 'CHN', 'CN': 'CHN',
  'Hong Kong': 'HKG', 'HK': 'HKG',
  'Taiwan': 'TPE', 'TW': 'TPE',
  'India': 'IND', 'IN': 'IND',
  'Iran': 'IRI', 'IR': 'IRI',
  'Israel': 'ISR', 'IL': 'ISR',
  'Turkey': 'TUR', 'TR': 'TUR',
  'Greece': 'GRE', 'GR': 'GRE',
  'Finland': 'FIN', 'FI': 'FIN',
  'New Zealand': 'NZL', 'NZ': 'NZL',
  'Bosnia and Herzegovina': 'BIH',
  'Saudi Arabia': 'KSA',
  'Unknown': '—',
};

const abbreviateCountry = (name) => {
  if (!name) return '';
  return COUNTRY_ABBREV[name] || name.slice(0, 3).toUpperCase();
};

/**
 * Custom hook for Movie Detail state management
 * Shared between iOS and tvOS implementations
 */
export function useMovieDetail(movie) {
  // State
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  // Watch links (Amazon, Apple TV, streaming services)
  const watchLinks = useMemo(() => {
    if (!movie) return [];
    return getWatchLinks(movie);
  }, [movie]);

  // Info links (trailer, RT, Wikipedia)
  const infoLinks = useMemo(() => {
    if (!movie) return [];
    return getInfoLinks(movie);
  }, [movie]);

  // Plex links (personal library - show first!)
  const plexLinks = useMemo(() => {
    return watchLinks.filter((link) => link.type === 'plex');
  }, [watchLinks]);

  // Purchase links (rent/buy)
  const purchaseLinks = useMemo(() => {
    return watchLinks.filter((link) => link.type === 'purchase');
  }, [watchLinks]);

  // Streaming links
  const streamingLinks = useMemo(() => {
    return watchLinks.filter((link) => link.type === 'streaming');
  }, [watchLinks]);

  // Get formatted runtime
  const formattedRuntime = useMemo(() => {
    if (!movie?.runtime) return null;

    const minutes = parseInt(movie.runtime, 10);
    if (isNaN(minutes)) return movie.runtime;

    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;

    if (hours === 0) return `${mins}m`;
    if (mins === 0) return `${hours}h`;
    return `${hours}h ${mins}m`;
  }, [movie]);

  // Get formatted genres
  const formattedGenres = useMemo(() => {
    if (!movie?.genres || !Array.isArray(movie.genres)) return '';
    return movie.genres.join(' • ');
  }, [movie]);

  // Get Rotten Tomatoes score display
  const rtScore = useMemo(() => {
    if (!movie?.rt_score && movie?.rt_score !== 0) return null;

    const score = parseInt(movie.rt_score, 10);
    if (isNaN(score)) return null;

    return {
      value: score,
      label: `${score}%`,
      isFresh: score >= 60,
    };
  }, [movie]);

  // Get Metacritic score display
  const mcScore = useMemo(() => {
    if (!movie?.metacritic_score) return null;
    const score = parseInt(movie.metacritic_score, 10);
    if (isNaN(score) || score === 0) return null;
    return { value: score, label: `${score}` };
  }, [movie]);

  // Get IMDB rating display
  const imdbScore = useMemo(() => {
    if (!movie?.imdb_rating) return null;
    const rating = parseFloat(movie.imdb_rating);
    if (isNaN(rating)) return null;
    return { value: rating, label: rating.toFixed(1) };
  }, [movie]);

  // Get Letterboxd score display \u2014 the honest number ("3.4"), never rounded
  // stars (whole-star rounding inflated 3.5 to \u2605\u2605\u2605\u2605; audit #7, owner call)
  const lbScore = useMemo(() => {
    if (!movie?.letterboxd_score) return null;
    const score = parseFloat(movie.letterboxd_score);
    if (isNaN(score)) return null;
    return { value: score, label: score.toFixed(1) };
  }, [movie]);

  // Get formatted countries — abbreviated per style guide (USA/UK exceptions, 3-letter for rest)
  const formattedCountries = useMemo(() => {
    const raw = (movie?.countries && Array.isArray(movie.countries) && movie.countries.length > 0)
      ? movie.countries
      : movie?.country ? [movie.country] : [];
    if (raw.length === 0) return '';
    return raw.map(abbreviateCountry).join(' / ');
  }, [movie]);

  // Get formatted language
  const formattedLanguage = useMemo(() => {
    if (!movie?.language) return '';
    if (Array.isArray(movie.language)) {
      return movie.language.join(', ');
    }
    return movie.language;
  }, [movie]);

  // Check if movie has any watch options
  const hasWatchOptions = useMemo(() => {
    return watchLinks.length > 0;
  }, [watchLinks]);

  // Check if movie has any info links
  const hasInfoLinks = useMemo(() => {
    return infoLinks.length > 0;
  }, [infoLinks]);

  return {
    // State
    isLoading,
    error,

    // Computed values
    watchLinks,
    infoLinks,
    plexLinks,
    purchaseLinks,
    streamingLinks,
    formattedRuntime,
    formattedGenres,
    rtScore,
    mcScore,
    imdbScore,
    lbScore,
    formattedCountries,
    formattedLanguage,
    hasWatchOptions,
    hasInfoLinks,
  };
}

/**
 * Get poster URL with preferred size
 */
export function getPosterUrl(movie, size = 'w780') {
  if (!movie) return null;

  // Check various poster URL fields
  const posterUrl = movie.poster_url || movie.posterUrl || movie.poster;

  if (!posterUrl) return null;

  // If it's a TMDB URL, we can adjust the size
  if (posterUrl.includes('image.tmdb.org')) {
    // Replace size in URL (e.g., /w500/ to /w780/)
    return posterUrl.replace(/\/w\d+\//, `/${size}/`);
  }

  return posterUrl;
}

/**
 * Get backdrop URL for detail screen background
 */
export function getBackdropUrl(movie) {
  if (!movie) return null;

  // Check for backdrop URL
  if (movie.backdrop_url || movie.backdropUrl || movie.backdrop) {
    return movie.backdrop_url || movie.backdropUrl || movie.backdrop;
  }

  // Fall back to poster (w1280 is plenty for a blurred TV backdrop, uses far less memory than original)
  return getPosterUrl(movie, 'w1280');
}

/**
 * Format synopsis for display
 * Truncates if too long with ellipsis
 */
export function formatSynopsis(synopsis, maxLength = 500) {
  if (!synopsis) return '';

  if (synopsis.length <= maxLength) return synopsis;

  // Truncate at word boundary
  const truncated = synopsis.substring(0, maxLength);
  const lastSpace = truncated.lastIndexOf(' ');

  return truncated.substring(0, lastSpace) + '...';
}

/**
 * Create metadata string for display
 */
export function getMetadataString(movie) {
  if (!movie) return '';

  const parts = [];

  if (movie.year) parts.push(movie.year);
  if (movie.runtime) {
    const minutes = parseInt(movie.runtime, 10);
    if (!isNaN(minutes)) {
      const hours = Math.floor(minutes / 60);
      const mins = minutes % 60;
      if (hours > 0) {
        parts.push(`${hours}h ${mins > 0 ? `${mins}m` : ''}`);
      } else {
        parts.push(`${mins}m`);
      }
    }
  }
  if (movie.rating) parts.push(movie.rating);

  return parts.join(' • ');
}

/**
 * Create accessibility label for movie
 */
export function getAccessibilityLabel(movie) {
  if (!movie) return '';

  const parts = [movie.title];

  if (movie.year) parts.push(`from ${movie.year}`);
  if (movie.director) parts.push(`directed by ${movie.director}`);
  if (movie.rt_score) parts.push(`${movie.rt_score} on Rotten Tomatoes`);

  return parts.join(', ');
}

export default {
  useMovieDetail,
  getPosterUrl,
  getBackdropUrl,
  formatSynopsis,
  getMetadataString,
  getAccessibilityLabel,
};
