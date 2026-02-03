package com.nrw.app.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.tv.foundation.lazy.list.TvLazyRow
import androidx.tv.foundation.lazy.list.items
import androidx.compose.material3.Text
import androidx.tv.material3.Border
import androidx.tv.material3.ExperimentalTvMaterial3Api
import androidx.tv.material3.FilterChip
import androidx.tv.material3.FilterChipDefaults
import com.nrw.app.data.FilterCategory
import com.nrw.app.ui.theme.Background
import com.nrw.app.ui.theme.BackgroundSecondary
import com.nrw.app.ui.theme.Primary
import com.nrw.app.ui.theme.TextMuted
import com.nrw.app.ui.theme.TextPrimary
import com.nrw.app.ui.theme.TextSecondary

/**
 * Horizontal row of filter chips for category selection
 */
@OptIn(ExperimentalTvMaterial3Api::class)
@Composable
fun FilterChips(
    selectedFilter: FilterCategory,
    onFilterSelected: (FilterCategory) -> Unit,
    modifier: Modifier = Modifier
) {
    TvLazyRow(
        modifier = modifier.fillMaxWidth(),
        contentPadding = PaddingValues(horizontal = 48.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        items(FilterCategory.entries) { category ->
            val isSelected = category == selectedFilter

            FilterChip(
                selected = isSelected,
                onClick = { onFilterSelected(category) },
                shape = FilterChipDefaults.shape(RoundedCornerShape(20.dp)),
                colors = FilterChipDefaults.colors(
                    containerColor = BackgroundSecondary,
                    contentColor = TextSecondary,
                    focusedContainerColor = BackgroundSecondary,
                    focusedContentColor = TextPrimary,
                    selectedContainerColor = Primary,
                    selectedContentColor = Background,
                    focusedSelectedContainerColor = Primary,
                    focusedSelectedContentColor = Background
                ),
                border = FilterChipDefaults.border(
                    focusedBorder = Border(
                        border = BorderStroke(2.dp, Primary),
                        shape = RoundedCornerShape(20.dp)
                    ),
                    focusedSelectedBorder = Border(
                        border = BorderStroke(2.dp, Primary),
                        shape = RoundedCornerShape(20.dp)
                    )
                ),
                scale = FilterChipDefaults.scale(
                    focusedScale = 1.1f
                )
            ) {
                Text(
                    text = category.displayName,
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                )
            }
        }
    }
}
