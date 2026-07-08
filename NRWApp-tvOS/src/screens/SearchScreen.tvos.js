/**
 * New Release Wall - tvOS Search Screen
 * Full-screen search destination with a custom two-mode on-screen keyboard,
 * porting the Roku app's pattern (NRWApp-Roku/components/screens/SearchScreen.brs):
 *
 *   KEYBOARD mode — d-pad key grid on the left; live match count (header) and
 *                   live results grid (right pane) visible AT ALL TIMES while
 *                   typing. The system tvOS keyboard blurred the results grid
 *                   until the query was committed — that's why it was replaced.
 *   BROWSE mode   — focus is inside the results grid (arrow RIGHT off the key
 *                   grid, or DOWN off its bottom row via the boundary focus
 *                   guide). Menu returns focus to the keyboard; LEFT off the
 *                   grid's first column also lands back on the keys.
 *
 * Mode is derived from where tvOS focus actually is (key onFocus vs result
 * card onFocus), so it can never desync from the focus engine.
 *
 * Menu-key contract (tvos-menu-pop landmine — do not "improve" this):
 * The hardware Menu pop of this route fires at the UIKit layer and, on screens
 * with focusable views, is NOT reliably interceptible (verified on-sim, three
 * ways: beforeRemove preventDefault, TVEventControl menu ownership, and
 * gestureEnabled:false all lost to it). Worse, a beforeRemove preventDefault
 * against the native pop DESYNCS react-navigation's JS state from the native
 * stack, and navigate('Search') becomes a no-op afterward — the original
 * "can't reselect search" bug. So this screen NEVER blocks or preventDefaults
 * the native pop. Instead:
 *   - KEYBOARD mode: Menu is left to the system → native pop → exit search.
 *     The exit-fresh contract holds: the route unmounts (search always reopens
 *     fresh) and HomeScreen re-seeds focus onto the SEARCH button on return.
 *   - BROWSE mode (and only while this route is focused): TVEventControl
 *     .enableTVMenuKey() is scoped on, per the TrailerPlayer pattern, and the
 *     JS 'menu' handler ONLY flips mode + re-seeds focus onto the key grid —
 *     it never calls navigation methods. If the native pop still wins on real
 *     hardware (sim can't prove Menu — TestFlight does), the worst case is
 *     search exits a mode early; the stack can never desync or double-pop.
 */

import React, { useState, useCallback, useEffect, useMemo } from 'react';
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  TVFocusGuideView,
  TVEventControl,
} from 'react-native';
import { useNavigation, useIsFocused } from '@react-navigation/native';
import { Colors } from '../constants/colors';
import MovieCard from '../components/MovieCard.tvos';
import SearchIcon from '../components/SearchIcon.tvos';
import SearchKeyboard from '../components/SearchKeyboard.tvos';
import { useTVEventHandler, TV_EVENTS } from '../utils/focusManager.tvos';
import { getSearchMovieList, setSharedMovieList } from './sharedMovieList';

const CARD_GAP = 24;
const NUM_COLUMNS = 3;

// Ported VERBATIM from assets/shared-config.js NRWConfig.matchesSearch — the
// shared 8-field matcher with accent folding. Keep in sync with the web sites.
// (The character class below is the combining-diacritics range U+0300–U+036F
// written as literal characters, exactly as the web source writes it.)
const matchesSearch = (movie, query) => {
  const norm = s => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const nq = norm(query);
  return norm(movie.title || '').includes(nq) ||
         norm(movie.original_title || '').includes(nq) ||
         norm(movie.crew?.director || movie.director || '').includes(nq) ||
         norm((movie.crew?.cast || []).join(' ')).includes(nq) ||
         norm(movie.capsule || movie.synopsis || '').includes(nq) ||
         norm((movie.genres || []).join(' ')).includes(nq) ||
         norm(movie.country || '').includes(nq) ||
         String(movie.year || '').includes(query);
};

const SearchScreen = ({ route }) => {
  const navigation = useNavigation();
  const isScreenFocused = useIsFocused();
  // Full movie list seeded by HomeScreen via the shared store (route params can't
  // carry the ~1.6MB list). route.params kept as a fallback for older callers.
  const movies = getSearchMovieList().length
    ? getSearchMovieList()
    : (route.params?.movies || []);

  const [query, setQuery] = useState('');
  // 'keyboard' | 'browse' — derived from focus (key onFocus vs card onFocus)
  const [mode, setMode] = useState('keyboard');
  // One-shot focus seed onto the 'A' key: true at mount (search opens typing)
  // and re-armed by Menu in browse mode. Same pattern as HomeScreen's
  // searchBtnPreferredFocus re-seed.
  const [kbdPreferredFocus, setKbdPreferredFocus] = useState(true);
  const [firstResultRef, setFirstResultRef] = useState(null);

  useEffect(() => {
    if (!kbdPreferredFocus) return;
    const t = setTimeout(() => setKbdPreferredFocus(false), 400);
    return () => clearTimeout(t);
  }, [kbdPreferredFocus]);

  // Live results — recomputed every keystroke; the grid never hides.
  const trimmedQuery = query.trim();
  const results = useMemo(
    () => (trimmedQuery ? movies.filter((movie) => matchesSearch(movie, trimmedQuery)) : []),
    [movies, trimmedQuery]
  );

  // Drop the boundary guide's target when there's nothing to land on.
  useEffect(() => {
    if (results.length === 0) setFirstResultRef(null);
  }, [results.length]);

  // Keyboard events
  const handleChar = useCallback((ch) => setQuery((q) => q + ch), []);
  const handleDelete = useCallback(() => setQuery((q) => q.slice(0, -1)), []);
  const handleClear = useCallback(() => setQuery(''), []);
  const handleKeyFocus = useCallback(() => setMode('keyboard'), []);
  const handleResultFocus = useCallback(() => setMode('browse'), []);

  // BROWSE-mode Menu ownership — scoped exactly like TrailerPlayer's effect,
  // and additionally gated on this route being the focused one so a pushed
  // MovieDetail (Search stays mounted beneath it) never has its Menu swallowed.
  useEffect(() => {
    if (mode !== 'browse' || !isScreenFocused) return undefined;
    TVEventControl.enableTVMenuKey();
    return () => TVEventControl.disableTVMenuKey();
  }, [mode, isScreenFocused]);

  useTVEventHandler({
    [TV_EVENTS.MENU]: () => {
      if (mode !== 'browse' || !isScreenFocused) return;
      // Flip mode FIRST (turns Menu ownership off even if the focus re-seed
      // fails, so the next Menu press can always exit natively — no trap),
      // then re-seed focus onto the key grid. Never touch navigation here.
      setMode('keyboard');
      setKbdPreferredFocus(true);
    },
  });

  // Movie selection — seed the shared list with the current results so
  // MovieDetail's left/right arrows browse within the search results.
  const handleMovieSelect = useCallback((movie, index) => {
    setSharedMovieList(results);
    navigation.navigate('MovieDetail', { movie, movieIndex: index });
  }, [navigation, results]);

  const renderItem = useCallback(({ item, index }) => (
    <View style={styles.cardWrapper}>
      <MovieCard
        ref={index === 0 ? ((r) => { if (r) setFirstResultRef(r); }) : undefined}
        movie={item}
        onSelect={() => handleMovieSelect(item, index)}
        onFocus={handleResultFocus}
        testID={`search-result-${index}`}
      />
    </View>
  ), [handleMovieSelect, handleResultFocus]);

  const keyExtractor = useCallback((item, index) => String(item.id || item.tmdb_id || index), []);

  return (
    <View style={styles.container}>
      {/* Header: glass icon + query readout (not a TextInput — focusing one
          summons the system keyboard) + live match count, visible every keystroke */}
      <View style={styles.header}>
        <View style={styles.searchIconWrap}>
          <SearchIcon size={34} color={Colors.primary} strokeWidth={1.8} />
        </View>
        <View style={styles.queryBox}>
          {query.length > 0 ? (
            <Text style={styles.queryText} numberOfLines={1}>
              {query}
              <Text style={styles.queryCursor}>▎</Text>
            </Text>
          ) : (
            <Text style={styles.queryPlaceholder} numberOfLines={1}>
              Search movies, directors, countries…
            </Text>
          )}
        </View>
        {trimmedQuery.length > 0 && (
          <Text style={styles.liveCount}>
            {results.length} {results.length === 1 ? 'match' : 'matches'}
          </Text>
        )}
      </View>

      <View style={styles.body}>
        {/* Left pane: the key grid (KEYBOARD mode home) */}
        <View style={styles.keyboardPane}>
          <SearchKeyboard
            onChar={handleChar}
            onDelete={handleDelete}
            onClear={handleClear}
            onKeyFocus={handleKeyFocus}
            preferredFocus={kbdPreferredFocus}
          />
          {/* DOWN boundary: focus falling off the keyboard's bottom row lands
              here and is redirected to the first result card. Sits under the
              keyboard only (NOT between the panes — a between-pane guide would
              also catch LEFT moves from the grid and trap focus in results). */}
          <TVFocusGuideView
            destinations={firstResultRef && results.length > 0 ? [firstResultRef] : []}
            style={styles.downBoundaryGuide}
          />
          <Text style={styles.hint}>
            {mode === 'browse'
              ? 'MENU back to keyboard  ·  press a poster to open'
              : 'RIGHT or DOWN to browse results  ·  MENU to exit'}
          </Text>
        </View>

        {/* Right pane: live results — visible at all times (the whole point) */}
        <View style={styles.resultsPane}>
          {results.length > 0 ? (
            <FlatList
              data={results}
              renderItem={renderItem}
              keyExtractor={keyExtractor}
              numColumns={NUM_COLUMNS}
              showsVerticalScrollIndicator={false}
              contentContainerStyle={styles.listContent}
              columnWrapperStyle={styles.row}
            />
          ) : trimmedQuery.length > 0 ? (
            <View style={styles.emptyContainer}>
              <SearchIcon size={72} color="rgba(255,255,255,0.18)" strokeWidth={1.4} />
              <Text style={styles.emptyText}>No movies found</Text>
              <Text style={styles.emptyHint}>Try a different title, director, or country</Text>
            </View>
          ) : (
            <View style={styles.emptyContainer}>
              <SearchIcon size={72} color="rgba(0,212,170,0.35)" strokeWidth={1.4} />
              <Text style={styles.emptyText}>Search the wall</Text>
              <Text style={styles.emptyHint}>Results appear here as you type</Text>
            </View>
          )}
        </View>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 68,
    paddingTop: 40,
    paddingBottom: 24,
    gap: 20,
  },
  searchIconWrap: {
    width: 44,
    alignItems: 'center',
  },
  // Query readout — 10-foot sizing, teal-adjacent chrome matching the app
  queryBox: {
    flex: 1,
    height: 84,
    justifyContent: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.08)',
    borderRadius: 16,
    borderWidth: 2,
    borderColor: 'rgba(255,255,255,0.16)',
    paddingHorizontal: 24,
  },
  queryText: {
    color: Colors.textPrimary,
    fontSize: 30,
  },
  queryCursor: {
    color: Colors.primary,
    fontSize: 30,
  },
  queryPlaceholder: {
    color: 'rgba(255,255,255,0.35)',
    fontSize: 30,
  },
  // Live match count — per-keystroke feedback, never hidden (10-foot: >= 22pt)
  liveCount: {
    color: Colors.primary,
    fontSize: 26,
    fontWeight: '700',
  },
  body: {
    flex: 1,
    flexDirection: 'row',
    paddingHorizontal: 68,
    gap: 48,
  },
  keyboardPane: {
    width: 506,
  },
  downBoundaryGuide: {
    width: '100%',
    height: 2,
  },
  hint: {
    marginTop: 16,
    color: Colors.textSecondary,
    fontSize: 22,
    lineHeight: 28,
  },
  resultsPane: {
    flex: 1,
  },
  listContent: {
    paddingBottom: 40,
  },
  row: {
    justifyContent: 'flex-start',
    marginBottom: CARD_GAP,
  },
  cardWrapper: {
    marginRight: CARD_GAP,
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 14,
  },
  emptyText: {
    color: Colors.textPrimary,
    fontSize: 30,
    marginTop: 8,
  },
  emptyHint: {
    color: Colors.textMuted,
    fontSize: 22,
  },
});

export default SearchScreen;
