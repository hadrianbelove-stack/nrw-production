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
import androidx.compose.foundation.layout.IntrinsicSize
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
import androidx.compose.ui.text.style.TextOverflow
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
import com.nrw.app.data.getDisplayDate
import com.nrw.app.data.getFormattedCountries
import com.nrw.app.data.getFormattedRuntime
import com.nrw.app.data.getPosterUrl
import com.nrw.app.data.getRtInfo
import com.nrw.app.data.isStaffPick
import com.nrw.app.ui.components.WatchButton
import com.nrw.app.ui.components.getServiceColor
import com.nrw.app.ui.theme.Background
import com.nrw.app.ui.theme.Primary
import com.nrw.app.ui.theme.RestorationGold
import com.nrw.app.ui.theme.StaffPickRed
import com.nrw.app.ui.theme.TextMuted
import com.nrw.app.ui.theme.TextPrimary
import com.nrw.app.ui.theme.TextSecondary
import com.nrw.app.util.DeepLinkHelper
import com.nrw.app.util.formatShortDate

/** ISO language code -> readable name (e.g. "es" -> "Spanish"); falls back to the upper code. */
private val LANGUAGE_NAMES = mapOf(
    "en" to "English", "es" to "Spanish", "fr" to "French", "de" to "German", "it" to "Italian",
    "pt" to "Portuguese", "ja" to "Japanese", "ko" to "Korean", "zh" to "Chinese", "hi" to "Hindi",
    "ru" to "Russian", "ar" to "Arabic", "nl" to "Dutch", "sv" to "Swedish", "da" to "Danish",
    "no" to "Norwegian", "fi" to "Finnish", "pl" to "Polish", "tr" to "Turkish", "th" to "Thai",
    "he" to "Hebrew", "fa" to "Persian", "el" to "Greek", "cs" to "Czech", "hu" to "Hungarian",
    "ro" to "Romanian", "uk" to "Ukrainian", "id" to "Indonesian", "vi" to "Vietnamese",
    "ta" to "Tamil", "te" to "Telugu", "is" to "Icelandic", "ga" to "Irish", "ca" to "Catalan",
)
private fun languageName(code: String): String = LANGUAGE_NAMES[code.lowercase()] ?: code.uppercase()

/**
 * Append text rendering a tiny markdown subset: **bold**, *italic*, and [text](url).
 * Links are stripped to their text — URLs are discarded (not navigable on Android TV),
 * matching the tvOS/iOS renderMarkdownSpans. Anything else is appended as plain text.
 * Canonical spec: docs/STYLE_GUIDE.md "Synopsis / Capsule Text Formatting".
 */
private fun androidx.compose.ui.text.AnnotatedString.Builder.appendMarkdown(text: String) {
    // Strip markdown links [text](url) -> text first, so **[Name](url)** still bolds correctly.
    val src = text.replace(Regex("""\[([^\]]+)\]\([^)]+\)"""), "$1")
    val regex = Regex("""\*\*([^*]+)\*\*|\*([^*]+)\*""")
    var last = 0
    for (m in regex.findAll(src)) {
        if (m.range.first > last) append(src.substring(last, m.range.first))
        val bold = m.groupValues[1]
        val italic = m.groupValues[2]
        if (bold.isNotEmpty()) {
            withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(bold) }
        } else {
            withStyle(SpanStyle(fontStyle = androidx.compose.ui.text.font.FontStyle.Italic)) { append(italic) }
        }
        last = m.range.last + 1
    }
    if (last < src.length) append(src.substring(last))
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
    val context = LocalContext.current  // for tappable pull-quote review links below

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
            // Left side - Large Poster with trailer overlay
            Box(
                modifier = Modifier
                    .fillMaxHeight(0.92f)
                    .aspectRatio(2f / 3f)
                    .clip(RoundedCornerShape(12.dp))
                    .then(
                        if (trailerOption != null) Modifier.border(3.dp, Color(0xFFE50914), RoundedCornerShape(12.dp))
                        else Modifier
                    )
            ) {
                AsyncImage(
                    model = movie.getPosterUrl("w780"),
                    contentDescription = movie.displayTitle ?: movie.title,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxSize()
                )

                // Trailer overlay (#10: dim + red circle + TRAILER text)
                if (trailerOption != null) {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .background(Color.Black.copy(alpha = 0.45f))
                            .clickable { onTrailerClick(trailerOption.url) },
                        contentAlignment = Alignment.Center
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            // Red play circle
                            Box(
                                modifier = Modifier
                                    .width(70.dp)
                                    .height(70.dp)
                                    .clip(RoundedCornerShape(35.dp))
                                    .background(Color(0xFFE50914)),
                                contentAlignment = Alignment.Center
                            ) {
                                // Play triangle
                                Image(
                                    painter = painterResource(id = android.R.drawable.ic_media_play),
                                    contentDescription = "Play",
                                    modifier = Modifier.height(28.dp),
                                    contentScale = ContentScale.Fit,
                                    colorFilter = ColorFilter.tint(Color.White)
                                )
                            }
                            Spacer(modifier = Modifier.height(10.dp))
                            Text(
                                text = "TRAILER",
                                color = Color.White,
                                fontSize = 18.sp,
                                fontWeight = FontWeight.ExtraBold,
                                letterSpacing = 4.sp
                            )
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.width(40.dp))

            // Right side - Compact Details
            // Top-aligned (no Center) so the hero block keeps a stable height and
            // nothing below it shifts as you move between films.
            Column(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxHeight()
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.Top
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
                                lineHeight = 32.sp,
                                maxLines = 2,
                                overflow = TextOverflow.Ellipsis,
                                modifier = Modifier.weight(1f)
                            )
                            if (movie.isStaffPick()) {
                                Box(
                                    modifier = Modifier
                                        .clip(RoundedCornerShape(4.dp))
                                        .background(StaffPickRed)
                                        .padding(horizontal = 8.dp, vertical = 4.dp)
                                ) {
                                    Text(
                                        text = "★ NRW SELECT ★",
                                        color = TextPrimary,
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 10.sp,
                                        letterSpacing = 0.5.sp
                                    )
                                }
                            }
                            if (movie.filters?.isRestoration == true) {
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
                            // Loud full-width gold screening banner removed — the screening
                            // is surfaced only via the inline gold-italic synopsis callout below.
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

                // Meta block — 3 lines
                movie.director?.let { director ->
                    Text(
                        text = buildAnnotatedString {
                            withStyle(SpanStyle(color = Primary, fontWeight = FontWeight.Bold)) {
                                append("Dir: ")
                            }
                            withStyle(SpanStyle(color = TextPrimary, fontWeight = FontWeight.Bold)) {
                                append(director)
                            }
                        },
                        fontSize = 18.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
                movie.crew?.cast?.takeIf { it.isNotEmpty() }?.let { cast ->
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = buildAnnotatedString {
                            withStyle(SpanStyle(color = Primary, fontWeight = FontWeight.Bold)) {
                                append("Cast: ")
                            }
                            withStyle(SpanStyle(color = TextPrimary, fontWeight = FontWeight.Bold)) {
                                append(cast.take(3).joinToString(", "))
                            }
                        },
                        fontSize = 18.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
                Spacer(modifier = Modifier.height(4.dp))
                // Meta row: Country · Genre · digital date (Mon D) · runtime · studio
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    movie.getFormattedCountries()?.let { country ->
                        Text(text = country, color = TextSecondary, fontSize = 18.sp)
                        Text(text = "•", color = TextMuted, fontSize = 18.sp)
                    }
                    movie.genres?.firstOrNull()?.let { genre ->
                        Text(text = genre, color = TextSecondary, fontSize = 18.sp)
                        Text(text = "•", color = TextMuted, fontSize = 18.sp)
                    }
                    movie.getDisplayDate()?.let { date ->
                        Text(text = formatShortDate(date), color = TextSecondary, fontSize = 18.sp)
                        Text(text = "•", color = TextMuted, fontSize = 18.sp)
                    }
                    movie.getFormattedRuntime()?.let { runtime ->
                        Text(text = runtime, color = TextSecondary, fontSize = 18.sp)
                    }
                    movie.studio?.let { studio ->
                        Text(text = "•", color = TextMuted, fontSize = 18.sp)
                        Text(text = studio, color = TextSecondary, fontSize = 18.sp)
                    }
                }

                // Language (only if not English)
                movie.originalLanguage?.takeIf { it != "en" }?.let { lang ->
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "Language: ${languageName(lang)}",
                        color = TextMuted,
                        fontSize = 11.sp
                    )
                }

                Spacer(modifier = Modifier.height(12.dp))

                // Pull quotes \u2014 teal italic with a teal left accent stripe (mockup .pq)
                if (!movie.pullQuotes.isNullOrEmpty()) {
                    movie.pullQuotes!!.forEach { pq ->
                        pq.text?.let { quoteText ->
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(bottom = 8.dp)
                                    .clip(RoundedCornerShape(6.dp))
                                    .background(Primary.copy(alpha = 0.07f))
                                    .let { base ->
                                        // Tap opens the source review (parity with iOS); inert if no URL.
                                        pq.reviewUrl?.takeIf { it.isNotBlank() }?.let { url ->
                                            base.clickable { DeepLinkHelper.openUrl(context, url, "review") }
                                        } ?: base
                                    }
                                    .height(IntrinsicSize.Min)
                            ) {
                                // Teal left border / accent stripe
                                Box(
                                    modifier = Modifier
                                        .width(3.dp)
                                        .fillMaxHeight()
                                        .background(Primary)
                                )
                                Column(
                                    modifier = Modifier.padding(horizontal = 10.dp, vertical = 8.dp)
                                ) {
                                    Text(
                                        text = "\u201C$quoteText\u201D",
                                        color = Primary,
                                        fontSize = 12.sp,
                                        fontStyle = androidx.compose.ui.text.font.FontStyle.Italic,
                                        lineHeight = 16.sp
                                    )
                                    val attribution = listOfNotNull(pq.critic, pq.outlet).joinToString(", ")
                                    if (attribution.isNotEmpty()) {
                                        Text(
                                            text = "\u2014 $attribution",
                                            color = Primary.copy(alpha = 0.6f),
                                            fontSize = 10.sp,
                                            modifier = Modifier.padding(top = 2.dp)
                                        )
                                    }
                                }
                            }
                        }
                    }
                    Spacer(modifier = Modifier.height(12.dp))
                }

                // Synopsis - compact (prefers editorial capsule over raw TMDB synopsis)
                (movie.capsule ?: movie.synopsis)?.let { synopsis ->
                    val screeningCallout = if (movie.filters?.isVirtualScreening == true && movie.screeningInfo?.screeningName != null) {
                        val festName = movie.screeningInfo!!.screeningName!!
                        val endStr = movie.screeningInfo?.availableEnd?.let { " Ends ${formatShortDate(it)}." } ?: ""
                        " Virtual screening available as part of the $festName.$endStr"
                    } else null

                    Text(
                        text = buildAnnotatedString {
                            appendMarkdown(synopsis)
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

                Spacer(modifier = Modifier.height(16.dp))

                // Trailer is now a poster overlay (see poster Box above)

                // Watch buttons — VOD (rent/buy) first, then streaming
                val vodOptions = watchOptions.filter { it.type == WatchType.PURCHASE }
                val streamOptions = watchOptions.filter { it.type == WatchType.STREAMING }
                val plexOptions = watchOptions.filter { it.type == WatchType.PLEX }

                if (vodOptions.isNotEmpty()) {
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        vodOptions.forEach { option ->
                            Column {
                                val hasPrice = option.rentPrice != null || option.buyPrice != null
                                if (hasPrice) {
                                    // V2: Logo left, prices stacked right
                                    val svcColor = getServiceColor(option.service)
                                    Row(
                                        modifier = Modifier.clip(RoundedCornerShape(6.dp)).height(IntrinsicSize.Min)
                                    ) {
                                        // Logo area (left half)
                                        Box(
                                            modifier = Modifier.weight(1f).fillMaxHeight(),
                                            contentAlignment = Alignment.Center
                                        ) {
                                            WatchButton(option = option, onClick = { onWatchClick(option) }, compact = true)
                                        }
                                        // Prices area (right half)
                                        Column(modifier = Modifier.weight(1f)) {
                                            if (option.rentPrice != null) {
                                                Box(
                                                    modifier = Modifier.fillMaxWidth().weight(1f).background(svcColor.copy(alpha = 0.8f)).padding(vertical = 8.dp),
                                                    contentAlignment = Alignment.Center
                                                ) {
                                                    Text(text = "RENT ${option.rentPrice}", color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 0.3.sp)
                                                }
                                            }
                                            if (option.buyPrice != null) {
                                                Box(
                                                    modifier = Modifier.fillMaxWidth().weight(1f).background(svcColor.copy(alpha = 0.6f)).padding(vertical = 8.dp),
                                                    contentAlignment = Alignment.Center
                                                ) {
                                                    Text(text = "BUY ${option.buyPrice}", color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 0.3.sp)
                                                }
                                            }
                                        }
                                    }
                                } else {
                                    WatchButton(option = option, onClick = { onWatchClick(option) }, compact = true)
                                }
                                if (option.sublabel != null) {
                                    Text(text = option.sublabel, color = Color(0xFFC4B5FD), fontSize = 11.sp, fontWeight = FontWeight.Medium, modifier = Modifier.padding(top = 2.dp))
                                }
                            }
                        }
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                }

                if (streamOptions.isNotEmpty()) {
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        streamOptions.forEach { option ->
                            WatchButton(option = option, onClick = { onWatchClick(option) }, compact = true)
                        }
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                }

                if (plexOptions.isNotEmpty()) {
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        plexOptions.forEach { option ->
                            WatchButton(option = option, onClick = { onWatchClick(option) }, compact = true)
                        }
                    }
                }

                // Scores row — RT + MC + IMDb + LB display-only (no Wiki on TV)
                val mcScore = movie.metacriticScore?.toIntOrNull()?.takeIf { it > 0 }
                val lbRating = movie.letterboxdScore?.toFloatOrNull()
                if (rtInfo != null || mcScore != null || movie.imdbRating?.toFloatOrNull() != null || lbRating != null) {
                    Spacer(modifier = Modifier.height(14.dp))
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(24.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        // RT: tomato icon + score + freshness label
                        rtInfo?.let { (score, _) ->
                            val isCertifiedFresh = score >= 75
                            val isFresh = score >= 60
                            val freshnessLabel = if (isCertifiedFresh) "CERTIFIED FRESH" else if (isFresh) "FRESH" else "ROTTEN"
                            val freshnessColor = if (isCertifiedFresh) Color(0xFFFFD700) else if (isFresh) Color(0xFFFA3232) else Color(0xFF77B900)
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Image(
                                    painter = painterResource(id = R.drawable.logo_rt),
                                    contentDescription = "Rotten Tomatoes",
                                    modifier = Modifier.height(32.dp).padding(end = 8.dp),
                                    contentScale = ContentScale.Fit,
                                    colorFilter = if (!isFresh) ColorFilter.tint(Color(0xFF77B900)) else null
                                )
                                Column {
                                    Text(
                                        text = "$score%",
                                        color = TextPrimary,
                                        fontWeight = FontWeight.ExtraBold,
                                        fontSize = 18.sp
                                    )
                                    Text(
                                        text = freshnessLabel,
                                        color = freshnessColor,
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 9.sp,
                                        letterSpacing = 0.5.sp
                                    )
                                }
                            }
                        }
                        // MC: colored score box + M logo + wordmark
                        mcScore?.let { score ->
                            val mcColor = when {
                                score >= 61 -> Color(0xFF66CC33)
                                score >= 40 -> Color(0xFFFFCC33)
                                else -> Color(0xFFFF0000)
                            }
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Box(
                                    modifier = Modifier
                                        .width(40.dp)
                                        .height(40.dp)
                                        .clip(RoundedCornerShape(4.dp))
                                        .background(mcColor),
                                    contentAlignment = Alignment.Center
                                ) {
                                    Text(
                                        text = "$score",
                                        color = Color.White,
                                        fontWeight = FontWeight.ExtraBold,
                                        fontSize = 20.sp
                                    )
                                }
                                Column(
                                    modifier = Modifier.padding(start = 8.dp),
                                    horizontalAlignment = Alignment.CenterHorizontally
                                ) {
                                    Image(
                                        painter = painterResource(id = R.drawable.logo_mc),
                                        contentDescription = "Metacritic",
                                        modifier = Modifier.height(18.dp),
                                        contentScale = ContentScale.Fit
                                    )
                                    Text(
                                        text = "METACRITIC",
                                        color = Color.White.copy(alpha = 0.5f),
                                        fontSize = 7.sp,
                                        fontWeight = FontWeight.SemiBold,
                                        letterSpacing = 1.sp
                                    )
                                }
                            }
                        }
                        // IMDb: logo + score (display-only)
                        movie.imdbRating?.toFloatOrNull()?.let { rating ->
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Image(
                                    painter = painterResource(id = R.drawable.logo_imdb),
                                    contentDescription = "IMDb",
                                    modifier = Modifier.height(20.dp).padding(end = 8.dp),
                                    contentScale = ContentScale.Fit
                                )
                                Text(
                                    text = "${"%.1f".format(rating)}",
                                    color = Color(0xFFF5C518),
                                    fontWeight = FontWeight.ExtraBold,
                                    fontSize = 18.sp
                                )
                            }
                        }
                        // Letterboxd: logo + numeric score (display-only, matches IMDb pattern)
                        lbRating?.let { score ->
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Image(
                                    painter = painterResource(id = R.drawable.logo_letterboxd),
                                    contentDescription = "Letterboxd",
                                    modifier = Modifier.height(24.dp).padding(end = 8.dp),
                                    contentScale = ContentScale.Fit,
                                    colorFilter = ColorFilter.tint(Color(0xFF00E054))
                                )
                                Text(
                                    text = "%.1f".format(score),
                                    color = Color(0xFF00E054),
                                    fontWeight = FontWeight.ExtraBold,
                                    fontSize = 18.sp
                                )
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
