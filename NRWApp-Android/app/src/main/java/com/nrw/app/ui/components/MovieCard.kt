package com.nrw.app.ui.components

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import kotlin.math.cos
import kotlin.math.sin
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
import com.nrw.app.util.formatShortDate
import com.nrw.app.data.getDirector
import com.nrw.app.data.getPosterUrl
import com.nrw.app.ui.theme.Background
import com.nrw.app.ui.theme.BackgroundSecondary
import com.nrw.app.ui.theme.Primary
import com.nrw.app.ui.theme.ScreeningGold
import com.nrw.app.ui.theme.StaffPickRed
import com.nrw.app.ui.theme.TextPrimary
import com.nrw.app.ui.theme.TextSecondary

// Card dimensions - sized to fit 8 cards per row like tvOS
val CARD_WIDTH = 100.dp
private val POSTER_ASPECT_RATIO = 2f / 3f  // Standard movie poster ratio
private val FocusCyan = Color(0xFF00FFCC)

// 3-letter Olympic country codes (UK stays UK)
private val CountryShortNames = mapOf(
    // Canonical 3-letter map (matches assets/shared-config.js). UK/USA kept; maps
    // both full names and 2-letter ISO codes. Keep in sync with the web map.
    "united states of america" to "USA", "united states" to "USA", "usa" to "USA", "us" to "USA",
    "united kingdom" to "UK", "great britain" to "UK", "gb" to "UK", "uk" to "UK",
    "india" to "IND", "in" to "IND",
    "canada" to "CAN", "ca" to "CAN",
    "france" to "FRA", "fr" to "FRA",
    "mexico" to "MEX", "mx" to "MEX",
    "australia" to "AUS", "au" to "AUS",
    "germany" to "GER", "de" to "GER",
    "italy" to "ITA", "it" to "ITA",
    "japan" to "JPN", "jp" to "JPN",
    "south korea" to "KOR", "kr" to "KOR",
    "belgium" to "BEL", "be" to "BEL",
    "spain" to "ESP", "es" to "ESP",
    "indonesia" to "IDN", "id" to "IDN",
    "brazil" to "BRA", "br" to "BRA",
    "argentina" to "ARG", "ar" to "ARG",
    "thailand" to "THA", "th" to "THA",
    "new zealand" to "NZL", "nz" to "NZL",
    "austria" to "AUT", "at" to "AUT",
    "poland" to "POL", "pl" to "POL",
    "china" to "CHN", "cn" to "CHN",
    "taiwan" to "TWN", "tw" to "TWN",
    "denmark" to "DEN", "dk" to "DEN",
    "netherlands" to "NED", "nl" to "NED",
    "ireland" to "IRL", "ie" to "IRL",
    "turkey" to "TUR", "tr" to "TUR",
    "nigeria" to "NGA", "ng" to "NGA",
    "philippines" to "PHI", "ph" to "PHI",
    "finland" to "FIN", "fi" to "FIN",
    "colombia" to "COL", "co" to "COL",
    "sweden" to "SWE", "se" to "SWE",
    "russia" to "RUS", "ru" to "RUS",
    "hong kong" to "HKG", "hk" to "HKG",
    "ukraine" to "UKR", "ua" to "UKR",
    "greece" to "GRE", "gr" to "GRE",
    "israel" to "ISR", "il" to "ISR",
    "georgia" to "GEO", "ge" to "GEO",
    "saudi arabia" to "KSA", "sa" to "KSA",
    "czech republic" to "CZE", "cz" to "CZE",
    "cuba" to "CUB", "cu" to "CUB",
    "switzerland" to "SUI", "ch" to "SUI",
    "south africa" to "RSA", "za" to "RSA",
    "venezuela" to "VEN", "ve" to "VEN",
    "croatia" to "CRO", "hr" to "CRO",
    "guatemala" to "GUA", "gt" to "GUA",
    "kenya" to "KEN", "ke" to "KEN",
    "iceland" to "ISL", "is" to "ISL",
    "bulgaria" to "BUL", "bg" to "BUL",
    "norway" to "NOR", "no" to "NOR",
    "iraq" to "IRQ", "iq" to "IRQ",
    "hungary" to "HUN", "hu" to "HUN",
    "nepal" to "NEP", "np" to "NEP",
    "slovenia" to "SLO", "si" to "SLO",
    "cambodia" to "CAM", "kh" to "CAM",
    "morocco" to "MAR", "ma" to "MAR",
    "chile" to "CHL", "cl" to "CHL",
    "singapore" to "SGP", "sg" to "SGP",
    "armenia" to "ARM", "am" to "ARM",
    "united arab emirates" to "UAE", "ae" to "UAE",
    "palestinian territory" to "PLE", "palestine" to "PLE", "ps" to "PLE",
    "bosnia and herzegovina" to "BIH", "ba" to "BIH",
    "unknown" to "—"
)

private fun formatCountry(country: String?): String? {
    if (country == null) return null
    val shortened = CountryShortNames[country.lowercase()]
    if (shortened != null) return shortened
    // Unmapped: fall back to first 3 letters, uppercased (stay 3-letter).
    val letters = country.filter { it.isLetter() }
    return if (letters.isEmpty()) country else letters.take(3).uppercase()
}

// Streaming service colors - source of truth: assets/service-colors.json
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
    "shudder" to Color(0xFF8B0000),
    "criterion" to Color(0xFF000000),
    "tubi" to Color(0xFFFA382F),
    "fawesome" to Color(0xFF5B8DEF),
    "pluto" to Color(0xFF00B4E4)
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
    val isStaffPick = movie.featured == true || movie.filters?.isStaffPick == true
    val isScreening = movie.filters?.isVirtualScreening == true

    // Animated gradient for focus state (Option E - rotating gradient border)
    val infiniteTransition = rememberInfiniteTransition(label = "gradientRotation")
    val gradientAngle by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 2500, easing = LinearEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "gradientAngle"
    )

    // Create rotating gradient brush for focus border
    val angleRad = Math.toRadians(gradientAngle.toDouble())
    val radius = 200f
    val focusGradientBrush = Brush.linearGradient(
        colors = listOf(
            Primary,           // Teal #00D4AA
            FocusCyan,         // Cyan #00FFCC
            Color.White,       // White
            Primary            // Back to teal
        ),
        start = Offset(
            (radius + radius * cos(angleRad)).toFloat(),
            (radius + radius * sin(angleRad)).toFloat()
        ),
        end = Offset(
            (radius + radius * cos(angleRad + Math.PI)).toFloat(),
            (radius + radius * sin(angleRad + Math.PI)).toFloat()
        )
    )

    Column(
        modifier = modifier.fillMaxWidth(),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        // Poster card with optional staff pick border
        Card(
            onClick = onClick,
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(POSTER_ASPECT_RATIO)
                .onFocusChanged { isFocused = it.isFocused },
            shape = CardDefaults.shape(RoundedCornerShape(8.dp)),
            colors = CardDefaults.colors(
                containerColor = BackgroundSecondary,
                focusedContainerColor = BackgroundSecondary
            ),
            border = CardDefaults.border(
                border = if (isStaffPick) {
                    Border(
                        border = BorderStroke(2.dp, StaffPickRed),
                        shape = RoundedCornerShape(8.dp)
                    )
                } else if (isScreening) {
                    Border(
                        border = BorderStroke(2.dp, ScreeningGold),
                        shape = RoundedCornerShape(8.dp)
                    )
                } else {
                    Border.None
                },
                focusedBorder = Border(
                    border = BorderStroke(4.dp, focusGradientBrush),
                    shape = RoundedCornerShape(8.dp)
                )
            ),
            scale = CardDefaults.scale(
                focusedScale = 1.08f
            ),
            glow = CardDefaults.glow(
                focusedGlow = androidx.tv.material3.Glow(
                    elevationColor = Primary.copy(alpha = 0.6f),
                    elevation = 24.dp
                )
            )
        ) {
            Box(modifier = Modifier.fillMaxSize()) {
                AsyncImage(
                    model = movie.getPosterUrl(),
                    contentDescription = movie.displayTitle ?: movie.title,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier
                        .fillMaxSize()
                        .clip(RoundedCornerShape(8.dp))
                )

                // Streaming service bar badge (full-width top bar)
                movie.watchLinks?.streaming
                    ?.firstOrNull { !it.service.isNullOrBlank() }
                    ?.service?.let { serviceName ->
                        StreamingBadge(
                            serviceName = serviceName,
                            modifier = Modifier
                                .align(Alignment.TopCenter)
                                .fillMaxWidth()
                        )
                    }

                // Pre-order badge (top right) — pipeline sets isPreorder flag
                if (movie.isPreorder) {
                    val poDate = movie.digitalDate?.let { formatShortDate(it) } ?: "TBD"
                    Column(
                        modifier = Modifier
                            .align(Alignment.TopEnd)
                            .padding(4.dp)
                            .background(Color(0xFF7C3AED), RoundedCornerShape(4.dp))
                            .padding(horizontal = 4.dp, vertical = 3.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Text(
                            text = "PRE-ORDER",
                            color = Color.White,
                            fontSize = 7.sp,
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 0.5.sp
                        )
                        Text(
                            text = poDate,
                            color = Color.White,
                            fontSize = 9.sp,
                            fontWeight = FontWeight.SemiBold
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
                            .padding(vertical = 2.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = "★ NRW SELECT ★",
                            color = TextPrimary,
                            fontSize = 7.sp,
                            fontWeight = FontWeight.ExtraBold,
                            letterSpacing = 0.5.sp
                        )
                    }
                }

                // Virtual screening top banner
                if (isScreening && !isStaffPick) {
                    Box(
                        modifier = Modifier
                            .align(Alignment.TopCenter)
                            .fillMaxWidth()
                            .background(ScreeningGold.copy(alpha = 0.92f))
                            .padding(vertical = 3.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = "VIRTUAL SCREENING",
                            color = Color.Black,
                            fontSize = 6.sp,
                            fontWeight = FontWeight.ExtraBold,
                            letterSpacing = 0.8.sp
                        )
                    }
                }

                // Virtual screening festival name strip (bottom)
                if (isScreening && !isStaffPick && movie.screeningInfo?.screeningName != null) {
                    Box(
                        modifier = Modifier
                            .align(Alignment.BottomCenter)
                            .fillMaxWidth()
                            .background(ScreeningGold)
                            .padding(vertical = 3.dp, horizontal = 4.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = movie.screeningInfo!!.screeningName!!,
                            color = Color.Black,
                            fontSize = 6.sp,
                            fontWeight = FontWeight.ExtraBold,
                            letterSpacing = 0.3.sp,
                            textAlign = TextAlign.Center,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                }

                // Score badges (bottom right, above staff pick if present)
                val rtScore = movie.rtScore?.replace("%", "")?.trim()?.toIntOrNull()
                val mcScore = movie.metacriticScore?.toIntOrNull()?.takeIf { it > 0 }
                val hasScores = rtScore != null || mcScore != null || movie.imdbRating != null
                if (hasScores) {
                    Row(
                        modifier = Modifier
                            .align(Alignment.BottomEnd)
                            .padding(
                                end = 2.dp,
                                bottom = if (isStaffPick || isScreening) 22.dp else 4.dp
                            ),
                        horizontalArrangement = Arrangement.spacedBy(2.dp)
                    ) {
                        if (rtScore != null) {
                            RtBadge(score = rtScore)
                        }
                        if (mcScore != null) {
                            McBadge(score = mcScore)
                        }
                        movie.imdbRating?.let { rating ->
                            ImdbBadge(rating = rating)
                        }
                    }
                }
            }
        }

        // Movie info below card (matching website)
        Spacer(modifier = Modifier.height(4.dp))

        // Director · Genre · Country below card (matches desktop caption)
        val director = movie.getDirector()
        val genre = movie.genres?.firstOrNull()
        val countryText = formatCountry(movie.country)
        val infoText = listOfNotNull(director, genre, countryText).joinToString(" · ")
        if (infoText.isNotEmpty()) {
            Text(
                text = infoText,
                color = Primary,
                fontSize = 11.sp,
                fontWeight = FontWeight.Bold,
                textAlign = TextAlign.Center,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.fillMaxWidth()
            )
        }

        // Virtual screening days-left pill (hollow): red ≤3 days, gold "Until …", gray "Opens …"
        if (isScreening) {
            val pill = screeningDaysPill(movie.screeningInfo?.availableStart, movie.screeningInfo?.availableEnd)
            if (pill != null) {
                Spacer(modifier = Modifier.height(3.dp))
                Box(
                    modifier = Modifier
                        .align(Alignment.CenterHorizontally)
                        .border(BorderStroke(1.5.dp, pill.second), RoundedCornerShape(12.dp))
                        .padding(horizontal = 10.dp, vertical = 2.dp)
                ) {
                    Text(
                        text = pill.first,
                        color = pill.second,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.ExtraBold,
                        textAlign = TextAlign.Center
                    )
                }
            }
        }
    }
}

// Virtual screening days-left pill text + color: red ≤3 days, gold "Until <date>", gray "Opens <date>"
private fun screeningDaysPill(start: String?, end: String?): Pair<String, Color>? {
    val s = (start ?: "").take(10)
    val e = (end ?: "").take(10)
    if (s.isEmpty() && e.isEmpty()) return null
    val fmt = java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US)
    val today = fmt.format(java.util.Date())
    val red = Color(0xFFFF6B6B); val gold = Color(0xFFFFD700); val gray = Color(0xFF9A9AA5)
    fun md(iso: String): String {
        val mon = listOf("Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec")
        val p = iso.split("-")
        return "${mon[p[1].toInt() - 1]} ${p[2].toInt()}"
    }
    if (s.isNotEmpty() && s > today) return Pair("Opens ${md(s)}", gray)
    if (e.isEmpty()) return Pair("Screening live", gold)
    val daysLeft = try {
        Math.round((fmt.parse(e)!!.time - fmt.parse(today)!!.time) / 86400000.0).toInt()
    } catch (ex: Exception) { 99 }
    if (daysLeft <= 3) return Pair(if (daysLeft <= 0) "Last day" else "$daysLeft ${if (daysLeft == 1) "day" else "days"} left", red)
    return Pair("Until ${md(e)}", gold)
}

@Composable
private fun StreamingBadge(
    serviceName: String,
    modifier: Modifier = Modifier
) {
    // Strip storefront wrappers ("Shudder Amazon Channel" -> "Shudder") so we name the
    // brand, not the platform it's sold through. Then match by substring so multi-word
    // names ("Amazon Prime Video") resolve correctly.
    val cleaned = serviceName
        .replace(Regex("\\s+(Amazon|Apple TV|Roku Premium)\\s+Channel\\s*$", RegexOption.IGNORE_CASE), "")
        .trim()
        .ifEmpty { serviceName }
    val s = cleaned.lowercase()
    val (displayName, colorKey) = when {
        s.contains("netflix") -> "NETFLIX" to "netflix"
        s.contains("disney") -> "DISNEY+" to "disney_plus"
        s.contains("max") || s.contains("hbo") -> "MAX" to "max"
        s.contains("amazon") || s.contains("prime") -> "PRIME" to "prime"
        s.contains("hulu") -> "HULU" to "hulu"
        s.contains("peacock") -> "PEACOCK" to "peacock"
        s.contains("paramount") -> "P+" to "paramount_plus"
        s.contains("apple") -> "APPLE TV+" to "apple_tv"
        s.contains("mubi") -> "MUBI" to "mubi"
        s.contains("shudder") -> "SHUDDER" to "shudder"
        s.contains("criterion") -> "CRITERION" to "criterion"
        s.contains("tubi") -> "TUBI" to "tubi"
        s.contains("fawesome") -> "FAWESOME" to "fawesome"
        s.contains("pluto") -> "PLUTO TV" to "pluto"
        else -> cleaned.uppercase().take(10) to "other"
    }
    val backgroundColor = StreamingColors[colorKey] ?: Color(0xFF333333)
    val textColor = if (colorKey in listOf("hulu", "prime", "pluto")) Color.Black else TextPrimary

    Column(
        modifier = modifier
            .background(backgroundColor)
            .padding(vertical = 3.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = displayName,
            color = textColor,
            fontSize = 7.sp,
            fontWeight = FontWeight.Bold,
            letterSpacing = 0.8.sp
        )
        Text(
            text = "NOW STREAMING",
            color = textColor.copy(alpha = 0.75f),
            fontSize = 5.sp,
            fontWeight = FontWeight.Medium,
            letterSpacing = 0.5.sp
        )
    }
}

@Composable
private fun RtBadge(
    score: Int,
    modifier: Modifier = Modifier
) {
    val brandColor = Color(0xFFFF6B6B)
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(3.dp))
            .background(brandColor.copy(alpha = 0.08f))
            .border(1.dp, brandColor.copy(alpha = 0.55f), RoundedCornerShape(3.dp))
            .padding(horizontal = 3.dp, vertical = 2.dp)
    ) {
        Text(text = "RT $score%", color = brandColor, fontSize = 7.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun McBadge(
    score: Int,
    modifier: Modifier = Modifier
) {
    val brandColor = Color(0xFF7DDF64)
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(3.dp))
            .background(brandColor.copy(alpha = 0.08f))
            .border(1.dp, brandColor.copy(alpha = 0.55f), RoundedCornerShape(3.dp))
            .padding(horizontal = 3.dp, vertical = 2.dp)
    ) {
        Text(text = "MC $score", color = brandColor, fontSize = 7.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun ImdbBadge(
    rating: String,
    modifier: Modifier = Modifier
) {
    val brandColor = Color(0xFFF5C518)
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(3.dp))
            .background(brandColor.copy(alpha = 0.08f))
            .border(1.dp, brandColor.copy(alpha = 0.55f), RoundedCornerShape(3.dp))
            .padding(horizontal = 3.dp, vertical = 2.dp)
    ) {
        Text(text = "IMDb $rating", color = brandColor, fontSize = 7.sp, fontWeight = FontWeight.Bold)
    }
}

/**
 * Date row strip — full-width neon banner between date groups
 * (bright top/bottom borders, colored day + white date, centered)
 */
@Composable
fun DateRowHeader(
    dateString: String,
    stripColor: Color = Primary,
    tinted: Boolean = false,
    modifier: Modifier = Modifier
) {
    val day: String
    var rest = ""
    val color: Color
    when (dateString) {
        "PRE-ORDER" -> { day = "PRE-ORDER"; rest = "COMING SOON"; color = Color(0xFF7C3AED) }
        "FEST" -> { day = "FESTS"; rest = "AVAILABLE NOW"; color = Color(0xFFFFD700) }
        "HIGHLIGHTS" -> { day = "SELECTS"; rest = "OF NOTE"; color = Color(0xFF00D4AA) }
        "SLOP" -> { day = "SLOP"; rest = "THE CONTENT RIVER"; color = Color(0xFFFF9500) }
        else -> {
            val parts = dateString.split("-")
            val month = parts.getOrNull(1)?.toIntOrNull()?.let { getMonthName(it) } ?: ""
            val dayNum = parts.getOrNull(2)?.trimStart('0') ?: ""
            day = getDayOfWeek(dateString).take(3)
            rest = "$month $dayNum"
            color = stripColor
        }
    }

    // Section banner (SLOP / SELECTS / FESTS / PRE-ORDER) renders ~2x the date dividers
    val isSection = dateString in listOf("PRE-ORDER", "FEST", "HIGHLIGHTS", "SLOP")
    val barHeight = if (isSection) 3.dp else 2.dp
    Column(modifier = modifier.fillMaxWidth().padding(top = 8.dp, bottom = 2.dp)) {
        Box(Modifier.fillMaxWidth().height(barHeight).background(color))
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(Color(0xF508080C))
                .padding(vertical = if (isSection) 18.dp else 8.dp),
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = day,
                color = color,
                fontSize = if (isSection) 32.sp else 16.sp,
                fontWeight = FontWeight.Black,
                letterSpacing = 4.sp
            )
            if (rest.isNotEmpty()) {
                Spacer(modifier = Modifier.width(14.dp))
                Text(
                    text = rest,
                    color = Color.White,
                    fontSize = if (isSection) 32.sp else 16.sp,
                    fontWeight = FontWeight.Light,
                    letterSpacing = 4.sp
                )
            }
        }
        Box(Modifier.fillMaxWidth().height(barHeight).background(color))
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

    // Animated gradient for focus state (same as MovieCard)
    val infiniteTransition = rememberInfiniteTransition(label = "trailersGradientRotation")
    val gradientAngle by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 2500, easing = LinearEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "trailersGradientAngle"
    )

    // Create rotating gradient brush for focus border
    val angleRad = Math.toRadians(gradientAngle.toDouble())
    val radius = 200f
    val focusGradientBrush = Brush.linearGradient(
        colors = listOf(
            Primary,           // Teal #00D4AA
            FocusCyan,         // Cyan #00FFCC
            Color.White,       // White
            Primary            // Back to teal
        ),
        start = Offset(
            (radius + radius * cos(angleRad)).toFloat(),
            (radius + radius * sin(angleRad)).toFloat()
        ),
        end = Offset(
            (radius + radius * cos(angleRad + Math.PI)).toFloat(),
            (radius + radius * sin(angleRad + Math.PI)).toFloat()
        )
    )

    Surface(
        onClick = onClick,
        modifier = modifier
            .width(CARD_WIDTH)
            .aspectRatio(POSTER_ASPECT_RATIO)
            .onFocusChanged { isFocused = it.isFocused },
        shape = ClickableSurfaceDefaults.shape(RoundedCornerShape(8.dp)),
        colors = ClickableSurfaceDefaults.colors(
            containerColor = BackgroundSecondary,
            focusedContainerColor = BackgroundSecondary
        ),
        border = ClickableSurfaceDefaults.border(
            border = Border(
                border = BorderStroke(2.dp, Primary),
                shape = RoundedCornerShape(8.dp)
            ),
            focusedBorder = Border(
                border = BorderStroke(4.dp, focusGradientBrush),
                shape = RoundedCornerShape(8.dp)
            )
        ),
        scale = ClickableSurfaceDefaults.scale(
            focusedScale = 1.08f
        ),
        glow = ClickableSurfaceDefaults.glow(
            focusedGlow = androidx.tv.material3.Glow(
                elevationColor = Primary.copy(alpha = 0.6f),
                elevation = 24.dp
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
                    fontSize = 11.sp,
                    fontWeight = FontWeight.SemiBold,
                    letterSpacing = 0.5.sp
                )
                Text(
                    text = "TRAILERS",
                    color = TextPrimary,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.ExtraBold,
                    letterSpacing = 1.sp
                )

                Spacer(modifier = Modifier.height(8.dp))

                // YouTube play button
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(8.dp))
                        .background(Color(0xFFFF0000))
                        .padding(horizontal = 14.dp, vertical = 8.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = "▶",
                        color = TextPrimary,
                        fontSize = 14.sp
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
