/**
 * New Release Wall - tvOS Movie Shelf Component
 * Horizontal scrolling row of movies (Netflix-style)
 */

import React, { useRef, useCallback, useState } from 'react';
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  Animated,
} from 'react-native';
import MovieCard from './MovieCard.tvos';
import { Colors, Typography, Spacing, Dimensions } from '../constants/colors';

const MovieShelf = ({
  title,
  movies,
  onMovieSelect,
  onMovieFocus,
  isFeatured = false,
  shelfIndex = 0,
  initialFocusIndex = 0,
  onShelfFocus,
  onShelfBlur,
  hasPreferredFocus = false,
}) => {
  const flatListRef = useRef(null);
  const [focusedIndex, setFocusedIndex] = useState(null);
  const titleOpacity = useRef(new Animated.Value(0.7)).current;

  // Card dimensions based on featured status
  const cardWidth = isFeatured
    ? Dimensions.tvos.featuredCardWidth
    : Dimensions.tvos.cardWidth;
  const cardSpacing = Spacing.tvos.cardGap;

  // Handle movie focus
  const handleMovieFocus = useCallback(
    (movie, index) => {
      setFocusedIndex(index);

      // Animate shelf title to full opacity
      Animated.timing(titleOpacity, {
        toValue: 1,
        duration: 150,
        useNativeDriver: true,
      }).start();

      // Let tvOS handle scrolling naturally - don't force scroll position
      // This prevents jittering from constant scroll adjustments

      if (onMovieFocus) {
        onMovieFocus(movie, shelfIndex, index);
      }

      if (onShelfFocus) {
        onShelfFocus(shelfIndex);
      }
    },
    [shelfIndex, onMovieFocus, onShelfFocus, titleOpacity]
  );

  // Handle movie blur
  const handleMovieBlur = useCallback(
    (movie, index) => {
      // Dim shelf title when no item is focused
      Animated.timing(titleOpacity, {
        toValue: 0.7,
        duration: 150,
        useNativeDriver: true,
      }).start();

      if (onShelfBlur) {
        onShelfBlur(shelfIndex);
      }
    },
    [shelfIndex, onShelfBlur, titleOpacity]
  );

  // Handle movie selection
  const handleMovieSelect = useCallback(
    (movie) => {
      if (onMovieSelect) {
        onMovieSelect(movie);
      }
    },
    [onMovieSelect]
  );

  // Render individual movie card
  const renderMovie = useCallback(
    ({ item, index }) => {
      // Only give preferred focus to the initialFocusIndex card in the shelf that has focus
      const shouldHaveFocus = hasPreferredFocus && index === initialFocusIndex;

      return (
        <View style={{ marginRight: cardSpacing }}>
          <MovieCard
            movie={item}
            onSelect={() => handleMovieSelect(item)}
            onFocus={() => handleMovieFocus(item, index)}
            onBlur={() => handleMovieBlur(item, index)}
            isFeatured={isFeatured}
            hasTVPreferredFocus={shouldHaveFocus}
            testID={`movie-card-${shelfIndex}-${index}`}
          />
        </View>
      );
    },
    [
      cardSpacing,
      handleMovieSelect,
      handleMovieFocus,
      handleMovieBlur,
      isFeatured,
      initialFocusIndex,
      shelfIndex,
      hasPreferredFocus,
    ]
  );

  // Key extractor
  const keyExtractor = useCallback(
    (item, index) => item.id?.toString() || item.title || `movie-${index}`,
    []
  );

  // Get item layout for optimized scrolling
  const getItemLayout = useCallback(
    (data, index) => ({
      length: cardWidth + cardSpacing,
      offset: (cardWidth + cardSpacing) * index,
      index,
    }),
    [cardWidth, cardSpacing]
  );

  // Handle scroll failure (out of bounds)
  const onScrollToIndexFailed = useCallback(
    (info) => {
      const wait = new Promise((resolve) => setTimeout(resolve, 100));
      wait.then(() => {
        if (flatListRef.current) {
          flatListRef.current.scrollToIndex({
            index: info.index,
            animated: true,
          });
        }
      });
    },
    []
  );

  if (!movies || movies.length === 0) {
    return null;
  }

  return (
    <View style={styles.container}>
      {/* Shelf title */}
      {title && (
        <Animated.View style={[styles.titleContainer, { opacity: titleOpacity }]}>
          <Text style={[styles.title, isFeatured && styles.featuredTitle]}>
            {title}
          </Text>
          {isFeatured && (
            <View style={styles.featuredBadge}>
              <Text style={styles.featuredBadgeText}>FEATURED</Text>
            </View>
          )}
          <Text style={styles.count}>{movies.length} films</Text>
        </Animated.View>
      )}

      {/* Horizontal movie list */}
      <FlatList
        ref={flatListRef}
        data={movies}
        renderItem={renderMovie}
        keyExtractor={keyExtractor}
        horizontal={true}
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.listContent}
        getItemLayout={getItemLayout}
        onScrollToIndexFailed={onScrollToIndexFailed}
        removeClippedSubviews={true}
        maxToRenderPerBatch={10}
        windowSize={5}
        initialNumToRender={6}
        decelerationRate="fast"
        snapToInterval={cardWidth + cardSpacing}
        snapToAlignment="start"
      />
    </View>
  );
};

// Empty shelf placeholder
export const EmptyShelf = ({ title, message }) => (
  <View style={styles.container}>
    {title && (
      <View style={styles.titleContainer}>
        <Text style={styles.title}>{title}</Text>
      </View>
    )}
    <View style={styles.emptyContainer}>
      <Text style={styles.emptyText}>
        {message || 'No movies to display'}
      </Text>
    </View>
  </View>
);

// Loading shelf placeholder
export const LoadingShelf = ({ title }) => (
  <View style={styles.container}>
    {title && (
      <View style={styles.titleContainer}>
        <Text style={styles.title}>{title}</Text>
      </View>
    )}
    <View style={styles.loadingContainer}>
      {[...Array(5)].map((_, index) => (
        <View
          key={index}
          style={[
            styles.loadingCard,
            {
              width: Dimensions.tvos.cardWidth,
              height: Dimensions.tvos.cardHeight,
              marginRight: Spacing.tvos.cardGap,
            },
          ]}
        />
      ))}
    </View>
  </View>
);

const styles = StyleSheet.create({
  container: {
    marginBottom: Spacing.tvos.shelfGap,
  },
  titleContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.tvos.screenPadding,
    marginBottom: Spacing.tvos.md,
  },
  title: {
    color: Colors.textPrimary,
    fontSize: Typography.tvos.subtitle,
    fontWeight: '600',
    marginRight: Spacing.tvos.md,
  },
  featuredTitle: {
    fontSize: Typography.tvos.title - 8,
    fontWeight: '700',
  },
  featuredBadge: {
    backgroundColor: Colors.primary,
    paddingHorizontal: Spacing.tvos.sm,
    paddingVertical: Spacing.tvos.xs / 2,
    borderRadius: 4,
    marginRight: Spacing.tvos.md,
  },
  featuredBadgeText: {
    color: Colors.background,
    fontSize: Typography.tvos.caption - 2,
    fontWeight: '700',
    letterSpacing: 1,
  },
  count: {
    color: Colors.textMuted,
    fontSize: Typography.tvos.caption,
  },
  listContent: {
    paddingHorizontal: Spacing.tvos.screenPadding,
    paddingVertical: 30, // Extra padding for scale animation
  },
  emptyContainer: {
    height: Dimensions.tvos.cardHeight,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: Spacing.tvos.screenPadding,
  },
  emptyText: {
    color: Colors.textMuted,
    fontSize: Typography.tvos.body,
  },
  loadingContainer: {
    flexDirection: 'row',
    paddingHorizontal: Spacing.tvos.screenPadding,
  },
  loadingCard: {
    backgroundColor: Colors.backgroundTertiary,
    borderRadius: 12,
    opacity: 0.5,
  },
});

export default MovieShelf;
