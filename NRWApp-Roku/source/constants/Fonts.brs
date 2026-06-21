' ============================================================================
' NRW Font System
' Bundled Lato (Light/Regular/Bold/Black/Italic) so the Roku app can use EXACT
' pixel sizes, matching the web/tvOS/Android typography. Roku's built-in system
' fonts only come in a few fixed sizes, which is why hand-sized elements (filter
' chips, badges) used to truncate. Use GetFont() instead of "font:...SystemFont".
'
' Sizes are authored at 1920x1080 (FHD); Roku auto-scales down to HD.
' Note: Label.font needs a Font NODE (the "font:...SystemFont" string syntax only
' works for Roku's built-in fonts), which is what GetFont() returns.
' ============================================================================

' Return a Lato Font node at an exact size.
'   weight: "light" | "regular" | "bold" | "black" | "italic"
' Font nodes are cached per weight+size on m.global so we don't rebuild them.
Function GetFont(weight as String, size as Integer) as Object
    key = "nrwFont_" + weight + "_" + size.ToStr()

    if m.global <> invalid
        existing = m.global.FindNode(key)
        if existing <> invalid then return existing
    end if

    uri = "pkg:/fonts/Lato-Regular.ttf"
    if weight = "light"
        uri = "pkg:/fonts/Lato-Light.ttf"
    else if weight = "bold"
        uri = "pkg:/fonts/Lato-Bold.ttf"
    else if weight = "black"
        uri = "pkg:/fonts/Lato-Black.ttf"
    else if weight = "italic"
        uri = "pkg:/fonts/Italic.ttf"
    end if

    font = CreateObject("roSGNode", "Font")
    font.id = key
    font.uri = uri
    font.size = size

    if m.global <> invalid then m.global.AppendChild(font)
    return font
End Function

' Named type ramp — px sizes match the approved tvOS app (NRWApp-tvOS), authored
' at FHD. See docs/STYLE_GUIDE.md.
Function Fonts() as Object
    return {
        wordmark:    GetFont("light", 56)   ' THE NEW RELEASE WALL (ultra-light; sized to Roku header)
        slogan:      GetFont("light", 24)   ' tagline
        sectionDay:  GetFont("black", 30)   ' date strip DAY (e.g. THU)
        sectionDate: GetFont("light", 30)   ' date strip DATE (e.g. JUN 20)
        cardMeta:    GetFont("bold", 20)    ' director · genre · nation
        serviceName: GetFont("black", 15)   ' NETFLIX / DISNEY+ ...
        nowStreaming: GetFont("regular", 9) ' NOW STREAMING subtext
        scoreBadge:  GetFont("black", 14)   ' RT / IMDb / MC score
        selectPill:  GetFont("black", 16)   ' ★ NRW SELECT ★
        restoration: GetFont("bold", 10)    ' RESTORATION
        filterChip:  GetFont("regular", 20) ' filter chip (use bold when active)
        filterChipActive: GetFont("bold", 20)
        detailTitle: GetFont("bold", 48)    ' detail screen movie title
        body:        GetFont("regular", 24) ' general body / synopsis
        bodyBold:    GetFont("bold", 24)
    }
End Function
