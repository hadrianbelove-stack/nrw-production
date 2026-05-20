/**
 * New Release Wall - Link Handler
 * Uses iOS Universal Links for seamless app/web transitions
 */

import {Linking, Alert} from 'react-native';

/**
 * Open a watch link using iOS Universal Links
 * iOS automatically detects if the native app is installed:
 * - If installed: prompts user to open in native app
 * - If not installed: opens in Safari
 *
 * @param {string} url - The watch link URL (already contains affiliate tags)
 */
export async function openWatchLink(url) {
  if (!url) {
    console.warn('[Links] No URL provided');
    return;
  }

  try {
    const canOpen = await Linking.canOpenURL(url);

    if (canOpen) {
      await Linking.openURL(url);
    } else {
      Alert.alert(
        'Unable to Open',
        'This link cannot be opened on your device.',
        [{text: 'OK'}],
      );
    }
  } catch (error) {
    console.error('[Links] Error opening URL:', error);
    Alert.alert(
      'Error',
      'There was a problem opening this link. Please try again.',
      [{text: 'OK'}],
    );
  }
}

/**
 * Open trailer link (YouTube)
 */
export async function openTrailer(url) {
  if (!url) return;

  try {
    await Linking.openURL(url);
  } catch (error) {
    console.error('[Links] Error opening trailer:', error);
  }
}

/**
 * Open Rotten Tomatoes link
 */
export async function openRottenTomatoes(url) {
  if (!url) return;

  try {
    await Linking.openURL(url);
  } catch (error) {
    console.error('[Links] Error opening RT:', error);
  }
}

/**
 * Open Metacritic link
 */
export async function openMetacritic(url) {
  if (!url) return;

  try {
    await Linking.openURL(url);
  } catch (error) {
    console.error('[Links] Error opening Metacritic:', error);
  }
}

/**
 * Open Letterboxd link
 */
export async function openLetterboxd(url) {
  if (!url) return;

  try {
    await Linking.openURL(url);
  } catch (error) {
    console.error('[Links] Error opening Letterboxd:', error);
  }
}

/**
 * Open Wikipedia link
 */
export async function openWikipedia(url) {
  if (!url) return;

  try {
    await Linking.openURL(url);
  } catch (error) {
    console.error('[Links] Error opening Wikipedia:', error);
  }
}

/**
 * Share movie (iOS share sheet)
 */
export async function shareMovie(movie) {
  if (!movie) return;

  try {
    const message = `Check out "${movie.title}" on New Release Wall`;
    // Future: Add share functionality with react-native-share
    console.log('[Links] Share:', message);
  } catch (error) {
    console.error('[Links] Error sharing:', error);
  }
}

/**
 * Extract YouTube video ID from various URL formats
 */
export function extractYouTubeId(url) {
  if (!url) return null;
  const patterns = [
    /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)/,
    /^([a-zA-Z0-9_-]{11})$/,
  ];
  for (const pattern of patterns) {
    const match = url.match(pattern);
    if (match && match[1]) return match[1];
  }
  return null;
}

export default {
  openWatchLink,
  openTrailer,
  openRottenTomatoes,
  openMetacritic,
  openLetterboxd,
  openWikipedia,
  shareMovie,
  extractYouTubeId,
};
