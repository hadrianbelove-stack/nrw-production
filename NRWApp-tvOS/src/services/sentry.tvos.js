/**
 * New Release Wall - tvOS Crash Reporting Service
 * Using Sentry for error tracking and performance monitoring
 */

import { Platform } from 'react-native';

// Sentry configuration
const SENTRY_DSN = 'YOUR_SENTRY_DSN'; // Replace with actual DSN
let Sentry = null;

/**
 * Initialize Sentry crash reporting
 */
export async function initializeSentry() {
  // Skip Sentry if no DSN configured
  if (!SENTRY_DSN || SENTRY_DSN === 'YOUR_SENTRY_DSN') {
    console.log('[Sentry] Skipping - no DSN configured');
    return;
  }

  try {
    Sentry = require('@sentry/react-native');

    Sentry.init({
      dsn: SENTRY_DSN,
      environment: __DEV__ ? 'development' : 'production',
      enableAutoSessionTracking: true,
      sessionTrackingIntervalMillis: 30000,

      // Performance monitoring
      tracesSampleRate: 0.2, // 20% of transactions

      // Automatic breadcrumbs
      enableAutoBreadcrumbs: true,

      // tvOS-specific configuration
      enableNativeCrashHandling: true,
      attachStacktrace: true,

      // Debug mode (disable in production)
      debug: __DEV__,

      // Before sending event (can filter/modify)
      beforeSend: (event) => {
        // Add tvOS-specific context
        event.tags = {
          ...event.tags,
          platform: Platform.OS,
          isTV: Platform.isTV,
        };
        return event;
      },
    });

    // Set initial context
    Sentry.setContext('device', {
      platform: Platform.OS,
      isTV: Platform.isTV,
      version: Platform.Version,
    });

    console.log('[Sentry] Initialized');
  } catch (error) {
    console.warn('[Sentry] Not available:', error.message);
    // Continue without Sentry - don't crash the app
  }
}

/**
 * Capture an exception
 */
export function captureException(error, context = {}) {
  if (!Sentry) {
    console.error('[Sentry] Error:', error);
    return;
  }

  Sentry.withScope((scope) => {
    // Add extra context
    Object.entries(context).forEach(([key, value]) => {
      scope.setExtra(key, value);
    });

    Sentry.captureException(error);
  });
}

/**
 * Capture a message
 */
export function captureMessage(message, level = 'info', context = {}) {
  if (!Sentry) {
    console.log(`[Sentry] ${level}:`, message);
    return;
  }

  Sentry.withScope((scope) => {
    scope.setLevel(level);

    Object.entries(context).forEach(([key, value]) => {
      scope.setExtra(key, value);
    });

    Sentry.captureMessage(message);
  });
}

/**
 * Add a breadcrumb (trail of events leading to an error)
 */
export function addBreadcrumb(category, message, data = {}, level = 'info') {
  if (!Sentry) return;

  Sentry.addBreadcrumb({
    category,
    message,
    data,
    level,
  });
}

/**
 * Set user context (for tracking errors by user)
 */
export function setUser(user) {
  if (!Sentry) return;

  if (user) {
    Sentry.setUser({
      id: user.id,
      email: user.email,
      username: user.username,
    });
  } else {
    Sentry.setUser(null);
  }
}

/**
 * Set tag for filtering errors
 */
export function setTag(key, value) {
  if (!Sentry) return;

  Sentry.setTag(key, value);
}

/**
 * Set context for additional data
 */
export function setContext(name, data) {
  if (!Sentry) return;

  Sentry.setContext(name, data);
}

/**
 * Start a performance transaction
 */
export function startTransaction(name, operation) {
  if (!Sentry) return null;

  return Sentry.startTransaction({
    name,
    op: operation,
  });
}

/**
 * Wrap a function with error boundary
 */
export function wrapWithSentry(fn, context = {}) {
  return async (...args) => {
    try {
      return await fn(...args);
    } catch (error) {
      captureException(error, {
        ...context,
        args: JSON.stringify(args),
      });
      throw error;
    }
  };
}

/**
 * Log navigation event (for breadcrumbs)
 */
export function logNavigation(fromScreen, toScreen, params = {}) {
  addBreadcrumb(
    'navigation',
    `Navigated from ${fromScreen} to ${toScreen}`,
    { from: fromScreen, to: toScreen, params },
    'info'
  );
}

/**
 * Log API call (for breadcrumbs)
 */
export function logApiCall(method, url, status, duration) {
  addBreadcrumb(
    'http',
    `${method} ${url}`,
    { method, url, status_code: status, duration_ms: duration },
    status >= 400 ? 'error' : 'info'
  );
}

/**
 * Log user action (for breadcrumbs)
 */
export function logUserAction(action, data = {}) {
  addBreadcrumb('user', action, data, 'info');
}

/**
 * Monitor memory warnings (tvOS has stricter limits)
 */
export function trackMemoryWarning() {
  captureMessage('Memory Warning', 'warning', {
    platform: Platform.OS,
    isTV: Platform.isTV,
  });
}

/**
 * Create an error boundary HOC for React components
 */
export function withErrorBoundary(Component, fallback = null) {
  if (!Sentry) return Component;

  return Sentry.withErrorBoundary(Component, { fallback });
}

export default {
  initializeSentry,
  captureException,
  captureMessage,
  addBreadcrumb,
  setUser,
  setTag,
  setContext,
  startTransaction,
  wrapWithSentry,
  logNavigation,
  logApiCall,
  logUserAction,
  trackMemoryWarning,
  withErrorBoundary,
};
