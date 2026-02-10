/**
 * New Release Wall - Crash Reporting Service
 * Placeholder for Sentry integration
 *
 * To enable:
 * 1. npm install @sentry/react-native
 * 2. Run: npx @sentry/wizard -i reactNative -p ios
 * 3. Add your DSN below
 * 4. Uncomment the implementation
 */

// import * as Sentry from '@sentry/react-native';

/**
 * Initialize Sentry
 */
export function initSentry() {
  console.log('[Sentry] Crash reporting not configured');
  // Sentry.init({
  //   dsn: 'YOUR_SENTRY_DSN',
  //   debug: __DEV__,
  //   enableAutoSessionTracking: true,
  // });
}

/**
 * Log error to Sentry
 */
export function logError(error, context = {}) {
  console.error('[Sentry] Error:', error, context);
  // Sentry.captureException(error, { extra: context });
}

/**
 * Log message to Sentry
 */
export function logMessage(message, level = 'info') {
  console.log(`[Sentry] ${level}:`, message);
  // Sentry.captureMessage(message, level);
}

/**
 * Set user context
 */
export function setUser(userId) {
  console.log('[Sentry] User set:', userId);
  // Sentry.setUser({ id: userId });
}

export default {
  initSentry,
  logError,
  logMessage,
  setUser,
};
