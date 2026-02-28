package com.nrw.app.ui.detail

import android.app.Activity
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.foundation.focusable
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.tv.material3.ExperimentalTvMaterial3Api
import coil.compose.AsyncImage
import com.nrw.app.data.Movie
import com.nrw.app.data.WatchType
import com.nrw.app.data.getBackdropUrl
import com.nrw.app.data.getFormattedCountries
import com.nrw.app.data.getFormattedRuntime
import com.nrw.app.data.getPosterUrl
import com.nrw.app.data.getRtInfo
import com.nrw.app.data.isStaffPick
import com.nrw.app.ui.components.TrailerButton
import com.nrw.app.ui.components.WatchButton
import com.nrw.app.ui.theme.Background
import com.nrw.app.ui.theme.Green
import com.nrw.app.ui.theme.Primary
import com.nrw.app.ui.theme.Red
import com.nrw.app.ui.theme.RestorationGold
import com.nrw.app.ui.theme.StaffPickRed
import com.nrw.app.ui.theme.TextMuted
import com.nrw.app.ui.theme.TextPrimary
import com.nrw.app.ui.theme.TextSecondary
import com.nrw.app.util.DeepLinkHelper

private fun formatShortDate(dateStr: String): String {
    val parts = dateStr.split("-")
    if (parts.size < 3) return dateStr
    val month = when (parts[1]) {
        "01" -> "Jan"; "02" -> "Feb"; "03" -> "Mar"; "04" -> "Apr"
        "05" -> "May"; "06" -> "Jun"; "07" -> "Jul"; "08" -> "Aug"
        "09" -> "Sep"; "10" -> "Oct"; "11" -> "Nov"; "12" -> "Dec"
        else -> parts[1]
    }
    val day = parts[2].trimStart('0')
    return "$month $day"
}

/**
 * Movie Detail Screen for Android TV
 * Matches tvOS layout: 35% poster, 60dp padding, buttons above synopsis
 */
@OptIn(ExperimentalTvMaterial3Api::class)
@Composable
fun DetailScreen(
    movieId: String,
    onBackPress: () -> Unit,
    viewModel: DetailViewModel = viewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    val context = LocalContext.current
    val focusRequester = remember { FocusRequester() }
    var trailerVisible by remember { mutableStateOf(false) }

    // Load movie when screen opens
    LaunchedEffect(movieId) {
        viewModel.loadMovie(movieId)
    }

    // Request focus for key event handling
    LaunchedEffect(Unit) {
        focusRequester.requestFocus()
    }

    // Handle back button
    BackHandler {
        onBackPress()
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Background)
            .focusRequester(focusRequester)
            .focusable()
            .onKeyEvent { event ->
                if (event.type == KeyEventType.KeyDown) {
                    when (event.key) {
                        Key.DirectionLeft -> {
                            viewModel.navigatePrevious()
                            true
                        }
                        Key.DirectionRight -> {
                            viewModel.navigateNext()
                            true
                        }
                        else -> false
                    }
                } else false
            }
    ) {
        when {
            uiState.isLoading -> {
                LoadingState()
            }
            uiState.error != null -> {
                ErrorState(error = uiState.error!!)
            }
            uiState.movie != null -> {
                MovieDetail(
                    movie = uiState.movie!!,
                    watchOptions = uiState.watchOptions,
                    infoOptions = uiState.infoOptions,
                    onWatchClick = { option ->
                        DeepLinkHelper.openUrl(context, option.url, option.service)
                    },
                    onTrailerClick = { _ ->
                        trailerVisible = true
                    }
                )
            }
        }

        // Trailer player overlay
        if (trailerVisible) {
            val movieList = viewModel.getMovieList()
            if (movieList.isNotEmpty()) {
                TrailerPlayerOverlay(
                    movieList = movieList,
                    initialIndex = uiState.currentIndex,
                    onClose = { lastIndex ->
                        trailerVisible = false
                        if (lastIndex != uiState.currentIndex) {
                            viewModel.navigateToIndex(lastIndex)
                        }
                    }
                )
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class, ExperimentalTvMaterial3Api::class)
@Composable
private fun MovieDetail(
    movie: Movie,
    watchOptions: List<com.nrw.app.data.WatchOption>,
    infoOptions: List<com.nrw.app.data.InfoOption>,
    onWatchClick: (com.nrw.app.data.WatchOption) -> Unit,
    onTrailerClick: (String) -> Unit
) {
    // Find trailer URL (only info option we use on TV)
    val trailerOption = infoOptions.find { it.type == "trailer" }
    val rtInfo = movie.getRtInfo()

    Box(modifier = Modifier.fillMaxSize()) {
        // Backdrop image with gradient overlay
        movie.getBackdropUrl()?.let { backdropUrl ->
            AsyncImage(
                model = backdropUrl,
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize()
            )
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(
                        Brush.horizontalGradient(
                            colors = listOf(
                                Background.copy(alpha = 0.95f),
                                Background.copy(alpha = 0.8f),
                                Background.copy(alpha = 0.6f)
                            )
                        )
                    )
            )
        }

        // Teal chevron - Left
        Text(
            text = "‹",
            color = Primary.copy(alpha = 0.6f),
            fontSize = 56.sp,
            fontWeight = FontWeight.Thin,
            modifier = Modifier
                .align(Alignment.CenterStart)
                .padding(start = 8.dp)
        )

        // Teal chevron - Right
        Text(
            text = "›",
            color = Primary.copy(alpha = 0.6f),
            fontSize = 56.sp,
            fontWeight = FontWeight.Thin,
            modifier = Modifier
                .align(Alignment.CenterEnd)
                .padding(end = 8.dp)
        )

        // Content - Centered layout with large poster
        Row(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 80.dp, vertical = 24.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.Center
        ) {
            // Left side - Large Poster (Option E: biggest poster)
            AsyncImage(
                model = movie.getPosterUrl("w780"),
                contentDescription = movie.title,
                contentScale = ContentScale.Crop,
                modifier = Modifier
                    .fillMaxHeight(0.92f)
                    .aspectRatio(2f / 3f)
                    .clip(RoundedCornerShape(12.dp))
            )

            Spacer(modifier = Modifier.width(40.dp))

            // Right side - Compact Details
            Column(
                modifier = Modifier
                    .weight(1f)
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.Center
            ) {
                // Title row with Staff Pick badge and date
                Column {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(12.dp),
                            modifier = Modifier.weight(1f)
                        ) {
                            Text(
                                text = movie.title,
                                color = TextPrimary,
                                fontSize = 28.sp,
                                fontWeight = FontWeight.Bold,
                                lineHeight = 32.sp
                            )
                            if (movie.isStaffPick()) {
                                Box(
                                    modifier = Modifier
                                        .clip(RoundedCornerShape(4.dp))
                                        .background(StaffPickRed)
                                        .padding(horizontal = 8.dp, vertical = 4.dp)
                                ) {
                                    Text(
                                        text = "STAFF PICK",
                                        color = TextPrimary,
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 10.sp,
                                        letterSpacing = 0.5.sp
                                    )
                                }
                            }
                            if (movie.categories?.isRestoration == true) {
                                Box(
                                    modifier = Modifier
                                        .clip(RoundedCornerShape(4.dp))
                                        .background(RestorationGold)
                                        .padding(horizontal = 8.dp, vertical = 4.dp)
                                ) {
                                    Text(
                                        text = "RESTORED",
                                        color = Color.Black,
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 10.sp,
                                        letterSpacing = 0.5.sp
                                    )
                                }
                            }
                            movie.festivalInfo?.festivalName?.let { festivalName ->
                                Text(
                                    text = festivalName,
                                    color = Color.Black,
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.ExtraBold,
                                    letterSpacing = 1.5.sp,
                                    textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .background(Color(0xFFFFD700))
                                        .padding(vertical = 8.dp, horizontal = 12.dp)
                                )
                            }
                        }
                        movie.digitalDate?.let { date ->
                            Text(
                                text = formatShortDate(date),
                                color = Primary,
                                fontSize = 22.sp,
                                fontWeight = FontWeight.Bold
                            )
                        }
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(2.dp)
                            .background(Primary.copy(alpha = 0.4f))
                    )
                }

                Spacer(modifier = Modifier.height(8.dp))

                // Meta row: Director • Country • Year • Runtime • RT Score
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    movie.director?.let { director ->
                        Text(
                            text = director,
                            color = Primary,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Medium
                        )
                        Text(text = "•", color = TextMuted, fontSize = 12.sp)
                    }
                    movie.getFormattedCountries()?.let { country ->
                        Text(text = country, color = Primary, fontSize = 12.sp)
                        Text(text = "•", color = TextMuted, fontSize = 12.sp)
                    }
                    movie.year?.let { year ->
                        Text(text = year.toString(), color = TextSecondary, fontSize = 12.sp)
                        Text(text = "•", color = TextMuted, fontSize = 12.sp)
                    }
                    movie.getFormattedRuntime()?.let { runtime ->
                        Text(text = runtime, color = TextSecondary, fontSize = 12.sp)
                    }
                    // RT Score badge inline
                    rtInfo?.let { (score, isFresh) ->
                        Spacer(modifier = Modifier.width(4.dp))
                        Box(
                            modifier = Modifier
                                .clip(RoundedCornerShape(4.dp))
                                .background(if (isFresh) Green else Red)
                                .padding(horizontal = 6.dp, vertical = 2.dp)
                        ) {
                            Text(
                                text = "🍅 $score%",
                                color = TextPrimary,
                                fontWeight = FontWeight.Bold,
                                fontSize = 11.sp
                            )
                        }
                    }
                }

                // Genres as chips
                movie.genres?.takeIf { it.isNotEmpty() }?.let { genres ->
                    Spacer(modifier = Modifier.height(10.dp))
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        genres.take(3).forEach { genre ->
                            Box(
                                modifier = Modifier
                                    .clip(RoundedCornerShape(12.dp))
                                    .background(Color.White.copy(alpha = 0.1f))
                                    .padding(horizontal = 10.dp, vertical = 4.dp)
                            ) {
                                Text(
                                    text = genre,
                                    color = TextSecondary,
                                    fontSize = 11.sp
                                )
                            }
                        }
                    }
                }

                // Cast - "Starring X, Y"
                movie.crew?.cast?.takeIf { it.isNotEmpty() }?.let { cast ->
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "Starring: ${cast.take(2).joinToString(", ")}",
                        color = TextMuted,
                        fontSize = 12.sp
                    )
                }

                // Language (only if not English)
                movie.original_language?.takeIf { it != "en" }?.let { lang ->
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "Language: ${lang.uppercase()}",
                        color = TextMuted,
                        fontSize = 11.sp
                    )
                }

                Spacer(modifier = Modifier.height(12.dp))

                // Synopsis - compact
                movie.synopsis?.let { synopsis ->
                    Text(
                        text = synopsis,
                        color = TextSecondary,
                        fontSize = 14.sp,
                        lineHeight = 20.sp
                    )
                }

                Spacer(modifier = Modifier.height(16.dp))

                // Action buttons - compact row
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    // Trailer button first (if available)
                    trailerOption?.let { option ->
                        TrailerButton(
                            onClick = { onTrailerClick(option.url) },
                            compact = true
                        )
                    }

                    // Watch buttons - all in one row
                    watchOptions.forEach { option ->
                        WatchButton(
                            option = option,
                            onClick = { onWatchClick(option) },
                            compact = true
                        )
                    }
                }

                Spacer(modifier = Modifier.height(24.dp))
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
            CircularProgressIndicator(color = Primary)
            Spacer(modifier = Modifier.height(16.dp))
            Text(
                text = "Loading movie...",
                color = TextSecondary,
                fontSize = 24.sp
            )
        }
    }
}

@Composable
private fun ErrorState(error: String) {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                text = "Movie not found",
                color = TextPrimary,
                fontSize = 32.sp,
                fontWeight = FontWeight.Bold
            )
            Spacer(modifier = Modifier.height(12.dp))
            Text(
                text = error,
                color = TextSecondary,
                fontSize = 24.sp
            )
            Spacer(modifier = Modifier.height(20.dp))
            Text(
                text = "Press Back to go back",
                color = TextMuted,
                fontSize = 18.sp
            )
        }
    }
}
