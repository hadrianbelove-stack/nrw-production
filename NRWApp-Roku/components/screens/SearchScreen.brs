' ============================================================================
' NRW Search Screen
' Two modes on one overlay:
'   TYPE   — the on-screen keyboard (spans most of the screen); live result count.
'            Press DOWN to browse. (The Roku Keyboard releases Down at its bottom row.)
'   BROWSE — keyboard hidden, results get the full screen as a 5-wide grid (like the
'            wall). UP or BACK returns to typing; OK opens a movie's detail.
' Searches title / director / country / cast.
' ============================================================================

Sub Init()
    m.kbd = m.top.FindNode("kbd")
    m.resultsGrid = m.top.FindNode("resultsGrid")
    m.resultCount = m.top.FindNode("resultCount")
    m.noResults = m.top.FindNode("noResults")
    m.hint = m.top.FindNode("searchHint")
    m.searchTitle = m.top.FindNode("searchTitle")

    ' Bundled Lato fonts (match tvOS)
    f = Fonts()
    if m.searchTitle <> invalid then m.searchTitle.font = f.detailTitle
    m.resultCount.font = f.body
    m.noResults.font = f.body
    m.hint.font = f.body

    m.allMovies = []
    m.results = []
    m.mode = "type"

    m.kbd.ObserveField("text", "onQueryChanged")
    m.resultsGrid.ObserveField("itemSelected", "onResultSelected")
End Sub

' Parent passes the searchable set; reset to a clean TYPE state.
Sub onAllMoviesChanged()
    m.allMovies = m.top.allMovies
    m.kbd.text = ""
    m.results = []
    m.resultsGrid.content = invalid
    m.resultCount.text = ""
    m.noResults.text = ""
    EnterTypeMode()
End Sub

' ============================================================================
' Mode transitions
' ============================================================================
Sub EnterTypeMode()
    m.mode = "type"
    m.resultsGrid.visible = false
    m.noResults.visible = false
    m.kbd.visible = true
    m.hint.text = "Type below  ·  DOWN to browse results  ·  BACK to close"
    m.kbd.SetFocus(true)
End Sub

Sub EnterBrowseMode()
    if m.results.Count() = 0 then return
    m.mode = "browse"
    m.kbd.visible = false
    m.resultsGrid.visible = true
    m.hint.text = "UP to edit search  ·  OK to open  ·  BACK to edit"
    m.resultsGrid.SetFocus(true)
    m.resultsGrid.jumpToItem = 0
End Sub

' Re-focus the current pane (parent calls this after a detail page closes).
Sub onReactivate()
    if NOT m.top.reactivate then return
    m.top.reactivate = false
    if m.mode = "browse"
        m.resultsGrid.SetFocus(true)
    else
        m.kbd.SetFocus(true)
    end if
End Sub

' ============================================================================
' Query changed — run the search and repaint the count + grid
' ============================================================================
Sub onQueryChanged()
    query = m.kbd.text
    if query = invalid then query = ""
    query = LCase(query.Trim())

    if Len(query) = 0
        m.results = []
        m.resultsGrid.content = invalid
        m.resultCount.text = ""
        m.noResults.text = ""
        return
    end if

    m.results = SearchMovies(query)
    BuildResultsGrid()

    if m.results.Count() = 0
        m.resultCount.text = "0 results"
    else
        suffix = "s"
        if m.results.Count() = 1 then suffix = ""
        m.resultCount.text = m.results.Count().ToStr() + " result" + suffix
    end if
End Sub

' Substring match across title / original_title / display_title / director /
' country / cast / capsule-synopsis / genres / year (same fields as the web sites).
Function SearchMovies(query as String) as Object
    matches = []
    for each movie in m.allMovies
        if movie.hidden = true then continue for

        hay = ""
        if movie.title <> invalid then hay = hay + LCase(movie.title) + " "
        if movie.original_title <> invalid then hay = hay + LCase(movie.original_title) + " "
        if movie.display_title <> invalid then hay = hay + LCase(movie.display_title) + " "

        director = GetDirector(movie)
        if director <> "" then hay = hay + LCase(director) + " "

        if movie.country <> invalid then hay = hay + LCase(movie.country) + " "

        castArr = GetCast(movie)
        if castArr <> invalid
            for each c in castArr
                if c <> invalid then hay = hay + LCase(c) + " "
            end for
        end if

        if movie.capsule <> invalid AND movie.capsule <> ""
            hay = hay + LCase(movie.capsule) + " "
        else if movie.synopsis <> invalid
            hay = hay + LCase(movie.synopsis) + " "
        end if

        if movie.genres <> invalid
            for each g in movie.genres
                if g <> invalid then hay = hay + LCase(g) + " "
            end for
        end if

        if movie.year <> invalid then hay = hay + Str(movie.year).Trim() + " "

        if InStr(1, hay, query) > 0
            matches.Push(movie)
            if matches.Count() >= 60 then exit for
        end if
    end for
    return matches
End Function

' Flat grid (no date sections) — MovieCard reads itemContent.movie.
Sub BuildResultsGrid()
    content = CreateObject("roSGNode", "ContentNode")
    for each movie in m.results
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
    m.resultsGrid.content = content
End Sub

' ============================================================================
' Result selected — hand the result list + index to the parent's DetailScreen
' ============================================================================
Sub onResultSelected()
    index = m.resultsGrid.itemSelected
    if index < 0 OR index >= m.results.Count() then return
    m.top.detailMovies = m.results
    m.top.detailIndex = index
    m.top.requestDetail = true
End Sub

' ============================================================================
' Key handling — switch between TYPE and BROWSE.
' In TYPE, the keyboard handles its own keys; only Down (at its bottom row) and
' Back bubble here. In BROWSE, the grid handles its own keys; Up (at its top row)
' and Back bubble here.
' ============================================================================
Function OnKeyEvent(key as String, press as Boolean) as Boolean
    if NOT press then return false

    if m.mode = "type"
        if key = "down" AND m.results.Count() > 0
            EnterBrowseMode()
            return true
        else if key = "back"
            m.top.closed = true
            return true
        end if

    else if m.mode = "browse"
        if key = "up" OR key = "back"
            EnterTypeMode()
            return true
        end if
    end if

    return false
End Function
