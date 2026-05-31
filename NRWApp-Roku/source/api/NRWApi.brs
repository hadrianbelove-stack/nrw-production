' ============================================================================
' NRW API Service
' Fetches data.json from GitHub (same URL as tvOS/Android apps)
' ============================================================================

' Data URL - same as all other NRW apps
Const DATA_URL = "https://raw.githubusercontent.com/hadrianbelove-stack/nrw-production/main/data.json"

' Request timeout in seconds
Const REQUEST_TIMEOUT = 15

' ============================================================================
' Fetch Movies (with caching)
' Returns: { success: Boolean, data: Object, error: String }
' ============================================================================
Function FetchMovies(forceRefresh as Boolean) as Object
    cacheKeys = GetCacheKeys()

    ' Check cache first (unless force refresh)
    if NOT forceRefresh
        cachedData = GetCachedData(cacheKeys.movies)
        if cachedData <> invalid
            return {
                success: true
                data: cachedData
                fromCache: true
                error: ""
            }
        end if
    end if

    ' Fetch from network
    result = FetchDataFromNetwork()

    if result.success
        ' Cache the successful response
        CacheData(cacheKeys.movies, result.data)
        return result
    end if

    ' Network failed - try stale cache as fallback
    staleData = GetStaleCachedData(cacheKeys.movies)
    if staleData <> invalid
        return {
            success: true
            data: staleData
            fromCache: true
            stale: true
            error: ""
        }
    end if

    ' No cache available
    return result
End Function

' ============================================================================
' Fetch Data from Network
' ============================================================================
Function FetchDataFromNetwork() as Object
    request = CreateObject("roUrlTransfer")
    port = CreateObject("roMessagePort")

    request.SetMessagePort(port)
    request.SetUrl(DATA_URL)
    request.SetCertificatesFile("common:/certs/ca-bundle.crt")
    request.InitClientCertificates()

    ' Enable HTTPS
    request.EnableEncodings(true)

    ' Start async request
    if NOT request.AsyncGetToString()
        return {
            success: false
            data: invalid
            fromCache: false
            error: "Failed to start network request"
        }
    end if

    ' Wait for response with timeout
    timeout = REQUEST_TIMEOUT * 1000  ' Convert to milliseconds
    msg = Wait(timeout, port)

    if msg = invalid
        ' Timeout
        request.AsyncCancel()
        return {
            success: false
            data: invalid
            fromCache: false
            error: "Request timed out"
        }
    end if

    if Type(msg) = "roUrlEvent"
        responseCode = msg.GetResponseCode()

        if responseCode = 200
            responseBody = msg.GetString()
            data = ParseJson(responseBody)

            if data = invalid
                return {
                    success: false
                    data: invalid
                    fromCache: false
                    error: "Failed to parse JSON response"
                }
            end if

            return {
                success: true
                data: data
                fromCache: false
                error: ""
            }
        else
            return {
                success: false
                data: invalid
                fromCache: false
                error: "HTTP error: " + responseCode.ToStr()
            }
        end if
    end if

    return {
        success: false
        data: invalid
        fromCache: false
        error: "Unknown error"
    }
End Function

' ============================================================================
' Extract Movies from API Response
' Filters to only show movies with digital_date <= today
' ============================================================================
Function ExtractMovies(apiResponse as Object) as Object
    if apiResponse = invalid OR apiResponse.movies = invalid
        return []
    end if

    movies = []
    today = CreateObject("roDateTime")
    todayStr = FormatDateString(today)

    for each movie in apiResponse.movies
        ' Skip hidden movies
        if movie.hidden = true
            continue for
        end if

        ' Only include movies with digital_date
        if movie.digital_date = invalid OR movie.digital_date = ""
            continue for
        end if

        ' Only include movies available today or earlier
        if movie.digital_date <= todayStr
            movies.Push(movie)
        end if
    end for

    return movies
End Function

' ============================================================================
' Helper: Format date as YYYY-MM-DD
' ============================================================================
Function FormatDateString(dateObj as Object) as String
    year = dateObj.GetYear().ToStr()
    month = Right("0" + dateObj.GetMonth().ToStr(), 2)
    day = Right("0" + dateObj.GetDayOfMonth().ToStr(), 2)
    return year + "-" + month + "-" + day
End Function
