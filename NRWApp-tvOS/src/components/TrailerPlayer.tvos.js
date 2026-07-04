/**
 * New Release Wall - tvOS Trailer Player
 * Fullscreen overlay for in-app trailer playback with prev/next navigation
 * Controls: LEFT/RIGHT or SWIPE = prev/next (playing) / scrub (paused), MENU = close,
 *           PLAY_PAUSE or SELECT = pause / confirm scrub + resume
 *
 * Trailers are self-hosted MP4s on Backblaze B2 (trailer_hosted field), played
 * via react-native-video. tvOS does not support WebView, so only MP4 trailers
 * are playable. See docs/features/TRAILER_HOSTING.md
 */

import React, { useState, useCallback, useRef, useMemo, useEffect } from 'react';
import { View, Text, StyleSheet, Dimensions, Animated, TVEventControl, ActivityIndicator } from 'react-native';
import Video from 'react-native-video';
import { useTVEventHandler, TV_EVENTS } from '../utils/focusManager.tvos';
import { Colors } from '../constants/colors';

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');

const SEEK_STEP = 5; // Scrub step per d-pad press (seconds)

const formatTime = (secs) => {
  const s = Math.floor(secs || 0);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, '0')}`;
};

const TrailerPlayer = ({ movieList, initialIndex, onClose, onIndexChange }) => {
  const [currentIndex, setCurrentIndex] = useState(initialIndex);
  const [paused, setPaused] = useState(false);
  const [closing, setClosing] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  // scrubPosition: where the user has moved the timeline cursor while paused.
  // null = not scrubbing. Committing (SELECT/PLAY_PAUSE while paused) seeks here and resumes.
  const [scrubPosition, setScrubPosition] = useState(null);
  const [buffering, setBuffering] = useState(false);
  // toastText: brief non-blocking notice ("Trailer unavailable"). Timers held
  // in refs so unmount/close can cancel them.
  const [toastText, setToastText] = useState(null);
  const videoRef = useRef(null);
  const leftArrowOpacity = useRef(new Animated.Value(0.4)).current;
  const rightArrowOpacity = useRef(new Animated.Value(0.4)).current;
  const seekBarOpacity = useRef(new Animated.Value(0)).current;
  // Chrome (title/counter/arrows/hints) auto-hides after 4s of playback; any
  // remote press brings it back via withPoke below.
  const chromeOpacity = useRef(new Animated.Value(1)).current;
  // Dip-to-black between trailers (single mounted <Video> — never crossfade
  // two players; that resurrects the background-audio leak).
  const transitionOpacity = useRef(new Animated.Value(0)).current;
  const hideTimerRef = useRef(null);
  const errorTimerRef = useRef(null);
  const forceFadeTimerRef = useRef(null);
  const firstMountRef = useRef(true);
  const pausedRef = useRef(false);
  const closingRef = useRef(false);

  // Show/hide seek bar when paused state changes
  useEffect(() => {
    Animated.timing(seekBarOpacity, {
      toValue: paused ? 1 : 0,
      duration: 200,
      useNativeDriver: true,
    }).start();
  }, [paused, seekBarOpacity]);

  // Reset scrub state when the movie changes
  useEffect(() => {
    setScrubPosition(null);
  }, [currentIndex]);

  // Chrome auto-hide: show now; while playing, re-arm a 4s hide timer.
  // Timer callbacks read pausedRef/closingRef so they never act on stale state.
  const showChrome = useCallback(() => {
    if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    Animated.timing(chromeOpacity, { toValue: 1, duration: 150, useNativeDriver: true }).start();
    if (!pausedRef.current && !closingRef.current) {
      hideTimerRef.current = setTimeout(() => {
        if (!pausedRef.current && !closingRef.current) {
          Animated.timing(chromeOpacity, { toValue: 0, duration: 300, useNativeDriver: true }).start();
        }
      }, 4000);
    }
  }, [chromeOpacity]);

  // Every remote press shows chrome AND performs its action — poke-and-act,
  // never poke-only (a hidden-chrome RIGHT must still advance the reel).
  const withPoke = useCallback((fn) => () => { showChrome(); fn(); }, [showChrome]);

  // Chrome pinned visible while paused; hide timer re-arms on resume.
  useEffect(() => {
    pausedRef.current = paused;
    showChrome();
  }, [paused, showChrome]);

  // Show chrome on mount and on every trailer change; clean up all timers.
  useEffect(() => {
    showChrome();
    return () => {
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
      if (errorTimerRef.current) clearTimeout(errorTimerRef.current);
      if (forceFadeTimerRef.current) clearTimeout(forceFadeTimerRef.current);
    };
  }, [currentIndex, showChrome]);

  // Dip-to-black on trailer change (skip the initial mount — the spinner covers
  // first load). onReadyForDisplay fades it out; the 1500ms timer is a safety
  // net in case that event never fires.
  useEffect(() => {
    if (firstMountRef.current) { firstMountRef.current = false; return; }
    transitionOpacity.setValue(1);
    if (forceFadeTimerRef.current) clearTimeout(forceFadeTimerRef.current);
    forceFadeTimerRef.current = setTimeout(() => {
      Animated.timing(transitionOpacity, { toValue: 0, duration: 250, useNativeDriver: true }).start();
    }, 1500);
  }, [currentIndex, transitionOpacity]);

  const currentMovie = movieList[currentIndex];
  const trailerUrl = currentMovie?.links?.trailer_hosted || '';
  const isMP4 = useMemo(() => {
    if (!trailerUrl) return false;
    try {
      return new URL(trailerUrl).pathname.endsWith('.mp4');
    } catch {
      return trailerUrl.endsWith('.mp4');
    }
  }, [trailerUrl]);

  // Pause — initialise scrub cursor at current playhead
  const handlePause = useCallback(() => {
    setScrubPosition(currentTime);
    setPaused(true);
  }, [currentTime]);

  // Resume — seek to wherever the scrub cursor ended up, then play
  const handleResume = useCallback(() => {
    if (scrubPosition !== null) {
      videoRef.current?.seek(scrubPosition);
      setCurrentTime(scrubPosition);
      setScrubPosition(null);
    }
    setPaused(false);
  }, [scrubPosition]);

  const togglePlayPause = useCallback(() => {
    if (paused) { handleResume(); } else { handlePause(); }
  }, [paused, handlePause, handleResume]);

  // Flash arrow animation for navigation feedback
  const flashArrow = useCallback((arrowAnim) => {
    Animated.sequence([
      Animated.timing(arrowAnim, { toValue: 1, duration: 100, useNativeDriver: true }),
      Animated.timing(arrowAnim, { toValue: 0.4, duration: 200, useNativeDriver: true }),
    ]).start();
  }, []);

  // Find next movie with an MP4 trailer in given direction, wrapping around.
  // Used by manual LEFT/RIGHT navigation and the edge-arrow visibility.
  const findNextTrailerIndex = useCallback((fromIndex, direction) => {
    const count = movieList.length;
    if (count === 0) return -1;
    let idx = fromIndex;
    for (let i = 0; i < count - 1; i++) {
      idx = (idx + direction + count) % count;
      const movie = movieList[idx];
      if (movie.links?.trailer_hosted) return idx;
    }
    return -1;
  }, [movieList]);

  // Find the next hosted trailer strictly AFTER fromIndex, no wrap-around.
  // Auto-advance uses this so "play all" runs each remaining trailer once and
  // then closes — never an infinite loop that keeps remounting AVPlayers
  // (the source of the background-audio leak / app break).
  const findNextTrailerForward = useCallback((fromIndex) => {
    for (let i = fromIndex + 1; i < movieList.length; i++) {
      if (movieList[i].links?.trailer_hosted) return i;
    }
    return -1;
  }, [movieList]);

  const navigateNext = useCallback(() => {
    const nextIdx = findNextTrailerIndex(currentIndex, 1);
    if (nextIdx >= 0) {
      flashArrow(rightArrowOpacity);
      setPaused(false);
      setCurrentIndex(nextIdx);
    }
  }, [currentIndex, findNextTrailerIndex, flashArrow, rightArrowOpacity]);

  const navigatePrevious = useCallback(() => {
    const prevIdx = findNextTrailerIndex(currentIndex, -1);
    if (prevIdx >= 0) {
      flashArrow(leftArrowOpacity);
      setPaused(false);
      setCurrentIndex(prevIdx);
    }
  }, [currentIndex, findNextTrailerIndex, flashArrow, leftArrowOpacity]);

  // Close handler — stop audio via the `paused` prop (not imperative pause(), which
  // is absent in newer react-native-video). Keep <Video> in the tree while the
  // AVPlayer drains, then let MovieDetail unmount the whole TrailerPlayer.
  const handleClose = useCallback(() => {
    if (closing) return;
    closingRef.current = true;
    setClosing(true);
    setPaused(true);
    setTimeout(() => onClose(currentIndex), 400);
  }, [closing, currentIndex, onClose]);

  // Report the on-screen trailer index to the parent route so it can return the
  // detail screen to whatever trailer was playing (incl. after auto-advance).
  useEffect(() => {
    onIndexChange?.(currentIndex);
  }, [currentIndex, onIndexChange]);

  // Own the Menu key in JS while a trailer is up. On real hardware this screen
  // has no focused view, so without this the Menu press bypasses the app and
  // suspends it (build 28), and giving the container focus instead double-handled
  // the press and wedged navigation (build 29). enableTVMenuKey makes RN's
  // recognizer swallow Menu and emit the 'menu' TV event; the handler below does
  // exactly one JS-driven close. Scoped to the player's lifetime so Menu at the
  // app root still suspends the app per Apple HIG.
  useEffect(() => {
    TVEventControl.enableTVMenuKey();
    return () => TVEventControl.disableTVMenuKey();
  }, []);

  // When a trailer finishes, roll forward to the next trailer ("play all").
  // No wrap: after the last hosted trailer the player closes, so the reel
  // never loops forever remounting AVPlayers. The `closing` guard stops an
  // end-of-stream event from re-arming playback mid-close.
  const handleTrailerEnd = useCallback(() => {
    if (closing) return;
    const nextIdx = findNextTrailerForward(currentIndex);
    if (nextIdx >= 0) {
      setPaused(false);
      setCurrentIndex(nextIdx);
    } else {
      handleClose();
    }
  }, [closing, currentIndex, findNextTrailerForward, handleClose]);

  // Playback error: brief toast, then roll forward (forward-only, so a run of
  // bad URLs terminates at close). Replaces the old silent handleClose.
  const handleError = useCallback(() => {
    if (closing) return;
    setBuffering(false);
    setToastText('Trailer unavailable');
    if (errorTimerRef.current) clearTimeout(errorTimerRef.current);
    errorTimerRef.current = setTimeout(() => {
      setToastText(null);
      handleTrailerEnd();
    }, 1200);
  }, [closing, handleTrailerEnd]);

  // Defensive no-source guard: a movie without a hosted MP4 at currentIndex
  // renders no <Video> and would otherwise sit on a frozen black screen.
  useEffect(() => {
    if (isMP4 || closing) return;
    setToastText('Trailer unavailable');
    const t = setTimeout(() => { setToastText(null); handleTrailerEnd(); }, 800);
    return () => clearTimeout(t);
  }, [isMP4, closing, currentIndex, handleTrailerEnd]);

  // Scrub cursor movement — moves the timeline position without seeking the video
  const scrubBackward = useCallback(() => {
    setScrubPosition(prev => Math.max(0, (prev ?? currentTime) - SEEK_STEP));
  }, [currentTime]);

  const scrubForward = useCallback(() => {
    setScrubPosition(prev => Math.min(duration || 999, (prev ?? currentTime) + SEEK_STEP));
  }, [currentTime, duration]);

  // Handle TV remote events
  // Playing:  LEFT/RIGHT navigate prev/next trailer
  // Paused:   LEFT/RIGHT move scrub cursor; SELECT/PLAY_PAUSE commits position and resumes
  // All handlers wrapped in withPoke: chrome reappears AND the action fires.
  useTVEventHandler({
    [TV_EVENTS.LEFT]: withPoke(paused ? scrubBackward : navigatePrevious),
    [TV_EVENTS.RIGHT]: withPoke(paused ? scrubForward : navigateNext),
    [TV_EVENTS.SWIPE_LEFT]: withPoke(paused ? scrubBackward : navigatePrevious),
    [TV_EVENTS.SWIPE_RIGHT]: withPoke(paused ? scrubForward : navigateNext),
    // MENU is handled HERE in JS (see the enableTVMenuKey effect above) — one
    // deterministic close, independent of the tvOS focus engine. handleClose
    // drains audio then onClose pops the route / dismisses the overlay host.
    [TV_EVENTS.MENU]: withPoke(handleClose),
    [TV_EVENTS.PLAY_PAUSE]: withPoke(togglePlayPause),
    [TV_EVENTS.SELECT]: withPoke(paused ? handleResume : handlePause),
  });

  // Count trailers for the counter display
  const trailerCount = useMemo(() => {
    return movieList.filter(m => m.links?.trailer_hosted).length;
  }, [movieList]);

  const currentTrailerNumber = useMemo(() => {
    let count = 0;
    for (let i = 0; i <= currentIndex; i++) {
      if (movieList[i].links?.trailer_hosted) count++;
    }
    return count;
  }, [movieList, currentIndex]);

  // What auto-advance will play next — drives the "Up next" pill
  const nextForwardIdx = useMemo(
    () => findNextTrailerForward(currentIndex),
    [findNextTrailerForward, currentIndex]
  );

  return (
    // Deliberately NO focusable views here: Menu is owned in JS via
    // enableTVMenuKey (see effect above). A focusable container (build 29)
    // double-handled the press on hardware and wedged navigation — don't re-add.
    <View style={styles.container}>
      {/* Video player — kept in tree during close so AVPlayer can drain audio cleanly.
          paused={closing || paused} stops audio immediately via prop (imperative pause()
          is absent in modern react-native-video). Unmount happens when parent removes
          the whole TrailerPlayer after the 400ms timeout. */}
      {isMP4 && (
        <Video
          key={trailerUrl}
          ref={videoRef}
          source={{ uri: trailerUrl }}
          style={styles.video}
          resizeMode="contain"
          paused={closing || paused}
          controls={false}
          playInBackground={false}
          playWhenInactive={false}
          onLoadStart={() => setBuffering(true)}
          onBuffer={({ isBuffering }) => setBuffering(isBuffering)}
          onReadyForDisplay={() => {
            setBuffering(false);
            if (forceFadeTimerRef.current) clearTimeout(forceFadeTimerRef.current);
            Animated.timing(transitionOpacity, { toValue: 0, duration: 250, useNativeDriver: true }).start();
          }}
          onLoad={({ duration: d }) => { setDuration(d); setCurrentTime(0); setScrubPosition(null); setBuffering(false); }}
          onProgress={({ currentTime: t }) => { if (!paused) setCurrentTime(t); }}
          onEnd={handleTrailerEnd}
          onError={handleError}
        />
      )}

      {/* Dip-to-black between trailers — above video, below chrome */}
      <Animated.View
        pointerEvents="none"
        style={[StyleSheet.absoluteFill, { backgroundColor: '#000', opacity: transitionOpacity }]}
      />

      {/* Buffering spinner */}
      {buffering && !closing && (
        <View style={styles.spinnerWrap} pointerEvents="none">
          <ActivityIndicator size="large" color={Colors.primary} />
        </View>
      )}

      {/* Chrome — title bar, arrows, playing hint. Auto-hides after 4s of playback. */}
      <Animated.View pointerEvents="none" style={[StyleSheet.absoluteFill, { opacity: chromeOpacity }]}>
        <View style={styles.titleBar}>
          <Text style={styles.title} numberOfLines={1}>{currentMovie?.title}</Text>
          <Text style={styles.counter}>{currentTrailerNumber} / {trailerCount}</Text>
        </View>

        {/* Navigation arrows — only visible when playing */}
        {!paused && findNextTrailerIndex(currentIndex, -1) >= 0 && (
          <View style={styles.arrowLeft}>
            <Animated.Text style={[styles.arrowText, { opacity: leftArrowOpacity }]}>‹</Animated.Text>
          </View>
        )}
        {!paused && findNextTrailerIndex(currentIndex, 1) >= 0 && (
          <View style={styles.arrowRight}>
            <Animated.Text style={[styles.arrowText, { opacity: rightArrowOpacity }]}>›</Animated.Text>
          </View>
        )}

        {/* Control hint while playing (pause has its own hint in the seek overlay) */}
        {!paused && (
          <Text style={styles.chromeHint}>‹ › prev / next · select to pause</Text>
        )}
      </Animated.View>

      {/* Up next — near the end of a trailer or while paused */}
      {nextForwardIdx >= 0 && (paused || (duration > 0 && duration - currentTime <= 10)) && (
        <View style={styles.upNextPill} pointerEvents="none">
          <Text style={styles.upNextLabel}>Up next:</Text>
          <Text style={styles.upNextTitle} numberOfLines={1}>{movieList[nextForwardIdx]?.title}</Text>
        </View>
      )}

      {/* Toast — brief notices (errors) */}
      {toastText && (
        <View style={styles.toastPill} pointerEvents="none">
          <Text style={styles.toastText}>{toastText}</Text>
        </View>
      )}

      {/* Seek bar — fades in when paused. Thumb tracks scrubPosition (not currentTime).
          Press SELECT or PLAY_PAUSE to confirm and jump to that position. */}
      {(() => {
        const displayPos = scrubPosition ?? currentTime;
        const pct = duration > 0 ? `${(displayPos / duration) * 100}%` : '0%';
        return (
          <Animated.View style={[styles.seekOverlay, { opacity: seekBarOpacity }]}>
            <View style={styles.seekBarWrap}>
              <View style={styles.seekBarTrack}>
                <View style={[styles.seekBarFill, { width: pct }]} />
                <View style={[styles.seekBarThumb, { left: pct }]} />
              </View>
              <View style={styles.seekTimeRow}>
                <Text style={styles.seekTime}>{formatTime(displayPos)}</Text>
                <Text style={styles.seekTime}>{formatTime(duration)}</Text>
              </View>
              <Text style={styles.seekHint}>‹ › scrub · select to resume · menu to close</Text>
            </View>
          </Animated.View>
        );
      })()}

    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    top: 0,
    left: 0,
    width: SCREEN_WIDTH,
    height: SCREEN_HEIGHT,
    backgroundColor: '#000',
    zIndex: 100,
  },
  video: {
    flex: 1,
    backgroundColor: '#000',
  },
  titleBar: {
    position: 'absolute',
    top: 40,
    left: 100,
    right: 100,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  title: {
    color: '#fff',
    fontSize: 32,
    fontWeight: '600',
    flex: 1,
  },
  counter: {
    color: Colors.textMuted,
    fontSize: 24,
    marginLeft: 20,
  },
  chromeHint: {
    position: 'absolute',
    bottom: 40,
    alignSelf: 'center',
    color: Colors.textMuted,
    fontSize: 20,
  },
  spinnerWrap: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    alignItems: 'center',
    justifyContent: 'center',
  },
  upNextPill: {
    position: 'absolute',
    right: 100,
    bottom: 180,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(10,12,16,0.85)',
    borderWidth: 1,
    borderColor: 'rgba(0,212,170,0.4)',
    borderRadius: 24,
    paddingVertical: 10,
    paddingHorizontal: 18,
    maxWidth: 560,
  },
  upNextLabel: {
    color: Colors.primary,
    fontSize: 20,
    fontWeight: '600',
    marginRight: 8,
  },
  upNextTitle: {
    color: '#fff',
    fontSize: 20,
    flexShrink: 1,
  },
  toastPill: {
    position: 'absolute',
    bottom: 100,
    alignSelf: 'center',
    backgroundColor: 'rgba(20,20,20,0.95)',
    borderWidth: 1,
    borderColor: 'rgba(0,212,170,0.5)',
    borderRadius: 24,
    paddingVertical: 10,
    paddingHorizontal: 20,
  },
  toastText: {
    color: '#fff',
    fontSize: 20,
    fontWeight: '600',
  },
  seekHint: {
    color: Colors.textMuted,
    fontSize: 20,
    textAlign: 'center',
    marginTop: 14,
  },
  arrowLeft: {
    position: 'absolute',
    left: 20,
    top: 0,
    bottom: 0,
    justifyContent: 'center',
  },
  arrowRight: {
    position: 'absolute',
    right: 20,
    top: 0,
    bottom: 0,
    justifyContent: 'center',
  },
  arrowText: {
    color: Colors.primary,
    fontSize: 80,
    fontWeight: '300',
  },
  seekOverlay: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    paddingBottom: 60,
    paddingHorizontal: 100,
    paddingTop: 30,
    backgroundColor: 'rgba(0,0,0,0.75)',
  },
  seekBarWrap: {
    width: '100%',
  },
  seekBarTrack: {
    height: 6,
    backgroundColor: 'rgba(255,255,255,0.25)',
    borderRadius: 3,
    position: 'relative',
    overflow: 'visible',
  },
  seekBarFill: {
    height: 6,
    backgroundColor: Colors.primary,
    borderRadius: 3,
  },
  seekBarThumb: {
    position: 'absolute',
    top: -7,
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: '#ffffff',
    marginLeft: -10,
  },
  seekTimeRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 10,
  },
  seekTime: {
    color: 'rgba(255,255,255,0.7)',
    fontSize: 22,
    fontWeight: '500',
  },
});

export default TrailerPlayer;
