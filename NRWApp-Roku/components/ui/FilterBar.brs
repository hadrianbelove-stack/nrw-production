' ============================================================================
' NRW Filter Bar Component
' BrightScript logic for filter chip row
' ============================================================================

Sub Init()
    m.filterRow = m.top.FindNode("filterRow")
    m.focusIndicator = m.top.FindNode("focusIndicator")

    ' Filter chip IDs in order
    m.filterIds = ["indie", "horror", "action", "comedy", "family", "thriller", "foreign", "documentary", "restorations", "slop_free", "show_highlights", "hide_fest", "show_preorders"]

    ' Chip widths for focus indicator positioning
    m.chipWidths = {
        indie: 60
        horror: 80
        action: 80
        comedy: 80
        family: 80
        thriller: 80
        foreign: 80
        documentary: 60
        restorations: 90
        slop_free: 120
        show_highlights: 110
        hide_fest: 110
        show_preorders: 130
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
    slopMode = m.top.slopMode
    hideFest = m.top.hideFest
    showPreorders = m.top.showPreorders
    showHighlights = m.top.showHighlights

    for each filterId in m.filterIds
        chipBg = m.chipBgs[filterId]
        chipLabel = m.chipLabels[filterId]

        ' Slop toggle cycles: free → all → only
        if filterId = "slop_free"
            if slopMode = "free"
                chipBg.color = "0x00342AFF"
                chipLabel.color = "0x00D4AAFF"
                chipLabel.text = "SLOP FREE"
            else if slopMode = "only"
                chipBg.color = "0x2D1A00FF"
                chipLabel.color = "0xFF9500FF"
                chipLabel.text = "SLOP ONLY"
            else
                chipBg.color = "0x0D0D0DFF"
                chipLabel.color = "0x00D4AA73"
                chipLabel.text = "ALL"
            end if
            continue for
        end if

        ' Selects toggle: crimson identity color when active (matches banner + strips)
        if filterId = "show_highlights"
            if showHighlights
                chipBg.color = "0x2D040CFF"
                chipLabel.color = "0xDC143CFF"
            else
                chipBg.color = "0x0D0D0DFF"
                chipLabel.color = "0x00D4AA73"
            end if
            continue for
        end if

        ' Fest toggle: amber identity color when active (matches banner + strips)
        if filterId = "hide_fest"
            if hideFest = false
                chipBg.color = "0x2D1D02FF"
                chipLabel.color = "0xF59E0BFF"
                chipLabel.text = "FESTS"
            else
                chipBg.color = "0x0D0D0DFF"
                chipLabel.color = "0x00D4AA73"
                chipLabel.text = "NO FEST"
            end if
            continue for
        end if

        ' Pre-orders toggle: purple identity color when active (matches banner + strips)
        if filterId = "show_preorders"
            if showPreorders
                chipBg.color = "0x190C2FFF"
                chipLabel.color = "0x7C3AEDFF"
                chipLabel.text = "PRE-ORDERS"
            else
                chipBg.color = "0x0D0D0DFF"
                chipLabel.color = "0x00D4AA73"
                chipLabel.text = "NO PRE-ORDERS"
            end if
            continue for
        end if

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

