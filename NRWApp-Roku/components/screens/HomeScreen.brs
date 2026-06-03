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

    ' Slop mode: free=hide slop, all=show all, only=show only slop
    if m.slopMode = "free"
        filtered = []
        for each movie in movies
            if movie.is_slop <> true AND movie._is_slop_guess <> true
                filtered.Push(movie)
            end if
        end for
        movies = filtered
    else if m.slopMode = "only"
        filtered = []
        for each movie in movies
            if movie.is_slop = true OR movie._is_slop_guess = true
                filtered.Push(movie)
            end if
        end for
        movies = filtered
    end if

    ' Hide-fest mode: hide virtual screenings
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
    end if

    ' Pre-orders: only show when toggle is ON (search always shows all)
    if NOT m.showPreorders
        filtered = []
        for each movie in movies
            isPreorder = (movie._is_preorder = true)
            if NOT isPreorder
                filtered.Push(movie)
            end if
        end for
        movies = filtered
    end if

    m.filteredMovies = movies

    ' Group by date
    grouped = GroupMoviesByDate(m.filteredMovies)

    ' Build content for grid
    BuildGridContent(grouped)
End Sub

' ============================================================================
' Build Grid Content
' ============================================================================
Sub BuildGridContent(groupedData as Object)
    content = CreateObject("roSGNode", "ContentNode")

    ' Add movies to content with date divider cards
    for each dateStr in groupedData.dates
        movies = groupedData.groups[dateStr]

        ' Insert date divider card
        divider = content.CreateChild("ContentNode")
        divider.AddFields({
            movie: {
                _type: "date-divider"
                dateString: dateStr
            }
        })

        for each movie in movies
            cardTitle = movie.title
            if movie.display_title <> invalid AND movie.display_title <> ""
                cardTitle = movie.display_title
            end if
            item = content.CreateChild("ContentNode")
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
        m.filterBar.slopMode = m.slopMode
        ApplyFilters()
        return
    end if

    ' Fest toggle is separate from category filters
    if filterId = "hide_fest"
        m.hideFest = NOT m.hideFest
        m.filterBar.hideFest = m.hideFest
        ApplyFilters()
        return
    end if

    ' Pre-orders toggle is separate from category filters
    if filterId = "show_preorders"
        m.showPreorders = NOT m.showPreorders
        m.filterBar.showPreorders = m.showPreorders
        ApplyFilters()
        return
    end if

    ' Toggle filter in array
    index = ArrayIndexOf(m.activeFilters, filterId)
    if index >= 0
        m.activeFilters.Delete(index)
    else
        m.activeFilters.Push(filterId)
    end if

    ' Update filter bar visual state
    m.filterBar.activeFilters = m.activeFilters

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
    ' Could add analytics or prefetching here
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

' ============================================================================
' Filter Description (shown when exactly 1 filter active)
' ============================================================================
Function GetFilterDescriptions() as Object
    return {
        staff_picks:   { title: "PICKS",       text: "The ones we're vouching for. Out of everything on the wall, these are the movies we think are genuinely worth your time." }
        indie:         { title: "INDIE",        text: "The smaller films, the independents, the ones without a billboard campaign. Worth knowing about now that they're available to stream at home." }
        horror:        { title: "HORROR",       text: "The stuff that goes bump. Horror films now streaming — from slow-burn dread to full-on splatter." }
        action:        { title: "ACTION",       text: "High-octane, kinetic filmmaking. Action movies now available to watch at home." }
        comedy:        { title: "COMEDY",       text: "Films that are actually funny. Comedies — broad and subtle — now streaming." }
        family:        { title: "FAMILY",       text: "Films for all ages. Family movies now available to watch at home." }
        foreign:       { title: "FOREIGN",      text: "Non-English language films from around the world. Subtitles and the fact that they're streaming now." }
        documentary:   { title: "DOCUMENTARY",  text: "Non-fiction filmmaking. Documentaries covering real stories, real people, and real events — now available to stream at home." }
        restorations:  { title: "REISSUES",     text: "Classic and catalog titles with new digital life. Restored, remastered, or newly reissued on streaming platforms. Old movies, fresh transfers." }
    }
End Function

Sub UpdateFilterDescription()
    if m.filterDescGroup = invalid
        return
    end if
    if m.activeFilters.Count() = 1
        descs = GetFilterDescriptions()
        filterId = m.activeFilters[0]
        if descs.DoesExist(filterId)
            d = descs[filterId]
            m.filterDescTitle.text = d.title
            m.filterDescText.text = d.text
            m.filterDescGroup.visible = true
        else
            m.filterDescGroup.visible = false
        end if
    else
        m.filterDescGroup.visible = false
    end if
End Sub
