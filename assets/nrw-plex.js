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
  var OWNED_KEY = 'nrw_plex_owned';   // sessionStorage cache of the owned id list
  var SECTION = '4';

  var _owned = null; // Set of tmdb id strings

  function trimSlash(s) { return (s || '').replace(/\/+$/, ''); }
  function getToken() { try { return localStorage.getItem(TOKEN_KEY) || ''; } catch (e) { return ''; } }
  function getServer() { try { return trimSlash(localStorage.getItem(SERVER_KEY) || ''); } catch (e) { return ''; } }
  function isUnlocked() { return !!(getToken() && getServer()); }

  function loadCachedOwned() {
    if (_owned) return _owned;
    try {
      var raw = sessionStorage.getItem(OWNED_KEY);
      if (raw) { _owned = new Set(JSON.parse(raw)); return _owned; }
    } catch (e) {}
    return null;
  }

  // Fetch the owner's library once and build the owned-id Set. Cached in
  // sessionStorage so navigating the wall doesn't refetch. Silent no-op when
  // locked; falls back to any cached set on error.
  function loadOwned() {
    if (!isUnlocked()) return Promise.resolve(null);
    var cached = loadCachedOwned();
    if (cached) return Promise.resolve(cached);
    var url = getServer() + '/library/sections/' + SECTION + '/all?includeGuids=1';
    return fetch(url, { headers: { Accept: 'application/json', 'X-Plex-Token': getToken() } })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (data) {
        var items = (data.MediaContainer && data.MediaContainer.Metadata) || [];
        var ids = [];
        for (var i = 0; i < items.length; i++) {
          var guids = items[i].Guid || [];
          for (var j = 0; j < guids.length; j++) {
            var id = guids[j].id || '';
            if (id.indexOf('tmdb://') === 0) { ids.push(id.slice(7)); break; }
          }
        }
        _owned = new Set(ids);
        try { sessionStorage.setItem(OWNED_KEY, JSON.stringify(ids)); } catch (e) {}
        if (global.console) console.log('[NRWPlex] ' + ids.length + ' owned films');
        return _owned;
      })
      .catch(function (e) {
        if (global.console) console.log('[NRWPlex] library fetch failed:', e && e.message);
        return loadCachedOwned();
      });
  }

  function owns(id) {
    var set = _owned || loadCachedOwned();
    return !!(set && set.has(String(id)));
  }

  function watchUrl(id) { return 'watch.html?m=' + encodeURIComponent(id); }

  function unlock(token, server) {
    try {
      localStorage.setItem(TOKEN_KEY, (token || '').trim());
      localStorage.setItem(SERVER_KEY, trimSlash((server || '').trim()));
      sessionStorage.removeItem(OWNED_KEY);
      _owned = null;
    } catch (e) {}
  }
  function lock() {
    try {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(SERVER_KEY);
      sessionStorage.removeItem(OWNED_KEY);
    } catch (e) {}
    _owned = null;
  }

  global.NRWPlex = {
    isUnlocked: isUnlocked,
    loadOwned: loadOwned,
    owns: owns,
    watchUrl: watchUrl,
    unlock: unlock,
    lock: lock,
    getServer: getServer,
    getToken: getToken,
  };
})(typeof window !== 'undefined' ? window : this);
