package com.nrw.app.util

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.util.Log
import android.widget.Toast

private const val TAG = "DeepLinkHelper"

/**
 * Service package names for Android TV apps
 */
object ServicePackages {
    const val NETFLIX = "com.netflix.ninja"  // Netflix for Android TV
    const val AMAZON = "com.amazon.avod.thirdpartyclient"
    const val YOUTUBE = "com.google.android.youtube.tv"
    const val YOUTUBE_MOBILE = "com.google.android.youtube"
    const val HULU = "com.hulu.livingroomplus"
    const val MAX = "com.wbd.stream"
    const val DISNEY_PLUS = "com.disney.disneyplus"
    const val PEACOCK = "com.peacocktv.peacockandroid"
    const val PARAMOUNT_PLUS = "com.cbs.ott"
    const val MUBI = "com.mubi"
    const val CRITERION = "com.criterion.channel"
}

/**
 * Service URI schemes for deep linking
 */
object ServiceSchemes {
    const val NETFLIX = "nflx://"
    const val AMAZON = "amzn://"
    const val YOUTUBE = "vnd.youtube://"
    const val HULU = "hulu://"
    const val MAX = "hbomax://"
    const val DISNEY_PLUS = "disneyplus://"
    const val PEACOCK = "peacocktv://"
    const val PARAMOUNT_PLUS = "paramountplus://"
}

/**
 * Helper class for opening streaming service deep links
 */
object DeepLinkHelper {

    /**
     * Open a URL in the appropriate streaming app or browser
     */
    fun openUrl(context: Context, url: String, service: String? = null): Boolean {
        Log.d(TAG, "Opening URL: $url, service: $service")

        return try {
            // Try service-specific deep linking first
            if (service != null) {
                val handled = handleServiceDeepLink(context, url, service)
                if (handled) return true
            }

            // Fall back to standard URL handling
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(intent)
            true
        } catch (e: Exception) {
            Log.e(TAG, "Error opening URL: $url", e)
            Toast.makeText(context, "Unable to open link", Toast.LENGTH_SHORT).show()
            false
        }
    }

    /**
     * Handle service-specific deep linking
     */
    private fun handleServiceDeepLink(context: Context, url: String, service: String): Boolean {
        return when (service.lowercase()) {
            "netflix" -> openNetflix(context, url)
            "amazon", "amazon_video", "prime_video" -> openAmazon(context, url)
            "youtube" -> openYouTube(context, url)
            "hulu" -> openHulu(context, url)
            "max", "hbo_max" -> openMax(context, url)
            "disney_plus" -> openDisneyPlus(context, url)
            "peacock" -> openPeacock(context, url)
            "paramount_plus" -> openParamountPlus(context, url)
            else -> false
        }
    }

    /**
     * Open Netflix
     */
    private fun openNetflix(context: Context, url: String): Boolean {
        return try {
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
            intent.setPackage(ServicePackages.NETFLIX)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

            if (isPackageInstalled(context, ServicePackages.NETFLIX)) {
                context.startActivity(intent)
                true
            } else {
                false
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error opening Netflix", e)
            false
        }
    }

    /**
     * Open Amazon Prime Video
     */
    private fun openAmazon(context: Context, url: String): Boolean {
        return try {
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
            intent.setPackage(ServicePackages.AMAZON)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

            if (isPackageInstalled(context, ServicePackages.AMAZON)) {
                context.startActivity(intent)
                true
            } else {
                false
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error opening Amazon", e)
            false
        }
    }

    /**
     * Open YouTube trailer
     */
    fun openYouTube(context: Context, url: String): Boolean {
        return try {
            // Extract video ID from URL
            val videoId = extractYouTubeId(url)
            if (videoId != null) {
                // Try YouTube TV app first
                val ytIntent = Intent(Intent.ACTION_VIEW, Uri.parse("vnd.youtube://$videoId"))
                ytIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

                if (isPackageInstalled(context, ServicePackages.YOUTUBE)) {
                    ytIntent.setPackage(ServicePackages.YOUTUBE)
                    context.startActivity(ytIntent)
                    return true
                } else if (isPackageInstalled(context, ServicePackages.YOUTUBE_MOBILE)) {
                    ytIntent.setPackage(ServicePackages.YOUTUBE_MOBILE)
                    context.startActivity(ytIntent)
                    return true
                }
            }

            // Fall back to web URL
            val webIntent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
            webIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(webIntent)
            true
        } catch (e: Exception) {
            Log.e(TAG, "Error opening YouTube", e)
            false
        }
    }

    /**
     * Open Hulu
     */
    private fun openHulu(context: Context, url: String): Boolean {
        return openServiceApp(context, url, ServicePackages.HULU, ServiceSchemes.HULU)
    }

    /**
     * Open Max (HBO Max)
     */
    private fun openMax(context: Context, url: String): Boolean {
        return openServiceApp(context, url, ServicePackages.MAX, ServiceSchemes.MAX)
    }

    /**
     * Open Disney+
     */
    private fun openDisneyPlus(context: Context, url: String): Boolean {
        return openServiceApp(context, url, ServicePackages.DISNEY_PLUS, ServiceSchemes.DISNEY_PLUS)
    }

    /**
     * Open Peacock
     */
    private fun openPeacock(context: Context, url: String): Boolean {
        return openServiceApp(context, url, ServicePackages.PEACOCK, ServiceSchemes.PEACOCK)
    }

    /**
     * Open Paramount+
     */
    private fun openParamountPlus(context: Context, url: String): Boolean {
        return openServiceApp(context, url, ServicePackages.PARAMOUNT_PLUS, ServiceSchemes.PARAMOUNT_PLUS)
    }

    /**
     * Generic service app opener
     */
    private fun openServiceApp(
        context: Context,
        url: String,
        packageName: String,
        scheme: String
    ): Boolean {
        return try {
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
            intent.setPackage(packageName)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

            if (isPackageInstalled(context, packageName)) {
                context.startActivity(intent)
                true
            } else {
                false
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error opening service app: $packageName", e)
            false
        }
    }

    /**
     * Open an app by package name
     */
    private fun openApp(context: Context, packageName: String): Boolean {
        return try {
            val intent = context.packageManager.getLeanbackLaunchIntentForPackage(packageName)
                ?: context.packageManager.getLaunchIntentForPackage(packageName)

            if (intent != null) {
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                context.startActivity(intent)
                true
            } else {
                false
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error opening app: $packageName", e)
            false
        }
    }

    /**
     * Check if a package is installed
     */
    private fun isPackageInstalled(context: Context, packageName: String): Boolean {
        return try {
            context.packageManager.getPackageInfo(packageName, 0)
            true
        } catch (e: PackageManager.NameNotFoundException) {
            false
        }
    }

    /**
     * Extract YouTube video ID from URL
     */
    fun extractYouTubeId(url: String): String? {
        val patterns = listOf(
            Regex("(?:youtube\\.com/watch\\?v=|youtu\\.be/|youtube\\.com/embed/)([^&\\n?#]+)"),
            Regex("^([a-zA-Z0-9_-]{11})$")
        )

        for (pattern in patterns) {
            val match = pattern.find(url)
            if (match != null) {
                return match.groupValues[1]
            }
        }

        return null
    }

    /**
     * Open Rotten Tomatoes page (web browser)
     */
    fun openRottenTomatoes(context: Context, url: String): Boolean {
        return openUrl(context, url)
    }

    /**
     * Open a trailer (YouTube or other)
     */
    fun openTrailer(context: Context, url: String): Boolean {
        // Self-hosted MP4 — open with native video player
        val path = Uri.parse(url).path ?: url
        if (path.endsWith(".mp4")) {
            return try {
                val intent = Intent(Intent.ACTION_VIEW)
                intent.setDataAndType(Uri.parse(url), "video/mp4")
                context.startActivity(intent)
                true
            } catch (e: android.content.ActivityNotFoundException) {
                Log.e(TAG, "No video player found for MP4: ${e.message}")
                openUrl(context, url)
            }
        }

        // Check if it's a YouTube URL
        if (url.contains("youtube") || url.contains("youtu.be")) {
            return openYouTube(context, url)
        }

        // Otherwise open as generic URL
        return openUrl(context, url)
    }
}
