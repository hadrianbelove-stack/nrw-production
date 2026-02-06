package com.nrw.app.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.material3.Text
import com.nrw.app.R
import androidx.tv.material3.Border
import androidx.tv.material3.Button
import androidx.tv.material3.ButtonDefaults
import androidx.tv.material3.ExperimentalTvMaterial3Api
import com.nrw.app.data.WatchOption
import com.nrw.app.ui.theme.AmazonOrange
import com.nrw.app.ui.theme.AppleGray
import com.nrw.app.ui.theme.BackgroundSecondary
import com.nrw.app.ui.theme.DisneyBlue
import com.nrw.app.ui.theme.HuluGreen
import com.nrw.app.ui.theme.MaxPurple
import com.nrw.app.ui.theme.NetflixRed
import com.nrw.app.ui.theme.ParamountBlue
import com.nrw.app.ui.theme.PeacockBlue
import com.nrw.app.ui.theme.PlexYellow
import com.nrw.app.ui.theme.Primary
import com.nrw.app.ui.theme.TextPrimary
import com.nrw.app.ui.theme.TrailerRed

/**
 * Unified action button for TV - used for Watch options AND Trailer
 * All buttons have same visual weight and sizing
 * compact = true for Option E layout (smaller buttons)
 */
@OptIn(ExperimentalTvMaterial3Api::class)
@Composable
fun ActionButton(
    label: String,
    color: Color,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    compact: Boolean = false
) {
    val minWidth = if (compact) 100.dp else 200.dp
    val minHeight = if (compact) 36.dp else 60.dp
    val horizontalPadding = if (compact) 16.dp else 40.dp
    val verticalPadding = if (compact) 10.dp else 24.dp
    val fontSize = if (compact) 12.sp else 22.sp
    val cornerRadius = if (compact) 8.dp else 12.dp
    val borderWidth = if (compact) 3.dp else 4.dp

    Button(
        onClick = onClick,
        modifier = modifier.defaultMinSize(minWidth = minWidth, minHeight = minHeight),
        colors = ButtonDefaults.colors(
            containerColor = color,
            contentColor = TextPrimary,
            focusedContainerColor = color,
            focusedContentColor = TextPrimary
        ),
        shape = ButtonDefaults.shape(RoundedCornerShape(cornerRadius)),
        border = ButtonDefaults.border(
            focusedBorder = Border(
                border = BorderStroke(borderWidth, TextPrimary),
                shape = RoundedCornerShape(cornerRadius)
            )
        ),
        scale = ButtonDefaults.scale(focusedScale = 1.1f),
        contentPadding = PaddingValues(horizontal = horizontalPadding, vertical = verticalPadding)
    ) {
        Text(
            text = label.uppercase(),
            fontWeight = FontWeight.Bold,
            fontSize = fontSize,
            letterSpacing = if (compact) 0.5.sp else 1.sp
        )
    }
}

/**
 * Watch button - wraps ActionButton with service-specific color
 * Uses logo images for Amazon/Apple, text for others
 */
@Composable
fun WatchButton(
    option: WatchOption,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    compact: Boolean = false
) {
    val logoResId = getServiceLogoResId(option.service)

    if (logoResId != null) {
        // Logo-based button for Amazon/Apple
        LogoButton(
            logoResId = logoResId,
            color = getServiceColor(option.service),
            onClick = onClick,
            modifier = modifier,
            compact = compact
        )
    } else {
        // Text-based button for other services
        ActionButton(
            label = getSimplifiedLabel(option.service),
            color = getServiceColor(option.service),
            onClick = onClick,
            modifier = modifier,
            compact = compact
        )
    }
}

/**
 * Logo-based action button for services with brand logos
 */
@OptIn(ExperimentalTvMaterial3Api::class)
@Composable
fun LogoButton(
    logoResId: Int,
    color: Color,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    compact: Boolean = false
) {
    val minWidth = if (compact) 100.dp else 200.dp
    val minHeight = if (compact) 36.dp else 60.dp
    val horizontalPadding = if (compact) 16.dp else 40.dp
    val verticalPadding = if (compact) 10.dp else 24.dp
    val cornerRadius = if (compact) 8.dp else 12.dp
    val borderWidth = if (compact) 3.dp else 4.dp
    val logoHeight = if (compact) 16.dp else 28.dp

    Button(
        onClick = onClick,
        modifier = modifier.defaultMinSize(minWidth = minWidth, minHeight = minHeight),
        colors = ButtonDefaults.colors(
            containerColor = color,
            contentColor = TextPrimary,
            focusedContainerColor = color,
            focusedContentColor = TextPrimary
        ),
        shape = ButtonDefaults.shape(RoundedCornerShape(cornerRadius)),
        border = ButtonDefaults.border(
            focusedBorder = Border(
                border = BorderStroke(borderWidth, TextPrimary),
                shape = RoundedCornerShape(cornerRadius)
            )
        ),
        scale = ButtonDefaults.scale(focusedScale = 1.1f),
        contentPadding = PaddingValues(horizontal = horizontalPadding, vertical = verticalPadding)
    ) {
        Image(
            painter = painterResource(id = logoResId),
            contentDescription = "Service logo",
            modifier = Modifier.height(logoHeight),
            contentScale = ContentScale.FillHeight
        )
    }
}

/**
 * Get drawable resource ID for service logo, or null if no logo
 */
private fun getServiceLogoResId(service: String): Int? {
    return when (service.lowercase()) {
        "amazon", "amazon_video", "prime_video" -> R.drawable.logo_amazon
        "apple_tv", "itunes" -> R.drawable.logo_apple
        else -> null
    }
}

/**
 * Trailer button - same style as Watch buttons
 */
@Composable
fun TrailerButton(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    compact: Boolean = false
) {
    ActionButton(
        label = "▶ Trailer",
        color = TrailerRed,
        onClick = onClick,
        modifier = modifier,
        compact = compact
    )
}

/**
 * Get simplified label (just service name, no "Rent on" prefix)
 */
private fun getSimplifiedLabel(service: String): String {
    return when (service.lowercase()) {
        "plex" -> "Plex"
        "amazon", "amazon_video", "prime_video" -> "Amazon"
        "apple_tv" -> "Apple TV"
        "netflix" -> "Netflix"
        "hulu" -> "Hulu"
        "max", "hbo_max" -> "Max"
        "disney_plus" -> "Disney+"
        "peacock" -> "Peacock"
        "paramount_plus" -> "Paramount+"
        else -> service.replaceFirstChar { it.uppercase() }
    }
}

/**
 * Get service-specific color
 */
private fun getServiceColor(service: String): Color {
    return when (service.lowercase()) {
        "plex" -> PlexYellow
        "amazon", "amazon_video", "prime_video" -> AmazonOrange
        "apple_tv" -> AppleGray
        "netflix" -> NetflixRed
        "hulu" -> HuluGreen
        "max", "hbo_max" -> MaxPurple
        "disney_plus" -> DisneyBlue
        "peacock" -> PeacockBlue
        "paramount_plus" -> ParamountBlue
        else -> BackgroundSecondary
    }
}

/**
 * @deprecated Use ActionButton or WatchButton instead
 * Kept for backwards compatibility during transition
 */
@OptIn(ExperimentalTvMaterial3Api::class)
@Composable
fun InfoButton(
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    // For trailer, use TrailerButton style
    if (label.lowercase().contains("trailer")) {
        TrailerButton(onClick = onClick, modifier = modifier)
    } else {
        // Other info buttons (shouldn't be used on TV apps)
        ActionButton(
            label = label,
            color = Primary,
            onClick = onClick,
            modifier = modifier
        )
    }
}
