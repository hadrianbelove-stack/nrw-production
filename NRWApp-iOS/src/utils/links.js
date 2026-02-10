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

export default {
  openWatchLink,
  openTrailer,
  openRottenTomatoes,
  openWikipedia,
  shareMovie,
};
