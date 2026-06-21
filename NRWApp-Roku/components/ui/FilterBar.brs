' ============================================================================
' NRW Filter Bar
' Row 1: genre chips (auto-sized rounded pills). Row 2: a bordered toggle module
' of iOS-style switches (FESTS, PRE-ORDER, SLOP 3-state, SELECTS) matching tvOS.
' Layout runs from a Timer because the bundled font loads async.
' ============================================================================

Sub Init()
    m.PAD = 22          ' chip horizontal padding
    m.GAP = 14          ' chip gap
    m.CHIP_H = 46       ' chip height

    m.filterRow = m.top.FindNode("filterRow")
    m.focusRing = m.top.FindNode("focusRing")
    m.toggleBox = m.top.FindNode("toggleBox")
    m.toggleBoxBorder = m.top.FindNode("toggleBoxBorder")
    m.toggleBoxBg = m.top.FindNode("toggleBoxBg")
    m.layoutTimer = m.top.FindNode("layoutTimer")

    m.genreIds = ["indie", "horror", "action", "comedy", "family", "thriller", "foreign", "documentary", "restorations"]
    m.switchIds = ["hide_fest", "show_preorders", "slop_free", "show_highlights"]
    m.filterIds = []
    for each g in m.genreIds : m.filterIds.Push(g) : end for
    for each s in m.switchIds : m.filterIds.Push(s) : end for

    m.colors = GetColors()
    m.fonts = Fonts()

    ' Accent color per switch (tvOS identity colors)
    m.switchAccent = {
        hide_fest: "0xF59E0BFF"        ' amber
        show_preorders: "0x7C3AEDFF"   ' purple
        slop_free: "0x00D4AAFF"        ' teal (free)
        show_highlights: "0x00D4AAFF"  ' teal
    }

    ' Genre chip nodes
    m.chips = {} : m.chipBgs = {} : m.chipLabels = {}
    for each id in m.genreIds
        m.chips[id] = m.top.FindNode("chip_" + id)
        m.chipBgs[id] = m.top.FindNode("chipBg_" + id)
        m.chipLabels[id] = m.top.FindNode("chipLabel_" + id)
        m.chipLabels[id].font = m.fonts.filterChip
    end for

    ' Switch nodes
    m.swLabels = {} : m.swTracks = {} : m.swThumbs = {}
    for each id in m.switchIds
        m.swLabels[id] = m.top.FindNode("swLabel_" + id)
        m.swTracks[id] = m.top.FindNode("swTrack_" + id)
        m.swThumbs[id] = m.top.FindNode("swThumb_" + id)
        m.swLabels[id].font = m.fonts.filterChipActive
    end for

    m.itemBounds = {}   ' id -> { x, y, w, h } for the focus ring
    m.swGeom = {}       ' id -> track/thumb geometry for thumb placement

    UpdateChipStyles()
    StartLayout()
End Sub

Sub StartLayout()
    m.layoutTimer.ObserveField("fire", "LayoutChips")
    m.layoutTimer.control = "start"
End Sub

Sub onFilterChanged()
    UpdateChipStyles()
    StartLayout()
End Sub

Sub onFocusChanged()
    UpdateFocusIndicator()
End Sub

' ============================================================================
' Lay out chips (row 1) and the switch module (row 2). Repeats via the timer
' until the font has loaded (label widths > 1).
' ============================================================================
Sub LayoutChips()
    for each id in m.genreIds
        if m.chipLabels[id].boundingRect().width <= 1 then return
    end for
    for each id in m.switchIds
        if m.swLabels[id].boundingRect().width <= 1 then return
    end for
    m.layoutTimer.control = "stop"

    ' --- Row 1: genre pills ---
    x = 0
    for each id in m.genreIds
        lbl = m.chipLabels[id]
        bg = m.chipBgs[id]
        tw = Int(lbl.boundingRect().width)
        bw = tw + 2 * m.PAD
        bg.width = bw : bg.height = m.CHIP_H
        lbl.width = tw : lbl.height = m.CHIP_H : lbl.translation = [m.PAD, 0]
        m.chips[id].translation = [x, 0]
        m.itemBounds[id] = { x: x, y: 0, w: bw, h: m.CHIP_H }
        x = x + bw + m.GAP
    end for

    ' --- Row 2: toggle module (bordered box + switches) ---
    boxPadH = 20
    boxPadV = 12
    swGap = 30
    boxH = 42 + 2 * boxPadV   ' tallest track (42) + padding
    cx = boxPadH
    for each id in m.switchIds
        isSlop = (id = "slop_free")
        trackW = 88 : trackH = 42 : thumbSz = 34
        if isSlop
            trackW = 122 : trackH = 32 : thumbSz = 24
        end if
        lbl = m.swLabels[id]
        lblW = Int(lbl.boundingRect().width)
        lblH = Int(lbl.boundingRect().height)
        track = m.swTracks[id]
        thumb = m.swThumbs[id]

        lbl.width = lblW : lbl.height = lblH
        lbl.translation = [cx, (boxH - lblH) / 2]
        trackX = cx + lblW + 10
        trackY = (boxH - trackH) / 2
        track.width = trackW : track.height = trackH : track.translation = [trackX, trackY]
        thumb.width = thumbSz : thumb.height = thumbSz

        ' track is the focusable bound (filterRow coords: + toggleBox y offset 62)
        m.itemBounds[id] = { x: trackX, y: 62 + trackY, w: trackW, h: trackH }
        m.swGeom[id] = { trackX: trackX, trackY: trackY, trackW: trackW, trackH: trackH, thumbSz: thumbSz }

        cx = trackX + trackW + swGap
    end for
    boxW = cx - swGap + boxPadH
    m.toggleBoxBorder.width = boxW : m.toggleBoxBorder.height = boxH
    m.toggleBoxBg.width = boxW - 2 : m.toggleBoxBg.height = boxH - 2 : m.toggleBoxBg.translation = [1, 1]

    UpdateSwitchVisuals()
    UpdateFocusIndicator()
End Sub

' ============================================================================
' Genre chip colors + SLOP label text
' ============================================================================
Sub UpdateChipStyles()
    activeFilters = m.top.activeFilters

    for each id in m.genreIds
        isActive = false
        for each af in activeFilters
            if af = id then isActive = true : exit for
        end for
        if isActive
            m.chipBgs[id].blendColor = m.colors.primary
            m.chipLabels[id].color = "0xFFFFFFFF"
            m.chipLabels[id].font = m.fonts.filterChipActive
        else
            m.chipBgs[id].blendColor = "0xFFFFFF1A"
            m.chipLabels[id].color = "0xFFFFFFFF"
            m.chipLabels[id].font = m.fonts.filterChip
        end if
    end for

    ' SLOP label text changes with state
    slopMode = m.top.slopMode
    if slopMode = "free"
        m.swLabels["slop_free"].text = "SLOP FREE"
    else if slopMode = "only"
        m.swLabels["slop_free"].text = "SLOP ONLY"
    else
        m.swLabels["slop_free"].text = "ALL"
    end if

    UpdateSwitchVisuals()
End Sub

' ============================================================================
' Switch track colors, thumb positions, label colors
' ============================================================================
Sub UpdateSwitchVisuals()
    if m.swGeom["hide_fest"] = invalid then return   ' not laid out yet

    SetSwitch("hide_fest", m.top.hideFest = false)        ' ON when fests shown
    SetSwitch("show_preorders", m.top.showPreorders = true)
    SetSwitch("show_highlights", m.top.showHighlights = true)

    ' SLOP 3-state slider
    g = m.swGeom["slop_free"]
    track = m.swTracks["slop_free"]
    thumb = m.swThumbs["slop_free"]
    lbl = m.swLabels["slop_free"]
    slopMode = m.top.slopMode
    midX = g.trackX + (g.trackW - g.thumbSz) / 2
    leftX = g.trackX + 4
    rightX = g.trackX + g.trackW - g.thumbSz - 4
    thumbY = g.trackY + (g.trackH - g.thumbSz) / 2
    if slopMode = "free"
        track.blendColor = "0x00D4AAFF" : thumb.blendColor = "0xFFFFFFFF" : thumb.translation = [leftX, thumbY]
        lbl.color = "0x00D4AAFF"
    else if slopMode = "only"
        track.blendColor = "0xFF9500FF" : thumb.blendColor = "0xFFFFFFFF" : thumb.translation = [rightX, thumbY]
        lbl.color = "0xFF9500FF"
    else
        track.blendColor = "0x1A1A1AFF" : thumb.blendColor = "0x00D4AAFF" : thumb.translation = [midX, thumbY]
        lbl.color = "0x00D4AA73"
    end if
End Sub

Sub SetSwitch(id as String, isOn as Boolean)
    g = m.swGeom[id]
    if g = invalid then return
    track = m.swTracks[id]
    thumb = m.swThumbs[id]
    lbl = m.swLabels[id]
    accent = m.switchAccent[id]
    thumbY = g.trackY + (g.trackH - g.thumbSz) / 2
    if isOn
        track.blendColor = accent
        thumb.translation = [g.trackX + g.trackW - g.thumbSz - 4, thumbY]
        lbl.color = accent
    else
        track.blendColor = "0x1A1A1AFF"
        thumb.translation = [g.trackX + 4, thumbY]
        lbl.color = "0x00D4AA73"
    end if
End Sub

' ============================================================================
' Orange focus ring around the focused item (genre pill or switch track)
' ============================================================================
Sub UpdateFocusIndicator()
    if NOT m.top.hasFocus
        m.focusRing.visible = false
        return
    end if
    idx = m.top.focusedIndex
    if idx < 0 OR idx >= m.filterIds.Count() then idx = 0
    id = m.filterIds[idx]
    b = m.itemBounds[id]
    if b = invalid then return
    m.focusRing.blendColor = "0xFF9500FF"
    m.focusRing.width = b.w + 6
    m.focusRing.height = b.h + 6
    m.focusRing.translation = [b.x - 3, b.y - 3]
    m.focusRing.visible = true
End Sub

' ============================================================================
' Keys: left/right across all items; OK activates the focused filter/toggle
' ============================================================================
Function OnKeyEvent(key as String, press as Boolean) as Boolean
    if NOT press then return false
    idx = m.top.focusedIndex

    if key = "left"
        if idx > 0
            m.top.focusedIndex = idx - 1
            UpdateFocusIndicator()
            return true
        end if
    else if key = "right"
        if idx < m.filterIds.Count() - 1
            m.top.focusedIndex = idx + 1
            UpdateFocusIndicator()
            return true
        end if
    else if key = "OK"
        m.top.selectedFilter = m.filterIds[idx]
        return true
    end if
    return false
End Function
