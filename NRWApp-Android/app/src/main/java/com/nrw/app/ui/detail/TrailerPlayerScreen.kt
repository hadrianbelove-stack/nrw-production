package com.nrw.app.ui.detail

import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.focusable
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import com.nrw.app.data.Movie
import com.nrw.app.ui.theme.Primary
import com.nrw.app.ui.theme.TextMuted
import com.nrw.app.util.DeepLinkHelper

/**
 * Find the next movie with a trailer in the given direction, wrapping around.
 * Returns -1 if no other movie has a trailer.
 */
private fun findNextTrailerIndex(movieList: List<Movie>, fromIndex: Int, direction: Int): Int {
    val count = movieList.size
    if (count == 0) return -1
    var idx = fromIndex
    repeat(count - 1) {
        idx = ((idx + direction) % count + count) % count
        val m = movieList[idx]
        val url = m.links?.trailerHosted ?: m.links?.trailer
        if (url != null) return idx
    }
    return -1
}

/**
 * Fullscreen trailer player overlay with D-pad prev/next navigation.
 * LEFT/RIGHT = prev/next trailer, BACK = close and return to detail screen.
 *
 * Trailers are self-hosted MP4s on Backblaze B2 (trailerHosted field), played
 * via Mp4Player. YouTube WebView embed is fallback only for movies not yet
 * downloaded. See docs/features/TRAILER_HOSTING.md
 */
@Composable
fun TrailerPlayerOverlay(
    movieList: List<Movie>,
    initialIndex: Int,
    onClose: (lastIndex: Int) -> Unit
) {
    var currentIndex by remember { mutableIntStateOf(initialIndex) }
    val currentMovie = movieList.getOrNull(currentIndex) ?: return
    val trailerUrl = currentMovie.links?.trailerHosted ?: currentMovie.links?.trailer ?: return
    val focusRequester = remember { FocusRequester() }
    val context = LocalContext.current

    val isYouTube = trailerUrl.contains("youtube") || trailerUrl.contains("youtu.be")
    val youtubeId = if (isYouTube) DeepLinkHelper.extractYouTubeId(trailerUrl) else null

    // Request focus for key handling
    LaunchedEffect(Unit) {
        focusRequester.requestFocus()
    }

    BackHandler { onClose(currentIndex) }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black)
            .focusRequester(focusRequester)
            .focusable()
            .onKeyEvent { event ->
                if (event.type == KeyEventType.KeyDown) {
                    when (event.key) {
                        Key.DirectionLeft -> {
                            val prev = findNextTrailerIndex(movieList, currentIndex, -1)
                            if (prev >= 0) currentIndex = prev
                            true
                        }
                        Key.DirectionRight -> {
                            val next = findNextTrailerIndex(movieList, currentIndex, 1)
                            if (next >= 0) currentIndex = next
                            true
                        }
                        else -> false
                    }
                } else false
            }
    ) {
        // Video player
        if (youtubeId != null) {
            YouTubeEmbed(videoId = youtubeId, key = currentIndex)
        } else {
            Mp4Player(
                url = trailerUrl,
                key = currentIndex,
                // When a trailer finishes, roll to the next one (continuous reel);
                // close the player only if this was the last remaining trailer.
                onEnded = {
                    val next = findNextTrailerIndex(movieList, currentIndex, 1)
                    if (next >= 0) currentIndex = next else onClose(currentIndex)
                }
            )
        }

        // Title overlay
        Text(
            text = currentMovie.displayTitle ?: currentMovie.title ?: "",
            color = Color.White,
            fontSize = 28.sp,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier
                .align(Alignment.TopStart)
                .padding(start = 60.dp, top = 40.dp)
        )

        // Navigation arrows
        if (findNextTrailerIndex(movieList, currentIndex, -1) >= 0) {
            Text(
                text = "‹",
                color = Primary.copy(alpha = 0.5f),
                fontSize = 72.sp,
                fontWeight = FontWeight.Light,
                modifier = Modifier
                    .align(Alignment.CenterStart)
                    .padding(start = 16.dp)
            )
        }
        if (findNextTrailerIndex(movieList, currentIndex, 1) >= 0) {
            Text(
                text = "›",
                color = Primary.copy(alpha = 0.5f),
                fontSize = 72.sp,
                fontWeight = FontWeight.Light,
                modifier = Modifier
                    .align(Alignment.CenterEnd)
                    .padding(end = 16.dp)
            )
        }

        // Hint
        Text(
            text = "◀ ▶ Navigate trailers  •  Back to return",
            color = TextMuted,
            fontSize = 16.sp,
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(bottom = 30.dp)
        )
    }
}

/**
 * ExoPlayer-based MP4 video player
 */
@Composable
private fun Mp4Player(url: String, key: Int, onEnded: () -> Unit) {
    val context = LocalContext.current
    val exoPlayer = remember(key) {
        ExoPlayer.Builder(context).build().apply {
            setMediaItem(MediaItem.fromUri(url))
            prepare()
            playWhenReady = true
        }
    }

    DisposableEffect(key) {
        val listener = object : Player.Listener {
            override fun onPlaybackStateChanged(playbackState: Int) {
                if (playbackState == Player.STATE_ENDED) onEnded()
            }
        }
        exoPlayer.addListener(listener)
        onDispose {
            exoPlayer.removeListener(listener)
            exoPlayer.release()
        }
    }

    AndroidView(
        factory = { ctx ->
            PlayerView(ctx).apply {
                player = exoPlayer
                useController = false
            }
        },
        update = { view ->
            view.player = exoPlayer
        },
        modifier = Modifier.fillMaxSize()
    )
}

/**
 * WebView-based YouTube embed player
 */
@Composable
private fun YouTubeEmbed(videoId: String, key: Int) {
    val html = remember(videoId) {
        """
        <html><head><meta name="viewport" content="width=device-width,initial-scale=1">
        <style>*{margin:0;padding:0;background:#000}iframe{width:100vw;height:100vh}</style></head>
        <body><iframe src="https://www.youtube.com/embed/$videoId?autoplay=1&controls=1&rel=0&modestbranding=1"
          frameborder="0" allow="autoplay;encrypted-media" allowfullscreen></iframe></body></html>
        """.trimIndent()
    }

    AndroidView(
        factory = { ctx ->
            WebView(ctx).apply {
                settings.javaScriptEnabled = true
                settings.mediaPlaybackRequiresUserGesture = false
                webChromeClient = WebChromeClient()
                webViewClient = WebViewClient()
                loadData(html, "text/html", "utf-8")
            }
        },
        update = { view ->
            view.loadData(html, "text/html", "utf-8")
        },
        modifier = Modifier.fillMaxSize()
    )
}
