package com.nrw.app.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.material3.Text
import androidx.tv.material3.Border
import androidx.tv.material3.Button
import androidx.tv.material3.ButtonDefaults
import androidx.tv.material3.ExperimentalTvMaterial3Api
import com.nrw.app.data.WatchOption
import com.nrw.app.data.WatchType
import com.nrw.app.ui.theme.AmazonOrange
import com.nrw.app.ui.theme.AppleGray
import com.nrw.app.ui.theme.Background
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

/**
 * Watch button for streaming services
 */
@OptIn(ExperimentalTvMaterial3Api::class)
@Composable
fun WatchButton(
    option: WatchOption,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    val backgroundColor = getServiceColor(option.service)

    Button(
        onClick = onClick,
        modifier = modifier,
        colors = ButtonDefaults.colors(
            containerColor = backgroundColor,
            contentColor = TextPrimary,
            focusedContainerColor = backgroundColor,
            focusedContentColor = TextPrimary
        ),
        shape = ButtonDefaults.shape(RoundedCornerShape(8.dp)),
        border = ButtonDefaults.border(
            focusedBorder = Border(
                border = BorderStroke(3.dp, Primary),
                shape = RoundedCornerShape(8.dp)
            )
        ),
        scale = ButtonDefaults.scale(focusedScale = 1.1f),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp)
    ) {
        Text(
            text = option.label,
            fontWeight = FontWeight.SemiBold,
            fontSize = 14.sp
        )
    }
}

/**
 * Info button for trailer, RT, etc.
 */
@OptIn(ExperimentalTvMaterial3Api::class)
@Composable
fun InfoButton(
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    Button(
        onClick = onClick,
        modifier = modifier,
        colors = ButtonDefaults.colors(
            containerColor = BackgroundSecondary,
            contentColor = TextPrimary,
            focusedContainerColor = BackgroundSecondary,
            focusedContentColor = TextPrimary
        ),
        shape = ButtonDefaults.shape(RoundedCornerShape(8.dp)),
        border = ButtonDefaults.border(
            border = Border(
                border = BorderStroke(1.dp, Primary.copy(alpha = 0.5f)),
                shape = RoundedCornerShape(8.dp)
            ),
            focusedBorder = Border(
                border = BorderStroke(3.dp, Primary),
                shape = RoundedCornerShape(8.dp)
            )
        ),
        scale = ButtonDefaults.scale(focusedScale = 1.1f),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp)
    ) {
        Text(
            text = label,
            fontWeight = FontWeight.Medium,
            fontSize = 14.sp
        )
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
