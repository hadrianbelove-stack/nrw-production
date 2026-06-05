/**
 * New Release Wall - tvOS Trailer Player
 * Fullscreen overlay for in-app trailer playback with prev/next navigation
 * Controls: LEFT/RIGHT or SWIPE = prev/next trailer, MENU = close,
 *           PLAY_PAUSE or SELECT = pause/resume
 *
 * Trailers are self-hosted MP4s on Backblaze B2 (trailer_hosted field), played
 * via react-native-video. tvOS does not support WebView, so only MP4 trailers
 * are playable. See docs/features/TRAILER_HOSTING.md
 */

import React, { useState, useCallback, useRef, useMemo, useEffect } from 'react';
import { View, Text, StyleSheet, Dimensions, Animated } from 'react-native';
import Video from 'react-native-video';
import { useTVEventHandler, TV_EVENTS } from '../utils/focusManager.tvos';
import { Colors } from '../constants/colors';

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');

const SEEK_STEP = 15;

const formatTime = (secs) => {
  const s = Math.floor(secs || 0);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, '0')}`;
};

const TrailerPlayer = ({ movieList, initialIndex, onClose }) => {
  const [currentIndex, setCurrentIndex] = useState(initialIndex);
  const [paused, setPaused] = useState(false);
  const [closing, setClosing] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [seekHint, setSeekHint] = useState(null); // '+15s' | '-15s' | null
  const videoRef = useRef(null);
  const leftArrowOpacity = useRef(new Animated.Value(0.4)).current;
  const rightArrowOpacity = useRef(new Animated.Value(0.4)).current;
  const seekBarOpacity = useRef(new Animated.Value(0)).current;
  const seekHintTimeout = useRef(null);

  // Show/hide seek bar when paused state changes
  useEffect(() => {
    Animated.timing(seekBarOpacity, {
      toValue: paused ? 1 : 0,
      duration: 200,
      useNativeDriver: true,
    }).start();
  }, [paused, seekBarOpacity]);

  // Clear any pending seek-hint timer on unmount
  useEffect(() => {
    return () => { if (seekHintTimeout.current) clearTimeout(seekHintTimeout.current); };
  }, []);

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

  // Toggle play/pause
  const togglePlayPause = useCallback(() => {
    setPaused(p => !p);
  }, []);

  // Flash arrow animation for navigation feedback
  const flashArrow = useCallback((arrowAnim) => {
    Animated.sequence([
      Animated.timing(arrowAnim, { toValue: 1, duration: 100, useNativeDriver: true }),
      Animated.timing(arrowAnim, { toValue: 0.4, duration: 200, useNativeDriver: true }),
    ]).start();
  }, []);

  // Find next movie with an MP4 trailer in given direction, wrapping around
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
    setClosing(true);
    setPaused(true);
    setTimeout(() => onClose(currentIndex), 400);
  }, [closing, currentIndex, onClose]);

  const showSeekHint = useCallback((label) => {
    setSeekHint(label);
    if (seekHintTimeout.current) clearTimeout(seekHintTimeout.current);
    seekHintTimeout.current = setTimeout(() => setSeekHint(null), 800);
  }, []);

  const seekBackward = useCallback(() => {
    const newTime = Math.max(0, currentTime - SEEK_STEP);
    videoRef.current?.seek(newTime);
    setCurrentTime(newTime);
    showSeekHint(`-${SEEK_STEP}s`);
  }, [currentTime, showSeekHint]);

  const seekForward = useCallback(() => {
    const newTime = Math.min(duration || 999, currentTime + SEEK_STEP);
    videoRef.current?.seek(newTime);
    setCurrentTime(newTime);
    showSeekHint(`+${SEEK_STEP}s`);
  }, [currentTime, duration, showSeekHint]);

  // Handle TV remote events — LEFT/RIGHT seek when paused, navigate when playing
  useTVEventHandler({
    [TV_EVENTS.LEFT]: paused ? seekBackward : navigatePrevious,
    [TV_EVENTS.RIGHT]: paused ? seekForward : navigateNext,
    [TV_EVENTS.SWIPE_LEFT]: paused ? seekBackward : navigatePrevious,
    [TV_EVENTS.SWIPE_RIGHT]: paused ? seekForward : navigateNext,
    [TV_EVENTS.MENU]: handleClose,
    [TV_EVENTS.PLAY_PAUSE]: togglePlayPause,
    [TV_EVENTS.SELECT]: togglePlayPause,
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

  return (
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
          onLoad={({ duration: d }) => { setDuration(d); setCurrentTime(0); }}
          onProgress={({ currentTime: t }) => { if (!paused) setCurrentTime(t); }}
          onEnd={handleClose}
          onError={handleClose}
        />
      )}

      {/* Title overlay */}
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

      {/* Seek bar — fades in when paused */}
      <Animated.View style={[styles.seekOverlay, { opacity: seekBarOpacity }]}>
        <View style={styles.seekRow}>
          <Text style={styles.seekHintLeft}>‹ -{SEEK_STEP}s</Text>
          <View style={styles.seekBarWrap}>
            <View style={styles.seekBarTrack}>
              <View style={[styles.seekBarFill, { width: duration > 0 ? `${(currentTime / duration) * 100}%` : '0%' }]} />
              <View style={[styles.seekBarThumb, { left: duration > 0 ? `${(currentTime / duration) * 100}%` : '0%' }]} />
            </View>
            <View style={styles.seekTimeRow}>
              <Text style={styles.seekTime}>{formatTime(currentTime)}</Text>
              <Text style={styles.seekTime}>{formatTime(duration)}</Text>
            </View>
          </View>
          <Text style={styles.seekHintRight}>+{SEEK_STEP}s ›</Text>
        </View>
        {seekHint && (
          <Text style={styles.seekJumpLabel}>{seekHint}</Text>
        )}
      </Animated.View>

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
    backgroundColor: 'rgba(0,0,0,0.75)',
    alignItems: 'center',
  },
  seekRow: {
    flexDirection: 'row',
    alignItems: 'center',
    width: '100%',
    paddingTop: 30,
  },
  seekHintLeft: {
    color: Colors.primary,
    fontSize: 28,
    fontWeight: '600',
    width: 120,
    textAlign: 'left',
  },
  seekHintRight: {
    color: Colors.primary,
    fontSize: 28,
    fontWeight: '600',
    width: 120,
    textAlign: 'right',
  },
  seekBarWrap: {
    flex: 1,
    marginHorizontal: 20,
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
  seekJumpLabel: {
    color: Colors.primary,
    fontSize: 36,
    fontWeight: '700',
    marginTop: 12,
    letterSpacing: 1,
  },
});

export default TrailerPlayer;
