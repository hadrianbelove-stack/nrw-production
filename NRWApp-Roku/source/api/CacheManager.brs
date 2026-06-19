' ============================================================================
' NRW Cache Manager
' 24-hour caching using Roku Registry (matches tvOS/Android caching strategy)
' ============================================================================

' Cache duration: 24 hours in seconds
Function CACHE_DURATION_SECONDS() as Integer
    return 86400
End Function

' Registry section name
Function CACHE_SECTION() as String
    return "nrw_cache"
End Function

' ============================================================================
' Cache Keys
' ============================================================================
Function GetCacheKeys() as Object
    return {
        movies: "movies_data"
        moviesTimestamp: "movies_timestamp"
        lastFilter: "last_filter"
        lastFocusIndex: "last_focus_index"
        focusTimestamp: "focus_timestamp"
    }
End Function

' ============================================================================
' Get Cached Data
' Returns cached data if valid, invalid if expired or not found
' ============================================================================
Function GetCachedData(key as String) as Dynamic
    sec = CreateObject("roRegistrySection", CACHE_SECTION())

    if NOT sec.Exists(key)
        return invalid
    end if

    timestampKey = key + "_timestamp"
    if NOT sec.Exists(timestampKey)
        return invalid
    end if

    ' Check if cache is expired
    timestamp = sec.Read(timestampKey).ToInt()
    now = CreateObject("roDateTime").AsSeconds()

    if (now - timestamp) > CACHE_DURATION_SECONDS()
        ' Cache expired
        return invalid
    end if

    ' Return cached data
    dataStr = sec.Read(key)
    if dataStr = ""
        return invalid
    end if

    return ParseJson(dataStr)
End Function

' ============================================================================
' Get Cached Data (ignore expiry - for offline fallback)
' ============================================================================
Function GetStaleCachedData(key as String) as Dynamic
    sec = CreateObject("roRegistrySection", CACHE_SECTION())

    if NOT sec.Exists(key)
        return invalid
    end if

    dataStr = sec.Read(key)
    if dataStr = ""
        return invalid
    end if

    return ParseJson(dataStr)
End Function

' ============================================================================
' Save Data to Cache
' ============================================================================
Sub CacheData(key as String, data as Dynamic)
    sec = CreateObject("roRegistrySection", CACHE_SECTION())

    ' Store the data
    dataStr = FormatJson(data)
    sec.Write(key, dataStr)

    ' Store the timestamp
    timestampKey = key + "_timestamp"
    now = CreateObject("roDateTime").AsSeconds()
    sec.Write(timestampKey, now.ToStr())

    ' Flush to persist
    sec.Flush()
End Sub

' ============================================================================
' Clear Cache Entry
' ============================================================================
Sub ClearCacheEntry(key as String)
    sec = CreateObject("roRegistrySection", CACHE_SECTION())

    if sec.Exists(key)
        sec.Delete(key)
    end if

    timestampKey = key + "_timestamp"
    if sec.Exists(timestampKey)
        sec.Delete(timestampKey)
    end if

    sec.Flush()
End Sub

' ============================================================================
' Clear All Cache
' ============================================================================
Sub ClearAllCache()
    sec = CreateObject("roRegistrySection", CACHE_SECTION())
    keys = sec.GetKeyList()

    for each key in keys
        sec.Delete(key)
    end for

    sec.Flush()
End Sub


' ============================================================================
' Focus Memory (for restoring position after navigation)
' Expires after 5 minutes
' ============================================================================
Function FOCUS_MEMORY_DURATION() as Integer
    return 300  ' 5 minutes
End Function

Sub SaveFocusIndex(index as Integer)
    sec = CreateObject("roRegistrySection", "nrw_focus")
    now = CreateObject("roDateTime").AsSeconds()

    sec.Write("index", index.ToStr())
    sec.Write("timestamp", now.ToStr())
    sec.Flush()
End Sub

Function GetFocusIndex() as Integer
    sec = CreateObject("roRegistrySection", "nrw_focus")

    if NOT sec.Exists("index") OR NOT sec.Exists("timestamp")
        return 0
    end if

    timestamp = sec.Read("timestamp").ToInt()
    now = CreateObject("roDateTime").AsSeconds()

    ' Only restore if within 5 minutes
    if (now - timestamp) > FOCUS_MEMORY_DURATION()
        return 0
    end if

    return sec.Read("index").ToInt()
End Function
