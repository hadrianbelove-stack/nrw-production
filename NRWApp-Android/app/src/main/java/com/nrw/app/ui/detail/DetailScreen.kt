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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
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
import com.nrw.app.data.getFormattedGenres
import com.nrw.app.data.getFormattedRuntime
import com.nrw.app.data.getPosterUrl
import com.nrw.app.data.getRtInfo
import com.nrw.app.ui.components.InfoButton
import com.nrw.app.ui.components.WatchButton
import com.nrw.app.ui.theme.Background
import com.nrw.app.ui.theme.Green
import com.nrw.app.ui.theme.Primary
import com.nrw.app.ui.theme.Red
import com.nrw.app.ui.theme.TextMuted
import com.nrw.app.ui.theme.TextPrimary
import com.nrw.app.ui.theme.TextSecondary
import com.nrw.app.util.DeepLinkHelper

/**
 * Movie Detail Screen for Android TV
 */
@OptIn(ExperimentalTvMaterial3Api::class)
@Composable
fun DetailScreen(
    movieId: Int,
    onBackPress: () -> Unit,
    viewModel: DetailViewModel = viewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    val context = LocalContext.current

    // Load movie when screen opens
    LaunchedEffect(movieId) {
        viewModel.loadMovie(movieId)
    }

    // Handle back button
    BackHandler {
        onBackPress()
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Background)
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
                    onInfoClick = { option ->
                        when (option.type) {
                            "trailer" -> DeepLinkHelper.openTrailer(context, option.url)
                            "rotten_tomatoes" -> DeepLinkHelper.openRottenTomatoes(context, option.url)
                            else -> DeepLinkHelper.openUrl(context, option.url)
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
    onInfoClick: (com.nrw.app.data.InfoOption) -> Unit
) {
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
                                Background.copy(alpha = 0.7f),
                                Background.copy(alpha = 0.5f)
                            )
                        )
                    )
            )
        }

        // Content
        Row(
            modifier = Modifier
                .fillMaxSize()
                .padding(48.dp)
        ) {
            // Left side - Poster
            Box(
                modifier = Modifier
                    .fillMaxHeight()
                    .width(300.dp)
            ) {
                AsyncImage(
                    model = movie.getPosterUrl("w780"),
                    contentDescription = movie.title,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier
                        .fillMaxHeight(0.85f)
                        .aspectRatio(2f / 3f)
                        .clip(RoundedCornerShape(16.dp))
                )

                // RT Score badge
                movie.getRtInfo()?.let { (score, isFresh) ->
                    Box(
                        modifier = Modifier
                            .align(Alignment.BottomStart)
                            .padding(start = 8.dp, bottom = 80.dp)
                            .clip(RoundedCornerShape(8.dp))
                            .background(if (isFresh) Green else Red)
                            .padding(horizontal = 12.dp, vertical = 8.dp)
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(
                                text = "$score%",
                                color = TextPrimary,
                                fontWeight = FontWeight.Bold,
                                fontSize = 18.sp
                            )
                            Text(
                                text = if (isFresh) "Fresh" else "Rotten",
                                color = TextPrimary,
                                fontSize = 12.sp
                            )
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.width(48.dp))

            // Right side - Details
            Column(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxHeight()
                    .verticalScroll(rememberScrollState())
            ) {
                // Title
                Text(
                    text = movie.title,
                    color = TextPrimary,
                    fontSize = 36.sp,
                    fontWeight = FontWeight.Bold,
                    lineHeight = 42.sp
                )

                Spacer(modifier = Modifier.height(12.dp))

                // Metadata row
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    movie.year?.let {
                        Text(text = it.toString(), color = TextSecondary, fontSize = 18.sp)
                    }
                    movie.getFormattedRuntime()?.let {
                        Text(text = "•", color = TextMuted, fontSize = 18.sp)
                        Text(text = it, color = TextSecondary, fontSize = 18.sp)
                    }
                    movie.rating?.let {
                        Text(text = "•", color = TextMuted, fontSize = 18.sp)
                        Box(
                            modifier = Modifier
                                .clip(RoundedCornerShape(4.dp))
                                .background(TextMuted.copy(alpha = 0.3f))
                                .padding(horizontal = 8.dp, vertical = 2.dp)
                        ) {
                            Text(text = it, color = TextSecondary, fontSize = 14.sp)
                        }
                    }
                }

                // Genres
                movie.getFormattedGenres()?.let { genres ->
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = genres,
                        color = Primary,
                        fontSize = 16.sp
                    )
                }

                // Director
                movie.director?.let { director ->
                    Spacer(modifier = Modifier.height(12.dp))
                    Row {
                        Text(text = "Directed by ", color = TextMuted, fontSize = 16.sp)
                        Text(text = director, color = TextPrimary, fontSize = 16.sp, fontWeight = FontWeight.Medium)
                    }
                }

                // Countries
                movie.getFormattedCountries()?.let { countries ->
                    Spacer(modifier = Modifier.height(4.dp))
                    Row {
                        Text(text = "Country ", color = TextMuted, fontSize = 16.sp)
                        Text(text = countries, color = TextPrimary, fontSize = 16.sp)
                    }
                }

                // Synopsis
                movie.synopsis?.let { synopsis ->
                    Spacer(modifier = Modifier.height(24.dp))
                    Text(
                        text = "Synopsis",
                        color = TextPrimary,
                        fontSize = 20.sp,
                        fontWeight = FontWeight.SemiBold
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = synopsis,
                        color = TextSecondary,
                        fontSize = 16.sp,
                        lineHeight = 24.sp
                    )
                }

                // Watch buttons
                if (watchOptions.isNotEmpty()) {
                    Spacer(modifier = Modifier.height(32.dp))
                    Text(
                        text = "Where to Watch",
                        color = TextPrimary,
                        fontSize = 20.sp,
                        fontWeight = FontWeight.SemiBold
                    )
                    Spacer(modifier = Modifier.height(12.dp))

                    // Plex buttons (personal library first)
                    val plexOptions = watchOptions.filter { it.type == WatchType.PLEX }
                    val purchaseOptions = watchOptions.filter { it.type == WatchType.PURCHASE }
                    val streamingOptions = watchOptions.filter { it.type == WatchType.STREAMING }

                    if (plexOptions.isNotEmpty()) {
                        FlowRow(
                            horizontalArrangement = Arrangement.spacedBy(12.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            plexOptions.forEach { option ->
                                WatchButton(
                                    option = option,
                                    onClick = { onWatchClick(option) }
                                )
                            }
                        }
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    if (purchaseOptions.isNotEmpty()) {
                        FlowRow(
                            horizontalArrangement = Arrangement.spacedBy(12.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            purchaseOptions.forEach { option ->
                                WatchButton(
                                    option = option,
                                    onClick = { onWatchClick(option) }
                                )
                            }
                        }
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    if (streamingOptions.isNotEmpty()) {
                        FlowRow(
                            horizontalArrangement = Arrangement.spacedBy(12.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            streamingOptions.forEach { option ->
                                WatchButton(
                                    option = option,
                                    onClick = { onWatchClick(option) }
                                )
                            }
                        }
                    }
                }

                // Info buttons
                if (infoOptions.isNotEmpty()) {
                    Spacer(modifier = Modifier.height(32.dp))
                    Text(
                        text = "More Info",
                        color = TextPrimary,
                        fontSize = 20.sp,
                        fontWeight = FontWeight.SemiBold
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        infoOptions.forEach { option ->
                            InfoButton(
                                label = option.label,
                                onClick = { onInfoClick(option) }
                            )
                        }
                    }
                }

                Spacer(modifier = Modifier.height(48.dp))
            }
        }

        // Footer hint
        Box(
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .fillMaxWidth()
                .background(Background.copy(alpha = 0.8f))
                .padding(vertical = 8.dp),
            contentAlignment = Alignment.Center
        ) {
            Text(
                text = "Press Back to return",
                color = TextMuted,
                fontSize = 14.sp
            )
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
                fontSize = 18.sp
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
                fontSize = 24.sp,
                fontWeight = FontWeight.Bold
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = error,
                color = TextSecondary,
                fontSize = 16.sp
            )
            Spacer(modifier = Modifier.height(16.dp))
            Text(
                text = "Press Back to go back",
                color = TextMuted,
                fontSize = 14.sp
            )
        }
    }
}
