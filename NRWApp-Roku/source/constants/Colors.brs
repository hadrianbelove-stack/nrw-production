' ============================================================================
' NRW Color System
' Ported from docs/STYLE_GUIDE.md - matches web, tvOS, and Android apps
' ============================================================================

' ============================================================================
' Brand Colors
' ============================================================================
Function GetColors() as Object
    return {
        ' Background colors
        backgroundDark: "0x0A0A0AFF"
        backgroundMid: "0x1A1A2EFF"
        backgroundCard: "0x1A1A1AFF"

        ' Primary accent (teal)
        primary: "0x00D4AAFF"
        primaryHover: "0x00FFBBFF"
        primaryDim: "0x00D4AA80"

        ' Text colors
        textPrimary: "0xFFFFFFFF"
        textSecondary: "0xBBBBBBFF"
        textMuted: "0x888888FF"

        ' Category colors
        staffPick: "0x00D4AAFF"
        restoration: "0xC8A951FF"
        studio: "0xFFFFFFFF"
        indie: "0x00D4AAFF"
        slop: "0x888888FF"

        ' Border colors
        borderSubtle: "0xFFFFFF33"
        borderFocus: "0x00D4AAFF"

        ' Screening / Festival
        screeningGold: "0xFFD700FF"

        ' Rotten Tomatoes
        rtFresh: "0x34C759FF"
        rtRotten: "0xFF3B30FF"

        ' Transparent
        transparent: "0x00000000"
    }
End Function

' ============================================================================
' Streaming Service Colors
' ============================================================================
Function GetServiceColors() as Object
    return {
        netflix: "0xE50914FF"
        amazon: "0xFF9900FF"
        prime: "0x00A8E1FF"
        disney_plus: "0x113CCFFF"
        max: "0xB537F2FF"
        hulu: "0x1CE783FF"
        peacock: "0x000000FF"
        paramount_plus: "0x0064FFFF"
        apple_tv: "0xAAAAAAFF"
        tubi: "0xFA382FFF"
        fawesome: "0x5B8DEFFF"
        mubi: "0xDA2128FF"
        shudder: "0x8B0000FF"
        criterion: "0x000000FF"
        youtube: "0xFF0000FF"
        vudu: "0x3399FFFF"
        fandango: "0xFF6600FF"
        vod: "0xFF9500FF"
        eventive: "0xFFD700FF"
    }
End Function

' Get color for a specific streaming service
Function GetServiceColor(service as String) as String
    colors = GetServiceColors()

    ' Normalize service name
    normalized = LCase(service)
    normalized = normalized.Replace(" ", "_")
    normalized = normalized.Replace("+", "_plus")

    ' Map variations to standard names
    if normalized = "amazon_video" OR normalized = "prime_video"
        normalized = "amazon"
    else if normalized = "hbo_max"
        normalized = "max"
    else if normalized = "itunes" OR normalized = "apple"
        normalized = "apple_tv"
    else if normalized = "disney"
        normalized = "disney_plus"
    end if

    if colors.DoesExist(normalized)
        return colors[normalized]
    end if

    ' Default to VOD color for unknown services
    return colors.vod
End Function

