package com.nrw.app.ui.home

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.tv.foundation.lazy.grid.TvGridCells
import androidx.tv.foundation.lazy.grid.TvLazyVerticalGrid
import androidx.tv.foundation.lazy.grid.items
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.tv.material3.Button
import androidx.tv.material3.ButtonDefaults
import androidx.tv.material3.ExperimentalTvMaterial3Api
import com.nrw.app.data.Movie
import com.nrw.app.data.getDisplayDate
import com.nrw.app.ui.components.DateDividerCard
import com.nrw.app.ui.components.FilterChips
import com.nrw.app.ui.components.MovieCard
import com.nrw.app.ui.components.TrailersCard
import com.nrw.app.ui.theme.Background
import com.nrw.app.ui.theme.BackgroundGradientEnd
import com.nrw.app.ui.theme.Primary
import com.nrw.app.ui.theme.TextMuted
import com.nrw.app.ui.theme.TextPrimary
import com.nrw.app.ui.theme.TextSecondary

// Trailers card temporarily disabled — set true to restore
private const val SHOW_TRAILERS_CARD = false

private val FILTER_DESCRIPTIONS = mapOf(
    FilterCategory.STAFF_PICKS to Pair("Picks", "The ones we're vouching for. Out of everything on the wall, these are the movies we think are genuinely worth your time. Not a popularity contest, just honest recommendations."),
    FilterCategory.INDIE to Pair("Indie", "The smaller films, the independents, the ones without a billboard campaign. These movies flew under the radar theatrically but are worth knowing about now that they're available to stream at home."),
    FilterCategory.HORROR to Pair("Horror", "The stuff that goes bump. Horror films now streaming — from slow-burn dread to full-on splatter."),
    FilterCategory.ACTION to Pair("Action", "High-octane, kinetic filmmaking. Action movies now available to watch at home."),
    FilterCategory.COMEDY to Pair("Comedy", "Films that are actually funny. Comedies — broad and subtle — now streaming."),
    FilterCategory.FAMILY to Pair("Family", "Films for all ages. Family movies now available to watch at home."),
    FilterCategory.FOREIGN to Pair("Foreign", "Non-English language films from around the world. Some are massive in their home countries, some are intimate art-house pieces. The only thing they have in common is subtitles and the fact that they're streaming now."),
    FilterCategory.DOCUMENTARY to Pair("Documentary", "Non-fiction filmmaking. Documentaries covering real stories, real people, and real events — now available to stream at home."),
    FilterCategory.RESTORATIONS to Pair("Reissues", "Classic and catalog titles with new digital life. These are films that have been restored, remastered, or newly reissued on streaming platforms. Old movies, fresh transfers.")
)

// Grid item can be either a movie, date divider, or trailers card
sealed class GridItem {
    data class MovieItem(val movie: Movie) : GridItem()
    data class DateItem(val date: String) : GridItem()
    object TrailersItem : GridItem()
}

/**
 * Home Screen for NRW Android TV
 * Matches website/tvOS design with search, trailers, date dividers
 */
@OptIn(ExperimentalTvMaterial3Api::class)
@Composable
fun HomeScreen(
    onMovieClick: (Movie) -> Unit,
    viewModel: HomeViewModel = viewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    val context = LocalContext.current

    // Create grid items with trailers card and date dividers
    val gridItems = remember(uiState.filteredMovies, uiState.playlistUrl) {
        createGridItems(uiState.filteredMovies, uiState.playlistUrl)
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.linearGradient(
                    colors = listOf(Background, BackgroundGradientEnd),
                    start = androidx.compose.ui.geometry.Offset(0f, 0f),
                    end = androidx.compose.ui.geometry.Offset(Float.POSITIVE_INFINITY, Float.POSITIVE_INFINITY)
                )
            )
    ) {
        when {
            uiState.isLoading -> {
                LoadingState()
            }
            uiState.error != null -> {
                ErrorState(
                    error = uiState.error!!,
                    onRetry = { viewModel.retry() }
                )
            }
            else -> {
                Column(modifier = Modifier.fillMaxSize()) {
                    // Header with title and search
                    Header(
                        searchQuery = uiState.searchQuery,
                        onSearchChange = { viewModel.setSearchQuery(it) }
                    )

                    // Filter chips
                    FilterChips(
                        activeFilters = uiState.activeFilters,
                        onFilterToggled = { viewModel.toggleFilter(it) },
                        slopMode = uiState.slopMode,
                        onSlopModeToggle = { viewModel.cycleSlopMode() },
                        hideFest = uiState.hideFest,
                        onHideFestToggle = { viewModel.toggleHideFest() },
                        showPreorders = uiState.showPreorders,
                        onShowPreordersToggle = { viewModel.toggleShowPreorders() }
                    )

                    // Filter description — shown when exactly one filter is active
                    if (uiState.activeFilters.size == 1) {
                        val desc = FILTER_DESCRIPTIONS[uiState.activeFilters.first()]
                        if (desc != null) {
                            FilterDescription(title = desc.first, text = desc.second)
                        }
                    }

                    Spacer(modifier = Modifier.height(6.dp))

                    // Movie grid with date dividers
                    if (uiState.filteredMovies.isEmpty()) {
                        EmptyState()
                    } else {
                        MovieGridWithDates(
                            gridItems = gridItems,
                            playlistUrl = uiState.playlistUrl,
                            onMovieClick = onMovieClick,
                            onTrailersClick = {
                                uiState.playlistUrl?.let { url ->
                                    try {
                                        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
                                        context.startActivity(intent)
                                    } catch (e: Exception) {
                                        // Handle if no app can handle the URL
                                    }
                                }
                            }
                        )
                    }
                }
            }
        }
    }
}

/**
 * Create grid items with trailers card and date dividers inserted
 */
private fun createGridItems(movies: List<Movie>, playlistUrl: String?): List<GridItem> {
    val items = mutableListOf<GridItem>()
    var currentDate: String? = null
    var addedTrailers = false

    // Separate pre-orders from regular movies
    val regularMovies = movies.filter { !it.isPreorder }
    val preorderMovies = movies.filter { it.isPreorder }.sortedBy { it.digitalDate ?: "" }

    // Sort regular movies by date (newest first)
    val sortedMovies = regularMovies.sortedByDescending { it.getDisplayDate() ?: "0000-00-00" }

    for (movie in sortedMovies) {
        val movieDate = movie.getDisplayDate()
        if (movieDate != null && movieDate != currentDate) {
            // Add trailers card before first date divider
            if (!addedTrailers && SHOW_TRAILERS_CARD) {
                items.add(GridItem.TrailersItem)
                addedTrailers = true
            }
            // Add date divider for new date
            items.add(GridItem.DateItem(movieDate))
            currentDate = movieDate
        }
        items.add(GridItem.MovieItem(movie))
    }

    // Add pre-orders section at the end
    if (preorderMovies.isNotEmpty()) {
        items.add(GridItem.DateItem("PRE-ORDER"))
        for (movie in preorderMovies) {
            items.add(GridItem.MovieItem(movie))
        }
    }

    return items
}

@Composable
private fun FilterDescription(title: String, text: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 32.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(20.dp),
        verticalAlignment = Alignment.Top
    ) {
        Text(
            text = title.uppercase(),
            color = Primary,
            fontSize = 14.sp,
            fontWeight = FontWeight.ExtraBold,
            letterSpacing = 2.sp
        )
        Text(
            text = text,
            color = TextMuted,
            fontSize = 13.sp,
            lineHeight = 20.sp,
            modifier = Modifier.weight(1f)
        )
    }
}

@Composable
private fun Header(
    searchQuery: String,
    onSearchChange: (String) -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 32.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        // Title (smaller to match tvOS proportions)
        Text(
            text = "THE NEW RELEASE WALL",
            color = Primary,
            fontSize = 20.sp,
            fontWeight = FontWeight.SemiBold,
            letterSpacing = 3.sp
        )

        // Search bar
        SearchBar(
            query = searchQuery,
            onQueryChange = onSearchChange,
            modifier = Modifier.width(140.dp)
        )
    }
}

@Composable
private fun SearchBar(
    query: String,
    onQueryChange: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    var isFocused by remember { mutableStateOf(false) }

    val backgroundColor = if (isFocused) {
        Color.White.copy(alpha = 0.15f)
    } else {
        Color.White.copy(alpha = 0.1f)
    }

    val borderColor = if (isFocused) Primary else Color.White.copy(alpha = 0.2f)

    Box(
        modifier = modifier
            .clip(RoundedCornerShape(20.dp))
            .background(backgroundColor)
            .border(1.dp, borderColor, RoundedCornerShape(20.dp))
            .padding(horizontal = 16.dp, vertical = 10.dp)
    ) {
        BasicTextField(
            value = query,
            onValueChange = onQueryChange,
            modifier = Modifier
                .fillMaxWidth()
                .onFocusChanged { isFocused = it.isFocused },
            textStyle = TextStyle(
                color = TextPrimary,
                fontSize = 14.sp
            ),
            singleLine = true,
            cursorBrush = SolidColor(Primary),
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            decorationBox = { innerTextField ->
                Box {
                    if (query.isEmpty()) {
                        Text(
                            text = "Search...",
                            color = Color.White.copy(alpha = 0.5f),
                            fontSize = 14.sp
                        )
                    }
                    innerTextField()
                }
            }
        )
    }
}

@OptIn(ExperimentalTvMaterial3Api::class)
@Composable
private fun MovieGridWithDates(
    gridItems: List<GridItem>,
    playlistUrl: String?,
    onMovieClick: (Movie) -> Unit,
    onTrailersClick: () -> Unit
) {
    val trailersFocusRequester = remember { FocusRequester() }

    // Request focus on trailers card when grid first loads
    LaunchedEffect(gridItems) {
        if (gridItems.any { it is GridItem.TrailersItem }) {
            try {
                trailersFocusRequester.requestFocus()
            } catch (e: Exception) {
                // Focus requester not yet attached, ignore
            }
        }
    }

    TvLazyVerticalGrid(
        columns = TvGridCells.Fixed(5),
        contentPadding = PaddingValues(horizontal = 32.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        modifier = Modifier.fillMaxSize()
    ) {
        items(
            items = gridItems,
            key = { item ->
                when (item) {
                    is GridItem.MovieItem -> "movie_${item.movie.id}"
                    is GridItem.DateItem -> "date_${item.date}"
                    is GridItem.TrailersItem -> "trailers"
                }
            }
        ) { item ->
            when (item) {
                is GridItem.TrailersItem -> {
                    TrailersCard(
                        onClick = onTrailersClick,
                        modifier = Modifier.focusRequester(trailersFocusRequester)
                    )
                }
                is GridItem.DateItem -> {
                    DateDividerCard(dateString = item.date)
                }
                is GridItem.MovieItem -> {
                    MovieCard(
                        movie = item.movie,
                        onClick = { onMovieClick(item.movie) }
                    )
                }
            }
        }
    }
}

@Composable
private fun LoadingState() {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            CircularProgressIndicator(
                color = Primary
            )
            Spacer(modifier = Modifier.height(16.dp))
            Text(
                text = "Loading movies...",
                color = TextSecondary,
                fontSize = 18.sp
            )
        }
    }
}

@OptIn(ExperimentalTvMaterial3Api::class)
@Composable
private fun ErrorState(
    error: String,
    onRetry: () -> Unit
) {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                text = "Error loading movies",
                color = TextPrimary,
                fontSize = 24.sp,
                fontWeight = FontWeight.Bold
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = error,
                color = TextSecondary,
                fontSize = 16.sp
            )
            Spacer(modifier = Modifier.height(24.dp))
            Button(
                onClick = onRetry,
                colors = ButtonDefaults.colors(
                    containerColor = Primary,
                    contentColor = Background
                ),
                shape = ButtonDefaults.shape(RoundedCornerShape(8.dp))
            ) {
                Text(
                    text = "Retry",
                    modifier = Modifier.padding(horizontal = 24.dp, vertical = 8.dp)
                )
            }
        }
    }
}

@Composable
private fun EmptyState() {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                text = "No movies found",
                color = TextPrimary,
                fontSize = 24.sp,
                fontWeight = FontWeight.Bold
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = "Try a different filter or search term",
                color = TextSecondary,
                fontSize = 16.sp
            )
        }
    }
}
