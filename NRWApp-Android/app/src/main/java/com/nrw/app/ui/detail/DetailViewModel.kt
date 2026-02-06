package com.nrw.app.ui.detail

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.nrw.app.data.InfoOption
import com.nrw.app.data.Movie
import com.nrw.app.data.MovieRepository
import com.nrw.app.data.WatchOption
import com.nrw.app.data.getInfoOptions
import com.nrw.app.data.getWatchOptions
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * UI State for Detail Screen
 */
data class DetailUiState(
    val isLoading: Boolean = true,
    val error: String? = null,
    val movie: Movie? = null,
    val watchOptions: List<WatchOption> = emptyList(),
    val infoOptions: List<InfoOption> = emptyList(),
    val currentIndex: Int = 0,
    val totalMovies: Int = 0,
    val canNavigate: Boolean = false
)

/**
 * ViewModel for Detail Screen
 * Supports left/right D-pad navigation to cycle through all movies
 */
class DetailViewModel(application: Application) : AndroidViewModel(application) {

    private val repository = MovieRepository(application)

    private val _uiState = MutableStateFlow(DetailUiState())
    val uiState: StateFlow<DetailUiState> = _uiState.asStateFlow()

    // Cache movie list for navigation
    private var movieList: List<Movie> = emptyList()

    /**
     * Load movie by ID
     */
    fun loadMovie(movieId: String) {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, error = null)

            repository.getMovies().fold(
                onSuccess = { movies ->
                    movieList = movies
                    val index = movies.indexOfFirst { it.id == movieId }
                    val movie = if (index >= 0) movies[index] else null

                    if (movie != null) {
                        _uiState.value = _uiState.value.copy(
                            isLoading = false,
                            movie = movie,
                            watchOptions = movie.getWatchOptions(),
                            infoOptions = movie.getInfoOptions(),
                            currentIndex = index,
                            totalMovies = movies.size,
                            canNavigate = movies.size > 1
                        )
                    } else {
                        _uiState.value = _uiState.value.copy(
                            isLoading = false,
                            error = "Movie not found"
                        )
                    }
                },
                onFailure = { error ->
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        error = error.message ?: "Unknown error"
                    )
                }
            )
        }
    }

    /**
     * Navigate to next movie (cycles to first if at end)
     */
    fun navigateNext() {
        if (movieList.isEmpty()) return
        val nextIndex = (_uiState.value.currentIndex + 1) % movieList.size
        loadMovieAtIndex(nextIndex)
    }

    /**
     * Navigate to previous movie (cycles to last if at start)
     */
    fun navigatePrevious() {
        if (movieList.isEmpty()) return
        val prevIndex = if (_uiState.value.currentIndex == 0) {
            movieList.size - 1
        } else {
            _uiState.value.currentIndex - 1
        }
        loadMovieAtIndex(prevIndex)
    }

    private fun loadMovieAtIndex(index: Int) {
        val movie = movieList.getOrNull(index) ?: return
        _uiState.value = _uiState.value.copy(
            movie = movie,
            watchOptions = movie.getWatchOptions(),
            infoOptions = movie.getInfoOptions(),
            currentIndex = index
        )
    }
}
