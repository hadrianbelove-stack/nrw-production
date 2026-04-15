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

    if buttonType = "filled"
        ' Filled button style (for Trailer button)
        m.buttonBg.color = m.serviceColor
        m.buttonBorder.visible = false
        m.buttonInner.visible = false

        if isFocused
            ' Brighten on focus
            m.buttonLabel.color = "0x000000FF"
        else
            m.buttonLabel.color = "0xFFFFFFFF"
        end if
    else
        ' Outline button style (for Watch buttons)
        m.buttonBg.color = "0x00000000"  ' Transparent
        m.buttonBorder.color = m.serviceColor
        m.buttonBorder.visible = true
        m.buttonInner.visible = true
        m.buttonInner.color = m.colors.backgroundDark

        if isFocused
            ' Fill slightly on focus
            m.buttonInner.color = m.serviceColor
            m.buttonInner.opacity = 0.2
            m.buttonLabel.color = m.serviceColor

            ' Thicker border on focus
            m.buttonInner.width = m.buttonBorder.width - 6
            m.buttonInner.height = m.buttonBorder.height - 6
            m.buttonInner.translation = [3, 3]
        else
            m.buttonInner.opacity = 1.0
            m.buttonLabel.color = m.serviceColor

            ' Normal border
            m.buttonInner.width = m.buttonBorder.width - 4
            m.buttonInner.height = m.buttonBorder.height - 4
            m.buttonInner.translation = [2, 2]
        end if
    end if
End Sub

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
