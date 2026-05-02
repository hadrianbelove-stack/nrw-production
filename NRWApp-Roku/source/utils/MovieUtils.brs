' ============================================================================
' NRW Movie Utilities
' Ported from Android MovieRepository.kt and tvOS api.js
' ============================================================================

' ============================================================================
' Filter Categories (matches Android FilterCategory enum)
' ============================================================================
Function GetFilterCategories() as Object
    return {
        ALL: "all"
        BIG_TIME: "big_time"
        INDIE: "indie"
        STAFF_PICKS: "staff_picks"
        FOREIGN: "foreign"
        SERIES: "series"
        PLEX: "plex"
        RESTORATIONS: "restorations"
        DOCUMENTARY: "documentary"
        VIRTUAL_SCREENINGS: "virtual_screenings"
    }
End Function

' Filter display names for UI
Function GetFilterDisplayName(filter as String) as String
    names = {
        all: "All"
        big_time: "Big Time Stuff"
        indie: "Indie"
        staff_picks: "Staff Picks"
        foreign: "Foreign"
        series: "Limited Series"
        plex: "Plex"
        restorations: "Restorations"
        documentary: "Documentary"
        virtual_screenings: "Virtual Screenings"
    }

    if names.DoesExist(filter)
        return names[filter]
    end if

    return "All"
End Function

' ============================================================================
' Filter Movies by Category
' Ported from MovieRepository.filterMovies()
' ============================================================================
Function FilterMovies(movies as Object, filter as String) as Object
    result = []
    categories = GetFilterCategories()

    for each movie in movies
        ' Skip hidden movies
        if movie.hidden = true
            continue for
        end if

        include = false

        if filter = categories.ALL
            include = true

        else if filter = categories.BIG_TIME
            if movie.categories <> invalid AND (movie.categories.is_big_time = true OR movie.categories.tier = "big_time")
                include = true
            end if

        else if filter = categories.INDIE
            if movie.categories <> invalid AND (movie.categories.is_indie = true OR movie.categories.tier = "indie")
                include = true
            end if

        else if filter = categories.STAFF_PICKS
            include = IsStaffPick(movie)

        else if filter = categories.FOREIGN
            include = IsForeign(movie)

        else if filter = categories.SERIES
            if movie.content_type = "limited_series"
                include = true
            end if

        else if filter = categories.PLEX
            if movie.plex <> invalid AND movie.plex.deep_link <> invalid
                include = true
            end if

        else if filter = categories.RESTORATIONS
            if movie.categories <> invalid AND movie.categories.is_restoration = true
                include = true
            end if

        else if filter = categories.DOCUMENTARY
            if movie.categories <> invalid AND movie.categories.is_documentary = true
                include = true
            end if

        else if filter = categories.VIRTUAL_SCREENINGS
            if movie.categories <> invalid AND movie.categories.is_virtual_screening = true
                include = true
            end if
        end if

        if include
            result.Push(movie)
        end if
    end for

    return result
End Function

' ============================================================================
' Filter Movies by Multiple Categories (OR logic - cumulative)
' ============================================================================
Function FilterMoviesMulti(movies as Object, activeFilters as Object) as Object
    result = []
    categories = GetFilterCategories()

    for each movie in movies
        if movie.hidden = true
            continue for
        end if

        ' No filters = show all
        if activeFilters.Count() = 0
            result.Push(movie)
            continue for
        end if

        ' OR logic: match ANY active filter
        matched = false
        for each filter in activeFilters
            if filter = categories.BIG_TIME
                if movie.categories <> invalid AND (movie.categories.is_big_time = true OR movie.categories.tier = "big_time")
                    matched = true
                end if
            else if filter = categories.INDIE
                if movie.categories <> invalid AND (movie.categories.is_indie = true OR movie.categories.tier = "indie")
                    matched = true
                end if
            else if filter = categories.STAFF_PICKS
                matched = IsStaffPick(movie)
            else if filter = categories.FOREIGN
                matched = IsForeign(movie)
            else if filter = categories.SERIES
                if movie.content_type = "limited_series"
                    matched = true
                end if
            else if filter = categories.PLEX
                if movie.plex <> invalid AND movie.plex.deep_link <> invalid
                    matched = true
                end if
            else if filter = categories.RESTORATIONS
                if movie.categories <> invalid AND movie.categories.is_restoration = true
                    matched = true
                end if
            else if filter = categories.DOCUMENTARY
                if movie.categories <> invalid AND movie.categories.is_documentary = true
                    matched = true
                end if
            else if filter = categories.VIRTUAL_SCREENINGS
                if movie.categories <> invalid AND movie.categories.is_virtual_screening = true
                    matched = true
                end if
            end if

            if matched then exit for
        end for

        if matched
            result.Push(movie)
        end if
    end for

    return result
End Function

' ============================================================================
' Search Movies
' Ported from MovieRepository.searchMovies()
' ============================================================================
Function SearchMovies(movies as Object, query as String) as Object
    if query = "" OR query = invalid
        return movies
    end if

    lowerQuery = LCase(query)
    result = []

    for each movie in movies
        ' Search in title
        title = LCase(movie.title)
        if InStr(1, title, lowerQuery) > 0
            result.Push(movie)
            continue for
        end if

        ' Search in director
        director = GetDirector(movie)
        if director <> ""
            if InStr(1, LCase(director), lowerQuery) > 0
                result.Push(movie)
                continue for
            end if
        end if

        ' Search in genres
        if movie.genres <> invalid
            found = false
            for each genre in movie.genres
                if InStr(1, LCase(genre), lowerQuery) > 0
                    found = true
                    exit for
                end if
            end for
            if found
                result.Push(movie)
                continue for
            end if
        end if
    end for

    return result
End Function

' ============================================================================
' Group Movies by Date
' Ported from MovieRepository.groupMoviesByDate()
' ============================================================================
Function GroupMoviesByDate(movies as Object) as Object
    groups = CreateObject("roAssociativeArray")
    preorderMovies = []

    for each movie in movies
        ' Separate pre-orders into their own group
        if movie._is_preorder <> invalid AND movie._is_preorder = true
            preorderMovies.Push(movie)
        else
            dateStr = GetDisplayDate(movie)
            if dateStr = invalid OR dateStr = ""
                dateStr = "Unknown"
            end if

            if NOT groups.DoesExist(dateStr)
                groups[dateStr] = []
            end if

            groups[dateStr].Push(movie)
        end if
    end for

    ' Get sorted date keys (descending)
    sortedDates = SortDatesDescending(groups.Keys())

    ' Append pre-orders section at the end (sorted alphabetically by title)
    if preorderMovies.Count() > 0
        ' Simple insertion sort by title
        for i = 1 to preorderMovies.Count() - 1
            key = preorderMovies[i]
            keyTitle = LCase(key.title)
            j = i - 1
            while j >= 0 AND LCase(preorderMovies[j].title) > keyTitle
                preorderMovies[j + 1] = preorderMovies[j]
                j = j - 1
            end while
            preorderMovies[j + 1] = key
        end for
        groups["PRE-ORDER"] = preorderMovies
        sortedDates.Push("PRE-ORDER")
    end if

    return {
        dates: sortedDates
        groups: groups
    }
End Function

' Sort dates in descending order
Function SortDatesDescending(dates as Object) as Object
    ' Convert to array with sortable values
    dateArray = []
    for each dateStr in dates
        if dateStr = "Unknown"
            dateArray.Push({ date: dateStr, sortKey: "0000-00-00" })
        else
            dateArray.Push({ date: dateStr, sortKey: dateStr })
        end if
    end for

    ' Simple bubble sort (descending)
    n = dateArray.Count()
    for i = 0 to n - 2
        for j = 0 to n - i - 2
            if dateArray[j].sortKey < dateArray[j + 1].sortKey
                temp = dateArray[j]
                dateArray[j] = dateArray[j + 1]
                dateArray[j + 1] = temp
            end if
        end for
    end for

    ' Extract just the date strings
    result = []
    for each item in dateArray
        result.Push(item.date)
    end for

    return result
End Function

' ============================================================================
' Movie Helper Functions
' ============================================================================

' Get display date (digital_date > premiere_date > release_date)
Function GetDisplayDate(movie as Object) as String
    if movie.digital_date <> invalid AND movie.digital_date <> ""
        return movie.digital_date
    else if movie.premiere_date <> invalid AND movie.premiere_date <> ""
        return movie.premiere_date
    else if movie.release_date <> invalid AND movie.release_date <> ""
        return movie.release_date
    end if
    return ""
End Function

' Get director from crew object
Function GetDirector(movie as Object) as String
    if movie.crew <> invalid AND movie.crew.director <> invalid
        return movie.crew.director
    end if
    return ""
End Function

' Get cast array
Function GetCast(movie as Object) as Object
    if movie.crew <> invalid AND movie.crew.cast <> invalid
        return movie.crew.cast
    end if
    return []
End Function

' Check if movie is a staff pick
Function IsStaffPick(movie as Object) as Boolean
    if movie.featured = true
        return true
    end if
    if movie.categories <> invalid AND movie.categories.is_staff_pick = true
        return true
    end if
    return false
End Function

' Check if movie is foreign (non-English)
Function IsForeign(movie as Object) as Boolean
    if movie.categories <> invalid AND movie.categories.is_foreign = true
        return true
    end if
    if movie.original_language <> invalid AND movie.original_language <> "en"
        return true
    end if
    return false
End Function

' Format country display name per STYLE_GUIDE.md
Function FormatCountry(country as String) as String
    if country = "" OR country = invalid
        return ""
    end if

    shortNames = {
        "united states of america": "USA"
        "united states": "USA"
        "usa": "USA"
        "united kingdom": "UK"
        "great britain": "UK"
        "south korea": "S. Korea"
        "south africa": "S. Africa"
        "new zealand": "N. Zealand"
        "bosnia and herzegovina": "Bosnia"
        "saudi arabia": "S. Arabia"
    }

    lowerCountry = LCase(country)
    if shortNames.DoesExist(lowerCountry)
        return shortNames[lowerCountry]
    end if

    ' Fix all-caps or all-lowercase (e.g. "SWEDEN" → "Sweden")
    titleCase = UCase(Left(country, 1)) + LCase(Mid(country, 2))
    if country <> titleCase
        return titleCase
    end if

    return country
End Function

' Format runtime (e.g., "2h 15m")
Function FormatRuntime(minutes as Dynamic) as String
    if minutes = invalid OR Type(minutes) <> "Integer" AND Type(minutes) <> "roInt"
        return ""
    end if

    hours = Int(minutes / 60)
    mins = minutes MOD 60

    if hours > 0 AND mins > 0
        return hours.ToStr() + "h " + mins.ToStr() + "m"
    else if hours > 0
        return hours.ToStr() + "h"
    else
        return mins.ToStr() + "m"
    end if
End Function

' Format date for display (e.g., "Jan 15, 2026")
Function FormatDateForDisplay(dateStr as String) as String
    if dateStr = "" OR dateStr = invalid
        return ""
    end if

    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    ' Parse YYYY-MM-DD
    parts = dateStr.Split("-")
    if parts.Count() < 3
        return dateStr
    end if

    year = parts[0]
    monthNum = parts[1].ToInt()
    day = parts[2].ToInt()

    if monthNum < 1 OR monthNum > 12
        return dateStr
    end if

    monthName = months[monthNum - 1]
    return monthName + " " + day.ToStr() + ", " + year
End Function

' Format date as "Feb 24" (no year) for title row display
Function FormatShortDate(dateStr as String) as String
    if dateStr = "" OR dateStr = invalid
        return ""
    end if

    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    parts = dateStr.Split("-")
    if parts.Count() < 3
        return dateStr
    end if

    monthNum = parts[1].ToInt()
    day = parts[2].ToInt()

    if monthNum < 1 OR monthNum > 12
        return dateStr
    end if

    monthName = months[monthNum - 1]
    return monthName + " " + day.ToStr()
End Function

' ============================================================================
' Watch Links Helpers
' ============================================================================

' Get streaming service info
Function GetStreamingService(movie as Object) as Object
    if movie.watch_links <> invalid AND movie.watch_links.streaming <> invalid
        return movie.watch_links.streaming
    end if
    return invalid
End Function

' Get pre-order links as array (Amazon and/or Apple TV deeplinks)
Function GetPreOrderLinks(movie as Object) as Object
    links = []
    if movie.pre_order_links = invalid then return links
    if movie.pre_order_links.amazon <> invalid AND movie.pre_order_links.amazon <> ""
        links.Push({ service: "Amazon", link: movie.pre_order_links.amazon, label: "Pre-Order on Amazon" })
    end if
    if movie.pre_order_links.apple_tv <> invalid AND movie.pre_order_links.apple_tv <> ""
        links.Push({ service: "Apple TV", link: movie.pre_order_links.apple_tv, label: "Pre-Order on Apple TV" })
    end if
    return links
End Function

' Get VOD services as array (handles both array and single object formats)
Function GetVodServices(movie as Object) as Object
    if movie.watch_links = invalid OR movie.watch_links.vod = invalid
        return []
    end if
    vod = movie.watch_links.vod
    ' If it's already an array (roArray), return as-is
    if Type(vod) = "roArray"
        return vod
    end if
    ' Single object: wrap in array
    if Type(vod) = "roAssociativeArray"
        return [vod]
    end if
    return []
End Function

' Get trailer URL (prefer self-hosted MP4, fall back to YouTube)
Function GetTrailerUrl(movie as Object) as String
    if movie.links <> invalid AND movie.links.trailer_hosted <> invalid
        return movie.links.trailer_hosted
    end if
    if movie.links <> invalid AND movie.links.trailer <> invalid
        return movie.links.trailer
    end if
    return ""
End Function

' Get Plex deep link
Function GetPlexDeepLink(movie as Object) as String
    if movie.plex <> invalid AND movie.plex.deep_link <> invalid
        return movie.plex.deep_link
    end if
    return ""
End Function

' Normalize service name for color lookup
Function NormalizeServiceName(service as String) as String
    normalized = LCase(service)
    normalized = normalized.Replace(" ", "_")
    normalized = normalized.Replace("+", "_plus")

    ' Map variations
    if normalized = "amazon_video" OR normalized = "prime_video"
        return "amazon"
    else if normalized = "hbo_max"
        return "max"
    else if normalized = "itunes" OR normalized = "apple"
        return "apple_tv"
    else if normalized = "disney"
        return "disney_plus"
    end if

    return normalized
End Function

' Check if a VOD link is an Eventive / virtual screening platform link
Function IsEventiveLink(service as String, url as String) as Boolean
    if service <> invalid
        lowerService = LCase(service)
        if InStr(1, lowerService, "eventive") > 0
            return true
        end if
    end if
    if url <> invalid
        lowerUrl = LCase(url)
        if InStr(1, lowerUrl, "eventive.org") > 0
            return true
        end if
        if InStr(1, lowerUrl, "festivalplayer") > 0
            return true
        end if
        if InStr(1, lowerUrl, "shift72.com") > 0
            return true
        end if
    end if
    return false
End Function

' Get short service name for badge display
Function GetServiceBadgeText(service as String) as String
    badges = {
        netflix: "N"
        amazon: "P"
        prime: "P"
        disney_plus: "D+"
        max: "MAX"
        hulu: "H"
        peacock: "PK"
        paramount_plus: "P+"
        apple_tv: "TV+"
        plex: "PLEX"
    }

    normalized = NormalizeServiceName(service)
    if badges.DoesExist(normalized)
        return badges[normalized]
    end if

    ' Return first letter as fallback
    return UCase(Left(service, 1))
End Function
