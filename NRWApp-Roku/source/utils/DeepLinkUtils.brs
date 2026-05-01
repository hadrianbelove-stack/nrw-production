' ============================================================================
' NRW Deep Link Utilities
' Launch streaming service apps on Roku
' Ported from Android DeepLinkHelper.kt
' ============================================================================

' ============================================================================
' Roku Channel IDs for Streaming Services
' These are the official Roku channel store IDs
' ============================================================================
Function GetChannelIds() as Object
    return {
        netflix: "12"
        amazon: "13"
        prime: "13"
        hulu: "2285"
        disney_plus: "291097"
        max: "61322"
        peacock: "593099"
        paramount_plus: "57665"
        apple_tv: "551012"
        plex: "27707"
        youtube: "837"
        vudu: "13842"
        fandango: "13842"
        tubi: "41468"
        pluto: "74519"
        freevee: "551013"
    }
End Function

' ============================================================================
' Launch Streaming Service
' Returns: { success: Boolean, error: String }
' ============================================================================
Function LaunchStreamingService(service as String, contentUrl as String) as Object
    channelIds = GetChannelIds()
    normalized = NormalizeServiceName(service)

    if NOT channelIds.DoesExist(normalized)
        return {
            success: false
            error: "Unknown service: " + service
        }
    end if

    channelId = channelIds[normalized]

    ' Check if channel is installed
    if NOT IsChannelInstalled(channelId)
        return {
            success: false
            error: "Channel not installed"
            channelId: channelId
            service: service
        }
    end if

    ' Build launch parameters
    params = {}

    ' Service-specific deep link handling
    if normalized = "netflix"
        params = BuildNetflixParams(contentUrl)
    else if normalized = "amazon" OR normalized = "prime"
        params = BuildAmazonParams(contentUrl)
    else if normalized = "disney_plus"
        params = BuildDisneyParams(contentUrl)
    else if normalized = "max"
        params = BuildMaxParams(contentUrl)
    else if normalized = "youtube"
        params = BuildYouTubeParams(contentUrl)
    else if normalized = "plex"
        params = BuildPlexParams(contentUrl)
    else
        ' Generic deep link
        params = { contentId: contentUrl }
    end if

    ' Launch the channel
    success = LaunchChannel(channelId, params)

    return {
        success: success
        error: ""
    }
End Function

' ============================================================================
' Check if Channel is Installed
' ============================================================================
Function IsChannelInstalled(channelId as String) as Boolean
    channelStore = CreateObject("roChannelStore")

    ' Get installed channels
    installed = channelStore.GetInstalledChannels()

    for each channel in installed
        if channel.id = channelId
            return true
        end if
    end for

    return false
End Function

' ============================================================================
' Launch Channel with Parameters
' ============================================================================
Function LaunchChannel(channelId as String, params as Object) as Boolean
    device = CreateObject("roDeviceInfo")

    ' Build the launch URL
    launchParams = CreateObject("roAssociativeArray")
    launchParams.Append(params)

    ' Use roAppManager to launch
    appManager = CreateObject("roAppManager")

    ' Launch the channel
    if params.Count() > 0
        return appManager.LaunchApp(channelId, launchParams)
    else
        return appManager.LaunchApp(channelId)
    end if
End Function

' ============================================================================
' Service-Specific Deep Link Builders
' ============================================================================

' Netflix: Uses movieid or seriesid parameter
Function BuildNetflixParams(contentUrl as String) as Object
    ' Extract Netflix content ID from URL
    ' Example: https://www.netflix.com/title/80100172
    contentId = ExtractContentIdFromUrl(contentUrl, "netflix")

    if contentId <> ""
        return { contentId: contentId }
    end if

    return { source: "nrw" }
End Function

' Amazon Prime Video: Uses contentId or asin
Function BuildAmazonParams(contentUrl as String) as Object
    ' Extract ASIN from Amazon URL
    ' Example: https://www.amazon.com/dp/B09XXXXX
    contentId = ExtractContentIdFromUrl(contentUrl, "amazon")

    if contentId <> ""
        return {
            contentId: contentId
            mediaType: "movie"
        }
    end if

    return {}
End Function

' Disney+: Uses contentId
Function BuildDisneyParams(contentUrl as String) as Object
    contentId = ExtractContentIdFromUrl(contentUrl, "disney")

    if contentId <> ""
        return { contentId: contentId }
    end if

    return {}
End Function

' Max (HBO Max): Uses contentId
Function BuildMaxParams(contentUrl as String) as Object
    contentId = ExtractContentIdFromUrl(contentUrl, "max")

    if contentId <> ""
        return { contentId: contentId }
    end if

    return {}
End Function

' YouTube: Uses videoId
Function BuildYouTubeParams(contentUrl as String) as Object
    videoId = ExtractYouTubeVideoId(contentUrl)

    if videoId <> ""
        return {
            contentId: videoId
            mediaType: "video"
        }
    end if

    return {}
End Function

' Plex: Uses deep link URL
Function BuildPlexParams(contentUrl as String) as Object
    ' Plex deep links are in format: plex://play/?metadataKey=...&server=...
    if InStr(1, contentUrl, "plex://") > 0
        return { contentId: contentUrl }
    end if

    return { contentId: contentUrl }
End Function

' ============================================================================
' URL Parsing Helpers
' ============================================================================

' Generic content ID extractor
Function ExtractContentIdFromUrl(url as String, service as String) as String
    if url = "" OR url = invalid
        return ""
    end if

    ' Handle different URL patterns
    if service = "netflix"
        ' https://www.netflix.com/title/80100172
        idx = InStr(1, url, "/title/")
        if idx > 0
            return Mid(url, idx + 7)
        end if
    else if service = "amazon"
        ' https://www.amazon.com/dp/B09XXXXX
        idx = InStr(1, url, "/dp/")
        if idx > 0
            asin = Mid(url, idx + 4)
            ' Trim any trailing path
            slashIdx = InStr(1, asin, "/")
            if slashIdx > 0
                asin = Left(asin, slashIdx - 1)
            end if
            return asin
        end if
    else if service = "disney"
        ' https://www.disneyplus.com/movies/title/contentId
        ' Just return the full URL as contentId
        return url
    else if service = "max"
        ' https://www.max.com/movies/title
        return url
    end if

    return ""
End Function

' Extract YouTube video ID from various URL formats
Function ExtractYouTubeVideoId(url as String) as String
    if url = "" OR url = invalid
        return ""
    end if

    ' Format: https://www.youtube.com/watch?v=VIDEO_ID
    idx = InStr(1, url, "v=")
    if idx > 0
        videoId = Mid(url, idx + 2)
        ' Trim any additional parameters
        ampIdx = InStr(1, videoId, "&")
        if ampIdx > 0
            videoId = Left(videoId, ampIdx - 1)
        end if
        return videoId
    end if

    ' Format: https://youtu.be/VIDEO_ID
    idx = InStr(1, url, "youtu.be/")
    if idx > 0
        videoId = Mid(url, idx + 9)
        ' Trim any query string
        qIdx = InStr(1, videoId, "?")
        if qIdx > 0
            videoId = Left(videoId, qIdx - 1)
        end if
        return videoId
    end if

    return ""
End Function

' ============================================================================
' Open Trailer
' ============================================================================
Function OpenTrailer(trailerUrl as String) as Object
    if trailerUrl = "" OR trailerUrl = invalid
        return {
            success: false
            error: "No trailer URL provided"
        }
    end if

    ' Self-hosted MP4 — play with native Roku Video node
    if InStr(1, trailerUrl, ".mp4") > 0
        return {
            success: true
            type: "video"
            url: trailerUrl
        }
    end if

    ' Check if it's a YouTube URL
    if InStr(1, trailerUrl, "youtube.com") > 0 OR InStr(1, trailerUrl, "youtu.be") > 0
        return LaunchStreamingService("youtube", trailerUrl)
    end if

    ' Unsupported format
    return {
        success: false
        error: "Unsupported trailer URL format"
    }
End Function

' ============================================================================
' Show Install Channel Dialog
' ============================================================================
Sub ShowInstallChannelDialog(channelId as String, serviceName as String)
    dialog = CreateObject("roSGNode", "Dialog")
    dialog.title = "Channel Not Installed"
    dialog.message = serviceName + " is not installed. Would you like to install it?"
    dialog.buttons = ["Install", "Cancel"]

    ' Note: Dialog handling should be done in the component that calls this
    ' This is just a helper to create the dialog
End Sub

' ============================================================================
' Get Service Display Name
' ============================================================================
Function GetServiceDisplayName(service as String) as String
    names = {
        netflix: "Netflix"
        amazon: "Prime Video"
        prime: "Prime Video"
        hulu: "Hulu"
        disney_plus: "Disney+"
        max: "Max"
        peacock: "Peacock"
        paramount_plus: "Paramount+"
        apple_tv: "Apple TV+"
        plex: "Plex"
        youtube: "YouTube"
        vudu: "Vudu"
        tubi: "Tubi"
        pluto: "Pluto TV"
        fandango: "Fandango"
    }

    normalized = NormalizeServiceName(service)
    if names.DoesExist(normalized)
        return names[normalized]
    end if

    return service
End Function
