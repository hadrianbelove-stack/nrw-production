/**
 * New Release Wall - Poster Close-up (View 1)
 * Mirrors mobile web's poster view: full-screen poster, swipe to navigate,
 * counter + scores, tap poster (or dot 3) for details.
 */

import React, {useState, useRef, useCallback} from 'react';
import {
  View,
  Text,
  Image,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  Dimensions as RNDimensions,
} from 'react-native';
import {useSafeAreaInsets} from 'react-native-safe-area-context';
import {Colors} from '../constants/colors';

const screenWidth = RNDimensions.get('window').width;

export default function PosterView({route, navigation}) {
  const insets = useSafeAreaInsets();
  const {movies = [], index = 0} = route.params || {};
  const [currentIndex, setCurrentIndex] = useState(index);
  const listRef = useRef(null);

  const openDetail = useCallback(
    (movie, movieIndex) => {
      navigation.navigate('MovieDetail', {
        movie,
        movieList: movies,
        currentIndex: movieIndex,
      });
    },
    [navigation, movies],
  );

  const onMomentumEnd = useCallback(e => {
    const newIndex = Math.round(e.nativeEvent.contentOffset.x / screenWidth);
    setCurrentIndex(newIndex);
  }, []);

  const scrollTo = useCallback(i => {
    if (i < 0 || i >= movies.length) return;
    listRef.current?.scrollToIndex({index: i, animated: true});
    setCurrentIndex(i);
  }, [movies.length]);

  const renderPoster = ({item, index: i}) => {
    const posterUrl = item.poster_url || item.poster;
    return (
      <TouchableOpacity
        style={styles.page}
        activeOpacity={0.9}
        onPress={() => openDetail(item, i)}>
        {posterUrl ? (
          <Image source={{uri: posterUrl}} style={styles.poster} resizeMode="contain" />
        ) : (
          <View style={styles.posterFallback}>
            <Text style={styles.posterFallbackText}>{item.display_title || item.title}</Text>
          </View>
        )}
        {/* Scores overlay */}
        {(item.rt_score || item.imdb_rating) && (
          <View style={[styles.scoreRow, {bottom: insets.bottom + 64}]}>
            {item.rt_score && (
              <View style={styles.scoreChip}>
                <Text style={styles.rtText}>RT {item.rt_score}</Text>
              </View>
            )}
            {item.imdb_rating && (
              <View style={styles.scoreChip}>
                <Text style={styles.imdbText}>IMDb {item.imdb_rating}</Text>
              </View>
            )}
          </View>
        )}
      </TouchableOpacity>
    );
  };

  const movie = movies[currentIndex];

  return (
    <View style={[styles.container, {paddingTop: insets.top}]}>
      {/* View dots — grid / poster / detail, matching mobile web */}
      <View style={styles.dotsRow}>
        <TouchableOpacity style={styles.dotHit} onPress={() => navigation.goBack()}>
          <View style={styles.dot} />
        </TouchableOpacity>
        <View style={styles.dotHit}>
          <View style={[styles.dot, styles.dotActive]} />
        </View>
        <TouchableOpacity
          style={styles.dotHit}
          onPress={() => movie && openDetail(movie, currentIndex)}>
          <View style={styles.dot} />
        </TouchableOpacity>
        <TouchableOpacity style={styles.closeBtn} onPress={() => navigation.goBack()}>
          <Text style={styles.closeText}>✕</Text>
        </TouchableOpacity>
      </View>

      <FlatList
        ref={listRef}
        data={movies}
        renderItem={renderPoster}
        keyExtractor={(item, i) => String(item.id ?? i)}
        horizontal
        pagingEnabled
        initialScrollIndex={index}
        getItemLayout={(_, i) => ({length: screenWidth, offset: screenWidth * i, index: i})}
        onMomentumScrollEnd={onMomentumEnd}
        showsHorizontalScrollIndicator={false}
      />

      {/* Counter + chevrons */}
      <View style={[styles.bottomBar, {paddingBottom: insets.bottom + 12}]}>
        <TouchableOpacity
          style={styles.chevron}
          onPress={() => scrollTo(currentIndex - 1)}
          disabled={currentIndex === 0}>
          <Text style={[styles.chevronText, currentIndex === 0 && styles.chevronDisabled]}>‹</Text>
        </TouchableOpacity>
        <Text style={styles.counter}>
          {movies.length ? currentIndex + 1 : 0} / {movies.length}
        </Text>
        <TouchableOpacity
          style={styles.chevron}
          onPress={() => scrollTo(currentIndex + 1)}
          disabled={currentIndex >= movies.length - 1}>
          <Text style={[styles.chevronText, currentIndex >= movies.length - 1 && styles.chevronDisabled]}>›</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#000',
  },
  dotsRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 8,
    gap: 4,
  },
  dotHit: {
    padding: 6,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: 'rgba(255,255,255,0.25)',
  },
  dotActive: {
    backgroundColor: Colors.primary,
  },
  closeBtn: {
    position: 'absolute',
    right: 16,
    top: 4,
    padding: 8,
  },
  closeText: {
    color: 'rgba(255,255,255,0.6)',
    fontSize: 18,
  },
  page: {
    width: screenWidth,
    flex: 1,
    justifyContent: 'center',
  },
  poster: {
    width: '100%',
    height: '100%',
  },
  posterFallback: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  posterFallbackText: {
    color: Colors.textSecondary,
    fontSize: 22,
    fontWeight: '600',
    textAlign: 'center',
  },
  scoreRow: {
    position: 'absolute',
    left: 16,
    flexDirection: 'row',
    gap: 6,
  },
  scoreChip: {
    backgroundColor: 'rgba(0,0,0,0.7)',
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  rtText: {
    color: '#ff6b6b',
    fontSize: 12,
    fontWeight: '800',
  },
  imdbText: {
    color: '#f5c518',
    fontSize: 12,
    fontWeight: '800',
  },
  bottomBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 24,
    paddingTop: 8,
  },
  chevron: {
    paddingHorizontal: 18,
    paddingVertical: 4,
  },
  chevronText: {
    color: Colors.primary,
    fontSize: 34,
    fontWeight: '700',
    lineHeight: 36,
  },
  chevronDisabled: {
    opacity: 0.25,
  },
  counter: {
    color: Colors.textSecondary,
    fontSize: 13,
    fontWeight: '600',
    letterSpacing: 1,
  },
});
