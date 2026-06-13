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
import { View, Text, StyleSheet, Dimensions, Animated } from 'react-native';
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

const TrailerPlayer = ({ movieList, initialIndex, onClose }) => {
  const [currentIndex, setCurrentIndex] = useState(initialIndex);
  const [paused, setPaused] = useState(false);
  const [closing, setClosing] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  // scrubPosition: where the user has moved the timeline cursor while paused.
  // null = not scrubbing. Committing (SELECT/PLAY_PAUSE while paused) seeks here and resumes.
  const [scrubPosition, setScrubPosition] = useState(null);
  const videoRef = useRef(null);
  const leftArrowOpacity = useRef(new Animated.Value(0.4)).current;
  const rightArrowOpacity = useRef(new Animated.Value(0.4)).current;
  const seekBarOpacity = useRef(new Animated.Value(0)).current;

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

  // When a trailer finishes, roll to the next trailer (continuous reel).
  // Only the last remaining trailer closes the player.
  const handleTrailerEnd = useCallback(() => {
    const nextIdx = findNextTrailerIndex(currentIndex, 1);
    if (nextIdx >= 0) {
      setPaused(false);
      setCurrentIndex(nextIdx);
    } else {
      handleClose();
    }
  }, [currentIndex, findNextTrailerIndex, handleClose]);

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
  useTVEventHandler({
    [TV_EVENTS.LEFT]: paused ? scrubBackward : navigatePrevious,
    [TV_EVENTS.RIGHT]: paused ? scrubForward : navigateNext,
    [TV_EVENTS.SWIPE_LEFT]: paused ? scrubBackward : navigatePrevious,
    [TV_EVENTS.SWIPE_RIGHT]: paused ? scrubForward : navigateNext,
    [TV_EVENTS.MENU]: handleClose,
    [TV_EVENTS.PLAY_PAUSE]: togglePlayPause,
    [TV_EVENTS.SELECT]: paused ? handleResume : handlePause,
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
          onLoad={({ duration: d }) => { setDuration(d); setCurrentTime(0); setScrubPosition(null); }}
          onProgress={({ currentTime: t }) => { if (!paused) setCurrentTime(t); }}
          onEnd={handleTrailerEnd}
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
