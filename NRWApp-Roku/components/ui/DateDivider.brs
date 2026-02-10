' ============================================================================
' NRW Date Divider Component
' BrightScript logic for date separator
' ============================================================================

Sub Init()
    m.dateLabel = m.top.FindNode("dateLabel")
    m.leftLine = m.top.FindNode("leftLine")
    m.rightLine = m.top.FindNode("rightLine")
End Sub

' ============================================================================
' Date String Changed
' ============================================================================
Sub onDateChanged()
    dateStr = m.top.dateString

    if dateStr = "" OR dateStr = invalid
        m.dateLabel.text = ""
        return
    end if

    ' Format the date for display
    formattedDate = FormatDateForDisplay(dateStr)
    m.dateLabel.text = formattedDate
End Sub
