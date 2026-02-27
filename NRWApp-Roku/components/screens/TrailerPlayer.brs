' ============================================================================
' NRW Trailer Player
' Fullscreen video player for self-hosted MP4 trailers
' Controls: play/pause (center), back (close)
' ============================================================================

Sub Init()
    m.videoPlayer = m.top.FindNode("videoPlayer")
    m.videoPlayer.ObserveField("state", "onVideoStateChanged")
End Sub

' ============================================================================
' Video URL Changed — start playback
' ============================================================================
Sub onVideoUrlChanged()
    url = m.top.videoUrl
    if url <> "" AND url <> invalid
        content = CreateObject("roSGNode", "ContentNode")
        content.url = url
        content.streamformat = "mp4"
        m.videoPlayer.content = content
        m.videoPlayer.control = "play"
        m.videoPlayer.SetFocus(true)
    end if
End Sub

' ============================================================================
' Video State Changed
' ============================================================================
Sub onVideoStateChanged()
    state = m.videoPlayer.state
    if state = "finished" OR state = "error"
        ClosePlayer()
    end if
End Sub

' ============================================================================
' Close Player
' ============================================================================
Sub ClosePlayer()
    m.videoPlayer.control = "stop"
    m.top.closed = true
End Sub

' ============================================================================
' Key Event Handler
' ============================================================================
Function OnKeyEvent(key as String, press as Boolean) as Boolean
    if NOT press
        return false
    end if

    if key = "back"
        ClosePlayer()
        return true
    end if

    return false
End Function
