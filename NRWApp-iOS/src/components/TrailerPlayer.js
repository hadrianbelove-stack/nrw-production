/**
 * New Release Wall - iOS Trailer Player
 * Fullscreen overlay for in-app trailer playback with prev/next navigation
 * Controls: Swipe left/right or tap arrows = prev/next, X button = close
 */

import React, { useState, useCallback, useRef, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Dimensions,
  TouchableOpacity,
  PanResponder,
  StatusBar,
} from 'react-native';
import Video from 'react-native-video';
import { WebView } from 'react-native-webview';
import { extractYouTubeId } from '../utils/links';
import { Colors } from '../constants/colors';

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');
const SWIPE_THRESHOLD = 50;

const TrailerPlayer = ({ movieList, initialIndex, onClose }) => {
  const [currentIndex, setCurrentIndex] = useState(initialIndex);
  const [paused, setPaused] = useState(false);

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
      setPaused(false);
      setCurrentIndex(nextIdx);
    }
  }, [currentIndex, findNextTrailerIndex]);

  const navigatePrevious = useCallback(() => {
    const prevIdx = findNextTrailerIndex(currentIndex, -1);
    if (prevIdx >= 0) {
      setPaused(false);
      setCurrentIndex(prevIdx);
    }
  }, [currentIndex, findNextTrailerIndex]);

  // Swipe gesture for navigation
  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => false,
      onMoveShouldSetPanResponder: (_, gs) =>
        Math.abs(gs.dx) > Math.abs(gs.dy) && Math.abs(gs.dx) > 10,
      onPanResponderRelease: (_, gs) => {
        if (gs.dx > SWIPE_THRESHOLD) navigatePrevious();
        else if (gs.dx < -SWIPE_THRESHOLD) navigateNext();
      },
    })
  ).current;

  const hasPrev = findNextTrailerIndex(currentIndex, -1) >= 0;
  const hasNext = findNextTrailerIndex(currentIndex, 1) >= 0;

  // YouTube embed HTML
  const youtubeHtml = useMemo(() => {
    if (!youtubeId) return '';
    return `
      <html><head><meta name="viewport" content="width=device-width,initial-scale=1">
      <style>*{margin:0;padding:0;background:#000}iframe{width:100vw;height:100vh}</style></head>
      <body><iframe src="https://www.youtube.com/embed/${youtubeId}?autoplay=1&playsinline=1&controls=1&rel=0&modestbranding=1"
        frameborder="0" allow="autoplay;encrypted-media" allowfullscreen></iframe></body></html>
    `;
  }, [youtubeId]);

  // Counter
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
    <View style={styles.container} {...panResponder.panHandlers}>
      <StatusBar hidden />

      {/* Video player */}
      {isMP4 ? (
        <Video
          source={{ uri: trailerUrl }}
          style={styles.video}
          resizeMode="contain"
          paused={paused}
          controls={true}
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

      {/* Top bar: close + title + counter */}
      <View style={styles.topBar}>
        <TouchableOpacity style={styles.closeButton} onPress={() => onClose(currentIndex)}>
          <Text style={styles.closeText}>✕</Text>
        </TouchableOpacity>
        <Text style={styles.title} numberOfLines={1}>{currentMovie?.title}</Text>
        <Text style={styles.counter}>{currentTrailerNumber}/{trailerCount}</Text>
      </View>

      {/* Navigation arrows */}
      {hasPrev && (
        <TouchableOpacity style={styles.arrowLeft} onPress={navigatePrevious}>
          <Text style={styles.arrowText}>‹</Text>
        </TouchableOpacity>
      )}
      {hasNext && (
        <TouchableOpacity style={styles.arrowRight} onPress={navigateNext}>
          <Text style={styles.arrowText}>›</Text>
        </TouchableOpacity>
      )}

      {/* Hint */}
      <View style={styles.hintBar}>
        <Text style={styles.hintText}>Swipe to navigate trailers</Text>
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
  topBar: {
    position: 'absolute',
    top: 50,
    left: 16,
    right: 16,
    flexDirection: 'row',
    alignItems: 'center',
  },
  closeButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: 'rgba(255,255,255,0.15)',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  closeText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '600',
  },
  title: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
    flex: 1,
  },
  counter: {
    color: Colors.textMuted,
    fontSize: 14,
    marginLeft: 8,
  },
  arrowLeft: {
    position: 'absolute',
    left: 8,
    top: '40%',
    width: 40,
    height: 60,
    justifyContent: 'center',
    alignItems: 'center',
  },
  arrowRight: {
    position: 'absolute',
    right: 8,
    top: '40%',
    width: 40,
    height: 60,
    justifyContent: 'center',
    alignItems: 'center',
  },
  arrowText: {
    color: Colors.primary,
    fontSize: 36,
    fontWeight: '300',
    opacity: 0.6,
  },
  hintBar: {
    position: 'absolute',
    bottom: 40,
    left: 0,
    right: 0,
    alignItems: 'center',
  },
  hintText: {
    color: Colors.textMuted,
    fontSize: 12,
  },
});

export default TrailerPlayer;
