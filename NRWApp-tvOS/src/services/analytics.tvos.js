/**
 * New Release Wall - tvOS Analytics Service
 * Tracking focus events, watch button taps, and session metrics
 */

import { Platform } from 'react-native';

// Mixpanel configuration
const MIXPANEL_TOKEN = 'YOUR_MIXPANEL_TOKEN'; // Replace with actual token
let mixpanel = null;

/**
 * Initialize analytics service
 */
export async function initializeAnalytics() {
  // Skip analytics if no token configured
  if (!MIXPANEL_TOKEN || MIXPANEL_TOKEN === 'YOUR_MIXPANEL_TOKEN') {
    console.log('[Analytics] Skipping - no token configured');
    return;
  }

  try {
    // Dynamically import to avoid bundler issues
    const MixpanelModule = require('mixpanel-react-native');
    if (!MixpanelModule || !MixpanelModule.Mixpanel) {
      console.warn('[Analytics] Mixpanel module not available');
      return;
    }

    const { Mixpanel } = MixpanelModule;
    mixpanel = new Mixpanel(MIXPANEL_TOKEN, true);
    await mixpanel.init();

    // Set super properties (sent with every event)
    mixpanel.registerSuperProperties({
      platform: Platform.OS,
      isTV: Platform.isTV,
      appVersion: '1.0.0',
    });

    console.log('[Analytics] Mixpanel initialized');
  } catch (error) {
    console.warn('[Analytics] Mixpanel not available:', error.message);
    // Continue without analytics - don't crash the app
  }
}

/**
 * Track screen view
 */
export function trackScreenView(screenName, properties = {}) {
  if (!mixpanel) return;

  mixpanel.track('Screen View', {
    screen_name: screenName,
    ...properties,
  });
}

/**
 * Track movie focus event (tvOS)
 */
export function trackMovieFocus(movie, shelfIndex, movieIndex) {
  if (!mixpanel) return;

  mixpanel.track('Movie Focus', {
    movie_id: movie.id,
    movie_title: movie.title,
    shelf_index: shelfIndex,
    movie_index: movieIndex,
    is_featured: movie.featured || false,
  });
}

/**
 * Track movie selection
 */
export function trackMovieSelect(movie) {
  if (!mixpanel) return;

  mixpanel.track('Movie Select', {
    movie_id: movie.id,
    movie_title: movie.title,
    director: movie.director,
    year: movie.year,
    is_featured: movie.featured || false,
    genres: movie.genres,
  });
}

/**
 * Track watch button tap
 * Enhanced to track multiple streaming services availability
 */
export function trackWatchButtonTap(movie, service, type) {
  if (!mixpanel) return;

  // Count available streaming services for analysis
  const watchLinks = movie?.watch_links || {};
  const streaming = watchLinks.streaming;
  const vod = watchLinks.vod;

  // Handle both array format (new) and single-object format (legacy)
  const streamingCount = Array.isArray(streaming) ? streaming.length :
    (streaming && streaming.link ? 1 : 0);
  const vodCount = Array.isArray(vod) ? vod.length :
    (vod && vod.link ? 1 : 0);

  mixpanel.track('Watch Button Tap', {
    movie_id: movie.id,
    movie_title: movie.title,
    service: service,
    link_type: type, // 'purchase' or 'streaming'
    has_multiple_streaming: streamingCount > 1,
    streaming_services_count: streamingCount,
    vod_services_count: vodCount,
  });
}

/**
 * Track info button tap (trailer, RT, Wikipedia)
 */
export function trackInfoButtonTap(movie, infoType) {
  if (!mixpanel) return;

  mixpanel.track('Info Button Tap', {
    movie_id: movie.id,
    movie_title: movie.title,
    info_type: infoType,
  });
}

/**
 * Track filter change
 */
export function trackFilterChange(filter, previousFilter) {
  if (!mixpanel) return;

  mixpanel.track('Filter Change', {
    filter: filter,
    previous_filter: previousFilter,
  });
}

/**
 * Track search query
 */
export function trackSearch(query, resultsCount) {
  if (!mixpanel) return;

  mixpanel.track('Search', {
    query: query,
    results_count: resultsCount,
  });
}

/**
 * Track session start
 */
export function trackSessionStart() {
  if (!mixpanel) return;

  mixpanel.track('Session Start', {
    timestamp: new Date().toISOString(),
  });
}

/**
 * Track session end
 */
export function trackSessionEnd(duration) {
  if (!mixpanel) return;

  mixpanel.track('Session End', {
    duration_seconds: duration,
    timestamp: new Date().toISOString(),
  });
}

/**
 * Track app error
 */
export function trackError(error, context = {}) {
  if (!mixpanel) return;

  mixpanel.track('App Error', {
    error_message: error.message || String(error),
    error_stack: error.stack,
    ...context,
  });
}

/**
 * Track remote control event (tvOS)
 */
export function trackRemoteEvent(eventType, context = {}) {
  if (!mixpanel) return;

  mixpanel.track('Remote Control Event', {
    event_type: eventType,
    ...context,
  });
}

/**
 * Set user properties
 */
export function setUserProperties(properties) {
  if (!mixpanel) return;

  mixpanel.getPeople().set(properties);
}

/**
 * Identify user (if you have user accounts)
 */
export function identifyUser(userId) {
  if (!mixpanel) return;

  mixpanel.identify(userId);
}

/**
 * Reset user (logout)
 */
export function resetUser() {
  if (!mixpanel) return;

  mixpanel.reset();
}

export default {
  initializeAnalytics,
  trackScreenView,
  trackMovieFocus,
  trackMovieSelect,
  trackWatchButtonTap,
  trackInfoButtonTap,
  trackFilterChange,
  trackSearch,
  trackSessionStart,
  trackSessionEnd,
  trackError,
  trackRemoteEvent,
  setUserProperties,
  identifyUser,
  resetUser,
};
