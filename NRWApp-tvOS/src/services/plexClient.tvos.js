/**
 * NRW tvOS — Personal Plex client (owner-only, per-device unlock)
 *
 * Privacy model: this app ships with NO Plex data. Nothing about the owner's
 * library is in data.json or the app binary. On a device the owner unlocks once
 * (UnlockScreen stores a token + server address in AsyncStorage), we query his
 * Plex server DIRECTLY for which films he owns and stream them via the NRW player.
 * A TestFlight tester who never unlocks has no token -> no fetch -> no NRW button.
 *
 * The membership map (tmdb id -> Plex ratingKey) is fetched at app start and
 * cached, so MovieDetail can decide synchronously whether to show the button.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';

const TOKEN_KEY = 'nrw_plex_token';
const SERVER_KEY = 'nrw_plex_server';
const LIBMAP_KEY = 'nrw_plex_libmap';
const SECTION = '4'; // movie library section key on the owner's server

let _memMap = null; // { [tmdbId]: ratingKey }

function encodeQuery(obj) {
  return Object.keys(obj)
    .map((k) => encodeURIComponent(k) + '=' + encodeURIComponent(obj[k]))
    .join('&');
}
function trimSlash(s) {
  return (s || '').replace(/\/+$/, '');
}

export async function getPlexConfig() {
  const [token, server] = await Promise.all([
    AsyncStorage.getItem(TOKEN_KEY),
    AsyncStorage.getItem(SERVER_KEY),
  ]);
  return { token: token || '', server: server || '' };
}

export async function setPlexConfig(token, server) {
  await AsyncStorage.multiSet([
    [TOKEN_KEY, (token || '').trim()],
    [SERVER_KEY, trimSlash((server || '').trim())],
  ]);
}

export async function clearPlexConfig() {
  await AsyncStorage.multiRemove([TOKEN_KEY, SERVER_KEY, LIBMAP_KEY]);
  _memMap = null;
}

export async function isUnlocked() {
  const { token, server } = await getPlexConfig();
  return !!(token && server);
}

async function loadCachedMap() {
  if (_memMap) return _memMap;
  try {
    const raw = await AsyncStorage.getItem(LIBMAP_KEY);
    _memMap = raw ? JSON.parse(raw) : {};
  } catch (e) {
    _memMap = {};
  }
  return _memMap;
}

/**
 * Fetch the owner's movie library and rebuild the tmdb -> ratingKey map.
 * Falls back to the cached map on any failure (offline, expired token) so the
 * app never breaks — the owner just sees stale membership until the next success.
 */
export async function refreshLibraryMap() {
  const { token, server } = await getPlexConfig();
  if (!token || !server) return null;
  try {
    const url = `${trimSlash(server)}/library/sections/${SECTION}/all?includeGuids=1`;
    const res = await fetch(url, {
      headers: { Accept: 'application/json', 'X-Plex-Token': token },
    });
    if (!res.ok) {
      console.log('[Plex] library fetch HTTP', res.status, '- using cached map');
      return await loadCachedMap();
    }
    const data = await res.json();
    const items = (data.MediaContainer && data.MediaContainer.Metadata) || [];
    const map = {};
    for (let i = 0; i < items.length; i++) {
      const guids = items[i].Guid || [];
      for (let j = 0; j < guids.length; j++) {
        const id = guids[j].id || '';
        if (id.indexOf('tmdb://') === 0) {
          map[id.slice(7)] = String(items[i].ratingKey);
          break;
        }
      }
    }
    _memMap = map;
    await AsyncStorage.setItem(LIBMAP_KEY, JSON.stringify(map));
    console.log('[Plex] library map: ' + Object.keys(map).length + ' owned films');
    return map;
  } catch (e) {
    console.log('[Plex] library fetch failed:', e && e.message, '- using cached map');
    return await loadCachedMap();
  }
}

/** Synchronous lookup for render paths — requires refreshLibraryMap() to have run. */
export function getRatingKeySync(tmdbId) {
  return _memMap ? _memMap[String(tmdbId)] || null : null;
}

export async function getRatingKey(tmdbId) {
  const map = _memMap || (await loadCachedMap());
  return map ? map[String(tmdbId)] || null : null;
}

/**
 * Build the Plex HLS transcode URL. Transcoding lets any container/codec
 * (mkv, hevc, eac3, DTS...) play through AVPlayer/react-native-video.
 */
export async function buildHlsUrl(ratingKey) {
  const { token, server } = await getPlexConfig();
  if (!token || !server || !ratingKey) return null;
  const session = 'nrw-' + ratingKey + '-' + Math.floor(Date.now() / 1000);
  const q = encodeQuery({
    path: '/library/metadata/' + ratingKey,
    mediaIndex: '0',
    partIndex: '0',
    protocol: 'hls',
    fastSeek: '1',
    directPlay: '0',
    directStream: '1',
    'X-Plex-Token': token,
    'X-Plex-Client-Identifier': 'nrw-tvos-player',
    'X-Plex-Product': 'NRW',
    'X-Plex-Platform': 'tvOS',
    session: session,
    videoResolution: '1920x1080',
    maxVideoBitrate: '20000',
  });
  return trimSlash(server) + '/video/:/transcode/universal/start.m3u8?' + q;
}
