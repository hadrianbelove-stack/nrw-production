/**
 * New Release Wall - Cache Utilities
 * AsyncStorage helpers for local data caching
 */

import AsyncStorage from '@react-native-async-storage/async-storage';

export const CACHE_KEYS = {
  MOVIES: '@nrw_movies',
  LAST_FETCH: '@nrw_last_fetch',
  FILTER_STATE: '@nrw_filter_state',
};

/**
 * Get cached data from AsyncStorage
 */
export async function getCachedData(key) {
  try {
    const value = await AsyncStorage.getItem(key);
    return value ? JSON.parse(value) : null;
  } catch (error) {
    console.error('[Cache] Error reading:', error);
    return null;
  }
}

/**
 * Set cached data in AsyncStorage
 */
export async function setCachedData(key, data) {
  try {
    await AsyncStorage.setItem(key, JSON.stringify(data));
  } catch (error) {
    console.error('[Cache] Error writing:', error);
  }
}

/**
 * Clear specific cache key
 */
export async function clearCache(key) {
  try {
    await AsyncStorage.removeItem(key);
  } catch (error) {
    console.error('[Cache] Error clearing:', error);
  }
}

/**
 * Clear all NRW cache
 */
export async function clearAllCache() {
  try {
    const keys = Object.values(CACHE_KEYS);
    await AsyncStorage.multiRemove(keys);
  } catch (error) {
    console.error('[Cache] Error clearing all:', error);
  }
}

/**
 * Get last fetch timestamp
 */
export async function getLastFetchTime() {
  const data = await getCachedData(CACHE_KEYS.LAST_FETCH);
  return data?.timestamp || null;
}

/**
 * Format last updated time for display
 */
export function formatLastUpdated(timestamp) {
  if (!timestamp) return null;

  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  return date.toLocaleDateString();
}

export default {
  CACHE_KEYS,
  getCachedData,
  setCachedData,
  clearCache,
  clearAllCache,
  getLastFetchTime,
  formatLastUpdated,
};
