package com.nrw.app.ui.theme

import androidx.compose.runtime.Composable
import androidx.tv.material3.ExperimentalTvMaterial3Api
import androidx.tv.material3.MaterialTheme
import androidx.tv.material3.darkColorScheme

// TV-specific dark color scheme
@OptIn(ExperimentalTvMaterial3Api::class)
private val NRWDarkColorScheme = darkColorScheme(
    primary = Primary,
    onPrimary = Background,
    primaryContainer = Primary,
    onPrimaryContainer = Background,
    secondary = TextSecondary,
    onSecondary = Background,
    background = Background,
    onBackground = TextPrimary,
    surface = BackgroundSecondary,
    onSurface = TextPrimary,
    surfaceVariant = BackgroundSecondary,
    onSurfaceVariant = TextSecondary,
    error = Red,
    onError = TextPrimary,
    border = Primary,
    borderVariant = TextMuted
)

@OptIn(ExperimentalTvMaterial3Api::class)
@Composable
fun NRWTheme(
    content: @Composable () -> Unit
) {
    MaterialTheme(
        colorScheme = NRWDarkColorScheme,
        content = content
    )
}
