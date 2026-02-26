' ============================================================================
' NRW Movie Card Component
' BrightScript logic for movie poster card
' ============================================================================

Sub Init()
    m.posterGroup = m.top.FindNode("posterGroup")
    m.cardContainer = m.top.FindNode("cardContainer")
    m.poster = m.top.FindNode("poster")
    m.focusBorder = m.top.FindNode("focusBorder")
    m.cardBackground = m.top.FindNode("cardBackground")

    ' Badges
    m.serviceBadgeBg = m.top.FindNode("serviceBadgeBg")
    m.serviceBadge = m.top.FindNode("serviceBadge")
    m.rtBadgeBg = m.top.FindNode("rtBadgeBg")
    m.rtBadge = m.top.FindNode("rtBadge")
    m.staffPickStrip = m.top.FindNode("staffPickStrip")

    ' Director label
    m.directorLabel = m.top.FindNode("directorLabel")

    ' Store original dimensions for scaling
    m.originalWidth = 200
    m.originalHeight = 300
End Sub

' ============================================================================
' Movie Data Changed
' ============================================================================
Sub onMovieChanged()
    movie = m.top.movie
    if movie = invalid
        return
    end if

    ' Set poster image
    if movie.poster <> invalid AND movie.poster <> ""
        m.poster.uri = movie.poster
    else if movie.poster_url <> invalid AND movie.poster_url <> ""
        m.poster.uri = movie.poster_url
    end if

    ' Set director
    director = GetDirector(movie)
    if director <> ""
        m.directorLabel.text = director
        m.directorLabel.visible = true
    else
        m.directorLabel.visible = false
    end if

    ' Set streaming service badge
    streaming = GetStreamingService(movie)
    if streaming <> invalid AND streaming.service <> invalid
        SetupServiceBadge(streaming.service)
    else
        m.serviceBadge.visible = false
        m.serviceBadgeBg.visible = false
    end if

    ' Set RT score badge
    if movie.rt_score <> invalid
        SetupRtBadge(movie.rt_score)
    else
        m.rtBadge.visible = false
        m.rtBadgeBg.visible = false
    end if

    ' Set staff pick strip
    if IsStaffPick(movie)
        m.staffPickStrip.visible = true
    else
        m.staffPickStrip.visible = false
    end if
End Sub

' ============================================================================
' Setup Streaming Service Badge
' ============================================================================
Sub SetupServiceBadge(service as String)
    colors = GetServiceColors()
    badgeText = GetServiceBadgeText(service)
    normalized = NormalizeServiceName(service)

    ' Set badge text
    m.serviceBadge.text = badgeText
    m.serviceBadge.visible = true

    ' Set badge color
    if colors.DoesExist(normalized)
        m.serviceBadgeBg.color = colors[normalized]
    else
        m.serviceBadgeBg.color = "0xFF9500FF"  ' Default VOD color
    end if
    m.serviceBadgeBg.visible = true

    ' Adjust badge width based on text
    if Len(badgeText) > 2
        m.serviceBadge.width = 48
        m.serviceBadgeBg.width = 48
        m.serviceBadge.translation = [148, 4]
        m.serviceBadgeBg.translation = [148, 4]
    else
        m.serviceBadge.width = 40
        m.serviceBadgeBg.width = 40
        m.serviceBadge.translation = [156, 4]
        m.serviceBadgeBg.translation = [156, 4]
    end if
End Sub

' ============================================================================
' Setup RT Score Badge
' ============================================================================
Sub SetupRtBadge(score as Dynamic)
    scoreInt = 0
    if Type(score) = "Integer" OR Type(score) = "roInt" OR Type(score) = "Float" OR Type(score) = "roFloat"
        scoreInt = Int(score)
    else if Type(score) = "String" OR Type(score) = "roString"
        cleaned = score.Replace("%", "")
        scoreInt = Int(Val(cleaned))
    else
        m.rtBadge.visible = false
        m.rtBadgeBg.visible = false
        return
    end if

    if scoreInt = 0
        m.rtBadge.visible = false
        m.rtBadgeBg.visible = false
        return
    end if

    ' Set badge text
    m.rtBadge.text = scoreInt.ToStr() + "%"
    m.rtBadge.visible = true

    ' Set color based on score (Fresh = 60+, Rotten = <60)
    if scoreInt >= 60
        m.rtBadgeBg.color = "0x34C759FF"  ' Green (fresh)
    else
        m.rtBadgeBg.color = "0xFF3B30FF"  ' Red (rotten)
    end if
    m.rtBadgeBg.visible = true
End Sub

' ============================================================================
' Focus State Changed
' ============================================================================
Sub onFocusChanged()
    focusPercent = m.top.focusPercent
    colors = GetColors()

    if focusPercent > 0.5
        ' Focused state
        m.focusBorder.visible = true

        ' Scale the card
        scale = 1.0 + (0.1 * focusPercent)  ' Max scale 1.1
        m.cardContainer.scale = [scale, scale]

        ' Animate border color (pulse effect could be added here)
        m.focusBorder.color = colors.primary
    else
        ' Unfocused state
        m.focusBorder.visible = false
        m.cardContainer.scale = [1.0, 1.0]
    end if
End Sub

' ============================================================================
' Handle Key Events
' ============================================================================
Function OnKeyEvent(key as String, press as Boolean) as Boolean
    if press
        if key = "OK"
            m.top.selected = true
            return true
        end if
    end if
    return false
End Function
