/**
 * New Release Wall - Movie Detail Screen
 * Full movie info with watch buttons
 */

import React, {useCallback} from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Image,
  Dimensions as RNDimensions,
  TouchableOpacity,
} from 'react-native';
import {useSafeAreaInsets} from 'react-native-safe-area-context';

import {WatchButtonGroup} from '../components/WatchButton';
import {Colors, Typography, Spacing} from '../constants/colors';
import {getWatchLinks} from '../services/api';
import {openWatchLink, openTrailer, openRottenTomatoes} from '../utils/links';
import {trackMovieView, trackWatchButtonTap} from '../services/analytics';

const screenWidth = RNDimensions.get('window').width;
const posterWidth = screenWidth * 0.45;
const posterHeight = posterWidth * 1.5;

export default function MovieDetail({route}) {
  const insets = useSafeAreaInsets();
  const {movie} = route.params;

  // Track view
  React.useEffect(() => {
    trackMovieView(movie);
  }, [movie]);

  const watchLinks = getWatchLinks(movie);

  const handleWatchPress = useCallback(
    link => {
      trackWatchButtonTap(movie, link.service);
      openWatchLink(link.url);
    },
    [movie],
  );

  const handleTrailerPress = useCallback(() => {
    if (movie.links?.trailer) {
      openTrailer(movie.links.trailer);
    }
  }, [movie]);

  const handleRTPress = useCallback(() => {
    if (movie.links?.rotten_tomatoes) {
      openRottenTomatoes(movie.links.rotten_tomatoes);
    }
  }, [movie]);

  const posterUrl = movie.poster_url || movie.poster;
  const director = movie.director || movie.crew?.director;
  const cast = movie.cast || movie.crew?.cast || [];
  const genres = movie.genres || [];
  const runtime = movie.runtime;
  const year = movie.year || (movie.release_date ? movie.release_date.split('-')[0] : null);

  // Format runtime
  const formatRuntime = mins => {
    if (!mins) return null;
    const hours = Math.floor(mins / 60);
    const minutes = mins % 60;
    return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
  };

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={{paddingBottom: insets.bottom + Spacing.xl}}>
      {/* Hero section with poster and basic info */}
      <View style={styles.heroSection}>
        <View style={styles.posterContainer}>
          {posterUrl ? (
            <Image
              source={{uri: posterUrl}}
              style={styles.poster}
              resizeMode="cover"
            />
          ) : (
            <View style={styles.posterPlaceholder}>
              <Text style={styles.placeholderText}>No Poster</Text>
            </View>
          )}
        </View>

        <View style={styles.heroInfo}>
          <Text style={styles.title}>{movie.title}</Text>

          {/* Metadata row */}
          <View style={styles.metaRow}>
            {year && <Text style={styles.metaText}>{year}</Text>}
            {runtime && (
              <>
                <Text style={styles.metaDot}>•</Text>
                <Text style={styles.metaText}>{formatRuntime(runtime)}</Text>
              </>
            )}
          </View>

          {/* RT Score */}
          {movie.rt_score && (
            <TouchableOpacity
              style={styles.rtContainer}
              onPress={handleRTPress}
              disabled={!movie.links?.rotten_tomatoes}>
              <View
                style={[
                  styles.rtBadge,
                  {
                    backgroundColor:
                      movie.rt_score >= 60 ? Colors.green : Colors.red,
                  },
                ]}>
                <Text style={styles.rtScore}>{movie.rt_score}%</Text>
              </View>
              <Text style={styles.rtLabel}>Rotten Tomatoes</Text>
            </TouchableOpacity>
          )}

          {/* Genres */}
          {genres.length > 0 && (
            <View style={styles.genresContainer}>
              {genres.slice(0, 3).map((genre, index) => (
                <View key={index} style={styles.genreTag}>
                  <Text style={styles.genreText}>{genre}</Text>
                </View>
              ))}
            </View>
          )}
        </View>
      </View>

      {/* Watch buttons section */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Watch Now</Text>
        <WatchButtonGroup links={watchLinks} onPress={handleWatchPress} maxButtons={4} />
      </View>

      {/* Info buttons */}
      {movie.links?.trailer && (
        <View style={styles.section}>
          <TouchableOpacity style={styles.infoButton} onPress={handleTrailerPress}>
            <Text style={styles.infoButtonText}>▶ Watch Trailer</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Synopsis */}
      {movie.synopsis && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Synopsis</Text>
          <Text style={styles.synopsis}>{movie.synopsis}</Text>
        </View>
      )}

      {/* Director */}
      {director && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Director</Text>
          <Text style={styles.crewText}>{director}</Text>
        </View>
      )}

      {/* Cast */}
      {cast.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Cast</Text>
          <Text style={styles.crewText}>
            {Array.isArray(cast) ? cast.slice(0, 5).join(', ') : cast}
          </Text>
        </View>
      )}

      {/* Additional info */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Details</Text>
        {movie.country && (
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Country</Text>
            <Text style={styles.detailValue}>{movie.country}</Text>
          </View>
        )}
        {movie.original_language && (
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Language</Text>
            <Text style={styles.detailValue}>
              {movie.original_language.toUpperCase()}
            </Text>
          </View>
        )}
        {movie.digital_date && (
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Available</Text>
            <Text style={styles.detailValue}>{movie.digital_date}</Text>
          </View>
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  heroSection: {
    flexDirection: 'row',
    padding: Spacing.screenPadding,
    paddingTop: Spacing.md,
  },
  posterContainer: {
    width: posterWidth,
    height: posterHeight,
    borderRadius: 8,
    overflow: 'hidden',
    backgroundColor: Colors.backgroundSecondary,
  },
  poster: {
    width: '100%',
    height: '100%',
  },
  posterPlaceholder: {
    width: '100%',
    height: '100%',
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: Colors.backgroundTertiary,
  },
  placeholderText: {
    color: Colors.textMuted,
    fontSize: Typography.caption,
  },
  heroInfo: {
    flex: 1,
    marginLeft: Spacing.md,
    justifyContent: 'flex-start',
  },
  title: {
    color: Colors.textPrimary,
    fontSize: Typography.subtitle,
    fontWeight: '700',
    lineHeight: 26,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: Spacing.xs,
  },
  metaText: {
    color: Colors.textSecondary,
    fontSize: Typography.caption,
  },
  metaDot: {
    color: Colors.textMuted,
    marginHorizontal: 6,
  },
  rtContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: Spacing.sm,
  },
  rtBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
  },
  rtScore: {
    color: Colors.textPrimary,
    fontSize: Typography.caption,
    fontWeight: '700',
  },
  rtLabel: {
    color: Colors.textMuted,
    fontSize: Typography.caption - 1,
    marginLeft: Spacing.xs,
  },
  genresContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: Spacing.sm,
    gap: Spacing.xs,
  },
  genreTag: {
    backgroundColor: Colors.backgroundSecondary,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
  },
  genreText: {
    color: Colors.textSecondary,
    fontSize: Typography.caption - 1,
  },
  section: {
    paddingHorizontal: Spacing.screenPadding,
    paddingTop: Spacing.lg,
  },
  sectionTitle: {
    color: Colors.textPrimary,
    fontSize: Typography.body,
    fontWeight: '600',
    marginBottom: Spacing.sm,
  },
  infoButton: {
    backgroundColor: Colors.backgroundSecondary,
    paddingVertical: Spacing.sm + 2,
    paddingHorizontal: Spacing.md,
    borderRadius: 8,
    alignItems: 'center',
  },
  infoButtonText: {
    color: Colors.primary,
    fontSize: Typography.button,
    fontWeight: '600',
  },
  synopsis: {
    color: Colors.textSecondary,
    fontSize: Typography.body,
    lineHeight: 24,
  },
  crewText: {
    color: Colors.textSecondary,
    fontSize: Typography.body,
    lineHeight: 22,
  },
  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: Spacing.xs,
    borderBottomWidth: 1,
    borderBottomColor: Colors.backgroundSecondary,
  },
  detailLabel: {
    color: Colors.textMuted,
    fontSize: Typography.body,
  },
  detailValue: {
    color: Colors.textSecondary,
    fontSize: Typography.body,
  },
});
