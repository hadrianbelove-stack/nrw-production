package com.nrw.app.ui.components

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Canvas
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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.tv.foundation.lazy.grid.TvGridCells
import androidx.tv.foundation.lazy.grid.TvLazyVerticalGrid
import androidx.tv.foundation.lazy.grid.items
import com.nrw.app.data.Movie
import com.nrw.app.ui.theme.Primary
import com.nrw.app.ui.theme.TextMuted
import com.nrw.app.ui.theme.TextPrimary
import com.nrw.app.ui.theme.TextSecondary

/**
 * Full-screen search destination (Apple TV / Netflix pattern; matches tvOS/Roku):
 * big query field up top, live-filtered results grid below. Back dismisses.
 * Searches title, original title, director, and country over the FULL movie
 * list (search bypasses wall view filters — matches desktop).
 */
@Composable
fun SearchOverlay(
    movies: List<Movie>,
    onMovieClick: (Movie) -> Unit,
    onDismiss: () -> Unit
) {
    var query by remember { mutableStateOf("") }
    var fieldFocused by remember { mutableStateOf(false) }
    val fieldFocus = remember { FocusRequester() }
    BackHandler(onBack = onDismiss)

    val results = remember(query, movies) {
        if (query.isBlank()) emptyList() else {
            val q = query.lowercase()
            movies.filter { m ->
                (m.title.lowercase().contains(q)) ||
                    (m.originalTitle?.lowercase()?.contains(q) == true) ||
                    ((m.crew?.director ?: m.director)?.lowercase()?.contains(q) == true) ||
                    (m.country?.lowercase()?.contains(q) == true)
            }
        }
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xF20A0A0A))
    ) {
        Column(modifier = Modifier.fillMaxSize()) {
            // Big query field — 10-foot sizing, teal focus treatment
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 32.dp, vertical = 20.dp)
                    .clip(RoundedCornerShape(14.dp))
                    .background(if (fieldFocused) Color(0x1400D4AA) else Color.White.copy(alpha = 0.1f))
                    .border(
                        2.dp,
                        if (fieldFocused) Primary else Color.White.copy(alpha = 0.16f),
                        RoundedCornerShape(14.dp)
                    )
                    .padding(horizontal = 20.dp, vertical = 14.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                SearchGlassIcon(
                    size = 20.dp,
                    color = if (fieldFocused) Primary else Color.White.copy(alpha = 0.55f)
                )
                Spacer(modifier = Modifier.width(14.dp))
                BasicTextField(
                    value = query,
                    onValueChange = { query = it },
                    modifier = Modifier
                        .fillMaxWidth()
                        .focusRequester(fieldFocus)
                        .onFocusChanged { fieldFocused = it.isFocused },
                    textStyle = TextStyle(color = TextPrimary, fontSize = 18.sp),
                    singleLine = true,
                    cursorBrush = SolidColor(Primary),
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                    decorationBox = { innerTextField ->
                        Box {
                            if (query.isEmpty()) {
                                Text(
                                    text = "Search movies, directors, countries…",
                                    color = Color.White.copy(alpha = 0.35f),
                                    fontSize = 18.sp
                                )
                            }
                            innerTextField()
                        }
                    }
                )
            }

            // Results count
            if (query.isNotEmpty()) {
                Text(
                    text = "${results.size} ${if (results.size == 1) "result" else "results"} for \"$query\"",
                    color = TextSecondary,
                    fontSize = 13.sp,
                    modifier = Modifier.padding(horizontal = 36.dp)
                )
                Spacer(modifier = Modifier.height(8.dp))
            }

            when {
                results.isNotEmpty() -> {
                    TvLazyVerticalGrid(
                        columns = TvGridCells.Fixed(5),
                        contentPadding = PaddingValues(horizontal = 32.dp, vertical = 8.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                        modifier = Modifier.fillMaxSize()
                    ) {
                        items(items = results, key = { "search_${it.id}" }) { movie ->
                            MovieCard(
                                movie = movie,
                                onClick = { onMovieClick(movie) }
                            )
                        }
                    }
                }
                else -> {
                    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            SearchGlassIcon(
                                size = 48.dp,
                                color = if (query.isEmpty()) Primary.copy(alpha = 0.35f) else Color.White.copy(alpha = 0.18f)
                            )
                            Spacer(modifier = Modifier.height(14.dp))
                            Text(
                                text = if (query.isEmpty()) "Search the wall" else "No movies found",
                                color = TextPrimary,
                                fontSize = 22.sp
                            )
                            Spacer(modifier = Modifier.height(6.dp))
                            Text(
                                text = if (query.isEmpty())
                                    "Results appear as you type — title, director, or country"
                                else
                                    "Try a different title, director, or country",
                                color = TextMuted,
                                fontSize = 14.sp
                            )
                        }
                    }
                }
            }
        }
    }

    LaunchedEffect(Unit) { fieldFocus.requestFocus() }
}

/**
 * Real magnifying-glass icon drawn with Canvas (replaces unicode glyphs; no
 * icon-library dependency). Matches the SVG used on web/tvOS.
 */
@Composable
fun SearchGlassIcon(size: Dp, color: Color) {
    Canvas(modifier = Modifier.size(size)) {
        val strokeW = this.size.minDimension * 0.09f
        val r = this.size.minDimension * 0.30f
        val c = Offset(this.size.width * 0.42f, this.size.height * 0.42f)
        drawCircle(color = color, radius = r, center = c, style = Stroke(width = strokeW))
        drawLine(
            color = color,
            start = Offset(c.x + r * 0.72f, c.y + r * 0.72f),
            end = Offset(this.size.width - strokeW, this.size.height - strokeW),
            strokeWidth = strokeW,
            cap = StrokeCap.Round
        )
    }
}
