' ============================================================================
' NRW Filter Bar Component
' Chips auto-size to their text (bundled Lato), use rounded 9-patch pill
' backgrounds tinted via blendColor, and show an orange focus ring (tvOS-style).
' Layout runs from a Timer because the custom font loads async — boundingRect()
' only reports real text width once the TTF is ready.
' ============================================================================

Sub Init()
    m.PAD = 22         ' horizontal padding inside a chip
    m.GAP = 14         ' gap between chips
    m.CHIP_H = 46      ' chip height
    m.DIVIDER_W = 2

    m.filterRow = m.top.FindNode("filterRow")
    m.focusRing = m.top.FindNode("focusRing")
    m.divider = m.top.FindNode("filterDivider")
    m.layoutTimer = m.top.FindNode("layoutTimer")

    m.filterIds = ["indie", "horror", "action", "comedy", "family", "thriller", "foreign", "documentary", "restorations", "hide_fest", "show_preorders", "slop_free", "show_highlights"]

    m.chips = {}
    m.chipBgs = {}
    m.chipLabels = {}
    for each filterId in m.filterIds
        m.chips[filterId] = m.top.FindNode("chip_" + filterId)
        m.chipBgs[filterId] = m.top.FindNode("chipBg_" + filterId)
        m.chipLabels[filterId] = m.top.FindNode("chipLabel_" + filterId)
    end for

    m.colors = GetColors()
    m.fonts = Fonts()
    m.chipX = {}
    m.chipW = {}

    ' Apply the chip font up front so measurement uses the real metrics
    for each filterId in m.filterIds
        m.chipLabels[filterId].font = m.fonts.filterChip
    end for

    UpdateChipStyles()
    StartLayout()
End Sub

' Kick the layout timer (used at init and whenever toggle text changes width)
Sub StartLayout()
    m.layoutTimer.ObserveField("fire", "LayoutChips")
    m.layoutTimer.control = "start"
End Sub

Sub onFilterChanged()
    UpdateChipStyles()
    StartLayout()   ' toggle labels change text → re-measure widths
End Sub

Sub onFocusChanged()
    UpdateFocusIndicator()
End Sub

' ============================================================================
' Measure each chip's text and lay the row out left-to-right. Repeats via the
' timer until the font has loaded (boundingRect width > 1).
' ============================================================================
Sub LayoutChips()
    for each filterId in m.filterIds
        if m.chipLabels[filterId].boundingRect().width <= 1 then return   ' font not ready; timer fires again
    end for
    m.layoutTimer.control = "stop"

    x = 0
    for each filterId in m.filterIds
        lbl = m.chipLabels[filterId]
        bg = m.chipBgs[filterId]
        tw = Int(lbl.boundingRect().width)
        bw = tw + 2 * m.PAD

        bg.width = bw
        bg.height = m.CHIP_H
        lbl.width = tw
        lbl.height = m.CHIP_H
        lbl.translation = [m.PAD, 0]
        m.chips[filterId].translation = [x, 0]

        m.chipX[filterId] = x
        m.chipW[filterId] = bw
        x = x + bw + m.GAP

        ' Insert the divider after the genre chips
        if filterId = "restorations"
            m.divider.translation = [x, (m.CHIP_H - 28) / 2]
            x = x + m.DIVIDER_W + m.GAP
        end if
    end for

    UpdateFocusIndicator()
End Sub

' ============================================================================
' Chip colors / text (active vs inactive, toggle identity colors)
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

        if filterId = "slop_free"
            if slopMode = "free"
                chipBg.blendColor = "0x00342AFF" : chipLabel.color = "0x00D4AAFF" : chipLabel.text = "SLOP FREE"
            else if slopMode = "only"
                chipBg.blendColor = "0x2D1A00FF" : chipLabel.color = "0xFF9500FF" : chipLabel.text = "SLOP ONLY"
            else
                chipBg.blendColor = "0x1A1A1AFF" : chipLabel.color = "0x00D4AA73" : chipLabel.text = "ALL"
            end if
            chipLabel.font = m.fonts.filterChipActive
            continue for
        end if

        if filterId = "show_highlights"
            if showHighlights
                chipBg.blendColor = "0x07261FFF" : chipLabel.color = "0x00D4AAFF"
            else
                chipBg.blendColor = "0x1A1A1AFF" : chipLabel.color = "0x00D4AA73"
            end if
            chipLabel.font = m.fonts.filterChipActive
            continue for
        end if

        if filterId = "hide_fest"
            if hideFest = false
                chipBg.blendColor = "0x2D1D02FF" : chipLabel.color = "0xF59E0BFF" : chipLabel.text = "FESTS"
            else
                chipBg.blendColor = "0x1A1A1AFF" : chipLabel.color = "0x00D4AA73" : chipLabel.text = "NO FEST"
            end if
            chipLabel.font = m.fonts.filterChipActive
            continue for
        end if

        if filterId = "show_preorders"
            if showPreorders
                chipBg.blendColor = "0x190C2FFF" : chipLabel.color = "0x7C3AEDFF" : chipLabel.text = "PRE-ORDERS"
            else
                chipBg.blendColor = "0x1A1A1AFF" : chipLabel.color = "0x00D4AA73" : chipLabel.text = "NO PRE-ORDERS"
            end if
            chipLabel.font = m.fonts.filterChipActive
            continue for
        end if

        ' Genre chips
        isActive = false
        for each af in activeFilters
            if af = filterId then isActive = true : exit for
        end for

        if isActive
            chipBg.blendColor = m.colors.primary
            chipLabel.color = "0xFFFFFFFF"
            chipLabel.font = m.fonts.filterChipActive
        else
            chipBg.blendColor = "0xFFFFFF1A"   ' subtle white fill (matches desktop rgba(255,255,255,0.1))
            chipLabel.color = "0xFFFFFFFF"
            chipLabel.font = m.fonts.filterChip
        end if
    end for
End Sub

' ============================================================================
' Orange focus ring around the focused chip
' ============================================================================
Sub UpdateFocusIndicator()
    if NOT m.top.hasFocus
        m.focusRing.visible = false
        return
    end if

    focusedIndex = m.top.focusedIndex
    if focusedIndex < 0 OR focusedIndex >= m.filterIds.Count() then focusedIndex = 0
    filterId = m.filterIds[focusedIndex]

    if m.chipX[filterId] = invalid then return   ' not laid out yet

    x = m.chipX[filterId]
    w = m.chipW[filterId]
    m.focusRing.blendColor = "0xFF9500FF"   ' tvOS orange focus
    m.focusRing.width = w + 6
    m.focusRing.height = m.CHIP_H + 6
    m.focusRing.translation = [x - 3, -3]
    m.focusRing.visible = true
End Sub

' ============================================================================
' Handle Key Events
' ============================================================================
Function OnKeyEvent(key as String, press as Boolean) as Boolean
    if NOT press then return false

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
        m.top.selectedFilter = m.filterIds[focusedIndex]
        return true
    end if

    return false
End Function
