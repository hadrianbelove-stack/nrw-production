package com.nrw.app.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.tv.foundation.lazy.list.TvLazyRow
import androidx.tv.foundation.lazy.list.items
import androidx.compose.material3.Text
import androidx.tv.material3.ClickableSurfaceDefaults
import androidx.tv.material3.ExperimentalTvMaterial3Api
import androidx.tv.material3.Surface
import com.nrw.app.data.FilterCategory
import com.nrw.app.ui.theme.Background
import com.nrw.app.ui.theme.Primary
import com.nrw.app.ui.theme.TextPrimary

// Website-matching colors
private val ChipBackgroundDefault = Color.White.copy(alpha = 0.1f)
private val ChipBorderDefault = Color.White.copy(alpha = 0.2f)
private val FocusCyan = Color(0xFF00FFCC)

/**
 * Horizontal row of filter chips for category selection
 * Matches website pill button design exactly
 */
@OptIn(ExperimentalTvMaterial3Api::class)
@Composable
fun FilterChips(
    activeFilters: Set<FilterCategory>,
    onFilterToggled: (FilterCategory) -> Unit,
    slopFree: Boolean = false,
    onSlopFreeToggle: () -> Unit = {},
    hideFest: Boolean = false,
    onHideFestToggle: () -> Unit = {},
    showPreorders: Boolean = false,
    onShowPreordersToggle: () -> Unit = {},
    modifier: Modifier = Modifier
) {
    TvLazyRow(
        modifier = modifier.fillMaxWidth(),
        contentPadding = PaddingValues(horizontal = 32.dp),
        horizontalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        items(FilterCategory.values().toList()) { category ->
            val isSelected = activeFilters.contains(category)

            FilterPill(
                text = category.displayName,
                isSelected = isSelected,
                onClick = { onFilterToggled(category) }
            )
        }

        item {
            // Divider
            Box(
                modifier = Modifier
                    .padding(horizontal = 4.dp)
                    .background(Color.White.copy(alpha = 0.2f))
                    .width(1.dp)
                    .padding(vertical = 4.dp),
                contentAlignment = Alignment.Center
            ) {}
        }

        item {
            MetaTogglePill(
                isActive = slopFree,
                activeLabel = "SLOP FREE",
                inactiveLabel = "WITH SLOP",
                onClick = onSlopFreeToggle
            )
        }

        item {
            MetaTogglePill(
                isActive = hideFest,
                activeLabel = "NO FEST",
                inactiveLabel = "WITH FEST",
                onClick = onHideFestToggle
            )
        }

        item {
            MetaTogglePill(
                isActive = showPreorders,
                activeLabel = "PRE-ORDERS",
                inactiveLabel = "NO PRE-ORDERS",
                onClick = onShowPreordersToggle
            )
        }
    }
}

private val SlopTeal = Color(0xFF00D4AA)
private val SlopTealDim = Color(0x4D00D4AA)

@OptIn(ExperimentalTvMaterial3Api::class)
@Composable
private fun MetaTogglePill(
    isActive: Boolean,
    activeLabel: String,
    inactiveLabel: String,
    onClick: () -> Unit
) {
    var isFocused by remember { mutableStateOf(false) }

    val backgroundColor = if (isActive) SlopTeal.copy(alpha = 0.15f) else Color.Transparent
    val borderColor = when {
        isFocused -> SlopTeal
        isActive -> SlopTeal
        else -> SlopTealDim
    }
    val textColor = if (isActive) SlopTeal else SlopTeal.copy(alpha = 0.45f)

    Surface(
        onClick = onClick,
        modifier = Modifier.onFocusChanged { isFocused = it.isFocused },
        shape = ClickableSurfaceDefaults.shape(RoundedCornerShape(14.dp)),
        colors = ClickableSurfaceDefaults.colors(
            containerColor = backgroundColor,
            focusedContainerColor = backgroundColor,
            pressedContainerColor = backgroundColor
        ),
        border = ClickableSurfaceDefaults.border(
            border = androidx.tv.material3.Border(
                border = BorderStroke(1.dp, borderColor),
                shape = RoundedCornerShape(14.dp)
            ),
            focusedBorder = androidx.tv.material3.Border(
                border = BorderStroke(2.dp, SlopTeal),
                shape = RoundedCornerShape(14.dp)
            )
        ),
        scale = ClickableSurfaceDefaults.scale(focusedScale = 1.1f, pressedScale = 0.95f)
    ) {
        Text(
            text = if (isActive) activeLabel else inactiveLabel,
            color = textColor,
            fontSize = 10.sp,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 3.dp)
        )
    }
}

@OptIn(ExperimentalTvMaterial3Api::class)
@Composable
private fun FilterPill(
    text: String,
    isSelected: Boolean,
    onClick: () -> Unit
) {
    var isFocused by remember { mutableStateOf(false) }

    val backgroundColor = when {
        isSelected -> Primary
        else -> ChipBackgroundDefault
    }

    val borderColor = when {
        isFocused -> FocusCyan
        isSelected -> Primary
        else -> ChipBorderDefault
    }

    val textColor = when {
        isSelected -> Background
        else -> TextPrimary
    }

    val scale = if (isFocused) 1.1f else 1f

    Surface(
        onClick = onClick,
        modifier = Modifier
            .onFocusChanged { isFocused = it.isFocused },
        shape = ClickableSurfaceDefaults.shape(RoundedCornerShape(14.dp)),
        colors = ClickableSurfaceDefaults.colors(
            containerColor = backgroundColor,
            focusedContainerColor = backgroundColor,
            pressedContainerColor = backgroundColor
        ),
        border = ClickableSurfaceDefaults.border(
            border = androidx.tv.material3.Border(
                border = BorderStroke(1.dp, borderColor),
                shape = RoundedCornerShape(14.dp)
            ),
            focusedBorder = androidx.tv.material3.Border(
                border = BorderStroke(2.dp, FocusCyan),
                shape = RoundedCornerShape(14.dp)
            ),
            pressedBorder = androidx.tv.material3.Border(
                border = BorderStroke(2.dp, Primary),
                shape = RoundedCornerShape(14.dp)
            )
        ),
        scale = ClickableSurfaceDefaults.scale(
            scale = scale,
            focusedScale = 1.1f,
            pressedScale = 0.95f
        ),
        glow = ClickableSurfaceDefaults.glow(
            focusedGlow = androidx.tv.material3.Glow(
                elevationColor = Primary.copy(alpha = 0.3f),
                elevation = 8.dp
            )
        )
    ) {
        Text(
            text = text,
            color = textColor,
            fontSize = 10.sp,
            fontWeight = if (isSelected) FontWeight.SemiBold else FontWeight.Medium,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 3.dp)
        )
    }
}
