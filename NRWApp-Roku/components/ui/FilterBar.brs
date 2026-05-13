' ============================================================================
' NRW Filter Bar Component
' BrightScript logic for filter chip row
' ============================================================================

Sub Init()
    m.filterRow = m.top.FindNode("filterRow")
    m.focusIndicator = m.top.FindNode("focusIndicator")

    ' Filter chip IDs in order
    m.filterIds = ["staff_picks", "studio", "indie", "exploitation", "foreign", "documentary", "series", "restorations", "virtual_screenings", "pre_orders"]

    ' Chip widths for focus indicator positioning
    m.chipWidths = {
        studio: 80
        indie: 60
        staff_picks: 110
        foreign: 80
        series: 100
        restorations: 90
        documentary: 60
        virtual_screenings: 130
        pre_orders: 110
        exploitation: 120
    }

    ' Store chip references
    m.chips = {}
    m.chipBgs = {}
    m.chipLabels = {}

    for each filterId in m.filterIds
        m.chips[filterId] = m.top.FindNode("chip_" + filterId)
        m.chipBgs[filterId] = m.top.FindNode("chipBg_" + filterId)
        m.chipLabels[filterId] = m.top.FindNode("chipLabel_" + filterId)
    end for

    ' Get colors
    m.colors = GetColors()

    ' Initial state
    UpdateChipStyles()
End Sub

' ============================================================================
' Filter Selection Changed
' ============================================================================
Sub onFilterChanged()
    UpdateChipStyles()
End Sub

' ============================================================================
' Focus State Changed
' ============================================================================
Sub onFocusChanged()
    UpdateFocusIndicator()
End Sub

' ============================================================================
' Update Chip Visual Styles
' ============================================================================
Sub UpdateChipStyles()
    activeFilters = m.top.activeFilters

    for each filterId in m.filterIds
        chipBg = m.chipBgs[filterId]
        chipLabel = m.chipLabels[filterId]

        isActive = false
        ' Check if this filter is in the active set
        for each af in activeFilters
            if af = filterId
                isActive = true
                exit for
            end if
        end for

        if isActive
            ' Selected state: teal background, dark text
            chipBg.color = m.colors.primary
            chipLabel.color = "0x000000FF"
        else
            ' Unselected state: dark background, white text
            chipBg.color = "0x333333FF"
            chipLabel.color = "0xFFFFFFFF"
        end if
    end for

    UpdateFocusIndicator()
End Sub

' ============================================================================
' Update Focus Indicator Position
' ============================================================================
Sub UpdateFocusIndicator()
    if NOT m.top.hasFocus
        m.focusIndicator.visible = false
        return
    end if

    focusedIndex = m.top.focusedIndex
    if focusedIndex < 0 OR focusedIndex >= m.filterIds.Count()
        focusedIndex = 0
    end if

    ' Calculate X position
    xPos = 60  ' Initial offset
    spacing = 12

    for i = 0 to focusedIndex - 1
        filterId = m.filterIds[i]
        xPos = xPos + m.chipWidths[filterId] + spacing
    end for

    ' Get width of focused chip
    focusedFilterId = m.filterIds[focusedIndex]
    indicatorWidth = m.chipWidths[focusedFilterId]

    ' Update focus indicator
    m.focusIndicator.translation = [xPos, 38]
    m.focusIndicator.width = indicatorWidth
    m.focusIndicator.visible = true

    ' Scale focused chip slightly
    for i = 0 to m.filterIds.Count() - 1
        filterId = m.filterIds[i]
        chip = m.chips[filterId]
        if i = focusedIndex
            chip.scale = [1.05, 1.05]
        else
            chip.scale = [1.0, 1.0]
        end if
    end for
End Sub

' ============================================================================
' Handle Key Events
' ============================================================================
Function OnKeyEvent(key as String, press as Boolean) as Boolean
    if NOT press
        return false
    end if

    focusedIndex = m.top.focusedIndex

    if key = "left"
        if focusedIndex > 0
            m.top.focusedIndex = focusedIndex - 1
            UpdateFocusIndicator()
            return true
        end if
    else if key = "right"
        if focusedIndex < m.filterIds.Count() - 1
            m.top.focusedIndex = focusedIndex + 1
            UpdateFocusIndicator()
            return true
        end if
    else if key = "OK"
        ' Select the focused filter
        m.top.selectedFilter = m.filterIds[focusedIndex]
        return true
    end if

    return false
End Function

' ============================================================================
' Get Filter ID at Index
' ============================================================================
Function GetFilterIdAtIndex(index as Integer) as String
    if index >= 0 AND index < m.filterIds.Count()
        return m.filterIds[index]
    end if
    return m.filterIds[0]
End Function

' ============================================================================
' Get Index for Filter ID
' ============================================================================
Function GetIndexForFilterId(filterId as String) as Integer
    for i = 0 to m.filterIds.Count() - 1
        if m.filterIds[i] = filterId
            return i
        end if
    end for
    return 0
End Function
