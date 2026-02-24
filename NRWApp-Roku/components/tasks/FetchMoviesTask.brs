' ============================================================================
' NRW Fetch Movies Task
' Async task for loading movie data
' ============================================================================

Sub Init()
    m.top.functionName = "Execute"
End Sub

Sub Execute()
    forceRefresh = m.top.forceRefresh

    ' Fetch movies using API service
    result = FetchMovies(forceRefresh)

    ' Return result
    m.top.result = result
End Sub
