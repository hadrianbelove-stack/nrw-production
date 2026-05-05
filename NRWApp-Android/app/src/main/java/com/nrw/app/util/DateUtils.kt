package com.nrw.app.util

/**
 * Format "YYYY-MM-DD" to "Mon D" (e.g. "May 12")
 */
fun formatShortDate(dateStr: String): String {
    val parts = dateStr.split("-")
    if (parts.size < 3) return dateStr
    val month = when (parts[1]) {
        "01" -> "Jan"; "02" -> "Feb"; "03" -> "Mar"; "04" -> "Apr"
        "05" -> "May"; "06" -> "Jun"; "07" -> "Jul"; "08" -> "Aug"
        "09" -> "Sep"; "10" -> "Oct"; "11" -> "Nov"; "12" -> "Dec"
        else -> parts[1]
    }
    val day = parts[2].trimStart('0')
    return "$month $day"
}
