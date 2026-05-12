' ============================================================================
' NRW Date Divider Card Component
' Card-style date divider matching mobile web design
' ============================================================================

Sub Init()
    m.topBar = m.top.FindNode("topBar")
    m.topBarLabel = m.top.FindNode("topBarLabel")
    m.dayNumber = m.top.FindNode("dayNumber")
    m.monthLabel = m.top.FindNode("monthLabel")

    ' Chevrons
    m.chevrons = []
    for i = 1 to 5
        m.chevrons.Push(m.top.FindNode("chevron" + i.ToStr()))
    end for
End Sub

' ============================================================================
' Date String Changed
' ============================================================================
Sub onDateChanged()
    dateStr = m.top.dateString

    if dateStr = "" OR dateStr = invalid
        return
    end if

    isPreOrder = (dateStr = "PRE-ORDER" OR dateStr = "pre-order")

    if isPreOrder
        ' Purple pre-order variant
        m.topBar.color = "0x7C3AEDFF"
        m.topBarLabel.text = "PRE-ORDER"
        m.dayNumber.text = "SOON"
        m.dayNumber.color = "0x7C3AEDFF"
        m.monthLabel.text = ""
        m.monthLabel.visible = false

        ' Purple chevrons
        purpleColors = ["0x7C3AEDE6", "0x7C3AEDB3", "0x7C3AED80", "0x7C3AED4D", "0x7C3AED26"]
        for i = 0 to 4
            m.chevrons[i].color = purpleColors[i]
        end for
    else
        ' Parse the date
        parts = dateStr.Split("-")
        if parts.Count() < 3 then return

        year = Val(parts[0])
        month = Val(parts[1])
        day = Val(parts[2])

        ' Get weekday name
        weekday = GetDayOfWeekStr(dateStr)

        ' Get month name
        months = ["", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
        monthName = ""
        if month >= 1 AND month <= 12
            monthName = months[month]
        end if

        ' Set teal color
        m.topBar.color = "0x00D4AAFF"
        m.topBarLabel.text = weekday
        m.dayNumber.text = day.ToStr()
        m.dayNumber.color = "0xFFFFFFFF"
        m.monthLabel.text = monthName
        m.monthLabel.visible = true

        ' Teal chevrons
        tealColors = ["0x00D4AAE6", "0x00D4AAB3", "0x00D4AA80", "0x00D4AA4D", "0x00D4AA26"]
        for i = 0 to 4
            m.chevrons[i].color = tealColors[i]
        end for
    end if
End Sub

' ============================================================================
' Get Day of Week from date string (YYYY-MM-DD)
' ============================================================================
Function GetDayOfWeekStr(dateStr as String) as String
    try
        dt = CreateObject("roDateTime")
        dt.FromISO8601String(dateStr + "T12:00:00Z")
        dow = dt.GetDayOfWeek()
        days = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]
        return days[dow]
    catch e
        return ""
    end try
End Function
