' ============================================================================
' NRW Home Screen
' Main screen with 8-column movie grid
' ============================================================================

Sub Init()
    ' UI references
    m.background = m.top.FindNode("background")
    m.header = m.top.FindNode("header")
    m.titleLabel = m.top.FindNode("titleLabel")
    m.filterBar = m.top.FindNode("filterBar")
    m.filterDescGroup = m.top.FindNode("filterDescGroup")
    m.filterDescTitle = m.top.FindNode("filterDescTitle")
    m.filterDescText = m.top.FindNode("filterDescText")
    m.movieGrid = m.top.FindNode("movieGrid")
    m.dateHud = m.top.FindNode("dateHud")
    m.dateHudTop = m.top.FindNode("dateHudTop")
    m.dateHudBottom = m.top.FindNode("dateHudBottom")
    m.dateHudDay = m.top.FindNode("dateHudDay")
    m.dateHudRest = m.top.FindNode("dateHudRest")
    m.loadingGroup = m.top.FindNode("loadingGroup")
    m.errorGroup = m.top.FindNode("errorGroup")
    m.trailersButton = m.top.FindNode("trailersButton")
    m.detailScreen = m.top.FindNode("detailScreen")

    ' State
    m.allMovies = []
    m.filteredMovies = []
    m.activeFilters = []
    m.slopMode = "free"
    m.showPreorders = false
    m.hideFest = true
    m.showHighlightsOnly = false
    m.itemStrips = []
    m.dateStripColor = "0x00D4AAFF"
    m.focusedArea = "grid"  ' "filter", "grid", or "detail"

    ' Set up observers
    m.filterBar.ObserveField("selectedFilter", "onFilterSelected")
    m.movieGrid.ObserveField("itemSelected", "onMovieSelected")
    m.movieGrid.ObserveField("itemFocused", "onMovieFocused")

    ' Load movies
    LoadMovies(false)

    ' Set initial focus
    m.top.SetFocus(true)
End Sub

' ============================================================================
' Load Movies from API
' ============================================================================
Sub LoadMovies(forceRefresh as Boolean)
    ShowLoading(true)
    HideError()

    ' Create task for async data fetching
    m.fetchTask = CreateObject("roSGNode", "FetchMoviesTask")
    m.fetchTask.ObserveField("result", "onMoviesLoaded")
    m.fetchTask.forceRefresh = forceRefresh
    m.fetchTask.control = "run"
End Sub

' ============================================================================
' Movies Loaded Callback
' ============================================================================
Sub onMoviesLoaded()
    result = m.fetchTask.result
    ShowLoading(false)

    if result = invalid OR NOT result.success
        ShowError(result.error)
        return
    end if

    ' Extract and store movies
    m.allMovies = ExtractMovies(result.data)

    if m.allMovies.Count() = 0
        ShowError("No movies available")
        return
    end if

    ' Sync filter bar visual state before applying filters
    m.filterBar.slopMode = m.slopMode
    m.filterBar.hideFest = m.hideFest
    m.filterBar.showHighlights = m.showHighlightsOnly

    ' Apply initial filter
    ApplyFilters()

    ' Show grid
    m.movieGrid.visible = true
    m.trailersButton.visible = false  ' Trailers card temporarily disabled — set true to restore

    ' Restore last focus position
    lastIndex = GetFocusIndex()
    if lastIndex > 0 AND lastIndex < m.filteredMovies.Count()
        m.movieGrid.jumpToItem = lastIndex
    end if

    ' Set focus to grid
    m.movieGrid.SetFocus(true)
    m.focusedArea = "grid"
End Sub

' ============================================================================
' Apply Filters (multi-select with OR logic)
' ============================================================================
Sub ApplyFilters()
    ' Filter movies using multi-select OR logic
    movies = FilterMoviesMulti(m.allMovies, m.activeFilters)

    ' Slop mode: free=hide slop, only=show only slop. Fests/pre-orders are exempt
    ' when their view is on (matches tvOS/desktop — you asked to see all of them).
    if m.slopMode = "free"
        filtered = []
        for each movie in movies
            isVS = false
            if movie.filters <> invalid
                isVS = (movie.filters.is_virtual_screening = true)
            end if
            keep = (movie.is_slop <> true AND movie._is_slop_guess <> true)
            if (NOT m.hideFest) AND isVS then keep = true
            if m.showPreorders AND movie._is_preorder = true then keep = true
            if keep
                filtered.Push(movie)
            end if
        end for
        movies = filtered
    else if m.slopMode = "only"
        filtered = []
        for each movie in movies
            isVS = false
            if movie.filters <> invalid
                isVS = (movie.filters.is_virtual_screening = true)
            end if
            keep = (movie.is_slop = true OR movie._is_slop_guess = true)
            if (NOT m.hideFest) AND isVS then keep = true
            if m.showPreorders AND movie._is_preorder = true then keep = true
            if keep
                filtered.Push(movie)
            end if
        end for
        movies = filtered
    end if

    ' Fests view is exclusive: ON (hideFest=false) => only LIVE virtual screenings
    ' (drop expired); OFF (hideFest=true) => hide them entirely (matches tvOS/desktop).
    if m.hideFest
        filtered = []
        for each movie in movies
            isVS = false
            if movie.filters <> invalid
                isVS = (movie.filters.is_virtual_screening = true)
            end if
            if NOT isVS
                filtered.Push(movie)
            end if
        end for
        movies = filtered
    else
        dt = CreateObject("roDateTime")
        today = Left(dt.GetISO8601(), 10)
        filtered = []
        for each movie in movies
            isVS = false
            if movie.filters <> invalid
                isVS = (movie.filters.is_virtual_screening = true)
            end if
            if isVS
                expired = false
                if movie.virtual_screening_info <> invalid
                    if movie.virtual_screening_info.status = "expired" then expired = true
                    endStr = movie.virtual_screening_info.available_end
                    if endStr <> invalid AND endStr <> ""
                        if Left(endStr, 10) < today then expired = true
                    end if
                end if
                if NOT expired
                    filtered.Push(movie)
                end if
            end if
        end for
        movies = filtered
    end if

    ' Pre-order view is exclusive: ON => only pre-orders; OFF => hide them (matches desktop).
    filtered = []
    for each movie in movies
        isPreorder = (movie._is_preorder = true)
        if m.showPreorders
            if isPreorder then filtered.Push(movie)
        else
            if NOT isPreorder then filtered.Push(movie)
        end if
    end for
    movies = filtered

    ' Highlights mode: only staff picks
    if m.showHighlightsOnly
        filtered = []
        for each movie in movies
            if IsStaffPick(movie)
                filtered.Push(movie)
            end if
        end for
        movies = filtered
    end if

    ' Group by date (FEST section first, then dates, PRE-ORDER last).
    ' In SELECTS mode, all regular picks collapse into one HIGHLIGHTS section.
    grouped = GroupMoviesByDate(movies, m.showHighlightsOnly)

    ' Flatten back in display order so grid item indices map 1:1 onto m.filteredMovies.
    ' itemStrips records each item's date group for the heads-up banner.
    flattened = []
    itemStrips = []
    for each dateStr in grouped.dates
        for each movie in grouped.groups[dateStr]
            flattened.Push(movie)
            itemStrips.Push(dateStr)
        end for
    end for
    m.filteredMovies = flattened
    m.itemStrips = itemStrips

    ' Date strips adopt the single active filter's color (HIGHLIGHTS mode goes crimson)
    UpdateSectionDividerColor()

    ' Build content for grid
    BuildGridContent(grouped)

    ' Sync the heads-up banner to the focused (or first) item
    UpdateDateHud(m.movieGrid.itemFocused)
End Sub

' ============================================================================
' Section Divider Color (strip color follows active filter / highlights mode)
' ============================================================================
Sub UpdateSectionDividerColor()
    stripColors = {
        indie: "0x00D4AAFF"
        horror: "0xFF5E57FF"
        action: "0xFF9500FF"
        comedy: "0xFFD32AFF"
        family: "0x2ED573FF"
        thriller: "0xD63031FF"
        foreign: "0xE84393FF"
        documentary: "0x4A90D9FF"
        restorations: "0xC8A951FF"
    }
    color = "0x00D4AAFF"  ' default teal
    if m.showHighlightsOnly
        color = "0x00D4AAFF"  ' crimson
    else if m.hideFest = false
        color = "0xF59E0BFF"  ' fest amber
    else if m.slopMode = "only"
        color = "0xFF9500FF"  ' slop orange
    else if m.activeFilters.Count() = 1 AND stripColors.DoesExist(m.activeFilters[0])
        color = stripColors[m.activeFilters[0]]
    end if
    m.dateStripColor = color
    m.movieGrid.sectionDividerTextColor = color
End Sub

' ============================================================================
' Heads-up Date Banner — neon bar above the grid that always shows the date
' group of the focused row (Roku's answer to the web's sticky banners)
' ============================================================================
Sub UpdateDateHud(index as Integer)
    if m.dateHud = invalid then return
    if m.itemStrips = invalid OR m.itemStrips.Count() = 0 OR m.filteredMovies.Count() = 0
        m.dateHud.visible = false
        return
    end if
    if index < 0 then index = 0
    if index >= m.itemStrips.Count() then index = m.itemStrips.Count() - 1
    key = m.itemStrips[index]

    day = ""
    rest = ""
    color = m.dateStripColor
    if key = "FEST"
        day = "FEST"
        rest = "NOW SCREENING"
        color = "0xF59E0BFF"
    else if key = "PRE-ORDER"
        day = "PRE-ORDER"
        rest = "COMING SOON"
        color = "0x7C3AEDFF"
    else if key = "HIGHLIGHTS"
        day = "SELECTS"
        rest = "OF NOTE"
        color = "0x00D4AAFF"
    else if key = "Unknown"
        day = "DATE TBD"
    else
        days = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]
        dt = CreateObject("roDateTime")
        dt.FromISO8601String(key)
        day = days[dt.GetDayOfWeek()]
        rest = UCase(FormatShortDate(key))
    end if
    if m.showHighlightsOnly then color = "0x00D4AAFF"

    m.dateHudDay.text = day
    m.dateHudRest.text = rest
    if rest = ""
        m.dateHudDay.width = 1780
        m.dateHudDay.horizAlign = "center"
        m.dateHudRest.visible = false
    else
        m.dateHudDay.width = 876
        m.dateHudDay.horizAlign = "right"
        m.dateHudRest.visible = true
    end if
    ' Section banners (the active view) use the largest system font so they read
    ' bigger than the per-date dividers. (The in-grid MarkupGrid dividers share one
    ' uniform style on Roku, so the focus HUD carries the size distinction.)
    isSection = (key = "FEST" OR key = "PRE-ORDER" OR key = "HIGHLIGHTS")
    if isSection
        m.dateHudDay.font = "font:LargeBoldSystemFont"
        m.dateHudRest.font = "font:LargeSystemFont"
    else
        m.dateHudDay.font = "font:MediumBoldSystemFont"
        m.dateHudRest.font = "font:MediumSystemFont"
    end if

    m.dateHudDay.color = color
    m.dateHudTop.color = color
    m.dateHudBottom.color = color
    m.dateHud.visible = true
End Sub

' ============================================================================
' Build Grid Content — date groups become native MarkupGrid sections, whose
' dividers render as full-width strips (label + line) instead of poster cells
' ============================================================================
Sub BuildGridContent(groupedData as Object)
    content = CreateObject("roSGNode", "ContentNode")

    for each dateStr in groupedData.dates
        section = content.CreateChild("ContentNode")
        section.contentType = "SECTION"
        section.title = FormatSectionTitle(dateStr)

        for each movie in groupedData.groups[dateStr]
            cardTitle = movie.title
            if movie.display_title <> invalid AND movie.display_title <> ""
                cardTitle = movie.display_title
            end if
            item = section.CreateChild("ContentNode")
            item.AddFields({
                movie: movie
                title: cardTitle
                posterUrl: movie.poster
            })
        end for
    end for

    m.movieGrid.content = content
End Sub

' ============================================================================
' Section Title (strip label): "WED · JUN 10", "FEST · NOW SCREENING", etc.
' ============================================================================
Function FormatSectionTitle(dateStr as String) as String
    if dateStr = "PRE-ORDER"
        return "PRE-ORDER"
    else if dateStr = "FEST"
        return "FEST · NOW SCREENING"
    else if dateStr = "HIGHLIGHTS"
        return "SELECTS  ·  OF NOTE"
    else if dateStr = "Unknown"
        return "DATE TBD"
    end if

    days = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]
    dt = CreateObject("roDateTime")
    dt.FromISO8601String(dateStr)
    weekday = days[dt.GetDayOfWeek()]
    return weekday + "  ·  " + UCase(FormatShortDate(dateStr))
End Function

' ============================================================================
' Exclusive View Selector
' View toggles (Selects / Fests / Pre-Orders) are mutually exclusive: at most one
' is active. winner is "selects", "fests", "preorders", or "none".
' (hideFest is inverted — fests are shown only for "fests".)
' ============================================================================
Sub SetExclusiveView(winner as String)
    m.showHighlightsOnly = (winner = "selects")
    m.hideFest = (winner <> "fests")
    m.showPreorders = (winner = "preorders")
    ' Toggles clear genre filters + slop so only one thing is ever active.
    m.slopMode = "free"
    m.activeFilters = []
    m.filterBar.showHighlights = m.showHighlightsOnly
    m.filterBar.hideFest = m.hideFest
    m.filterBar.showPreorders = m.showPreorders
    m.filterBar.slopMode = m.slopMode
    m.filterBar.activeFilters = m.activeFilters
    UpdateFilterDescription()
    ApplyFilters()
End Sub

' ============================================================================
' Filter Selected Callback
' ============================================================================
Sub onFilterSelected()
    filterId = m.filterBar.selectedFilter

    ' Slop toggle cycles: free → all → only → free
    if filterId = "slop_free"
        if m.slopMode = "free"
            m.slopMode = "all"
        else if m.slopMode = "all"
            m.slopMode = "only"
        else
            m.slopMode = "free"
        end if
        ' Slop is part of the exclusive group: clear genre filters, and (for a
        ' non-free state) the other view toggles.
        m.activeFilters = []
        if m.slopMode <> "free"
            m.showHighlightsOnly = false
            m.hideFest = true
            m.showPreorders = false
            m.filterBar.showHighlights = m.showHighlightsOnly
            m.filterBar.hideFest = m.hideFest
            m.filterBar.showPreorders = m.showPreorders
        end if
        m.filterBar.slopMode = m.slopMode
        m.filterBar.activeFilters = m.activeFilters
        UpdateFilterDescription()
        ApplyFilters()
        return
    end if

    ' View toggles (Selects / Fests / Pre-Orders) are mutually exclusive — each
    ' tap either makes its view the winner or, if already on, returns to "none".
    if filterId = "hide_fest"
        if m.hideFest
            SetExclusiveView("fests")
        else
            SetExclusiveView("none")
        end if
        return
    end if

    if filterId = "show_preorders"
        if m.showPreorders
            SetExclusiveView("none")
        else
            SetExclusiveView("preorders")
        end if
        return
    end if

    if filterId = "show_highlights"
        if m.showHighlightsOnly
            SetExclusiveView("none")
        else
            SetExclusiveView("selects")
        end if
        return
    end if

    ' Genres are single-select: a genre replaces any current genre (tap again clears).
    index = ArrayIndexOf(m.activeFilters, filterId)
    if index >= 0 AND m.activeFilters.Count() = 1
        m.activeFilters = []
    else
        m.activeFilters = [filterId]
    end if

    ' Picking a genre clears the view toggles — only one filter OR one toggle at a time.
    m.slopMode = "free"
    m.showHighlightsOnly = false
    m.hideFest = true
    m.showPreorders = false

    ' Update filter bar visual state
    m.filterBar.activeFilters = m.activeFilters
    m.filterBar.slopMode = m.slopMode
    m.filterBar.showHighlights = m.showHighlightsOnly
    m.filterBar.hideFest = m.hideFest
    m.filterBar.showPreorders = m.showPreorders

    UpdateFilterDescription()
    ApplyFilters()
End Sub

' ============================================================================
' Array Index Of Helper
' ============================================================================
Function ArrayIndexOf(arr as Object, value as String) as Integer
    for i = 0 to arr.Count() - 1
        if arr[i] = value
            return i
        end if
    end for
    return -1
End Function

' ============================================================================
' Movie Selected Callback
' ============================================================================
Sub onMovieSelected()
    index = m.movieGrid.itemSelected

    if index < 0 OR index >= m.filteredMovies.Count()
        return
    end if

    ' Save focus position
    SaveFocusIndex(index)

    ' Show detail screen
    ShowDetailScreen(index)
End Sub

' ============================================================================
' Movie Focused Callback
' ============================================================================
Sub onMovieFocused()
    UpdateDateHud(m.movieGrid.itemFocused)
End Sub

' ============================================================================
' Show Detail Screen
' ============================================================================
Sub ShowDetailScreen(index as Integer)
    m.detailScreen.movies = m.filteredMovies
    m.detailScreen.currentIndex = index
    m.detailScreen.visible = true
    m.detailScreen.SetFocus(true)

    m.focusedArea = "detail"

    ' Observe detail screen close
    m.detailScreen.ObserveField("closed", "onDetailClosed")
End Sub

' ============================================================================
' Detail Screen Closed
' ============================================================================
Sub onDetailClosed()
    m.detailScreen.visible = false
    m.movieGrid.SetFocus(true)
    m.focusedArea = "grid"
End Sub

' ============================================================================
' Deep Link Handler
' ============================================================================
Sub onDeepLink()
    movieId = m.top.deepLinkMovieId
    if movieId = "" OR movieId = invalid
        return
    end if

    ' Find movie by ID
    for i = 0 to m.filteredMovies.Count() - 1
        movie = m.filteredMovies[i]
        if movie.id.ToStr() = movieId OR movie.tmdb_id.ToStr() = movieId
            ShowDetailScreen(i)
            return
        end if
    end for
End Sub

' ============================================================================
' UI State Helpers
' ============================================================================
Sub ShowLoading(show as Boolean)
    m.loadingGroup.visible = show
    if show
        m.movieGrid.visible = false
        m.trailersButton.visible = false
        if m.dateHud <> invalid then m.dateHud.visible = false
    end if
End Sub

Sub ShowError(message as String)
    m.errorGroup.visible = true
    errorLabel = m.top.FindNode("errorLabel")
    if message <> "" AND message <> invalid
        errorLabel.text = message
    else
        errorLabel.text = "Failed to load movies"
    end if
End Sub

Sub HideError()
    m.errorGroup.visible = false
End Sub

' ============================================================================
' Key Event Handler
' ============================================================================
Function OnKeyEvent(key as String, press as Boolean) as Boolean
    if NOT press
        return false
    end if

    ' Handle based on focused area
    if m.focusedArea = "detail"
        ' Detail screen handles its own keys
        return false

    else if m.focusedArea = "filter"
        if key = "down"
            m.movieGrid.SetFocus(true)
            m.focusedArea = "grid"
            return true
        else if key = "back"
            ' Go to grid
            m.movieGrid.SetFocus(true)
            m.focusedArea = "grid"
            return true
        end if

    else if m.focusedArea = "grid"
        if key = "up"
            ' Check if at top row
            focusedIndex = m.movieGrid.itemFocused
            if focusedIndex < 5  ' First row
                m.filterBar.SetFocus(true)
                m.filterBar.hasFocus = true
                m.focusedArea = "filter"
                return true
            end if
        else if key = "back"
            ' Exit app (or go back if there's history)
            return false
        else if key = "play"
            ' Refresh data
            LoadMovies(true)
            return true
        else if key = "options"
            ' Show filter bar
            m.filterBar.SetFocus(true)
            m.filterBar.hasFocus = true
            m.focusedArea = "filter"
            return true
        end if
    end if

    return false
End Function

' ============================================================================
' Focus Changed
' ============================================================================
Sub OnFocusChanged()
    if m.top.hasFocus
        if m.focusedArea = "grid"
            m.movieGrid.SetFocus(true)
        else if m.focusedArea = "filter"
            m.filterBar.SetFocus(true)
        end if
    end if
End Sub

Sub UpdateFilterDescription()
    ' Filter description blurbs removed (matches tvOS — no genre/view descriptions).
    if m.filterDescGroup <> invalid
        m.filterDescGroup.visible = false
    end if
End Sub
