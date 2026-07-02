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

// Search list — HomeScreen writes the FULL movie list here before opening the
// Search screen (search covers everything, bypassing wall view filters — matches
// desktop). Separate slot from _movieList, which carries the MovieDetail contract.
let _searchList = [];

export function setSearchMovieList(list) {
  _searchList = list;
}

export function getSearchMovieList() {
  return _searchList;
}

// Pending trailer index — the Trailer route writes the index of the trailer that
// was last on screen; MovieDetail reads (and clears) it when it regains focus so
// it can show the detail of whatever trailer was playing. null = nothing pending.
let _pendingTrailerIndex = null;

export function setPendingTrailerIndex(index) {
  _pendingTrailerIndex = index;
}

export function takePendingTrailerIndex() {
  const index = _pendingTrailerIndex;
  _pendingTrailerIndex = null;
  return index;
}
