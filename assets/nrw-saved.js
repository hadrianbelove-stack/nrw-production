/**
 * NRW — Saved list (per-browser watchlist, the ☆ / SAVED view).
 *
 * Stars live in this browser's localStorage only: no accounts, nothing sent
 * anywhere, nothing in data.json. Each entry keeps a full copy of the movie so
 * it stays in SAVED after it ages off the 90-day wall. While the film is still
 * on the wall, sync() refreshes that copy on every load (links/scores stay
 * current); once it ages off, the copy freezes as it was on its last day.
 *
 * Shared by desktop (assets/app.js) and mobile (mobile/mobile.js) — same origin,
 * so one browser has one list across both.
 */
(function (global) {
  'use strict';
  var KEY = 'nrw_saved';

  var _items = null; // { [id]: { savedAt: ms, movie: {...full movie record} } }

  function load() {
    if (_items) return _items;
    try {
      var parsed = JSON.parse(localStorage.getItem(KEY) || '{}');
      _items = (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) ? parsed : {};
    } catch (e) {
      console.warn('[Saved] could not read saved list:', e && e.message);
      _items = {};
    }
    return _items;
  }

  function persist() {
    try { localStorage.setItem(KEY, JSON.stringify(_items)); }
    catch (e) { console.warn('[Saved] could not write saved list:', e && e.message); }
  }

  // Deep copy, with the Select flag baked in — the staff_picks list in a later
  // data.json won't carry an aged-off id, so the snapshot must remember it.
  function snapshot(movie, isPick) {
    var copy = JSON.parse(JSON.stringify(movie));
    copy.filters = Object.assign({}, copy.filters, { is_staff_pick: !!isPick });
    return copy;
  }

  function has(id) { return !!load()[String(id)]; }

  function count() { return Object.keys(load()).length; }

  // Star / unstar. Returns the new state (true = saved).
  function toggle(movie, isPick) {
    var items = load();
    var id = String(movie.id);
    if (items[id]) {
      delete items[id];
    } else {
      items[id] = { savedAt: Date.now(), movie: snapshot(movie, isPick) };
    }
    persist();
    return !!items[id];
  }

  // Refresh the stored copy of every saved film that is still on the wall.
  function sync(movies, isPickFn) {
    var items = load();
    if (!Object.keys(items).length) return;
    var changed = false;
    (movies || []).forEach(function (m) {
      var entry = items[String(m.id)];
      if (!entry) return;
      entry.movie = snapshot(m, isPickFn ? isPickFn(m) : entry.movie.filters && entry.movie.filters.is_staff_pick);
      changed = true;
    });
    if (changed) persist();
  }

  // Every saved film, most recently starred first. Uses the live record when
  // the film is still on the wall, the stored copy otherwise.
  function list(liveMovies) {
    var items = load();
    var live = {};
    (liveMovies || []).forEach(function (m) { live[String(m.id)] = m; });
    return Object.keys(items)
      .sort(function (a, b) { return (items[b].savedAt || 0) - (items[a].savedAt || 0); })
      .map(function (id) { return live[id] || items[id].movie; })
      .filter(function (m) { return m && m.id != null; });
  }

  global.NRWSaved = { has: has, count: count, toggle: toggle, sync: sync, list: list };
})(window);
