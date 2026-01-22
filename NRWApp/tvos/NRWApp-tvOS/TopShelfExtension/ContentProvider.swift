/**
 * New Release Wall - tvOS Top Shelf Extension
 * Shows featured movies on Apple TV home screen when app is in top row
 */

import TVServices
import Foundation

class ContentProvider: TVTopShelfContentProvider {

    // MARK: - Properties

    private let dataURL = URL(string: "https://raw.githubusercontent.com/YOUR_USERNAME/nrw-production/main/data.json")!
    private let cacheKey = "topShelfMovies"
    private let maxItems = 5

    // MARK: - TVTopShelfContentProvider

    override func loadTopShelfContent(completionHandler: @escaping (TVTopShelfContent?) -> Void) {
        // Fetch featured movies and create Top Shelf content
        fetchFeaturedMovies { [weak self] movies in
            guard let self = self, let movies = movies, !movies.isEmpty else {
                completionHandler(nil)
                return
            }

            // Create carousel items for featured movies
            let items = movies.prefix(self.maxItems).compactMap { movie -> TVTopShelfCarouselItem? in
                return self.createCarouselItem(for: movie)
            }

            // Create sectioned content with carousel style
            let sectionedContent = TVTopShelfSectionedContent(sections: [
                TVTopShelfItemCollection(items: items)
            ])

            completionHandler(sectionedContent)
        }
    }

    // MARK: - Private Methods

    private func fetchFeaturedMovies(completion: @escaping ([[String: Any]]?) -> Void) {
        // Check cache first
        if let cached = loadCachedMovies() {
            completion(cached)
            return
        }

        // Fetch from network
        let task = URLSession.shared.dataTask(with: dataURL) { [weak self] data, response, error in
            guard let data = data,
                  let json = try? JSONSerialization.jsonObject(with: data) else {
                completion(nil)
                return
            }

            var movies: [[String: Any]] = []
            var featuredIds: [String] = []

            // Parse root dictionary format: { movies: [...], featured: [...] }
            if let rootDict = json as? [String: Any] {
                movies = rootDict["movies"] as? [[String: Any]] ?? []
                featuredIds = (rootDict["featured"] as? [Any])?.compactMap { item -> String? in
                    if let str = item as? String { return str }
                    if let num = item as? Int { return String(num) }
                    return nil
                } ?? []
            } else if let moviesArray = json as? [[String: Any]] {
                // Legacy array format
                movies = moviesArray
            }

            // Filter featured movies using featuredIds list or movie.featured flag
            let featured: [[String: Any]]
            if !featuredIds.isEmpty {
                let featuredSet = Set(featuredIds)
                featured = movies.filter { movie in
                    if let id = movie["id"] as? String {
                        return featuredSet.contains(id)
                    } else if let id = movie["id"] as? Int {
                        return featuredSet.contains(String(id))
                    }
                    return false
                }
            } else {
                featured = movies.filter { movie in
                    (movie["featured"] as? Bool) == true
                }
            }

            // Cache the results
            self?.cacheMovies(featured)

            completion(featured)
        }
        task.resume()
    }

    private func createCarouselItem(for movie: [String: Any]) -> TVTopShelfCarouselItem? {
        guard let title = movie["title"] as? String else {
            return nil
        }

        // Get poster URL - try "poster" first, then "poster_url"
        let posterURLString = movie["poster"] as? String ?? movie["poster_url"] as? String
        guard let posterString = posterURLString,
              let url = URL(string: posterString) else {
            return nil
        }

        // Get movie ID as string (handle both String and Int types)
        let movieID: String?
        if let id = movie["id"] as? String {
            movieID = id
        } else if let id = movie["id"] as? Int {
            movieID = String(id)
        } else {
            movieID = nil
        }

        // Create item identifier (movie ID or title-based)
        let identifier = TVTopShelfIdentifier(rawValue: movieID ?? title)

        // Create carousel item
        let item = TVTopShelfCarouselItem(identifier: identifier)
        item.title = title

        // Set poster image
        item.setImageURL(url, for: .screenScale1x)
        item.setImageURL(url, for: .screenScale2x)

        // Set display action (opens app to movie detail)
        if let id = movieID {
            if let displayURL = URL(string: "nrw://movie/\(id)") {
                item.displayAction = TVTopShelfAction(url: displayURL)
                item.playAction = TVTopShelfAction(url: displayURL)
            }
        }

        // Add metadata - prefer director from crew.director, fallback to top-level director
        var contextParts: [String] = []

        if let year = movie["year"] as? Int {
            contextParts.append(String(year))
        }

        // Try crew.director first, then fallback to top-level director
        if let crew = movie["crew"] as? [String: Any],
           let director = crew["director"] as? String {
            contextParts.append("Dir. \(director)")
        } else if let director = movie["director"] as? String {
            contextParts.append("Dir. \(director)")
        }

        if !contextParts.isEmpty {
            item.contextTitle = contextParts.joined(separator: " • ")
        }

        return item
    }

    // MARK: - Caching

    private func cacheMovies(_ movies: [[String: Any]]) {
        guard let data = try? JSONSerialization.data(withJSONObject: movies) else { return }
        UserDefaults.standard.set(data, forKey: cacheKey)
        UserDefaults.standard.set(Date(), forKey: "\(cacheKey)_timestamp")
    }

    private func loadCachedMovies() -> [[String: Any]]? {
        // Check if cache is still valid (24 hours)
        guard let timestamp = UserDefaults.standard.object(forKey: "\(cacheKey)_timestamp") as? Date,
              Date().timeIntervalSince(timestamp) < 24 * 60 * 60,
              let data = UserDefaults.standard.data(forKey: cacheKey),
              let movies = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]] else {
            return nil
        }
        return movies
    }
}
