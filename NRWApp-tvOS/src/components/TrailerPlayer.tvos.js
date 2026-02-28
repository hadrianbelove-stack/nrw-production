/**
 * New Release Wall - tvOS Trailer Player
 * Fullscreen overlay for in-app trailer playback with prev/next navigation
 * Controls: LEFT/RIGHT = prev/next trailer, MENU = close, PLAY_PAUSE = pause/resume
 */

import React, { useState, useCallback, useRef, useMemo } from 'react';
import { View, Text, StyleSheet, Dimensions, Animated } from 'react-native';
import Video from 'react-native-video';
import { WebView } from 'react-native-webview';
import { useTVEventHandler, TV_EVENTS } from '../utils/focusManager.tvos';
import { extractYouTubeId } from '../utils/links.tvos';
import { Colors } from '../constants/colors';

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');

const TrailerPlayer = ({ movieList, initialIndex, onClose }) => {
  const [currentIndex, setCurrentIndex] = useState(initialIndex);
  const [paused, setPaused] = useState(false);
  const leftArrowOpacity = useRef(new Animated.Value(0.4)).current;
  const rightArrowOpacity = useRef(new Animated.Value(0.4)).current;

  const currentMovie = movieList[currentIndex];
  const trailerUrl = currentMovie?.links?.trailer_hosted || currentMovie?.links?.trailer || '';
  const youtubeId = useMemo(() => extractYouTubeId(trailerUrl), [trailerUrl]);
  const isMP4 = useMemo(() => {
    if (!trailerUrl) return false;
    try {
      return new URL(trailerUrl).pathname.endsWith('.mp4');
    } catch {
      return trailerUrl.endsWith('.mp4');
    }
  }, [trailerUrl]);

  // Flash arrow animation for navigation feedback
  const flashArrow = useCallback((arrowAnim) => {
    Animated.sequence([
      Animated.timing(arrowAnim, { toValue: 1, duration: 100, useNativeDriver: true }),
      Animated.timing(arrowAnim, { toValue: 0.4, duration: 200, useNativeDriver: true }),
    ]).start();
  }, []);

  // Find next movie with a trailer in given direction, wrapping around
  const findNextTrailerIndex = useCallback((fromIndex, direction) => {
    const count = movieList.length;
    if (count === 0) return -1;
    let idx = fromIndex;
    for (let i = 0; i < count - 1; i++) {
      idx = (idx + direction + count) % count;
      const movie = movieList[idx];
      const url = movie.links?.trailer_hosted || movie.links?.trailer;
      if (url) return idx;
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

  // Handle TV remote events
  useTVEventHandler({
    [TV_EVENTS.LEFT]: navigatePrevious,
    [TV_EVENTS.RIGHT]: navigateNext,
    [TV_EVENTS.MENU]: () => onClose(currentIndex),
    [TV_EVENTS.PLAY_PAUSE]: () => setPaused(p => !p),
  });

  // YouTube embed HTML
  const youtubeHtml = useMemo(() => {
    if (!youtubeId) return '';
    return `
      <html><head><meta name="viewport" content="width=device-width,initial-scale=1">
      <style>*{margin:0;padding:0;background:#000}iframe{width:100vw;height:100vh}</style></head>
      <body><iframe src="https://www.youtube.com/embed/${youtubeId}?autoplay=1&controls=1&rel=0&modestbranding=1"
        frameborder="0" allow="autoplay;encrypted-media" allowfullscreen></iframe></body></html>
    `;
  }, [youtubeId]);

  // Count trailers for the counter display
  const trailerCount = useMemo(() => {
    return movieList.filter(m => m.links?.trailer_hosted || m.links?.trailer).length;
  }, [movieList]);

  const currentTrailerNumber = useMemo(() => {
    let count = 0;
    for (let i = 0; i <= currentIndex; i++) {
      const m = movieList[i];
      if (m.links?.trailer_hosted || m.links?.trailer) count++;
    }
    return count;
  }, [movieList, currentIndex]);

  return (
    <View style={styles.container}>
      {/* Video player */}
      {isMP4 ? (
        <Video
          source={{ uri: trailerUrl }}
          style={styles.video}
          resizeMode="contain"
          paused={paused}
          controls={false}
          onEnd={() => onClose(currentIndex)}
          onError={() => onClose(currentIndex)}
        />
      ) : youtubeId ? (
        <WebView
          source={{ html: youtubeHtml }}
          style={styles.video}
          allowsInlineMediaPlayback={true}
          mediaPlaybackRequiresUserAction={false}
          javaScriptEnabled={true}
        />
      ) : null}

      {/* Title overlay */}
      <View style={styles.titleBar}>
        <Text style={styles.title} numberOfLines={1}>{currentMovie?.title}</Text>
        <Text style={styles.counter}>{currentTrailerNumber} / {trailerCount}</Text>
      </View>

      {/* Navigation arrows */}
      {findNextTrailerIndex(currentIndex, -1) >= 0 && (
        <View style={styles.arrowLeft}>
          <Animated.Text style={[styles.arrowText, { opacity: leftArrowOpacity }]}>‹</Animated.Text>
        </View>
      )}
      {findNextTrailerIndex(currentIndex, 1) >= 0 && (
        <View style={styles.arrowRight}>
          <Animated.Text style={[styles.arrowText, { opacity: rightArrowOpacity }]}>›</Animated.Text>
        </View>
      )}

      {/* Hint */}
      <View style={styles.hintBar}>
        <Text style={styles.hintText}>◀ ▶ Navigate trailers  •  Menu to return</Text>
      </View>
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
  hintBar: {
    position: 'absolute',
    bottom: 30,
    left: 0,
    right: 0,
    alignItems: 'center',
  },
  hintText: {
    color: Colors.textMuted,
    fontSize: 20,
  },
});

export default TrailerPlayer;
