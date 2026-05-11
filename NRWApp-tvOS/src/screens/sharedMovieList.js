/**
 * Shared movie list store — avoids passing 1.6MB through React Navigation route params.
 * HomeScreen writes the sorted list here before navigating to DetailScreen.
 * DetailScreen reads from here for left/right arrow navigation.
 */

let _movieList = [];

export function setSharedMovieList(list) {
  _movieList = list;
}

export function getSharedMovieList() {
  return _movieList;
}
