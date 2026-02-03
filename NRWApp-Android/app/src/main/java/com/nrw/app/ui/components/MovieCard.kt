package com.nrw.app.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.material3.Text
import androidx.tv.material3.Border
import androidx.tv.material3.Card
import androidx.tv.material3.CardDefaults
import androidx.tv.material3.ClickableSurfaceDefaults
import androidx.tv.material3.ExperimentalTvMaterial3Api
import androidx.tv.material3.Surface
import coil.compose.AsyncImage
import com.nrw.app.data.Movie
import com.nrw.app.data.getDirector
import com.nrw.app.data.getPosterUrl
import com.nrw.app.ui.theme.Background
import com.nrw.app.ui.theme.BackgroundSecondary
import com.nrw.app.ui.theme.Primary
import com.nrw.app.ui.theme.StaffPickRed
import com.nrw.app.ui.theme.TextPrimary
import com.nrw.app.ui.theme.TextSecondary

// Card dimensions matching tvOS app (scaled for Android TV)
val CARD_WIDTH = 160.dp
private val POSTER_ASPECT_RATIO = 2f / 3f  // Standard movie poster ratio
private val FocusCyan = Color(0xFF00FFCC)

// Streaming service colors
private val StreamingColors = mapOf(
    "netflix" to Color(0xFFE50914),
    "disney_plus" to Color(0xFF113CCF),
    "max" to Color(0xFFB537F2),
    "hbo_max" to Color(0xFFB537F2),
    "prime" to Color(0xFF00A8E1),
    "amazon" to Color(0xFF00A8E1),
    "hulu" to Color(0xFF1CE783),
    "peacock" to Color(0xFF000000),
    "paramount_plus" to Color(0xFF0064FF),
    "apple_tv" to Color(0xFF000000),
    "mubi" to Color(0xFFDA2128),
    "shudder" to Color(0xFFE31B23),
    "criterion" to Color(0xFF000000)
)

/**
 * Movie poster card component for TV grid
 * Matches tvOS design with streaming badge and focus states
 */
@OptIn(ExperimentalTvMaterial3Api::class)
@Composable
fun MovieCard(
    movie: Movie,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    var isFocused by remember { mutableStateOf(false) }
    val isStaffPick = movie.featured == true || movie.categories?.isStaffPick == true

    Column(
        modifier = modifier.width(CARD_WIDTH),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        // Poster card with optional staff pick border
        Card(
            onClick = onClick,
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(POSTER_ASPECT_RATIO)
                .onFocusChanged { isFocused = it.isFocused },
            shape = CardDefaults.shape(RoundedCornerShape(12.dp)),
            colors = CardDefaults.colors(
                containerColor = BackgroundSecondary,
                focusedContainerColor = BackgroundSecondary
            ),
            border = CardDefaults.border(
                border = if (isStaffPick) {
                    Border(
                        border = BorderStroke(3.dp, StaffPickRed),
                        shape = RoundedCornerShape(12.dp)
                    )
                } else {
                    Border.None
                },
                focusedBorder = Border(
                    border = BorderStroke(4.dp, FocusCyan),
                    shape = RoundedCornerShape(12.dp)
                )
            ),
            scale = CardDefaults.scale(
                focusedScale = 1.08f
            ),
            glow = CardDefaults.glow(
                focusedGlow = androidx.tv.material3.Glow(
                    elevationColor = Primary.copy(alpha = 0.5f),
                    elevation = 20.dp
                )
            )
        ) {
            Box(modifier = Modifier.fillMaxSize()) {
                AsyncImage(
                    model = movie.getPosterUrl(),
                    contentDescription = movie.title,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier
                        .fillMaxSize()
                        .clip(RoundedCornerShape(12.dp))
                )

                // Streaming service badge (top right)
                movie.watchLinks?.streaming?.let { streaming ->
                    streaming.service?.let { serviceName ->
                        StreamingBadge(
                            serviceName = serviceName,
                            modifier = Modifier
                                .align(Alignment.TopEnd)
                                .padding(8.dp)
                        )
                    }
                }

                // Staff pick strip at bottom (like tvOS)
                if (isStaffPick) {
                    Box(
                        modifier = Modifier
                            .align(Alignment.BottomCenter)
                            .fillMaxWidth()
                            .background(StaffPickRed)
                            .padding(vertical = 4.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = "STAFF PICK",
                            color = TextPrimary,
                            fontSize = 10.sp,
                            fontWeight = FontWeight.ExtraBold,
                            letterSpacing = 1.sp
                        )
                    }
                }

                // RT Score badge (bottom right, above staff pick if present)
                movie.rtScore?.let { scoreStr ->
                    val score = scoreStr.replace("%", "").trim().toIntOrNull()
                    if (score != null) {
                        RtBadge(
                            score = score,
                            modifier = Modifier
                                .align(Alignment.BottomEnd)
                                .padding(
                                    end = 8.dp,
                                    bottom = if (isStaffPick) 28.dp else 8.dp
                                )
                        )
                    }
                }
            }
        }

        // Movie info below card (matching website)
        Spacer(modifier = Modifier.height(6.dp))

        // Title
        Text(
            text = movie.title,
            color = TextPrimary,
            fontSize = 13.sp,
            fontWeight = FontWeight.Bold,
            textAlign = TextAlign.Center,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
            lineHeight = 16.sp,
            modifier = Modifier.fillMaxWidth()
        )

        // Director (in accent color like website)
        movie.getDirector()?.let { director ->
            Spacer(modifier = Modifier.height(2.dp))
            Text(
                text = director,
                color = Primary,
                fontSize = 11.sp,
                fontWeight = FontWeight.Medium,
                textAlign = TextAlign.Center,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.fillMaxWidth()
            )
        }
    }
}

@Composable
private fun StreamingBadge(
    serviceName: String,
    modifier: Modifier = Modifier
) {
    val backgroundColor = StreamingColors[serviceName.lowercase()] ?: Color(0xFF333333)
    val displayName = when (serviceName.lowercase()) {
        "netflix" -> "NETFLIX"
        "disney_plus" -> "DISNEY+"
        "max", "hbo_max" -> "MAX"
        "prime", "amazon" -> "PRIME"
        "hulu" -> "HULU"
        "peacock" -> "PEACOCK"
        "paramount_plus" -> "P+"
        "apple_tv" -> "APPLE"
        "mubi" -> "MUBI"
        "shudder" -> "SHUDDER"
        "criterion" -> "CRITERION"
        else -> serviceName.uppercase().take(6)
    }

    Box(
        modifier = modifier
            .clip(RoundedCornerShape(8.dp))
            .background(backgroundColor)
            .padding(horizontal = 6.dp, vertical = 3.dp)
    ) {
        Text(
            text = displayName,
            color = TextPrimary,
            fontSize = 9.sp,
            fontWeight = FontWeight.Bold,
            letterSpacing = 0.5.sp
        )
    }
}

@Composable
private fun RtBadge(
    score: Int,
    modifier: Modifier = Modifier
) {
    val isFresh = score >= 60
    val backgroundColor = if (isFresh) Color(0xFF2ECC71) else Color(0xFFE74C3C)

    Box(
        modifier = modifier
            .clip(RoundedCornerShape(4.dp))
            .background(backgroundColor)
            .padding(horizontal = 6.dp, vertical = 3.dp)
    ) {
        Text(
            text = "$score%",
            color = TextPrimary,
            fontSize = 11.sp,
            fontWeight = FontWeight.Bold
        )
    }
}

/**
 * Date divider card matching website/tvOS design
 */
@Composable
fun DateDividerCard(
    dateString: String,
    modifier: Modifier = Modifier
) {
    val parts = dateString.split("-")
    val month = parts.getOrNull(1)?.toIntOrNull()?.let { getMonthName(it) } ?: ""
    val day = parts.getOrNull(2) ?: ""
    val dayOfWeek = getDayOfWeek(dateString)

    Box(
        modifier = modifier
            .width(CARD_WIDTH)
            .aspectRatio(POSTER_ASPECT_RATIO)
            .clip(RoundedCornerShape(12.dp))
            .background(
                Brush.linearGradient(
                    colors = listOf(Background, BackgroundSecondary)
                )
            )
            .border(2.dp, Primary, RoundedCornerShape(12.dp)),
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            // Day of week (3-letter abbrev)
            Text(
                text = dayOfWeek.take(3),
                color = TextSecondary,
                fontSize = 12.sp,
                letterSpacing = 2.sp
            )

            // Day number (large)
            Text(
                text = day.trimStart('0'),
                color = Primary,
                fontSize = 48.sp,
                fontWeight = FontWeight.Bold,
                lineHeight = 52.sp
            )

            // Month
            Text(
                text = month,
                color = Primary,
                fontSize = 18.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 3.sp
            )
        }
    }
}

/**
 * NEW TRAILERS card - links to YouTube playlist
 */
@OptIn(ExperimentalTvMaterial3Api::class)
@Composable
fun TrailersCard(
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    var isFocused by remember { mutableStateOf(false) }

    Surface(
        onClick = onClick,
        modifier = modifier
            .width(CARD_WIDTH)
            .aspectRatio(POSTER_ASPECT_RATIO)
            .onFocusChanged { isFocused = it.isFocused },
        shape = ClickableSurfaceDefaults.shape(RoundedCornerShape(12.dp)),
        colors = ClickableSurfaceDefaults.colors(
            containerColor = BackgroundSecondary,
            focusedContainerColor = BackgroundSecondary
        ),
        border = ClickableSurfaceDefaults.border(
            border = BorderStroke(2.dp, Primary),
            focusedBorder = BorderStroke(4.dp, FocusCyan)
        ),
        scale = ClickableSurfaceDefaults.scale(
            focusedScale = 1.08f
        ),
        glow = ClickableSurfaceDefaults.glow(
            focusedGlow = androidx.tv.material3.Glow(
                elevationColor = Primary.copy(alpha = 0.4f),
                elevation = 20.dp
            )
        )
    ) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(
                    Brush.linearGradient(
                        colors = listOf(Background, BackgroundSecondary)
                    )
                ),
            contentAlignment = Alignment.Center
        ) {
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center
            ) {
                // Title text
                Text(
                    text = "THIS WEEK'S",
                    color = TextPrimary,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 1.sp
                )
                Text(
                    text = "TRAILERS",
                    color = TextPrimary,
                    fontSize = 20.sp,
                    fontWeight = FontWeight.ExtraBold,
                    letterSpacing = 2.sp
                )

                Spacer(modifier = Modifier.height(12.dp))

                // YouTube play button
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(10.dp))
                        .background(Color(0xFFFF0000))
                        .padding(horizontal = 20.dp, vertical = 10.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = "▶",
                        color = TextPrimary,
                        fontSize = 18.sp
                    )
                }
            }
        }
    }
}

private fun getMonthName(month: Int): String {
    return when (month) {
        1 -> "JAN"
        2 -> "FEB"
        3 -> "MAR"
        4 -> "APR"
        5 -> "MAY"
        6 -> "JUN"
        7 -> "JUL"
        8 -> "AUG"
        9 -> "SEP"
        10 -> "OCT"
        11 -> "NOV"
        12 -> "DEC"
        else -> ""
    }
}

private fun getDayOfWeek(dateString: String): String {
    return try {
        val sdf = java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US)
        val date = sdf.parse(dateString)
        val dayFormat = java.text.SimpleDateFormat("EEEE", java.util.Locale.US)
        dayFormat.format(date!!).uppercase()
    } catch (e: Exception) {
        ""
    }
}
