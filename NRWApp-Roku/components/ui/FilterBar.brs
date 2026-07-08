' ============================================================================
' NRW Filter Bar — tvOS layout
' One filled control row (matches web): SLOP FILTER · SELECTS · FESTS ·
' PRE-ORDER · GENRE, with the Search box at the far right.
' Focus is 2-D spatial (up/down/left/right find the nearest item); at an edge
' OnKeyEvent returns false so HomeScreen takes over (up=search, down=grid).
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

    ' Genres — now collapsed behind the GENRE control; shown in a single
    ' horizontal strip inside the overlay.
    m.genreIds = ["indie", "horror", "action", "comedy", "family", "thriller", "foreign", "documentary", "restorations"]

    ' One switch row (matches web): SLOP FILTER · SELECTS · FESTS · PRE-ORDER
    m.switchRow = ["slop_free", "show_highlights", "hide_fest", "show_preorders"]
    m.switchIds = m.switchRow

    ' Full focus order for the bar (index space for the public focusedIndex field):
    ' switches, then the GENRE control, then search.
    m.filterIds = []
    for each s in m.switchIds : m.filterIds.Push(s) : end for
    m.filterIds.Push("genre")
    m.filterIds.Push("search")

    ' GENRE overlay state
    m.overlayOpen = false
    m.overlayIndex = 0

    m.colors = GetColors()
    m.fonts = Fonts()

    m.switchAccent = {
        hide_fest: "0xFFD700FF"
        show_preorders: "0x7C3AEDFF"
        slop_free: "0x00D4AAFF"
        show_highlights: "0x00D4AAFF"
    }

    m.chips = {} : m.chipBgs = {} : m.chipLabels = {}
    for each id in m.genreIds
        m.chips[id] = m.top.FindNode("chip_" + id)
        m.chipBgs[id] = m.top.FindNode("chipBg_" + id)
        m.chipLabels[id] = m.top.FindNode("chipLabel_" + id)
        m.chipLabels[id].font = m.fonts.filterChip
    end for

    ' GENRE control + overlay
    m.genreControl = m.top.FindNode("chip_genre")
    m.genreControlBg = m.top.FindNode("chipBg_genre")
    m.genreControlLabel = m.top.FindNode("chipLabel_genre")
    m.genreControlLabel.font = m.fonts.filterChipActive
    m.genreOverlay = m.top.FindNode("genreOverlay")
    m.genreOverlayBg = m.top.FindNode("genreOverlayBg")

    m.swLabels = {} : m.swTracks = {} : m.swThumbs = {}
    for each id in m.switchIds
        m.swLabels[id] = m.top.FindNode("swLabel_" + id)
        m.swTracks[id] = m.top.FindNode("swTrack_" + id)
        m.swThumbs[id] = m.top.FindNode("swThumb_" + id)
        m.swLabels[id].font = m.fonts.filterChipActive
    end for

    ' Search box nodes
    m.searchBar = m.top.FindNode("searchBar")
    m.searchBarBg = m.top.FindNode("searchBarBg")
    m.searchBarLabel = m.top.FindNode("searchBarLabel")
    m.searchBarLabel.font = m.fonts.cardMeta

    m.itemBounds = {}   ' id -> {x,y,w,h}
    m.itemCenter = {}   ' id -> {x,y}
    m.swGeom = {}

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
' Lay out the one control row (switches + GENRE) and the genre overlay strip.
' Gate only on VISIBLE labels being measured — the overlay chips may not report a
' boundingRect while hidden, so requiring them here could stall the whole layout.
' ============================================================================
Sub LayoutChips()
    for each id in m.switchIds
        if m.swLabels[id].boundingRect().width <= 1 then return
    end for
    if m.genreControlLabel.boundingRect().width <= 1 then return
    m.layoutTimer.control = "stop"

    ' --- One filled control row: SLOP FILTER · SELECTS · FESTS · PRE-ORDER · GENRE ---
    boxPadH = 20 : boxPadV = 12
    rowH = 46 : swGap = 26
    rowY = boxPadV
    rowRight = LayoutSwitchRow(m.switchRow, boxPadH, rowY, rowH, swGap)

    ' GENRE control at the end of the row
    gcTextW = Int(m.genreControlLabel.boundingRect().width)
    gcW = gcTextW + 2 * m.PAD
    gcX = rowRight + swGap
    gcY = rowY + (rowH - m.CHIP_H) / 2
    m.genreControlBg.width = gcW : m.genreControlBg.height = m.CHIP_H
    m.genreControlLabel.width = gcTextW : m.genreControlLabel.height = m.CHIP_H : m.genreControlLabel.translation = [m.PAD, 0]
    m.genreControl.translation = [gcX, gcY]
    m.itemBounds["genre"] = { x: gcX, y: gcY, w: gcW, h: m.CHIP_H }

    ' Filled bar spans switches + GENRE
    boxW = gcX + gcW + boxPadH
    boxH = boxPadV * 2 + rowH
    m.toggleBoxBorder.width = boxW : m.toggleBoxBorder.height = boxH
    m.toggleBoxBg.width = boxW - 2 : m.toggleBoxBg.height = boxH - 2 : m.toggleBoxBg.translation = [1, 1]

    ' --- Search box: right of the bar ---
    searchX = boxW + 44
    searchW = 1600 - searchX
    if searchW < 260 then searchW = 260
    m.searchBar.translation = [searchX, 0]
    m.searchBarBg.width = searchW : m.searchBarBg.height = boxH
    m.searchBarLabel.width = searchW : m.searchBarLabel.height = boxH : m.searchBarLabel.translation = [0, 0]
    m.itemBounds["search"] = { x: searchX, y: 0, w: searchW, h: boxH }

    ' --- Genre overlay strip (below the bar), laid out but hidden until opened ---
    LayoutGenreOverlay(boxH + 12)

    ' Centers for spatial nav (bar items only)
    for each id in m.filterIds
        b = m.itemBounds[id]
        m.itemCenter[id] = { x: b.x + b.w / 2, y: b.y + b.h / 2 }
    end for

    UpdateSwitchVisuals()
    UpdateChipStyles()
    UpdateFocusIndicator()
End Sub

' Lay one row of switches; returns the row's right edge (inner width)
Function LayoutSwitchRow(ids as Object, startX as Integer, rowY as Integer, rowH as Integer, swGap as Integer) as Integer
    x = startX
    for each id in ids
        isSlop = (id = "slop_free")
        trackW = 88 : trackH = 42 : thumbSz = 34
        if isSlop
            trackW = 122 : trackH = 32 : thumbSz = 24
        end if
        lbl = m.swLabels[id]
        track = m.swTracks[id]
        thumb = m.swThumbs[id]
        lblW = Int(lbl.boundingRect().width)
        lblH = Int(lbl.boundingRect().height)

        lbl.width = lblW : lbl.height = lblH
        lbl.translation = [x, rowY + (rowH - lblH) / 2]
        trackX = x + lblW + 8
        trackY = rowY + (rowH - trackH) / 2
        track.width = trackW : track.height = trackH : track.translation = [trackX, trackY]
        thumb.width = thumbSz : thumb.height = thumbSz

        m.itemBounds[id] = { x: trackX, y: trackY, w: trackW, h: trackH }
        m.swGeom[id] = { trackX: trackX, trackY: trackY, trackW: trackW, trackH: trackH, thumbSz: thumbSz }
        x = trackX + trackW + swGap
    end for
    return x - swGap
End Function

' Lay the genre chips as one horizontal strip inside the overlay. Chip
' translations are relative to the overlay's origin; m.itemBounds stores the
' ABSOLUTE position (for the focus ring, which lives in filterRow).
Sub LayoutGenreOverlay(overlayY as Integer)
    padH = 20 : padV = 14 : gap = 12
    x = padH
    for each id in m.genreIds
        lbl = m.chipLabels[id]
        bg = m.chipBgs[id]
        tw = Int(lbl.boundingRect().width)
        bw = tw + 2 * m.PAD
        bg.width = bw : bg.height = m.CHIP_H
        lbl.width = tw : lbl.height = m.CHIP_H : lbl.translation = [m.PAD, 0]
        m.chips[id].translation = [x, padV]
        m.itemBounds[id] = { x: x, y: overlayY + padV, w: bw, h: m.CHIP_H }
        x = x + bw + gap
    end for
    m.genreOverlayBg.width = x - gap + padH
    m.genreOverlayBg.height = m.CHIP_H + padV * 2
    m.genreOverlay.translation = [0, overlayY]
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

    slopMode = m.top.slopMode
    if slopMode = "free"
        m.swLabels["slop_free"].text = "SLOP FREE"
    else if slopMode = "only"
        m.swLabels["slop_free"].text = "SLOP ONLY"
    else
        m.swLabels["slop_free"].text = "SLOP FILTER"
    end if

    ' GENRE control — show the chosen genre's name (else "GENRE"); brighter when active
    if m.genreControlLabel <> invalid
        activeGenre = ""
        for each id in m.genreIds
            for each af in activeFilters
                if af = id then activeGenre = id : exit for
            end for
            if activeGenre <> "" then exit for
        end for
        if activeGenre <> ""
            m.genreControlLabel.text = UCase(m.chipLabels[activeGenre].text)
            m.genreControlLabel.color = "0x00D4AAFF"
            m.genreControlBg.blendColor = "0x00D4AA8C"
        else
            m.genreControlLabel.text = "GENRE"
            m.genreControlLabel.color = "0x00D4AABF"
            m.genreControlBg.blendColor = "0x00D4AA40"
        end if
    end if

    UpdateSwitchVisuals()
End Sub

' ============================================================================
' Switch visuals
' ============================================================================
Sub UpdateSwitchVisuals()
    if m.swGeom["hide_fest"] = invalid then return

    SetSwitch("hide_fest", m.top.hideFest = false)
    SetSwitch("show_preorders", m.top.showPreorders = true)
    SetSwitch("show_highlights", m.top.showHighlights = true)

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
' Orange focus ring (hollow, on top)
' ============================================================================
Sub UpdateFocusIndicator()
    if NOT m.top.hasFocus
        m.focusRing.visible = false
        return
    end if
    if m.overlayOpen
        if m.overlayIndex < 0 OR m.overlayIndex >= m.genreIds.Count() then m.overlayIndex = 0
        id = m.genreIds[m.overlayIndex]
    else
        idx = m.top.focusedIndex
        if idx < 0 OR idx >= m.filterIds.Count() then idx = 0
        id = m.filterIds[idx]
    end if
    b = m.itemBounds[id]
    if b = invalid then return
    m.focusRing.blendColor = "0xFF9500FF"
    m.focusRing.width = b.w + 6
    m.focusRing.height = b.h + 6
    m.focusRing.translation = [b.x - 3, b.y - 3]
    m.focusRing.visible = true
End Sub

' ============================================================================
' GENRE overlay show / hide
' ============================================================================
Sub ShowGenreOverlay()
    m.overlayOpen = true
    m.overlayIndex = 0
    activeFilters = m.top.activeFilters
    for i = 0 to m.genreIds.Count() - 1
        for each af in activeFilters
            if af = m.genreIds[i] then m.overlayIndex = i
        end for
    end for
    m.genreOverlay.visible = true
    ' Re-run layout now that the chips are visible, in case they weren't measured
    ' while hidden (LayoutChips is idempotent for the bar).
    StartLayout()
    UpdateFocusIndicator()
End Sub

Sub HideGenreOverlay()
    m.overlayOpen = false
    m.genreOverlay.visible = false
    UpdateFocusIndicator()
End Sub

' ============================================================================
' Spatial navigation: find the nearest item in a direction
' ============================================================================
Function FindNeighbor(curId as String, dir as String) as Object
    cur = m.itemCenter[curId]
    if cur = invalid then return invalid
    best = invalid : bestScore = 9999999
    for each id in m.filterIds
        if id <> curId
            c = m.itemCenter[id]
            dx = c.x - cur.x : dy = c.y - cur.y
            ok = false
            if dir = "right" AND dx > 6 then ok = true
            if dir = "left" AND dx < -6 then ok = true
            if dir = "down" AND dy > 6 then ok = true
            if dir = "up" AND dy < -6 then ok = true
            if ok
                if dir = "left" OR dir = "right"
                    score = Abs(dx) + Abs(dy) * 4
                else
                    score = Abs(dy) + Abs(dx) * 4
                end if
                if score < bestScore then bestScore = score : best = id
            end if
        end if
    end for
    return best
End Function

Function IndexOfId(id as Object) as Integer
    for i = 0 to m.filterIds.Count() - 1
        if m.filterIds[i] = id then return i
    end for
    return 0
End Function

' ============================================================================
' Keys
' ============================================================================
Function OnKeyEvent(key as String, press as Boolean) as Boolean
    if NOT press then return false

    ' --- GENRE overlay mode: navigate the chip strip; OK applies, Back/up/down close ---
    if m.overlayOpen
        if key = "back"
            HideGenreOverlay()
            return true
        else if key = "OK"
            m.top.selectedFilter = m.genreIds[m.overlayIndex]
            HideGenreOverlay()
            return true
        else if key = "left"
            if m.overlayIndex > 0
                m.overlayIndex = m.overlayIndex - 1
                UpdateFocusIndicator()
            end if
            return true
        else if key = "right"
            if m.overlayIndex < m.genreIds.Count() - 1
                m.overlayIndex = m.overlayIndex + 1
                UpdateFocusIndicator()
            end if
            return true
        else if key = "up" OR key = "down"
            HideGenreOverlay()
            return true
        end if
        return true   ' swallow everything else while the overlay is open
    end if

    ' --- Bar mode ---
    idx = m.top.focusedIndex
    if idx < 0 OR idx >= m.filterIds.Count() then idx = 0
    curId = m.filterIds[idx]

    if key = "OK"
        if curId = "genre"
            ShowGenreOverlay()   ' open the pulldown (handled internally, not a filter)
        else
            m.top.selectedFilter = curId
        end if
        return true
    end if

    if key = "left" OR key = "right" OR key = "up" OR key = "down"
        nb = FindNeighbor(curId, key)
        if nb <> invalid
            m.top.focusedIndex = IndexOfId(nb)
            UpdateFocusIndicator()
            return true
        end if
        return false   ' edge: let HomeScreen handle (up=search, down=grid)
    end if

    return false
End Function
