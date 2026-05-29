package com.nrw.app.data

import android.content.Context
import android.util.Log
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.google.gson.Gson
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withContext
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.GET

private const val TAG = "MovieRepository"
private const val DATA_URL = "https://raw.githubusercontent.com/hadrianbelove-stack/nrw-production/main/"
private const val CACHE_DURATION_MS = 24 * 60 * 60 * 1000L // 24 hours

// DataStore for caching
private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "nrw_cache")

private val CACHE_KEY_DATA = stringPreferencesKey("movies_data")
private val CACHE_KEY_TIMESTAMP = longPreferencesKey("movies_timestamp")

/**
 * Retrofit API service for fetching movie data
 */
interface NRWApiService {
    @GET("data.json")
    suspend fun getMovies(): MoviesResponse
}

/**
 * Data class for repository response with movies and metadata
 */
data class MovieData(
    val movies: List<Movie>,
    val playlistUrl: String? = null
)

/**
 * Repository for fetching and caching movie data
 */
class MovieRepository(private val context: Context) {

    private val gson = Gson()

    // Cache the playlist URL
    private var cachedPlaylistUrl: String? = null

    private val api: NRWApiService by lazy {
        Retrofit.Builder()
            .baseUrl(DATA_URL)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(NRWApiService::class.java)
    }

    /**
     * Fetch movies from network or cache
     */
    suspend fun getMovies(forceRefresh: Boolean = false): Result<List<Movie>> {
        return withContext(Dispatchers.IO) {
            try {
                // Check cache first (unless force refresh)
                if (!forceRefresh) {
                    val cached = getCachedMovies()
                    if (cached != null) {
                        Log.d(TAG, "Returning ${cached.size} movies from cache")
                        return@withContext Result.success(cached)
                    }
                }

                // Fetch from network
                Log.d(TAG, "Fetching movies from network")
                val response = api.getMovies()
                val movies = response.movies
                cachedPlaylistUrl = response.latestPlaylistUrl

                // Cache the response
                cacheMovies(response)

                Log.d(TAG, "Fetched ${movies.size} movies from network")
                Result.success(movies)

            } catch (e: Exception) {
                Log.e(TAG, "Error fetching movies", e)

                // Try to return stale cache on error
                val staleCache = getCachedMovies(ignoreExpiry = true)
                if (staleCache != null) {
                    Log.d(TAG, "Returning stale cache due to network error")
                    return@withContext Result.success(staleCache)
                }

                Result.failure(e)
            }
        }
    }

    /**
     * Get the YouTube playlist URL for trailers
     */
    fun getPlaylistUrl(): String? = cachedPlaylistUrl

    private suspend fun getCachedMovies(ignoreExpiry: Boolean = false): List<Movie>? {
        return try {
            val prefs = context.dataStore.data.first()
            val timestamp = prefs[CACHE_KEY_TIMESTAMP] ?: 0L
            val dataJson = prefs[CACHE_KEY_DATA] ?: return null

            // Check if cache is expired
            if (!ignoreExpiry && System.currentTimeMillis() - timestamp > CACHE_DURATION_MS) {
                Log.d(TAG, "Cache expired")
                return null
            }

            val response = gson.fromJson(dataJson, MoviesResponse::class.java)
            cachedPlaylistUrl = response.latestPlaylistUrl
            response.movies
        } catch (e: Exception) {
            Log.e(TAG, "Error reading cache", e)
            null
        }
    }

    private suspend fun cacheMovies(response: MoviesResponse) {
        try {
            val json = gson.toJson(response)

            context.dataStore.edit { prefs ->
                prefs[CACHE_KEY_DATA] = json
                prefs[CACHE_KEY_TIMESTAMP] = System.currentTimeMillis()
            }
            Log.d(TAG, "Cached ${response.movies.size} movies")
        } catch (e: Exception) {
            Log.e(TAG, "Error caching movies", e)
        }
    }

    /**
     * Filter movies by category
     */
    fun filterMovies(movies: List<Movie>, filter: FilterCategory): List<Movie> {
        return when (filter) {
            FilterCategory.INDIE -> movies.filter {
                it.hidden != true && it.enrichmentStatus != "reverted" && (it.categories?.isIndie == true || it.categories?.tier == "indie")
            }
            FilterCategory.STAFF_PICKS -> movies.filter {
                it.hidden != true && it.enrichmentStatus != "reverted" && it.isStaffPick()
            }
            FilterCategory.FOREIGN -> movies.filter {
                it.hidden != true && it.enrichmentStatus != "reverted" && it.isForeign()
            }
            FilterCategory.RESTORATIONS -> movies.filter {
                it.hidden != true && it.enrichmentStatus != "reverted" && it.categories?.isRestoration == true
            }
            FilterCategory.DOCUMENTARY -> movies.filter {
                it.hidden != true && it.enrichmentStatus != "reverted" && it.categories?.isDocumentary == true
            }
            FilterCategory.HORROR -> movies.filter {
                it.hidden != true && it.enrichmentStatus != "reverted" && (it.genres?.any { g -> g.lowercase().contains("horror") } == true)
            }
            FilterCategory.ACTION -> movies.filter {
                it.hidden != true && it.enrichmentStatus != "reverted" && (it.genres?.any { g -> g.lowercase().contains("action") } == true)
            }
            FilterCategory.COMEDY -> movies.filter {
                it.hidden != true && it.enrichmentStatus != "reverted" && (it.genres?.any { g -> g.lowercase().contains("comedy") } == true)
            }
        }
    }

    /**
     * Filter movies by multiple categories (OR logic - cumulative)
     */
    fun filterMoviesMulti(movies: List<Movie>, activeFilters: Set<FilterCategory>, searchQuery: String = ""): List<Movie> {
        if (activeFilters.isEmpty()) {
            return movies.filter { it.hidden != true && it.enrichmentStatus != "reverted" }
        }
        return movies.filter { movie ->
            if (movie.hidden == true || movie.enrichmentStatus == "reverted") return@filter false
            activeFilters.any { filter ->
                when (filter) {
                    FilterCategory.INDIE -> movie.categories?.isIndie == true || movie.categories?.tier == "indie"
                    FilterCategory.STAFF_PICKS -> movie.isStaffPick()
                    FilterCategory.FOREIGN -> movie.isForeign()
                    FilterCategory.RESTORATIONS -> movie.categories?.isRestoration == true
                    FilterCategory.DOCUMENTARY -> movie.categories?.isDocumentary == true
                    FilterCategory.HORROR -> movie.genres?.any { it.lowercase().contains("horror") } == true
                    FilterCategory.ACTION -> movie.genres?.any { it.lowercase().contains("action") } == true
                    FilterCategory.COMEDY -> movie.genres?.any { it.lowercase().contains("comedy") } == true
                }
            }
        }
    }

    /**
     * Search movies by title, director, or genre
     */
    fun searchMovies(movies: List<Movie>, query: String): List<Movie> {
        if (query.isBlank()) return movies

        val lowerQuery = query.lowercase().trim()
        return movies.filter { movie ->
            val title = movie.title.lowercase()
            val director = movie.getDirector()?.lowercase() ?: ""
            val genres = movie.genres?.map { it.lowercase() } ?: emptyList()

            title.contains(lowerQuery) ||
                    director.contains(lowerQuery) ||
                    genres.any { it.contains(lowerQuery) }
        }
    }

    /**
     * Group movies by release date
     */
    fun groupMoviesByDate(movies: List<Movie>): Map<String, List<Movie>> {
        val grouped = movies.groupBy { it.getDisplayDate() ?: "Unknown" }

        // Sort by date descending
        return grouped.toSortedMap(compareByDescending { dateStr ->
            if (dateStr == "Unknown") {
                Long.MIN_VALUE
            } else {
                try {
                    java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US)
                        .parse(dateStr)?.time ?: Long.MIN_VALUE
                } catch (e: Exception) {
                    Long.MIN_VALUE
                }
            }
        })
    }
}
