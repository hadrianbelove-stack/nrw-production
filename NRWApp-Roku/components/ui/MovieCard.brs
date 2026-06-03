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
    m.serviceBadgeSubtext = m.top.FindNode("serviceBadgeSubtext")
    m.rtBadgeBorder = m.top.FindNode("rtBadgeBorder")
    m.rtBadgeBg = m.top.FindNode("rtBadgeBg")
    m.rtBadge = m.top.FindNode("rtBadge")
    m.mcBadgeBorder = m.top.FindNode("mcBadgeBorder")
    m.mcBadgeBg = m.top.FindNode("mcBadgeBg")
    m.mcBadge = m.top.FindNode("mcBadge")
    m.imdbBadgeBorder = m.top.FindNode("imdbBadgeBorder")
    m.imdbBadgeBg = m.top.FindNode("imdbBadgeBg")
    m.imdbBadge = m.top.FindNode("imdbBadge")
    m.staffPickStrip = m.top.FindNode("staffPickStrip")
    m.staffPickBorder = m.top.FindNode("staffPickBorder")
    m.restorationBadgeBg = m.top.FindNode("restorationBadgeBg")
    m.restorationBadgeLabel = m.top.FindNode("restorationBadgeLabel")
    m.preOrderBadgeBg = m.top.FindNode("preOrderBadgeBg")
    m.preOrderBadgeLabel = m.top.FindNode("preOrderBadgeLabel")
    m.preOrderBadgeDate = m.top.FindNode("preOrderBadgeDate")
    m.screeningBorder = m.top.FindNode("screeningBorder")
    m.screeningTopBannerBg = m.top.FindNode("screeningTopBannerBg")
    m.screeningTopBannerLabel = m.top.FindNode("screeningTopBannerLabel")
    m.screeningFestivalBg = m.top.FindNode("screeningFestivalBg")
    m.screeningFestivalLabel = m.top.FindNode("screeningFestivalLabel")

    ' Director label
    m.directorLabel = m.top.FindNode("directorLabel")

    ' Date divider elements
    m.dateDividerGroup = m.top.FindNode("dateDividerGroup")
    m.dateDividerBar = m.top.FindNode("dateDividerBar")
    m.dateDividerBarLabel = m.top.FindNode("dateDividerBarLabel")
    m.dateDividerNumber = m.top.FindNode("dateDividerNumber")
    m.dateDividerMonth = m.top.FindNode("dateDividerMonth")
    m.dateDividerChevrons = []
    for i = 1 to 5
        m.dateDividerChevrons.Push(m.top.FindNode("dateDividerChevron" + i.ToStr()))
    end for

    ' Store original dimensions for scaling
    m.originalWidth = 320
    m.originalHeight = 480
End Sub

' ============================================================================
' Movie Data Changed
' ============================================================================
Sub onMovieChanged()
    movie = m.top.movie
    if movie = invalid
        return
    end if

    ' Check if this is a date divider item
    if movie._type <> invalid AND movie._type = "date-divider"
        ShowAsDateDivider(movie)
        return
    end if

    ' Regular movie card — hide date divider, show card
    m.dateDividerGroup.visible = false
    m.cardContainer.visible = true
    m.directorLabel.visible = true

    ' Set poster image
    if movie.poster <> invalid AND movie.poster <> ""
        m.poster.uri = movie.poster
    else if movie.poster_url <> invalid AND movie.poster_url <> ""
        m.poster.uri = movie.poster_url
    end if

    ' Set director · genre · country (matches desktop caption)
    director = GetDirector(movie)
    genre = ""
    if movie.genres <> invalid AND movie.genres.Count() > 0
        genre = movie.genres[0]
    end if
    countryText = ""
    if movie.country <> invalid AND movie.country <> ""
        countryText = FormatCountry(movie.country)
    end if
    parts = []
    if director <> "" then parts.Push(director)
    if genre <> "" then parts.Push(genre)
    if countryText <> "" then parts.Push(countryText)
    if parts.Count() > 0
        meta = parts[0]
        for i = 1 to parts.Count() - 1
            meta = meta + " · " + parts[i]
        end for
        m.directorLabel.text = meta
        m.directorLabel.visible = true
    else
        m.directorLabel.visible = false
    end if

    ' Determine card state flags
    isStaffPick = IsStaffPick(movie)
    isScreening = (movie.filters <> invalid AND movie.filters.is_virtual_screening = true)
    isPreOrder = (movie._is_preorder <> invalid AND movie._is_preorder = true)
    isRestoration = (movie.filters <> invalid AND movie.filters.is_restoration = true)

    ' Set streaming service badge (hidden for pre-orders — pre-order badge takes that spot)
    streaming = GetStreamingService(movie)
    if NOT isPreOrder AND streaming <> invalid AND streaming.service <> invalid
        SetupServiceBadge(streaming.service)
    else
        m.serviceBadge.visible = false
        m.serviceBadgeBg.visible = false
        m.serviceBadgeSubtext.visible = false
    end if

    ' Pre-order badge (top-right, replaces streaming badge)
    if isPreOrder
        m.preOrderBadgeLabel.text = "PRE"
        if movie.digital_date <> invalid AND movie.digital_date <> ""
            m.preOrderBadgeDate.text = FormatShortDate(movie.digital_date)
        else
            m.preOrderBadgeDate.text = "TBD"
        end if
        m.preOrderBadgeBg.visible = true
        m.preOrderBadgeLabel.visible = true
        m.preOrderBadgeDate.visible = true
    else
        m.preOrderBadgeBg.visible = false
        m.preOrderBadgeLabel.visible = false
        m.preOrderBadgeDate.visible = false
    end if

    ' Restoration badge (top-left)
    m.restorationBadgeBg.visible = isRestoration
    m.restorationBadgeLabel.visible = isRestoration

    ' Staff pick border + strip
    m.staffPickStrip.visible = isStaffPick
    m.staffPickBorder.visible = (isStaffPick AND NOT isScreening)

    ' Virtual screening treatment
    if isScreening AND NOT isStaffPick
        m.screeningBorder.visible = true
        m.screeningTopBannerBg.visible = true
        m.screeningTopBannerLabel.visible = true
        ' Festival name strip
        if movie.virtual_screening_info <> invalid AND movie.virtual_screening_info.screening_name <> invalid AND movie.virtual_screening_info.screening_name <> ""
            m.screeningFestivalLabel.text = movie.virtual_screening_info.screening_name
            m.screeningFestivalBg.visible = true
            m.screeningFestivalLabel.visible = true
        else
            m.screeningFestivalBg.visible = false
            m.screeningFestivalLabel.visible = false
        end if
    else
        m.screeningBorder.visible = false
        m.screeningTopBannerBg.visible = false
        m.screeningTopBannerLabel.visible = false
        m.screeningFestivalBg.visible = false
        m.screeningFestivalLabel.visible = false
    end if

    ' Set RT score badge
    if movie.rt_score <> invalid
        SetupRtBadge(movie.rt_score)
    else
        m.rtBadge.visible = false
        m.rtBadgeBg.visible = false
        m.rtBadgeBorder.visible = false
    end if

    ' Set Metacritic score badge
    if movie.metacritic_score <> invalid
        SetupMcBadge(movie.metacritic_score)
    else
        m.mcBadge.visible = false
        m.mcBadgeBg.visible = false
        m.mcBadgeBorder.visible = false
    end if

    ' Set IMDb rating badge
    if movie.imdb_rating <> invalid AND movie.imdb_rating <> ""
        SetupImdbBadge(movie.imdb_rating)
    else
        m.imdbBadge.visible = false
        m.imdbBadgeBg.visible = false
        m.imdbBadgeBorder.visible = false
    end if

    ' Shift score badges up if festival strip is visible at bottom
    if m.screeningFestivalBg.visible
        badgeY = 400
    else
        badgeY = 438
    end if
    PositionScoreBadges(badgeY)
End Sub

' ============================================================================
' Position score badges (RT, MC, IMDb) — right-aligned, shifted based on count
' ============================================================================
Sub PositionScoreBadges(baseY as Integer)
    ' Count visible badges and position right-to-left
    ' RT is rightmost, then IMDb, then MC
    xPos = 243

    if m.rtBadge.visible
        m.rtBadge.translation = [xPos, baseY]
        m.rtBadgeBg.translation = [xPos, baseY]
        m.rtBadgeBorder.translation = [xPos - 1, baseY - 1]
        xPos = xPos - 64  ' 70 width - 6 overlap
    end if

    if m.imdbBadge.visible
        m.imdbBadge.translation = [xPos, baseY]
        m.imdbBadgeBg.translation = [xPos, baseY]
        m.imdbBadgeBorder.translation = [xPos - 1, baseY - 1]
        xPos = xPos - 64  ' 58 width + 6 gap
    end if

    if m.mcBadge.visible
        m.mcBadge.translation = [xPos, baseY]
        m.mcBadgeBg.translation = [xPos, baseY]
        m.mcBadgeBorder.translation = [xPos - 1, baseY - 1]
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
    m.serviceBadgeSubtext.visible = true

    ' Set badge color
    if colors.DoesExist(normalized)
        m.serviceBadgeBg.color = colors[normalized]
    else
        m.serviceBadgeBg.color = "0xFF9500FF"  ' Default VOD color
    end if
    m.serviceBadgeBg.visible = true

    ' Light backgrounds (hulu, prime, pluto) need dark text
    if normalized = "hulu" OR normalized = "prime" OR normalized = "pluto"
        m.serviceBadge.color = "0x000000FF"
        m.serviceBadgeSubtext.color = "0x000000BF"
    else
        m.serviceBadge.color = "0xFFFFFFFF"
        m.serviceBadgeSubtext.color = "0xFFFFFFBF"
    end if

    ' Full-width bar — always 320px wide at top
    m.serviceBadge.width = 320
    m.serviceBadgeBg.width = 320
    m.serviceBadge.translation = [0, 2]
    m.serviceBadgeBg.translation = [0, 0]
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
    m.rtBadge.text = "RT " + scoreInt.ToStr() + "%"
    m.rtBadge.visible = true
    m.rtBadgeBg.visible = true
    m.rtBadgeBorder.visible = true
End Sub

' ============================================================================
' Setup Metacritic Score Badge
' ============================================================================
Sub SetupMcBadge(score as Dynamic)
    scoreInt = 0
    if Type(score) = "Integer" OR Type(score) = "roInt" OR Type(score) = "Float" OR Type(score) = "roFloat"
        scoreInt = Int(score)
    else if Type(score) = "String" OR Type(score) = "roString"
        scoreInt = Int(Val(score))
    else
        m.mcBadge.visible = false
        m.mcBadgeBg.visible = false
        return
    end if

    if scoreInt = 0
        m.mcBadge.visible = false
        m.mcBadgeBg.visible = false
        return
    end if

    m.mcBadge.text = "MC " + scoreInt.ToStr()
    m.mcBadge.visible = true
    m.mcBadgeBg.visible = true
    m.mcBadgeBorder.visible = true
End Sub

' ============================================================================
' Setup IMDb Rating Badge
' ============================================================================
Sub SetupImdbBadge(rating as Dynamic)
    ratingStr = ""
    if Type(rating) = "String" OR Type(rating) = "roString"
        ratingStr = rating
    else if Type(rating) = "Float" OR Type(rating) = "roFloat"
        ratingStr = Str(rating).Trim()
    else if Type(rating) = "Integer" OR Type(rating) = "roInt"
        ratingStr = Str(rating).Trim()
    else
        m.imdbBadge.visible = false
        m.imdbBadgeBg.visible = false
        return
    end if

    if ratingStr = "" OR ratingStr = "0"
        m.imdbBadge.visible = false
        m.imdbBadgeBg.visible = false
        return
    end if

    m.imdbBadge.text = ratingStr
    m.imdbBadge.visible = true
    m.imdbBadgeBg.visible = true
    m.imdbBadgeBorder.visible = true
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

' ============================================================================
' Show card as a date divider (mobile design: teal bar + chevrons)
' ============================================================================
Sub ShowAsDateDivider(data as Object)
    ' Hide movie card, show date divider
    m.cardContainer.visible = false
    m.directorLabel.visible = false
    m.dateDividerGroup.visible = true

    dateStr = ""
    if data.dateString <> invalid
        dateStr = data.dateString
    end if

    isPreOrder = (dateStr = "PRE-ORDER" OR dateStr = "pre-order")

    if isPreOrder
        m.dateDividerBar.color = "0x7C3AEDFF"
        m.dateDividerBarLabel.text = "PRE-ORDER"
        m.dateDividerNumber.text = "SOON"
        m.dateDividerNumber.color = "0x7C3AEDFF"
        m.dateDividerMonth.text = ""
        m.dateDividerMonth.visible = false

        purpleColors = ["0x7C3AEDE6", "0x7C3AEDB3", "0x7C3AED80", "0x7C3AED4D", "0x7C3AED26"]
        for i = 0 to 4
            m.dateDividerChevrons[i].color = purpleColors[i]
        end for
    else
        parts = dateStr.Split("-")
        if parts.Count() >= 3
            month = Val(parts[1])
            day = Val(parts[2])

            ' Get weekday
            weekday = ""
            try
                dt = CreateObject("roDateTime")
                dt.FromISO8601String(dateStr + "T12:00:00Z")
                dow = dt.GetDayOfWeek()
                days = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]
                weekday = days[dow]
            catch e
            end try

            months = ["", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
            monthName = ""
            if month >= 1 AND month <= 12
                monthName = months[month]
            end if

            m.dateDividerBar.color = "0x00D4AAFF"
            m.dateDividerBarLabel.text = weekday
            m.dateDividerNumber.text = day.ToStr()
            m.dateDividerNumber.color = "0xFFFFFFFF"
            m.dateDividerMonth.text = monthName
            m.dateDividerMonth.visible = true

            tealColors = ["0x00D4AAE6", "0x00D4AAB3", "0x00D4AA80", "0x00D4AA4D", "0x00D4AA26"]
            for i = 0 to 4
                m.dateDividerChevrons[i].color = tealColors[i]
            end for
        end if
    end if
End Sub
