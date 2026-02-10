' ============================================================================
' NRW - New Release Wall
' Main entry point for Roku channel
' ============================================================================

Sub Main(args as Dynamic)
    ' Initialize the screen
    screen = CreateObject("roSGScreen")
    m.port = CreateObject("roMessagePort")
    screen.SetMessagePort(m.port)

    ' Create the main scene
    scene = screen.CreateScene("HomeScreen")
    screen.Show()

    ' Handle deep link launch if provided
    if args <> invalid AND args.contentId <> invalid
        scene.deepLinkMovieId = args.contentId
    end if

    ' Main event loop
    while true
        msg = Wait(0, m.port)
        msgType = Type(msg)

        if msgType = "roSGScreenEvent"
            if msg.IsScreenClosed()
                exit while
            end if
        end if
    end while
End Sub

' ============================================================================
' RunScreenSaver - Required for Roku certification
' ============================================================================
Sub RunScreenSaver()
    screen = CreateObject("roSGScreen")
    port = CreateObject("roMessagePort")
    screen.SetMessagePort(port)

    scene = screen.CreateScene("ScreenSaver")
    screen.Show()

    while true
        msg = Wait(0, port)
        if Type(msg) = "roSGScreenEvent"
            if msg.IsScreenClosed()
                exit while
            end if
        end if
    end while
End Sub
