package com.nrw.app.ui.home

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.nrw.app.data.FilterCategory
import com.nrw.app.data.Movie
import com.nrw.app.data.MovieRepository
import com.nrw.app.data.isStaffPick
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
    val activeFilters: Set<FilterCategory> = emptySet(),
    val slopMode: String = "free",
    val hideFest: Boolean = true,
    val showPreorders: Boolean = false,
    val showHighlightsOnly: Boolean = false,
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
     * Cycle slop mode: free → all → only → free (matches desktop 3-state)
     */
    fun cycleSlopMode() {
        val next = when (_uiState.value.slopMode) {
            "free" -> "all"
            "all" -> "only"
            else -> "free"
        }
        _uiState.value = _uiState.value.copy(slopMode = next)
        applyFilters()
    }

    // View toggles (Selects / Fests / Pre-Orders) are mutually exclusive: at most
    // one is active. Each public toggle maps to its winning view, or "none" when
    // toggled off. (hideFest is inverted — fests are shown only for "fests".)
    private fun showExclusiveView(view: String) {
        _uiState.value = _uiState.value.copy(
            showHighlightsOnly = view == "selects",
            hideFest = view != "fests",
            showPreorders = view == "preorders",
        )
        applyFilters()
    }

    fun toggleHideFest() = showExclusiveView(if (_uiState.value.hideFest) "fests" else "none")
    fun toggleShowPreorders() = showExclusiveView(if (_uiState.value.showPreorders) "none" else "preorders")
    fun toggleShowHighlights() = showExclusiveView(if (_uiState.value.showHighlightsOnly) "none" else "selects")

    /**
     * Apply filters and search to movies
     */
    private fun applyFilters() {
        val state = _uiState.value
        var filtered = repository.filterMoviesMulti(state.movies, state.activeFilters, state.searchQuery)

        // Toggles are view modes — an active search bypasses them all
        if (state.searchQuery.isBlank()) {
            if (state.showHighlightsOnly) {
                filtered = filtered.filter { it.isStaffPick() }
            }

            if (state.slopMode == "free") {
                filtered = filtered.filter { !it.isSlop && !it.isSlopGuess }
            } else if (state.slopMode == "only") {
                filtered = filtered.filter { it.isSlop || it.isSlopGuess }
            }

            if (state.hideFest) {
                filtered = filtered.filter { it.filters?.isVirtualScreening != true }
            }
        }

        if (!state.showPreorders && state.searchQuery.isBlank()) {
            filtered = filtered.filter { !it.isPreorder }
        }

        if (state.searchQuery.isNotBlank()) {
            filtered = repository.searchMovies(filtered, state.searchQuery)
        }

        filtered = repository.sortMovies(filtered)

        _uiState.value = _uiState.value.copy(
            filteredMovies = filtered
        )
    }

    /**
     * Retry loading after error
     */
    fun retry() {
        loadMovies(forceRefresh = true)
    }
}
