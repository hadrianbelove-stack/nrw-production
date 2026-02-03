/**
 * New Release Wall - tvOS Link Handling Utilities
 * Handles Universal Links, app launching, and affiliate integration
 */

import { Linking, Platform, Alert } from 'react-native';

// Service app identifiers for deep linking
// Note: Some schemes may need verification on actual devices
const SERVICE_SCHEMES = {
  amazon: 'aiv://',
  prime_video: 'primevideo://',
  apple_tv: 'videos://',
  netflix: 'nflx://',
  hulu: 'hulu://',
  max: 'hbomax://',
  disney_plus: 'disneyplus://',
  peacock: 'peacock://',
  paramount_plus: 'paramountplus://',
  mubi: 'mubi://',
  criterion: 'criterionchannel://',
  youtube: 'youtube://',
  vix: 'vix://',
  angel_studios: 'angel://',
  shudder: 'shudder://',
  fandango: 'fandangoathome://',
  plex: 'plex://',
};

// Web fallback URLs
const SERVICE_WEB_URLS = {
  amazon: 'https://www.amazon.com',
  apple_tv: 'https://tv.apple.com',
  netflix: 'https://www.netflix.com',
  hulu: 'https://www.hulu.com',
  max: 'https://www.max.com',
  disney_plus: 'https://www.disneyplus.com',
  peacock: 'https://www.peacocktv.com',
  paramount_plus: 'https://www.paramountplus.com',
  mubi: 'https://mubi.com',
  criterion: 'https://www.criterionchannel.com',
  youtube: 'https://www.youtube.com',
  vix: 'https://www.vix.com',
  angel_studios: 'https://www.angel.com',
  shudder: 'https://www.shudder.com',
  fandango: 'https://www.fandangoathome.com',
  plex: 'https://app.plex.tv',
};

/**
 * Open a URL with the appropriate handler
 * Attempts to open the provided content URL first, then falls back to app scheme or web
 * @param {string} url - The URL to open (content-specific URL)
 * @param {string} service - Optional service identifier for fallback
 */
export async function openURL(url, service = null) {
  try {
    // First, try to open the provided content URL directly
    // This preserves content-specific deep links (e.g., YouTube video URLs)
    if (url) {
      const canOpenUrl = await Linking.canOpenURL(url);
      if (canOpenUrl) {
        await Linking.openURL(url);
        return { success: true };
      }
    }

    // If content URL fails and service specified, try generic app scheme
    if (service && SERVICE_SCHEMES[service]) {
      const appScheme = SERVICE_SCHEMES[service];
      const canOpenApp = await Linking.canOpenURL(appScheme);

      if (canOpenApp) {
        await Linking.openURL(appScheme);
        return { success: true, usedAppScheme: true };
      }
    }

    // Fallback to web URL
    const webUrl = getWebFallbackUrl(url, service);
    if (webUrl) {
      const canOpenWeb = await Linking.canOpenURL(webUrl);
      if (canOpenWeb) {
        await Linking.openURL(webUrl);
        return { success: true, fallback: true };
      }
    }

    throw new Error('Unable to open URL');
  } catch (error) {
    console.error('[Links] Error opening URL:', error);
    return { success: false, error: error.message };
  }
}

/**
 * Get web fallback URL for a service
 */
function getWebFallbackUrl(originalUrl, service) {
  if (originalUrl.startsWith('http')) {
    return originalUrl;
  }

  if (service && SERVICE_WEB_URLS[service]) {
    return SERVICE_WEB_URLS[service];
  }

  return null;
}

/**
 * Open Amazon Prime Video with affiliate tag preserved
 * @param {string} url - Amazon URL with affiliate tag
 */
export async function openAmazon(url) {
  // Ensure affiliate tag is present
  if (url && !url.includes('tag=')) {
    // Add default affiliate tag if missing
    const separator = url.includes('?') ? '&' : '?';
    url = `${url}${separator}tag=nrw04-20`;
  }

  return openURL(url, 'amazon');
}

/**
 * Open Apple TV with affiliate token
 * @param {string} url - Apple TV URL
 * @param {string} affiliateToken - Optional affiliate token
 */
export async function openAppleTV(url, affiliateToken = null) {
  if (affiliateToken && url && !url.includes('at=')) {
    const separator = url.includes('?') ? '&' : '?';
    url = `${url}${separator}at=${affiliateToken}`;
  }

  return openURL(url, 'apple_tv');
}

/**
 * Open trailer (usually YouTube)
 * Uses multiple URL formats for tvOS compatibility
 * @param {string} url - Trailer URL
 */
export async function openTrailer(url) {
  if (!url) {
    return { success: false, error: 'No trailer URL provided' };
  }

  // Extract YouTube video ID if it's a YouTube URL
  const youtubeId = extractYouTubeId(url);

  if (youtubeId) {
    // Try multiple URL formats for tvOS YouTube deep linking
    // Note: canOpenURL is unreliable on tvOS, so we try formats directly
    const urlsToTry = [
      `youtube://www.youtube.com/watch?v=${youtubeId}`,
      `youtube://watch?v=${youtubeId}`,
      `vnd.youtube://www.youtube.com/watch?v=${youtubeId}`,
    ];

    for (let i = 0; i < urlsToTry.length; i++) {
      try {
        console.log(`[Links] Trying YouTube format ${i + 1}: ${urlsToTry[i]}`);
        await Linking.openURL(urlsToTry[i]);
        return { success: true };
      } catch (error) {
        console.log(`[Links] Format ${i + 1} failed:`, error.message);
        // Continue to next format
      }
    }

    // All YouTube formats failed
    console.error('[Links] All YouTube URL formats failed');
    return { success: false, error: 'Unable to open YouTube' };
  }

  // For non-YouTube trailers, use openURL directly
  return openURL(url);
}

/**
 * Extract YouTube video ID from various URL formats
 */
function extractYouTubeId(url) {
  if (!url) return null;

  const patterns = [
    /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)/,
    /^([a-zA-Z0-9_-]{11})$/,
  ];

  for (const pattern of patterns) {
    const match = url.match(pattern);
    if (match && match[1]) {
      return match[1];
    }
  }

  return null;
}

/**
 * Open Rotten Tomatoes page
 * @param {string} url - Rotten Tomatoes URL
 */
export async function openRottenTomatoes(url) {
  return openURL(url);
}

/**
 * Open Wikipedia page
 * @param {string} url - Wikipedia URL
 */
export async function openWikipedia(url) {
  return openURL(url);
}

/**
 * Open Plex with deep link to specific content
 * Uses plex:// scheme for tvOS app deep linking
 * @param {string} deepLink - Plex deep link URL (plex://play/?metadataKey=...)
 */
export async function openPlex(deepLink) {
  if (!deepLink) {
    return { success: false, error: 'No Plex deep link provided' };
  }

  try {
    // Try the deep link directly - it should open in Plex app
    console.log('[Links] Opening Plex with deep link:', deepLink);
    await Linking.openURL(deepLink);
    return { success: true };
  } catch (error) {
    console.error('[Links] Error opening Plex:', error);
    // Fall back to generic Plex app launch
    return openURL(null, 'plex');
  }
}

/**
 * Check if a streaming service app is installed
 * @param {string} service - Service identifier
 */
export async function isServiceAppInstalled(service) {
  if (!SERVICE_SCHEMES[service]) {
    return false;
  }

  try {
    return await Linking.canOpenURL(SERVICE_SCHEMES[service]);
  } catch {
    return false;
  }
}

/**
 * Get list of installed streaming service apps
 */
export async function getInstalledServiceApps() {
  const services = Object.keys(SERVICE_SCHEMES);
  const installed = [];

  for (const service of services) {
    const isInstalled = await isServiceAppInstalled(service);
    if (isInstalled) {
      installed.push(service);
    }
  }

  return installed;
}

/**
 * Handle incoming Universal Link (when app is opened via link)
 * @param {function} callback - Called with parsed movie ID
 */
export function setupUniversalLinkHandler(callback) {
  // Handle initial URL (app was opened via link)
  Linking.getInitialURL().then(url => {
    if (url) {
      handleIncomingLink(url, callback);
    }
  });

  // Handle URL when app is already running
  const subscription = Linking.addEventListener('url', event => {
    handleIncomingLink(event.url, callback);
  });

  return subscription;
}

/**
 * Parse incoming Universal Link and extract movie ID
 */
function handleIncomingLink(url, callback) {
  if (!url || !callback) return;

  // Parse URL to extract movie ID
  // Example: nrw://movie/123 or https://newreleasewall.com/movie/123
  const patterns = [
    /nrw:\/\/movie\/(\d+)/,
    /newreleasewall\.com\/movie\/(\d+)/,
    /movie\/(\d+)/,
  ];

  for (const pattern of patterns) {
    const match = url.match(pattern);
    if (match && match[1]) {
      callback({ movieId: match[1], url });
      return;
    }
  }

  // No match, callback with just the URL
  callback({ url });
}

/**
 * Show error alert when link fails to open
 */
export function showLinkError(serviceName = 'this service') {
  Alert.alert(
    'Unable to Open',
    `We couldn't open ${serviceName}. Please try again later.`,
    [{ text: 'OK', style: 'default' }]
  );
}

export default {
  openURL,
  openAmazon,
  openAppleTV,
  openTrailer,
  openRottenTomatoes,
  openWikipedia,
  openPlex,
  isServiceAppInstalled,
  getInstalledServiceApps,
  setupUniversalLinkHandler,
  showLinkError,
  SERVICE_SCHEMES,
  SERVICE_WEB_URLS,
};
