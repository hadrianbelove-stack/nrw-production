package com.nrw.app.data

import com.google.gson.annotations.SerializedName
import com.nrw.app.util.formatShortDate

/**
 * Main movie data class matching data.json structure
 */
data class Movie(
    val id: String,
    val title: String,
    @SerializedName("display_title")
    val displayTitle: String? = null,
    val year: Int? = null,
    val rating: String? = null,
    val runtime: Int? = null,
    val capsule: String? = null,
    val synopsis: String? = null,
    val director: String? = null,
    val crew: Crew? = null,
    val genres: List<String>? = null,

    @SerializedName("poster_path")
    val posterPath: String? = null,

    @SerializedName("backdrop_path")
    val backdropPath: String? = null,

    // Full poster URL from JSON (takes precedence over poster_path)
    val poster: String? = null,

    @SerializedName("release_date")
    val releaseDate: String? = null,

    @SerializedName("digital_date")
    val digitalDate: String? = null,

    @SerializedName("premiere_date")
    val premiereDate: String? = null,

    @SerializedName("original_language")
    val originalLanguage: String? = null,

    val studio: String? = null,

    @SerializedName("production_countries")
    val productionCountries: List<Country>? = null,

    // Simple country string from JSON (takes precedence)
    val country: String? = null,

    val featured: Boolean? = null,
    val hidden: Boolean? = null,

    @SerializedName("_enrichment_status")
    val enrichmentStatus: String? = null,

    @SerializedName("content_type")
    val contentType: String? = null,

    @SerializedName("filters")
    val filters: Categories? = null,

    @SerializedName("rt_score")
    val rtScore: String? = null,

    @SerializedName("metacritic_score")
    val metacriticScore: String? = null,

    @SerializedName("imdb_rating")
    val imdbRating: String? = null,

    @SerializedName("letterboxd_score")
    val letterboxdScore: String? = null,

    val links: MovieLinks? = null,

    @SerializedName("watch_links")
    val watchLinks: WatchLinks? = null,

    @SerializedName("is_slop")
    val isSlop: Boolean = false,

    @SerializedName("_is_slop_guess")
    val isSlopGuess: Boolean = false,

    @SerializedName("_is_preorder")
    val isPreorder: Boolean = false,

    @SerializedName("pre_order_links")
    @com.google.gson.annotations.JsonAdapter(VodLinksAdapter::class)
    val preOrderLinks: List<ServiceLink>? = null,

    val plex: PlexInfo? = null,

    @SerializedName("pull_quotes")
    val pullQuotes: List<PullQuote>? = null,

    @SerializedName("virtual_screening_info")
    val screeningInfo: ScreeningInfo? = null
)

data class Country(
    @SerializedName("iso_3166_1")
    val iso: String? = null,
    val name: String? = null
)

data class Crew(
    val director: String? = null,
    val cast: List<String>? = null
)

data class Categories(
    val tier: String? = null,

    @SerializedName("is_studio")
    val isStudio: Boolean? = null,

    @SerializedName("is_indie")
    val isIndie: Boolean? = null,

    @SerializedName("is_staff_pick")
    val isStaffPick: Boolean? = null,

    @SerializedName("is_foreign")
    val isForeign: Boolean? = null,

    @SerializedName("is_restoration")
    val isRestoration: Boolean? = null,

    @SerializedName("is_documentary")
    val isDocumentary: Boolean? = null,

    @SerializedName("is_virtual_screening")
    val isVirtualScreening: Boolean? = null,

    @SerializedName("is_exploitation")
    val isExploitation: Boolean? = null
)

data class MovieLinks(
    val trailer: String? = null,

    @SerializedName("trailer_hosted")
    val trailerHosted: String? = null,

    val rt: String? = null,

    @SerializedName("rotten_tomatoes")
    val rottenTomatoes: String? = null,

    val metacritic: String? = null,

    val wikipedia: String? = null,

    val imdb: String? = null,

    val letterboxd: String? = null
)

data class WatchLinks(
    @com.google.gson.annotations.JsonAdapter(VodLinksAdapter::class)
    val streaming: List<ServiceLink>? = null,  // Array of streaming services (data.json uses array form)
    @com.google.gson.annotations.JsonAdapter(VodLinksAdapter::class)
    val vod: List<ServiceLink>? = null  // Array of VOD services (Amazon, Apple TV)
)

/**
 * Gson adapter that handles vod as either a single object or an array
 */
class VodLinksAdapter : com.google.gson.TypeAdapter<List<ServiceLink>?>() {
    private val gson = com.google.gson.Gson()

    override fun write(out: com.google.gson.stream.JsonWriter, value: List<ServiceLink>?) {
        if (value == null) { out.nullValue(); return }
        out.beginArray()
        value.forEach { gson.toJson(it, ServiceLink::class.java, out) }
        out.endArray()
    }

    override fun read(`in`: com.google.gson.stream.JsonReader): List<ServiceLink>? {
        return when (`in`.peek()) {
            com.google.gson.stream.JsonToken.NULL -> { `in`.nextNull(); null }
            com.google.gson.stream.JsonToken.BEGIN_ARRAY -> {
                val list = mutableListOf<ServiceLink>()
                `in`.beginArray()
                while (`in`.hasNext()) {
                    list.add(gson.fromJson(`in`, ServiceLink::class.java))
                }
                `in`.endArray()
                list
            }
            com.google.gson.stream.JsonToken.BEGIN_OBJECT -> {
                // Legacy single-object format: wrap in a list
                listOf(gson.fromJson(`in`, ServiceLink::class.java))
            }
            else -> { `in`.skipValue(); null }
        }
    }
}

data class ServiceLink(
    val service: String? = null,
    val link: String? = null,
    @SerializedName("rent_price")
    val rentPrice: String? = null,
    @SerializedName("buy_price")
    val buyPrice: String? = null,
    val price: String? = null
)

data class PlexInfo(
    @SerializedName("web_url")
    val webUrl: String? = null,

    @SerializedName("deep_link")
    val deepLink: String? = null,

    val ratingKey: String? = null
)

data class PullQuote(
    val text: String? = null,
    val critic: String? = null,
    val outlet: String? = null,
    val source: String? = null,
    @SerializedName("review_url")
    val reviewUrl: String? = null
)

data class ScreeningInfo(
    @SerializedName("platform") val platform: String? = null,
    @SerializedName("screening_slug") val screeningSlug: String? = null,
    @SerializedName("screening_name") val screeningName: String? = null,
    @SerializedName("available_start") val availableStart: String? = null,
    @SerializedName("available_end") val availableEnd: String? = null,
    @SerializedName("status") val status: String? = null
)

/**
 * API response wrapper
 */
data class MoviesResponse(
    val movies: List<Movie> = emptyList(),
    val featured: List<Int> = emptyList(),

    @SerializedName("latest_playlist_url")
    val latestPlaylistUrl: String? = null
)

/**
 * UI-friendly watch link for display
 */
data class WatchOption(
    val service: String,
    val label: String,
    val url: String,
    val type: WatchType,
    val icon: String,
    val sublabel: String? = null,
    val rentPrice: String? = null,
    val buyPrice: String? = null
)

enum class WatchType {
    PURCHASE,
    STREAMING,
    PLEX
}

/**
 * UI-friendly info link for display
 */
data class InfoOption(
    val type: String,
    val label: String,
    val url: String
)

/**
 * Filter categories for the UI
 */
enum class FilterCategory(val id: String, val displayName: String) {
    STAFF_PICKS("staff-picks", "Picks"),
    INDIE("indie", "Indie"),
    HORROR("horror", "Horror"),
    ACTION("action", "Action"),
    COMEDY("comedy", "Comedy"),
    FAMILY("family", "Family"),
    FOREIGN("foreign", "Foreign"),
    DOCUMENTARY("documentary", "Docs"),
    RESTORATIONS("restorations", "Reissues")
}

/**
 * Extension functions for Movie
 */
fun Movie.getPosterUrl(size: String = "w500"): String? {
    // Return full poster URL if available, otherwise construct from path
    return poster ?: posterPath?.let { "https://image.tmdb.org/t/p/$size$it" }
}

fun Movie.getBackdropUrl(size: String = "w1280"): String? {
    return backdropPath?.let { "https://image.tmdb.org/t/p/$size$it" }
}

fun Movie.getDisplayDate(): String? {
    return digitalDate ?: premiereDate ?: releaseDate
}

fun Movie.getFormattedRuntime(): String? {
    return runtime?.let {
        val hours = it / 60
        val minutes = it % 60
        if (hours > 0) "${hours}h ${minutes}m" else "${minutes}m"
    }
}

fun Movie.getFormattedGenres(): String? {
    return genres?.joinToString(" / ")
}

fun Movie.getFormattedCountries(): String? {
    return country ?: productionCountries?.mapNotNull { it.name }?.joinToString(", ")
}

fun Movie.getRtInfo(): Pair<Int, Boolean>? {
    return rtScore?.let { scoreStr ->
        // Parse "68%" string to integer
        val score = scoreStr.replace("%", "").trim().toIntOrNull() ?: return@let null
        val isFresh = score >= 60
        Pair(score, isFresh)
    }
}

fun Movie.isStaffPick(): Boolean {
    return filters?.isStaffPick == true || featured == true
}

fun Movie.isForeign(): Boolean {
    return filters?.isForeign == true || (originalLanguage != null && originalLanguage != "en")
}

fun Movie.getDirector(): String? {
    // Return direct director field if available, otherwise check crew object
    return director ?: crew?.director
}

/**
 * Get watch options for a movie
 */
fun Movie.getWatchOptions(): List<WatchOption> {
    val options = mutableListOf<WatchOption>()

    // Plex link (personal library — highest priority)
    plex?.deepLink?.let { url ->
        options.add(WatchOption(
            service = "plex",
            label = "Play on Plex",
            url = url,
            type = WatchType.PLEX,
            icon = "plex"
        ))
    }

    // Add VOD options (purchase/rent) — Amazon + Apple TV + Eventive
    watchLinks?.vod?.forEach { link ->
        if (link.link != null && isValidVodService(link.service)) {
            val isEventive = isEventiveLink(link.service, link.link)
            val vodLabel = if (isEventive) "Buy Ticket" else getVodDisplayName(link.service)
            options.add(WatchOption(
                service = normalizeServiceId(link.service) ?: "vod",
                label = vodLabel,
                url = link.link,
                type = WatchType.PURCHASE,
                icon = normalizeServiceId(link.service) ?: "vod",
                rentPrice = link.rentPrice,
                buyPrice = link.buyPrice
            ))
        }
    }

    // Add streaming options - array (one button per streaming service)
    watchLinks?.streaming?.forEach { link ->
        if (link.link != null) {
            options.add(WatchOption(
                service = normalizeServiceId(link.service) ?: "streaming",
                label = getStreamDisplayName(link.service),
                url = link.link,
                type = WatchType.STREAMING,
                icon = normalizeServiceId(link.service) ?: "streaming"
            ))
        }
    }

    // Pre-order links (JustWatch buy offers for pre-order movies)
    if (options.isEmpty()) {
        val poDateLabel = digitalDate?.let { "Available ${formatShortDate(it)}" } ?: "Available TBD"
        preOrderLinks?.forEach { link ->
            if (link.link != null) {
                options.add(WatchOption(
                    service = normalizeServiceId(link.service) ?: "vod",
                    label = "Pre-Order",
                    sublabel = poDateLabel,
                    url = link.link,
                    type = WatchType.PURCHASE,
                    icon = normalizeServiceId(link.service) ?: "vod"
                ))
            }
        }
    }

    return options
}

/**
 * Get info options for a movie
 */
fun Movie.getInfoOptions(): List<InfoOption> {
    val options = mutableListOf<InfoOption>()

    val trailerUrl = links?.trailerHosted ?: links?.trailer
    trailerUrl?.let { url ->
        options.add(InfoOption(
            type = "trailer",
            label = "Watch Trailer",
            url = url
        ))
    }

    val rtUrl = links?.rt ?: links?.rottenTomatoes
    rtUrl?.let { url ->
        options.add(InfoOption(
            type = "rotten_tomatoes",
            label = "Rotten Tomatoes",
            url = url
        ))
    }

    return options
}

private fun isValidVodService(serviceName: String?): Boolean {
    if (serviceName == null) return false
    val lower = serviceName.lowercase()
    return lower.contains("amazon") ||
            lower.contains("apple") ||
            lower.contains("itunes") ||
            lower.contains("fandango") ||
            lower.contains("vudu") ||
            lower.contains("eventive")
}

private val SERVICE_NAME_MAP = mapOf(
    "amazon" to "amazon",
    "amazon video" to "amazon",
    "amazon prime video" to "amazon",
    "prime video" to "amazon",
    "apple tv" to "apple_tv",
    "apple tv+" to "apple_tv",
    "apple itunes" to "apple_tv",
    "itunes" to "apple_tv",
    "netflix" to "netflix",
    "hulu" to "hulu",
    "max" to "max",
    "hbo max" to "max",
    "peacock" to "peacock",
    "paramount+" to "paramount_plus",
    "paramount plus" to "paramount_plus",
    "disney+" to "disney_plus",
    "disney plus" to "disney_plus",
    "mubi" to "mubi",
    "criterion" to "criterion",
    "criterion channel" to "criterion",
    "angel studios" to "angel_studios",
    "fandango at home" to "fandango",
    "vudu" to "fandango",
    "vix" to "vix",
    "shudder" to "shudder",
    "fawesome" to "fawesome"
)

private fun isEventiveLink(service: String?, url: String?): Boolean {
    val lowerService = service?.lowercase() ?: ""
    val lowerUrl = url?.lowercase() ?: ""
    return lowerService.contains("eventive") ||
            lowerUrl.contains("eventive.org") ||
            lowerUrl.contains("festivalplayer") ||
            lowerUrl.contains("shift72.com")
}

private fun normalizeServiceId(serviceName: String?): String? {
    if (serviceName == null) return null
    // Strip storefront wrappers ("Shudder Amazon Channel" -> "Shudder") so the brand,
    // not the platform it's sold through, drives the id / icon / label.
    val stripped = serviceName
        .replace(Regex("\\s+(Amazon|Apple TV|Roku Premium)\\s+Channel\\s*$", RegexOption.IGNORE_CASE), "")
        .trim()
        .ifEmpty { serviceName }
    val normalized = stripped.lowercase().trim()
    return SERVICE_NAME_MAP[normalized] ?: normalized.replace(" ", "_")
}

private val VOD_DISPLAY_NAMES = mapOf(
    "amazon" to "AMAZON",
    "apple_tv" to "APPLE TV",
    "fandango" to "FANDANGO",
    "youtube" to "YOUTUBE"
)

private val STREAM_DISPLAY_NAMES = mapOf(
    "amazon" to "PRIME",
    "prime" to "PRIME",
    "apple_tv" to "APPLE TV+",
    "disney_plus" to "DISNEY+",
    "paramount_plus" to "PARAMOUNT+",
    "netflix" to "NETFLIX",
    "max" to "MAX",
    "hulu" to "HULU",
    "peacock" to "PEACOCK",
    "mubi" to "MUBI",
    "criterion" to "CRITERION"
)

private fun getVodDisplayName(service: String?): String {
    val normalized = normalizeServiceId(service) ?: return "VOD"
    return VOD_DISPLAY_NAMES[normalized] ?: normalized.uppercase()
}

private fun getStreamDisplayName(service: String?): String {
    val normalized = normalizeServiceId(service) ?: return "STREAMING"
    return STREAM_DISPLAY_NAMES[normalized] ?: normalized.uppercase()
}
