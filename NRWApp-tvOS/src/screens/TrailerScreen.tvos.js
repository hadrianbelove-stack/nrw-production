/**
 * New Release Wall - tvOS Trailer Screen
 * A real navigation route that hosts the fullscreen TrailerPlayer.
 *
 * Why a route (not an in-detail overlay): on tvOS the native stack pops the top
 * route when MENU is pressed. As an overlay we had to fight that pop with
 * BackHandler/beforeRemove guards, which wedged navigation and left audio playing.
 * As its own route, MENU simply pops Trailer -> MovieDetail with no guards.
 *
 * The detail screen returns to whatever trailer was playing via the pending-index
 * store: we push the on-screen index as the reel advances; MovieDetail reads it
 * when it regains focus. See sharedMovieList.takePendingTrailerIndex.
 */

import React, { useCallback } from 'react';
import { useNavigation, useRoute } from '@react-navigation/native';
import TrailerPlayer from '../components/TrailerPlayer.tvos';
import { getSharedMovieList, setPendingTrailerIndex } from './sharedMovieList';

const TrailerScreen = () => {
  const navigation = useNavigation();
  const route = useRoute();
  const movieList = getSharedMovieList();
  const initialIndex = route.params?.initialIndex ?? 0;

  // Programmatic close (last trailer ended, or playback error). MENU is handled
  // natively by the stack, so it does not come through here.
  const handleClose = useCallback(() => {
    if (navigation.canGoBack()) navigation.goBack();
  }, [navigation]);

  return (
    <TrailerPlayer
      movieList={movieList}
      initialIndex={initialIndex}
      onClose={handleClose}
      onIndexChange={setPendingTrailerIndex}
    />
  );
};

export default TrailerScreen;
