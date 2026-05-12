/**
 * New Release Wall - Cache Utilities
 * Shared caching logic using AsyncStorage
 */

import AsyncStorage from '@react-native-async-storage/async-storage';

// Cache keys
export const CACHE_KEYS = {
  MOVIES: '@nrw_movies',
  LAST_FOCUSED_INDEX: '@nrw_last_focused',
  USER_PREFERENCES: '@nrw_preferences',
  TOP_SHELF_DATA: '@nrw_top_shelf',
};

/**
 * Get cached data by key
 */
export async function getCachedData(key) {
  try {
    const jsonValue = await AsyncStorage.getItem(key);
    return jsonValue != null ? JSON.parse(jsonValue) : null;
  } catch (error) {
    console.error('[Cache] Error reading cache:', error);
    return null;
  }
}

/**
 * Set cached data by key
 */
export async function setCachedData(key, value) {
  try {
    const jsonValue = JSON.stringify(value);
    await AsyncStorage.setItem(key, jsonValue);
  } catch (error) {
    console.error('[Cache] Error writing cache:', error);
  }
}

/**
 * Remove cached data by key
 */
export async function removeCachedData(key) {
  try {
    await AsyncStorage.removeItem(key);
  } catch (error) {
    console.error('[Cache] Error removing cache:', error);
  }
}

/**
 * Clear all cached data
 */
export async function clearAllCache() {
  try {
    const keys = Object.values(CACHE_KEYS);
    await AsyncStorage.multiRemove(keys);
  } catch (error) {
    console.error('[Cache] Error clearing cache:', error);
  }
}

/**
 * Get cache size (approximate)
 */
export async function getCacheSize() {
  try {
    const keys = await AsyncStorage.getAllKeys();
    let totalSize = 0;

    for (const key of keys) {
      const value = await AsyncStorage.getItem(key);
      if (value) {
        totalSize += value.length;
      }
    }

    return totalSize;
  } catch (error) {
    console.error('[Cache] Error getting cache size:', error);
    return 0;
  }
}

/**
 * Save last focused movie index (for returning from detail screen)
 */
export async function saveLastFocusedIndex(shelfIndex, movieIndex) {
  await setCachedData(CACHE_KEYS.LAST_FOCUSED_INDEX, {
    shelfIndex,
    movieIndex,
    timestamp: Date.now(),
  });
}

/**
 * Get last focused movie index
 */
export async function getLastFocusedIndex() {
  const data = await getCachedData(CACHE_KEYS.LAST_FOCUSED_INDEX);

  // Only return if saved within last 5 minutes
  if (data && Date.now() - data.timestamp < 5 * 60 * 1000) {
    return {
      shelfIndex: data.shelfIndex,
      movieIndex: data.movieIndex,
    };
  }

  return null;
}

/**
 * Save user preferences (filter, sort order, etc.)
 */
export async function saveUserPreferences(preferences) {
  await setCachedData(CACHE_KEYS.USER_PREFERENCES, preferences);
}

/**
 * Get user preferences
 */
export async function getUserPreferences() {
  return await getCachedData(CACHE_KEYS.USER_PREFERENCES) || {
    filter: null,
    sortOrder: 'date',
  };
}

export default {
  CACHE_KEYS,
  getCachedData,
  setCachedData,
  removeCachedData,
  clearAllCache,
  getCacheSize,
  saveLastFocusedIndex,
  getLastFocusedIndex,
  saveUserPreferences,
  getUserPreferences,
};
