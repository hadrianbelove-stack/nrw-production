/**
 * NRW — Personal Plex (owner-only, client-side).
 *
 * Privacy model (mirrors the tvOS app): NOTHING about the owner's library is in
 * data.json or this repo. On a browser the owner has unlocked (token + server in
 * localStorage — set by visiting watch.html and pasting them once), we query his
 * Plex server DIRECTLY for which films he owns, and show a teal NRW button on the
 * wall + detail that opens the reskinned watch.html player. A visitor who never
 * unlocks has no token → no query → no button. Shared localStorage keys with
 * watch.html so one unlock covers the whole site.
 */
(function (global) {
  'use strict';
  var TOKEN_KEY = 'nrw_plex_token';
  var SERVER_KEY = 'nrw_plex_server';
  var LIBMAP_KEY = 'nrw_plex_libmap'; // sessionStorage cache of { tmdbId: ratingKey }

  var _map = null; // { [tmdbId]: ratingKey }

  function trimSlash(s) { return (s || '').replace(/\/+$/, ''); }
  function getToken() { try { return localStorage.getItem(TOKEN_KEY) || ''; } catch (e) { return ''; } }
  function getServer() { try { return trimSlash(localStorage.getItem(SERVER_KEY) || ''); } catch (e) { return ''; } }
  function isUnlocked() { return !!(getToken() && getServer()); }

  function loadCachedMap() {
    if (_map) return _map;
    try {
      var raw = sessionStorage.getItem(LIBMAP_KEY);
      if (raw) { _map = JSON.parse(raw); return _map; }
    } catch (e) {}
    return null;
  }
  function clearCache() {
    _map = null;
    try { sessionStorage.removeItem(LIBMAP_KEY); } catch (e) {}
  }

  function getJson(url) {
    return fetch(url, { headers: { Accept: 'application/json', 'X-Plex-Token': getToken() } })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
  }

  // Section keys differ per server, so discover every movie library rather
  // than hardcoding one.
  function movieSectionKeys(server) {
    return getJson(server + '/library/sections').then(function (data) {
      var dirs = (data.MediaContainer && data.MediaContainer.Directory) || [];
      return dirs.filter(function (d) { return d.type === 'movie'; })
                 .map(function (d) { return String(d.key); });
    });
  }

  // Fetch the owner's movie libraries once and build the tmdb -> ratingKey map.
  // Cached in sessionStorage so navigating the wall doesn't refetch. Silent
  // no-op when locked; falls back to any cached map on error.
  function loadOwned() {
    if (!isUnlocked()) return Promise.resolve(null);
    var cached = loadCachedMap();
    if (cached) return Promise.resolve(cached);
    var server = getServer();
    return movieSectionKeys(server)
      .then(function (keys) {
        return Promise.all(keys.map(function (k) {
          return getJson(server + '/library/sections/' + k + '/all?includeGuids=1');
        }));
      })
      .then(function (results) {
        var map = {};
        for (var r = 0; r < results.length; r++) {
          var items = (results[r].MediaContainer && results[r].MediaContainer.Metadata) || [];
          for (var i = 0; i < items.length; i++) {
            var guids = items[i].Guid || [];
            for (var j = 0; j < guids.length; j++) {
              var id = guids[j].id || '';
              if (id.indexOf('tmdb://') === 0) { map[id.slice(7)] = String(items[i].ratingKey); break; }
            }
          }
        }
        _map = map;
        try { sessionStorage.setItem(LIBMAP_KEY, JSON.stringify(map)); } catch (e) {}
        if (global.console) console.log('[NRWPlex] ' + Object.keys(map).length + ' owned films');
        return _map;
      })
      .catch(function (e) {
        if (global.console) console.log('[NRWPlex] library fetch failed:', e && e.message);
        return loadCachedMap();
      });
  }

  function ratingKey(id) {
    var map = _map || loadCachedMap();
    return (map && map[String(id)]) || null;
  }
  function owns(id) { return !!ratingKey(id); }

  // Carry the ratingKey so watch.html (opened in a fresh tab with no session
  // cache) can start playback without refetching the whole library.
  function watchUrl(id) {
    var rk = ratingKey(id);
    return 'watch.html?m=' + encodeURIComponent(id) + (rk ? '&k=' + encodeURIComponent(rk) : '');
  }

  function unlock(token, server) {
    try {
      localStorage.setItem(TOKEN_KEY, (token || '').trim());
      localStorage.setItem(SERVER_KEY, trimSlash((server || '').trim()));
    } catch (e) {}
    clearCache();
  }
  function lock() {
    try {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(SERVER_KEY);
    } catch (e) {}
    clearCache();
  }

  global.NRWPlex = {
    isUnlocked: isUnlocked,
    loadOwned: loadOwned,
    owns: owns,
    ratingKey: ratingKey,
    watchUrl: watchUrl,
    unlock: unlock,
    lock: lock,
    clearCache: clearCache,
    getServer: getServer,
    getToken: getToken,
  };
})(typeof window !== 'undefined' ? window : this);
