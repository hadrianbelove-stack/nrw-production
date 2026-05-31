' ============================================================================
' NRW Movie Utilities
' Ported from Android MovieRepository.kt and tvOS api.js
' ============================================================================

' ============================================================================
' Filter Categories (matches Android FilterCategory enum)
' ============================================================================
Function GetFilterCategories() as Object
    return {
        INDIE: "indie"
        STAFF_PICKS: "staff_picks"
        FOREIGN: "foreign"
        RESTORATIONS: "restorations"
        DOCUMENTARY: "documentary"
        PRE_ORDERS: "pre_orders"
        HORROR: "horror"
        ACTION: "action"
        COMEDY: "comedy"
        FAMILY: "family"
    }
End Function

' Filter display names for UI
Function GetFilterDisplayName(filter as String) as String
    names = {
        indie: "Indie"
        staff_picks: "Picks"
        foreign: "Foreign"
        restorations: "Reissues"
        documentary: "Docs"
        pre_orders: "Pre-Orders"
        horror: "Horror"
        action: "Action"
        comedy: "Comedy"
        family: "Family"
    }

    if names.DoesExist(filter)
        return names[filter]
    end if

    return ""
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
        ' Skip reverted movies (failed JustWatch verification, no watch links)
        if movie._enrichment_status <> invalid AND movie._enrichment_status = "reverted"
            continue for
        end if

        ' Pre-orders only appear when the pre-orders filter is active
        if movie._is_preorder <> invalid AND movie._is_preorder = true
            hasPreOrderFilter = false
            for each filter in activeFilters
                if filter = categories.PRE_ORDERS
                    hasPreOrderFilter = true
                end if
            end for
            if NOT hasPreOrderFilter
                continue for
            end if
        end if

        ' No filters = show all
        if activeFilters.Count() = 0
            result.Push(movie)
            continue for
        end if

        ' OR logic: match ANY active filter
        matched = false
        for each filter in activeFilters
            if filter = categories.INDIE
                if movie.categories <> invalid AND (movie.categories.is_indie = true OR movie.categories.tier = "indie")
                    matched = true
                end if
            else if filter = categories.STAFF_PICKS
                matched = IsStaffPick(movie)
            else if filter = categories.FOREIGN
                matched = IsForeign(movie)
            else if filter = categories.RESTORATIONS
                if movie.categories <> invalid AND movie.categories.is_restoration = true
                    matched = true
                end if
            else if filter = categories.DOCUMENTARY
                if movie.categories <> invalid AND movie.categories.is_documentary = true
                    matched = true
                end if
            else if filter = categories.PRE_ORDERS
                if movie._is_preorder <> invalid AND movie._is_preorder = true
                    matched = true
                end if
            else if filter = categories.HORROR
                if movie.genres <> invalid
                    for each g in movie.genres
                        if LCase(g).InStr("horror") >= 0 then matched = true
                    end for
                end if
            else if filter = categories.ACTION
                if movie.genres <> invalid
                    for each g in movie.genres
                        if LCase(g).InStr("action") >= 0 then matched = true
                    end for
                end if
            else if filter = categories.COMEDY
                if movie.genres <> invalid
                    for each g in movie.genres
                        if LCase(g).InStr("comedy") >= 0 then matched = true
                    end for
                end if
            else if filter = categories.FAMILY
                if movie.genres <> invalid
                    for each g in movie.genres
                        if LCase(g).InStr("family") >= 0 then matched = true
                    end for
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

    ' Append pre-orders section at the end (sorted by date ascending, nearest first)
    if preorderMovies.Count() > 0
        ' Simple insertion sort by digital_date
        for i = 1 to preorderMovies.Count() - 1
            key = preorderMovies[i]
            keyDate = key.digital_date
            if keyDate = invalid then keyDate = ""
            j = i - 1
            jDate = preorderMovies[j].digital_date
            if jDate = invalid then jDate = ""
            while j >= 0 AND jDate > keyDate
                preorderMovies[j + 1] = preorderMovies[j]
                j = j - 1
                if j >= 0
                    jDate = preorderMovies[j].digital_date
                    if jDate = invalid then jDate = ""
                end if
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

    ' 3-letter Olympic codes (UK stays UK)
    shortNames = {
        ' Canonical 3-letter map (matches assets/shared-config.js). UK/USA kept;
        ' maps both full names and 2-letter ISO codes. Keep in sync with the web map.
        "united states of america": "USA", "united states": "USA", "usa": "USA", "us": "USA"
        "united kingdom": "UK", "great britain": "UK", "gb": "UK", "uk": "UK"
        "india": "IND", "in": "IND"
        "canada": "CAN", "ca": "CAN"
        "france": "FRA", "fr": "FRA"
        "mexico": "MEX", "mx": "MEX"
        "australia": "AUS", "au": "AUS"
        "germany": "GER", "de": "GER"
        "italy": "ITA", "it": "ITA"
        "japan": "JPN", "jp": "JPN"
        "south korea": "KOR", "kr": "KOR"
        "belgium": "BEL", "be": "BEL"
        "spain": "ESP", "es": "ESP"
        "indonesia": "IDN", "id": "IDN"
        "brazil": "BRA", "br": "BRA"
        "argentina": "ARG", "ar": "ARG"
        "thailand": "THA", "th": "THA"
        "new zealand": "NZL", "nz": "NZL"
        "austria": "AUT", "at": "AUT"
        "poland": "POL", "pl": "POL"
        "china": "CHN", "cn": "CHN"
        "taiwan": "TWN", "tw": "TWN"
        "denmark": "DEN", "dk": "DEN"
        "netherlands": "NED", "nl": "NED"
        "ireland": "IRL", "ie": "IRL"
        "turkey": "TUR", "tr": "TUR"
        "nigeria": "NGA", "ng": "NGA"
        "philippines": "PHI", "ph": "PHI"
        "finland": "FIN", "fi": "FIN"
        "colombia": "COL", "co": "COL"
        "sweden": "SWE", "se": "SWE"
        "russia": "RUS", "ru": "RUS"
        "hong kong": "HKG", "hk": "HKG"
        "ukraine": "UKR", "ua": "UKR"
        "greece": "GRE", "gr": "GRE"
        "israel": "ISR", "il": "ISR"
        "georgia": "GEO", "ge": "GEO"
        "saudi arabia": "KSA", "sa": "KSA"
        "czech republic": "CZE", "cz": "CZE"
        "cuba": "CUB", "cu": "CUB"
        "switzerland": "SUI", "ch": "SUI"
        "south africa": "RSA", "za": "RSA"
        "venezuela": "VEN", "ve": "VEN"
        "croatia": "CRO", "hr": "CRO"
        "guatemala": "GUA", "gt": "GUA"
        "kenya": "KEN", "ke": "KEN"
        "iceland": "ISL", "is": "ISL"
        "bulgaria": "BUL", "bg": "BUL"
        "norway": "NOR", "no": "NOR"
        "iraq": "IRQ", "iq": "IRQ"
        "hungary": "HUN", "hu": "HUN"
        "nepal": "NEP", "np": "NEP"
        "slovenia": "SLO", "si": "SLO"
        "cambodia": "CAM", "kh": "CAM"
        "morocco": "MAR", "ma": "MAR"
        "chile": "CHL", "cl": "CHL"
        "singapore": "SGP", "sg": "SGP"
        "armenia": "ARM", "am": "ARM"
        "united arab emirates": "UAE", "ae": "UAE"
        "palestinian territory": "PLE", "palestine": "PLE", "ps": "PLE"
        "bosnia and herzegovina": "BIH", "ba": "BIH"
        "unknown": "—"
    }

    lowerCountry = LCase(country)
    if shortNames.DoesExist(lowerCountry)
        return shortNames[lowerCountry]
    end if

    ' Unmapped: first 3 letters, uppercased (stay 3-letter)
    return UCase(Left(country, 3))
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
        s = movie.watch_links.streaming
        ' data.json uses array form ([{service, link}]); callers expect a single object
        if Type(s) = "roArray"
            if s.Count() > 0
                return s[0]
            end if
            return invalid
        end if
        return s  ' legacy single-object form
    end if
    return invalid
End Function

' Strip storefront wrappers ("Shudder Amazon Channel" -> "Shudder") so we name the
' brand, not the platform it is sold through. Leaves "Amazon Prime Video" /
' "The Roku Channel" alone (only strips a trailing storefront suffix).
Function CleanServiceName(service as String) as String
    if service = invalid then return service
    lower = LCase(service)
    suffixes = [" amazon channel", " apple tv channel", " roku premium channel"]
    for each suf in suffixes
        endPos = Len(service) - Len(suf) + 1
        if endPos > 1 AND InStr(1, lower, suf) = endPos
            return Mid(service, 1, endPos - 1).Trim()
        end if
    end for
    return service
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

' Get pre-order links as array (JustWatch buy offers for pre-order movies)
Function GetPreOrderLinks(movie as Object) as Object
    if movie.pre_order_links = invalid
        return []
    end if
    pol = movie.pre_order_links
    if Type(pol) = "roArray"
        return pol
    end if
    if Type(pol) = "roAssociativeArray"
        return [pol]
    end if
    return []
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
    normalized = LCase(CleanServiceName(service))
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

    ' Return first letter as fallback (of cleaned brand)
    return UCase(Left(CleanServiceName(service), 1))
End Function
