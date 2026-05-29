package com.nrw.app.ui.home

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.nrw.app.data.FilterCategory
import com.nrw.app.data.Movie
import com.nrw.app.data.MovieRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * UI State for Home Screen
 */
data class HomeUiState(
    val isLoading: Boolean = true,
    val error: String? = null,
    val movies: List<Movie> = emptyList(),
    val filteredMovies: List<Movie> = emptyList(),
    val groupedMovies: Map<String, List<Movie>> = emptyMap(),
    val activeFilters: Set<FilterCategory> = emptySet(),
    val slopFree: Boolean = true,
    val hideFest: Boolean = false,
    val showPreorders: Boolean = false,
    val searchQuery: String = "",
    val playlistUrl: String? = null
)

/**
 * ViewModel for Home Screen
 */
class HomeViewModel(application: Application) : AndroidViewModel(application) {

    private val repository = MovieRepository(application)

    private val _uiState = MutableStateFlow(HomeUiState())
    val uiState: StateFlow<HomeUiState> = _uiState.asStateFlow()

    init {
        loadMovies()
    }

    /**
     * Load movies from repository
     */
    fun loadMovies(forceRefresh: Boolean = false) {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, error = null)

            repository.getMovies(forceRefresh).fold(
                onSuccess = { movies ->
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        movies = movies,
                        playlistUrl = repository.getPlaylistUrl()
                    )
                    applyFilters()
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
     * Toggle a filter category on/off (multi-select)
     */
    fun toggleFilter(filter: FilterCategory) {
        val current = _uiState.value.activeFilters
        val newFilters = if (current.contains(filter)) {
            current - filter
        } else {
            current + filter
        }
        _uiState.value = _uiState.value.copy(activeFilters = newFilters)
        applyFilters()
    }

    /**
     * Set the search query
     */
    fun setSearchQuery(query: String) {
        _uiState.value = _uiState.value.copy(searchQuery = query)
        applyFilters()
    }

    /**
     * Toggle slop-free mode
     */
    fun toggleSlopFree() {
        _uiState.value = _uiState.value.copy(slopFree = !_uiState.value.slopFree)
        applyFilters()
    }

    fun toggleHideFest() {
        _uiState.value = _uiState.value.copy(hideFest = !_uiState.value.hideFest)
        applyFilters()
    }

    fun toggleShowPreorders() {
        _uiState.value = _uiState.value.copy(showPreorders = !_uiState.value.showPreorders)
        applyFilters()
    }

    /**
     * Apply filters and search to movies
     */
    private fun applyFilters() {
        val state = _uiState.value
        var filtered = repository.filterMoviesMulti(state.movies, state.activeFilters, state.searchQuery)

        if (state.slopFree) {
            filtered = filtered.filter { !it.isSlop && !it.isSlopGuess }
        }

        if (state.hideFest) {
            filtered = filtered.filter { it.categories?.isVirtualScreening != true }
        }

        if (!state.showPreorders && state.searchQuery.isBlank()) {
            filtered = filtered.filter { !it.isPreorder }
        }

        if (state.searchQuery.isNotBlank()) {
            filtered = repository.searchMovies(filtered, state.searchQuery)
        }

        val grouped = repository.groupMoviesByDate(filtered)

        _uiState.value = _uiState.value.copy(
            filteredMovies = filtered,
            groupedMovies = grouped
        )
    }

    /**
     * Retry loading after error
     */
    fun retry() {
        loadMovies(forceRefresh = true)
    }
}
