/**
 * Saved list (per-device watchlist, the SAVE button / SAVED view).
 *
 * Lives in AsyncStorage on this Apple TV only: no accounts, nothing sent
 * anywhere, nothing in data.json. Deliberately NOT in utils/cache.js CACHE_KEYS
 * — clearAllCache() must never wipe someone's list.
 *
 * Each entry keeps a full copy of the movie so it stays in SAVED after it ages
 * off the 90-day wall. syncSaved() refreshes that copy on every data load while
 * the film is still on the wall; once it ages off, the copy freezes.
 * Mirrors assets/nrw-saved.js on the web.
 */
import { useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

const SAVED_KEY = 'nrw_saved';

let _items = null; // { [id]: { savedAt: ms, movie: {...full movie record} } }
let _loading = null;
const _listeners = new Set();

function notify() {
  _listeners.forEach((fn) => {
    try { fn(); } catch (e) { console.log('[Saved] listener failed:', e && e.message); }
  });
}

async function persist() {
  try {
    await AsyncStorage.setItem(SAVED_KEY, JSON.stringify(_items));
  } catch (e) {
    console.log('[Saved] could not write saved list:', e && e.message);
  }
}

export function loadSaved() {
  if (_items) return Promise.resolve(_items);
  if (!_loading) {
    _loading = AsyncStorage.getItem(SAVED_KEY)
      .then((raw) => {
        const parsed = raw ? JSON.parse(raw) : {};
        _items = parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
      })
      .catch((e) => {
        console.log('[Saved] could not read saved list:', e && e.message);
        _items = {};
      })
      .then(() => { notify(); return _items; });
  }
  return _loading;
}

// Deep copy with the Select flag baked in — a later data.json's staff picks
// won't carry an aged-off film, so the snapshot must remember it.
function snapshot(movie) {
  const copy = JSON.parse(JSON.stringify(movie));
  copy.filters = { ...(copy.filters || {}), is_staff_pick: !!(movie.filters?.is_staff_pick || movie.featured) };
  return copy;
}

export function isSaved(id) {
  return !!(_items && _items[String(id)]);
}

// Star / unstar. Returns the new state (true = saved).
export async function toggleSaved(movie) {
  await loadSaved();
  const id = String(movie.id);
  if (_items[id]) {
    delete _items[id];
  } else {
    _items[id] = { savedAt: Date.now(), movie: snapshot(movie) };
  }
  notify();
  await persist();
  return !!_items[id];
}

// Refresh the stored copy of every saved film still on the wall. No notify —
// the list's membership doesn't change, only the copies.
export async function syncSaved(movies) {
  await loadSaved();
  if (!Object.keys(_items).length) return;
  let changed = false;
  (movies || []).forEach((m) => {
    const entry = _items[String(m.id)];
    if (!entry) return;
    entry.movie = snapshot(m);
    changed = true;
  });
  if (changed) await persist();
}

// Every saved film, most recently saved first: the live record when the film
// is still on the wall, the stored copy otherwise.
export function savedList(liveMovies) {
  if (!_items) return [];
  const live = new Map((liveMovies || []).map((m) => [String(m.id), m]));
  return Object.keys(_items)
    .sort((a, b) => (_items[b].savedAt || 0) - (_items[a].savedAt || 0))
    .map((id) => live.get(id) || _items[id].movie)
    .filter((m) => m && m.id != null);
}

// Re-render hook: returns a counter that bumps on load and on every star/unstar.
export function useSavedVersion() {
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const bump = () => setVersion((v) => v + 1);
    _listeners.add(bump);
    loadSaved();
    return () => { _listeners.delete(bump); };
  }, []);
  return version;
}
