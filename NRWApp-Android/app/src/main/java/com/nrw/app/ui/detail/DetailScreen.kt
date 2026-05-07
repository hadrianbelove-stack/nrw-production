package com.nrw.app.ui.detail

import android.app.Activity
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.tv.material3.ExperimentalTvMaterial3Api
import androidx.compose.foundation.Image
import androidx.compose.ui.res.painterResource
import coil.compose.AsyncImage
import com.nrw.app.R
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
import com.nrw.app.util.formatShortDate

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
                contentDescription = movie.displayTitle ?: movie.title,
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
                                text = movie.displayTitle ?: movie.title,
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
                            if (movie.isVirtualScreening) {
                                Text(
                                    text = movie.screeningInfo?.screeningName ?: "VIRTUAL SCREENING",
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
                    movie.rating?.let { rating ->
                        Text(text = "•", color = TextMuted, fontSize = 12.sp)
                        Box(
                            modifier = Modifier
                                .border(1.dp, TextSecondary, RoundedCornerShape(3.dp))
                                .padding(horizontal = 6.dp, vertical = 2.dp)
                        ) {
                            Text(
                                text = rating,
                                color = TextSecondary,
                                fontSize = 10.sp,
                                fontWeight = FontWeight.SemiBold
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
                    val screeningCallout = if (movie.isVirtualScreening && movie.screeningInfo?.screeningName != null) {
                        val festName = movie.screeningInfo!!.screeningName!!
                        val endStr = movie.screeningInfo?.availableEnd?.let { " Ends ${formatShortDate(it)}." } ?: ""
                        " Virtual screening available as part of the $festName.$endStr"
                    } else null

                    Text(
                        text = buildAnnotatedString {
                            append(synopsis)
                            screeningCallout?.let {
                                withStyle(SpanStyle(
                                    color = Color(0xFFFFD700),
                                    fontWeight = FontWeight.Bold,
                                    fontStyle = androidx.compose.ui.text.font.FontStyle.Italic
                                )) {
                                    append(it)
                                }
                            }
                        },
                        color = TextSecondary,
                        fontSize = 14.sp,
                        lineHeight = 20.sp
                    )
                }

                // Pull quotes
                if (!movie.pullQuotes.isNullOrEmpty()) {
                    Spacer(modifier = Modifier.height(12.dp))
                    movie.pullQuotes!!.take(2).forEach { pq ->
                        pq.text?.let { quoteText ->
                            Column(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(bottom = 8.dp)
                                    .border(0.dp, Color.Transparent)
                            ) {
                                Row {
                                    Box(
                                        modifier = Modifier
                                            .background(
                                                if (pq.source == "rotten_tomatoes") Color(0xFFFA3232)
                                                else Color(0xFF00E054),
                                                RoundedCornerShape(3.dp)
                                            )
                                            .padding(horizontal = 6.dp, vertical = 2.dp)
                                    ) {
                                        Text(
                                            text = if (pq.source == "rotten_tomatoes") "RT" else "LB",
                                            color = Color.White,
                                            fontSize = 9.sp,
                                            fontWeight = FontWeight.Bold
                                        )
                                    }
                                    Spacer(modifier = Modifier.width(8.dp))
                                    Text(
                                        text = "\u201C$quoteText\u201D",
                                        color = TextSecondary,
                                        fontSize = 12.sp,
                                        fontStyle = androidx.compose.ui.text.font.FontStyle.Italic,
                                        lineHeight = 16.sp,
                                        modifier = Modifier.weight(1f)
                                    )
                                }
                                val attribution = listOfNotNull(pq.critic, pq.outlet).joinToString(", ")
                                if (attribution.isNotEmpty()) {
                                    Text(
                                        text = "\u2014 $attribution",
                                        color = TextMuted,
                                        fontSize = 10.sp,
                                        modifier = Modifier.padding(start = 32.dp, top = 2.dp)
                                    )
                                }
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))

                // Trailer — full-width on top
                trailerOption?.let { option ->
                    TrailerButton(
                        onClick = { onTrailerClick(option.url) },
                        compact = false
                    )
                    Spacer(modifier = Modifier.height(10.dp))
                }

                // Watch buttons row
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    watchOptions.forEach { option ->
                        Column {
                            WatchButton(
                                option = option,
                                onClick = { onWatchClick(option) },
                                compact = true
                            )
                            if (option.sublabel != null) {
                                Text(
                                    text = option.sublabel,
                                    color = Color(0xFFC4B5FD),
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Medium,
                                    modifier = Modifier.padding(top = 2.dp)
                                )
                            }
                        }
                    }
                }

                // Info row — Wiki + RT + IMDb shared
                val hasWiki = movie.links?.wikipedia != null
                if (hasWiki || rtInfo != null || movie.metacriticScore?.toIntOrNull() != null || movie.imdbRating?.toFloatOrNull() != null) {
                    Spacer(modifier = Modifier.height(10.dp))
                    val context = androidx.compose.ui.platform.LocalContext.current
                    val rtUrl = movie.links?.rt ?: movie.links?.rottenTomatoes
                    val mcUrl = movie.links?.metacritic
                    val imdbUrl = movie.links?.imdb
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        movie.links?.wikipedia?.let { wikiUrl ->
                            Box(
                                modifier = Modifier
                                    .weight(1f)
                                    .clip(RoundedCornerShape(6.dp))
                                    .background(Color.White.copy(alpha = 0.1f))
                                    .border(1.dp, Color.White.copy(alpha = 0.3f), RoundedCornerShape(6.dp))
                                    .clickable { com.nrw.app.utils.DeepLinkHelper.openUrl(context, wikiUrl, "wikipedia") }
                                    .padding(horizontal = 10.dp, vertical = 6.dp),
                                contentAlignment = Alignment.Center
                            ) {
                                Text(
                                    text = "Wiki",
                                    color = TextPrimary,
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 12.sp
                                )
                            }
                        }
                        rtInfo?.let { (score, _) ->
                            Box(
                                modifier = Modifier
                                    .weight(1f)
                                    .clip(RoundedCornerShape(6.dp))
                                    .background(Color.White.copy(alpha = 0.06f))
                                    .border(1.dp, Color.White.copy(alpha = 0.1f), RoundedCornerShape(6.dp))
                                    .then(if (rtUrl != null) Modifier.clickable { com.nrw.app.utils.DeepLinkHelper.openUrl(context, rtUrl, "rt") } else Modifier)
                                    .padding(horizontal = 10.dp, vertical = 6.dp),
                                contentAlignment = Alignment.Center
                            ) {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.Center
                                ) {
                                    Image(
                                        painter = painterResource(id = R.drawable.logo_rt),
                                        contentDescription = null,
                                        modifier = Modifier.height(18.dp).padding(end = 4.dp),
                                        contentScale = ContentScale.Fit
                                    )
                                    Text(
                                        text = "$score%",
                                        color = Color(0xFFFF6B6B),
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 12.sp
                                    )
                                }
                            }
                        }
                        movie.metacriticScore?.toIntOrNull()?.let { score ->
                            if (score > 0) {
                                Box(
                                    modifier = Modifier
                                        .weight(1f)
                                        .clip(RoundedCornerShape(6.dp))
                                        .background(Color.White.copy(alpha = 0.06f))
                                        .border(1.dp, Color.White.copy(alpha = 0.1f), RoundedCornerShape(6.dp))
                                        .then(if (mcUrl != null) Modifier.clickable { com.nrw.app.utils.DeepLinkHelper.openUrl(context, mcUrl, "metacritic") } else Modifier)
                                        .padding(horizontal = 10.dp, vertical = 6.dp),
                                    contentAlignment = Alignment.Center
                                ) {
                                    Row(
                                        verticalAlignment = Alignment.CenterVertically,
                                        horizontalArrangement = Arrangement.Center
                                    ) {
                                        Image(
                                            painter = painterResource(id = R.drawable.logo_mc),
                                            contentDescription = null,
                                            modifier = Modifier.height(18.dp).padding(end = 4.dp),
                                            contentScale = ContentScale.Fit,
                                            colorFilter = ColorFilter.tint(Color(0xFF7DDF64))
                                        )
                                        Text(
                                            text = "$score",
                                            color = Color(0xFF7DDF64),
                                            fontWeight = FontWeight.Bold,
                                            fontSize = 12.sp
                                        )
                                    }
                                }
                            }
                        }
                        movie.imdbRating?.toFloatOrNull()?.let { rating ->
                            Box(
                                modifier = Modifier
                                    .weight(1f)
                                    .clip(RoundedCornerShape(6.dp))
                                    .background(Color.White.copy(alpha = 0.06f))
                                    .border(1.dp, Color.White.copy(alpha = 0.1f), RoundedCornerShape(6.dp))
                                    .then(if (imdbUrl != null) Modifier.clickable { com.nrw.app.utils.DeepLinkHelper.openUrl(context, imdbUrl, "imdb") } else Modifier)
                                    .padding(horizontal = 10.dp, vertical = 6.dp),
                                contentAlignment = Alignment.Center
                            ) {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.Center
                                ) {
                                    Image(
                                        painter = painterResource(id = R.drawable.logo_imdb),
                                        contentDescription = null,
                                        modifier = Modifier.height(18.dp).padding(end = 4.dp),
                                        contentScale = ContentScale.Fit
                                    )
                                    Text(
                                        text = "${"%.1f".format(rating)}",
                                        color = Color(0xFFF5C518),
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 12.sp
                                    )
                                }
                            }
                        }
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
