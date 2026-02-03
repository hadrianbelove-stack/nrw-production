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
    val infoOptions: List<InfoOption> = emptyList()
)

/**
 * ViewModel for Detail Screen
 */
class DetailViewModel(application: Application) : AndroidViewModel(application) {

    private val repository = MovieRepository(application)

    private val _uiState = MutableStateFlow(DetailUiState())
    val uiState: StateFlow<DetailUiState> = _uiState.asStateFlow()

    /**
     * Load movie by ID
     */
    fun loadMovie(movieId: Int) {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, error = null)

            repository.getMovies().fold(
                onSuccess = { movies ->
                    val movie = movies.find { it.id == movieId }
                    if (movie != null) {
                        _uiState.value = _uiState.value.copy(
                            isLoading = false,
                            movie = movie,
                            watchOptions = movie.getWatchOptions(),
                            infoOptions = movie.getInfoOptions()
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
}
