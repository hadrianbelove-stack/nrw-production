' ============================================================================
' NRW Detail Screen
' Full-screen movie details
' ============================================================================

Sub Init()
    ' UI references
    m.background = m.top.FindNode("background")
    m.backdrop = m.top.FindNode("backdrop")
    m.moviePoster = m.top.FindNode("moviePoster")
    m.posterBorder = m.top.FindNode("posterBorder")

    m.titleLabel = m.top.FindNode("titleLabel")
    m.dateLabel = m.top.FindNode("dateLabel")
    m.metadataLabel = m.top.FindNode("metadataLabel")
    m.genresLabel = m.top.FindNode("genresLabel")
    m.castLabel = m.top.FindNode("castLabel")
    m.languageLabel = m.top.FindNode("languageLabel")
    m.synopsisLabel = m.top.FindNode("synopsisLabel")

    m.staffPickBadge = m.top.FindNode("staffPickBadge")
    m.staffPickLabel = m.top.FindNode("staffPickLabel")
    m.restorationBadge = m.top.FindNode("restorationBadge")
    m.restorationLabel = m.top.FindNode("restorationLabel")

    m.buttonsRow = m.top.FindNode("buttonsRow")
    m.trailerButton = m.top.FindNode("trailerButton")
    m.streamButton = m.top.FindNode("streamButton")
    m.vodButton1 = m.top.FindNode("vodButton1")
    m.vodButton2 = m.top.FindNode("vodButton2")
    m.plexButton = m.top.FindNode("plexButton")

    m.leftChevron = m.top.FindNode("leftChevron")
    m.rightChevron = m.top.FindNode("rightChevron")
    m.counterLabel = m.top.FindNode("counterLabel")

    ' State
    m.movies = []
    m.currentIndex = 0
    m.focusedButtonIndex = 0
    m.buttons = []

    ' Set up button observers
    m.trailerButton.ObserveField("selected", "onTrailerSelected")
    m.streamButton.ObserveField("selected", "onStreamSelected")
    m.vodButton1.ObserveField("selected", "onVod1Selected")
    m.vodButton2.ObserveField("selected", "onVod2Selected")
    m.plexButton.ObserveField("selected", "onPlexSelected")
End Sub

' ============================================================================
' Movies Array Changed
' ============================================================================
Sub onMoviesChanged()
    m.movies = m.top.movies
    if m.movies <> invalid AND m.movies.Count() > 0
        LoadMovie(m.currentIndex)
    end if
End Sub

' ============================================================================
' Current Index Changed
' ============================================================================
Sub onIndexChanged()
    m.currentIndex = m.top.currentIndex
    LoadMovie(m.currentIndex)
End Sub

' ============================================================================
' Load Movie Data
' ============================================================================
Sub LoadMovie(index as Integer)
    if m.movies = invalid OR index < 0 OR index >= m.movies.Count()
        return
    end if

    movie = m.movies[index]
    colors = GetColors()

    ' Update counter
    m.counterLabel.text = (index + 1).ToStr() + " / " + m.movies.Count().ToStr()

    ' Update chevron visibility
    m.leftChevron.visible = (index > 0)
    m.rightChevron.visible = (index < m.movies.Count() - 1)

    ' Set poster
    if movie.poster <> invalid AND movie.poster <> ""
        m.moviePoster.uri = movie.poster
    else if movie.poster_url <> invalid
        m.moviePoster.uri = movie.poster_url
    end if

    ' Set title
    m.titleLabel.text = movie.title
    if movie.year <> invalid
        m.titleLabel.text = movie.title + " (" + movie.year.ToStr() + ")"
    end if

    ' Set release date
    if movie.digital_date <> invalid AND movie.digital_date <> ""
        m.dateLabel.text = FormatShortDate(movie.digital_date)
    else
        m.dateLabel.text = ""
    end if

    ' Build metadata line
    metaParts = []

    director = GetDirector(movie)
    if director <> ""
        metaParts.Push(director)
    end if

    if movie.country <> invalid AND movie.country <> ""
        metaParts.Push(FormatCountry(movie.country))
    end if

    if movie.runtime <> invalid
        metaParts.Push(FormatRuntime(movie.runtime))
    end if

    if movie.rt_score <> invalid
        scoreStr = movie.rt_score.ToStr()
        scoreStr = scoreStr.Replace("%", "")
        scoreNum = Val(scoreStr)
        if scoreNum > 0
            metaParts.Push(Int(scoreNum).ToStr() + "% RT")
        end if
    end if

    m.metadataLabel.text = metaParts.Join(" • ")

    ' Set genres
    if movie.genres <> invalid AND movie.genres.Count() > 0
        m.genresLabel.text = movie.genres.Join(", ")
        m.genresLabel.visible = true
    else
        m.genresLabel.visible = false
    end if

    ' Set cast
    castArray = GetCast(movie)
    if castArray <> invalid AND castArray.Count() > 0
        ' Take first 2 cast members
        castNames = []
        for i = 0 to 1
            if i < castArray.Count()
                castNames.Push(castArray[i])
            end if
        end for
        m.castLabel.text = "Starring: " + castNames.Join(", ")
        m.castLabel.visible = true
    else
        m.castLabel.visible = false
    end if

    ' Set language (only if not English)
    if movie.original_language <> invalid AND movie.original_language <> "en" AND movie.original_language <> ""
        m.languageLabel.text = "Language: " + UCase(movie.original_language)
        m.languageLabel.visible = true
    else
        m.languageLabel.visible = false
    end if

    ' Set synopsis
    if movie.synopsis <> invalid AND movie.synopsis <> ""
        m.synopsisLabel.text = movie.synopsis
    else
        m.synopsisLabel.text = "No synopsis available."
    end if

    ' Staff pick badge
    if IsStaffPick(movie)
        m.staffPickBadge.visible = true
        m.staffPickLabel.visible = true
        m.posterBorder.color = "0xDC143CFF"  ' Red border for staff picks
    else
        m.staffPickBadge.visible = false
        m.staffPickLabel.visible = false
        m.posterBorder.color = "0x00D4AA40"  ' Teal border
    end if

    ' Restoration badge
    if movie.categories <> invalid AND movie.categories.is_restoration = true
        m.restorationBadge.visible = true
        m.restorationLabel.visible = true
    else
        m.restorationBadge.visible = false
        m.restorationLabel.visible = false
    end if

    ' Setup watch buttons
    SetupWatchButtons(movie)
End Sub

' ============================================================================
' Setup Watch Buttons
' ============================================================================
Sub SetupWatchButtons(movie as Object)
    m.buttons = []

    ' Trailer button
    trailerUrl = GetTrailerUrl(movie)
    if trailerUrl <> ""
        m.trailerButton.url = trailerUrl
        m.trailerButton.visible = true
        m.buttons.Push(m.trailerButton)
    else
        m.trailerButton.visible = false
    end if

    ' Streaming button
    streaming = GetStreamingService(movie)
    if streaming <> invalid AND streaming.service <> invalid
        m.streamButton.service = streaming.service
        m.streamButton.label = GetServiceDisplayName(streaming.service)
        m.streamButton.url = streaming.link
        m.streamButton.visible = true
        m.buttons.Push(m.streamButton)
    else
        m.streamButton.visible = false
    end if

    ' VOD buttons (up to 2: Amazon + Apple TV)
    vodServices = GetVodServices(movie)
    vodButtons = [m.vodButton1, m.vodButton2]
    for i = 0 to 1
        if i < vodServices.Count() AND vodServices[i].service <> invalid
            vodButtons[i].service = vodServices[i].service
            vodButtons[i].label = "Rent on " + GetServiceDisplayName(vodServices[i].service)
            vodButtons[i].url = vodServices[i].link
            vodButtons[i].visible = true
            m.buttons.Push(vodButtons[i])
        else
            vodButtons[i].visible = false
        end if
    end for

    ' Plex button
    plexLink = GetPlexDeepLink(movie)
    if plexLink <> ""
        m.plexButton.url = plexLink
        m.plexButton.visible = true
        m.buttons.Push(m.plexButton)
    else
        m.plexButton.visible = false
    end if

    ' Set initial focus
    m.focusedButtonIndex = 0
    UpdateButtonFocus()
End Sub

' ============================================================================
' Update Button Focus State
' ============================================================================
Sub UpdateButtonFocus()
    for i = 0 to m.buttons.Count() - 1
        button = m.buttons[i]
        if i = m.focusedButtonIndex
            button.focusPercent = 1.0
        else
            button.focusPercent = 0.0
        end if
    end for
End Sub

' ============================================================================
' Button Selection Handlers
' ============================================================================
Sub onTrailerSelected()
    trailerUrl = m.trailerButton.url
    if trailerUrl <> ""
        OpenTrailer(trailerUrl)
    end if
End Sub

Sub onStreamSelected()
    service = m.streamButton.service
    url = m.streamButton.url
    if service <> "" AND url <> ""
        LaunchStreamingService(service, url)
    end if
End Sub

Sub onVod1Selected()
    service = m.vodButton1.service
    url = m.vodButton1.url
    if service <> "" AND url <> ""
        LaunchStreamingService(service, url)
    end if
End Sub

Sub onVod2Selected()
    service = m.vodButton2.service
    url = m.vodButton2.url
    if service <> "" AND url <> ""
        LaunchStreamingService(service, url)
    end if
End Sub

Sub onPlexSelected()
    url = m.plexButton.url
    if url <> ""
        LaunchStreamingService("plex", url)
    end if
End Sub

' ============================================================================
' Key Event Handler
' ============================================================================
Function OnKeyEvent(key as String, press as Boolean) as Boolean
    if NOT press
        return false
    end if

    if key = "back"
        ' Close detail screen
        m.top.closed = true
        return true

    else if key = "left"
        ' Navigate to previous movie or button
        if m.focusedButtonIndex > 0
            m.focusedButtonIndex = m.focusedButtonIndex - 1
            UpdateButtonFocus()
        else if m.currentIndex > 0
            m.currentIndex = m.currentIndex - 1
            m.top.currentIndex = m.currentIndex
            LoadMovie(m.currentIndex)
        end if
        return true

    else if key = "right"
        ' Navigate to next movie or button
        if m.focusedButtonIndex < m.buttons.Count() - 1
            m.focusedButtonIndex = m.focusedButtonIndex + 1
            UpdateButtonFocus()
        else if m.currentIndex < m.movies.Count() - 1
            m.currentIndex = m.currentIndex + 1
            m.top.currentIndex = m.currentIndex
            LoadMovie(m.currentIndex)
        end if
        return true

    else if key = "up"
        ' Could navigate to other UI elements
        return false

    else if key = "down"
        ' Could navigate to buttons
        return false

    else if key = "OK"
        ' Activate focused button
        if m.focusedButtonIndex >= 0 AND m.focusedButtonIndex < m.buttons.Count()
            button = m.buttons[m.focusedButtonIndex]
            button.selected = true
        end if
        return true

    else if key = "play"
        ' Play trailer if available
        trailerUrl = m.trailerButton.url
        if trailerUrl <> ""
            OpenTrailer(trailerUrl)
            return true
        end if

    else if key = "rewind"
        ' Previous movie
        if m.currentIndex > 0
            m.currentIndex = m.currentIndex - 1
            m.top.currentIndex = m.currentIndex
            LoadMovie(m.currentIndex)
            return true
        end if

    else if key = "fastforward"
        ' Next movie
        if m.currentIndex < m.movies.Count() - 1
            m.currentIndex = m.currentIndex + 1
            m.top.currentIndex = m.currentIndex
            LoadMovie(m.currentIndex)
            return true
        end if
    end if

    return false
End Function
