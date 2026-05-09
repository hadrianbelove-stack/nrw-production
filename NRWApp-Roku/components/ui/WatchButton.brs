' ============================================================================
' NRW Watch Button Component
' BrightScript logic for streaming service button
' ============================================================================

Sub Init()
    m.buttonContainer = m.top.FindNode("buttonContainer")
    m.buttonBg = m.top.FindNode("buttonBg")
    m.buttonBorder = m.top.FindNode("buttonBorder")
    m.buttonInner = m.top.FindNode("buttonInner")
    m.buttonLabel = m.top.FindNode("buttonLabel")
    m.serviceIcon = m.top.FindNode("serviceIcon")

    m.serviceColor = "0xFFFFFFFF"
    m.colors = GetColors()
End Sub

' ============================================================================
' Service Changed
' ============================================================================
Sub onServiceChanged()
    service = m.top.service
    if service = "" OR service = invalid
        return
    end if

    ' Get service color
    serviceColors = GetServiceColors()
    normalized = NormalizeServiceName(service)

    if serviceColors.DoesExist(normalized)
        m.serviceColor = serviceColors[normalized]
    else
        m.serviceColor = "0xFF9500FF"  ' Default VOD orange
    end if

    ' Try to show logo image instead of text
    logoPath = GetServiceLogoPath(normalized)
    if logoPath <> ""
        m.serviceIcon.uri = logoPath
        m.serviceIcon.blendColor = "0xFFFFFFFF"
        m.serviceIcon.width = 120
        m.serviceIcon.height = 30
        m.serviceIcon.translation = [10, 7]
        m.serviceIcon.visible = true
        m.buttonLabel.visible = false
        SetButtonWidth(140)
    else
        m.serviceIcon.visible = false
        m.buttonLabel.visible = true
    end if

    UpdateButtonStyle()

    ' Set default label if not provided
    if m.top.label = "" OR m.top.label = invalid
        m.top.label = GetServiceDisplayName(service)
    end if
End Sub

' ============================================================================
' Label Changed
' ============================================================================
Sub onLabelChanged()
    m.buttonLabel.text = m.top.label

    ' Override color for screening/festival buttons
    if LCase(m.top.label) = "buy ticket"
        m.serviceColor = "0xFFD700FF"
        UpdateButtonStyle()
    end if

    ' Adjust button width based on label length
    labelLen = Len(m.top.label)
    if labelLen > 12
        SetButtonWidth(180)
    else if labelLen > 8
        SetButtonWidth(160)
    else
        SetButtonWidth(140)
    end if
End Sub

' ============================================================================
' Set Button Width
' ============================================================================
Sub SetButtonWidth(width as Integer)
    m.buttonBg.width = width
    m.buttonBorder.width = width
    m.buttonInner.width = width - 4
    m.buttonLabel.width = width
End Sub

' ============================================================================
' Focus Changed
' ============================================================================
Sub onFocusChanged()
    focusPercent = m.top.focusPercent
    UpdateButtonStyle()

    ' Scale on focus
    if focusPercent > 0.5
        scale = 1.0 + (0.05 * focusPercent)
        m.buttonContainer.scale = [scale, scale]
    else
        m.buttonContainer.scale = [1.0, 1.0]
    end if
End Sub

' ============================================================================
' Update Button Visual Style
' ============================================================================
Sub UpdateButtonStyle()
    buttonType = m.top.buttonType
    focusPercent = m.top.focusPercent
    isFocused = focusPercent > 0.5

    ' All buttons use filled brand-color style
    m.buttonBg.color = m.serviceColor
    m.buttonBorder.visible = false
    m.buttonInner.visible = false

    ' White text on brand color (black text for hulu green)
    normalized = NormalizeServiceName(m.top.service)
    if normalized = "hulu"
        m.buttonLabel.color = "0x000000FF"
    else
        m.buttonLabel.color = "0xFFFFFFFF"
    end if

    ' Black services (apple_tv, peacock, criterion) get a subtle border
    if normalized = "apple_tv" OR normalized = "peacock" OR normalized = "criterion"
        m.buttonBorder.color = "0x444444FF"
        m.buttonBorder.visible = true
    end if

    if isFocused
        ' Brighten on focus — scale handles the visual feedback
        m.buttonLabel.color = "0xFFFFFFFF"
    end if
End Sub

' ============================================================================
' Get service logo image path (returns "" if none)
' ============================================================================
Function GetServiceLogoPath(service as String) as String
    logos = {
        "amazon": "pkg:/images/services/amazon.png"
        "apple_tv": "pkg:/images/services/apple_tv.png"
        "netflix": "pkg:/images/services/netflix.png"
        "prime_video": "pkg:/images/services/prime_video.png"
        "disney_plus": "pkg:/images/services/disney_plus.png"
        "max": "pkg:/images/services/max.png"
        "hulu": "pkg:/images/services/hulu.png"
        "peacock": "pkg:/images/services/peacock.png"
        "paramount_plus": "pkg:/images/services/paramount_plus.png"
        "mubi": "pkg:/images/services/mubi.png"
        "criterion": "pkg:/images/services/criterion.png"
        "amc": "pkg:/images/services/amc.png"
        "fandango": "pkg:/images/services/fandango.png"
        "plex": "pkg:/images/services/plex.png"
    }
    if logos.DoesExist(service)
        return logos[service]
    end if
    return ""
End Function

' ============================================================================
' Handle Key Events
' ============================================================================
Function OnKeyEvent(key as String, press as Boolean) as Boolean
    if press AND key = "OK"
        m.top.selected = true
        return true
    end if
    return false
End Function
