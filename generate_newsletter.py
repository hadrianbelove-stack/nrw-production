#!/usr/bin/env python3
"""
Newsletter Generator for New Release Watcher (NRW)

Generates newsletters from movie data and reviews in multiple formats.
"""

import json
import argparse
try:
    import yaml
except ImportError:
    yaml = None
import os
import sys
import html as html_module
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict


class NewsletterGenerator:
    """Generates newsletters from movie data and reviews."""

    def __init__(self, config_path: str = "config.yaml"):
        """Initialize the newsletter generator with configuration."""
        self.config = self._load_config(config_path)
        self.movies: List[Dict[str, Any]] = []
        self.reviews: Dict[str, Dict[str, Any]] = {}
        self.filtered_movies: List[Dict[str, Any]] = []

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        if yaml is None:
            return {}
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print(f"Warning: Config file {config_path} not found, using defaults")
            return {}
        except Exception as e:
            print(f"Error loading config: {e}")
            return {}

    def load_data(self, data_file: str = "data.json") -> bool:
        """Load movie data from JSON file."""
        try:
            with open(data_file, 'r') as f:
                data = json.load(f)
                self.movies = data.get('movies', [])
                return True
        except FileNotFoundError:
            print(f"Error: Data file {data_file} not found")
            return False
        except json.JSONDecodeError as e:
            print(f"Error parsing data file: {e}")
            return False
        except Exception as e:
            print(f"Error loading data: {e}")
            return False

    def load_reviews(self, reviews_file: str = "admin/movie_reviews.json") -> bool:
        """Load movie reviews from JSON file."""
        try:
            with open(reviews_file, 'r') as f:
                self.reviews = json.load(f)
                return True
        except FileNotFoundError:
            print(f"Info: Reviews file {reviews_file} not found, proceeding without reviews")
            self.reviews = {}
            return True
        except json.JSONDecodeError as e:
            print(f"Error parsing reviews file: {e}")
            self.reviews = {}
            return True
        except Exception as e:
            print(f"Error loading reviews: {e}")
            self.reviews = {}
            return True

    def _safe_parse_date(self, date_str: str) -> Optional[datetime]:
        """Safely parse date string in YYYY-MM-DD format."""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            try:
                # Try parsing with time component
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            except ValueError:
                return None

    def filter_by_date_range(self, days: int) -> List[Dict[str, Any]]:
        """Filter movies by date range (last N days)."""
        if not self.movies:
            return []

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        filtered = []
        for movie in self.movies:
            movie_date = self._safe_parse_date(movie.get('digital_date'))
            if movie_date and start_date <= movie_date <= end_date:
                filtered.append(movie)

        # Sort by date (newest first)
        filtered.sort(key=lambda m: self._safe_parse_date(m.get('digital_date')) or datetime.min, reverse=True)
        self.filtered_movies = filtered
        return filtered

    def _normalize_provider_name(self, provider: str) -> str:
        """Normalize provider names for consistency."""
        normalization_map = {
            "Amazon Video": "Amazon Prime Video",
            "Apple TV": "Apple TV+",
            "Fandango At Home": "Vudu",
            "Google Play Movies": "Google Play",
            "Microsoft Store": "Microsoft",
        }
        return normalization_map.get(provider, provider)

    def group_by_platform(self, movies: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group movies by streaming platform."""
        platform_groups = defaultdict(list)

        for movie in movies:
            providers = movie.get('providers', {})
            movie_platforms = set()

            # Collect all platforms for this movie
            for provider_type in ['streaming', 'rent', 'buy']:
                for provider in providers.get(provider_type, []):
                    normalized = self._normalize_provider_name(provider)
                    movie_platforms.add(normalized)

            # Add movie to each platform group
            for platform in movie_platforms:
                platform_groups[platform].append(movie)

        # Sort platforms by movie count (descending)
        sorted_platforms = dict(sorted(
            platform_groups.items(),
            key=lambda x: len(x[1]),
            reverse=True
        ))

        return sorted_platforms

    def get_reviewed_movies(self) -> List[Dict[str, Any]]:
        """Get movies that have reviews."""
        reviewed = []
        for movie in self.filtered_movies:
            movie_id = movie.get('id')
            if movie_id is not None and str(movie_id) in self.reviews:
                movie_with_review = movie.copy()
                movie_with_review['review'] = self.reviews[str(movie_id)]
                reviewed.append(movie_with_review)
        return reviewed

    def get_hero_review(self) -> Optional[Dict[str, Any]]:
        """Get the hero review movie (featured or highest-rated)."""
        reviewed_movies = self.get_reviewed_movies()
        if not reviewed_movies:
            return None

        # First priority: featured_in_newsletter flag
        for movie in reviewed_movies:
            review = movie.get('review', {})
            if review.get('featured_in_newsletter'):
                return movie

        # Second priority: highest-rated reviewed movie
        def get_score(movie):
            rt_score = movie.get('rt_score', '0%')
            try:
                return int(rt_score.rstrip('%'))
            except (ValueError, AttributeError):
                return 0

        return max(reviewed_movies, key=get_score)

    def _truncate_text(self, text: str, max_length: int) -> str:
        """Truncate text to maximum length with ellipsis."""
        if len(text) <= max_length:
            return text
        return text[:max_length-3] + "..."

    def _fmt_rt_score(self, value: Any) -> str:
        """Format RT score value, returning N/A when missing or invalid."""
        if not value or not isinstance(value, str) or value.strip() == "":
            return "N/A"
        return value

    def _get_platform_availability(self, movie: Dict[str, Any]) -> str:
        """Get formatted platform availability text."""
        providers = movie.get('providers', {})
        streaming = [self._normalize_provider_name(p) for p in providers.get('streaming', [])]
        rent = [self._normalize_provider_name(p) for p in providers.get('rent', [])]
        buy = [self._normalize_provider_name(p) for p in providers.get('buy', [])]

        parts = []
        if streaming:
            parts.append(f"Streaming: {', '.join(streaming)}")
        if rent:
            parts.append(f"Rent: {', '.join(rent)}")
        if buy:
            parts.append(f"Buy: {', '.join(buy)}")

        return " | ".join(parts) if parts else "Platform information not available"

    def generate_markdown(self, movies: List[Dict[str, Any]], output_date: str) -> str:
        """Generate newsletter in Markdown format."""
        hero_movie = self.get_hero_review()
        reviewed_movies = self.get_reviewed_movies()
        platform_groups = self.group_by_platform(movies)

        content = []

        # Header
        content.append(f"# New Release Watcher Newsletter")
        content.append(f"*Generated on {output_date}*\n")

        # Hero Review Section
        content.append("## 🌟 Hero Review")
        if hero_movie:
            review = hero_movie.get('review', {})
            content.append(f"### {hero_movie['title']} ({hero_movie.get('year', 'TBD')})")
            content.append(f"**RT Score:** {self._fmt_rt_score(hero_movie.get('rt_score'))}")
            content.append(f"**Director:** {hero_movie.get('crew', {}).get('director', 'N/A')}")
            content.append(f"**Cast:** {', '.join(hero_movie.get('crew', {}).get('cast', []))}")
            content.append(f"**Genres:** {', '.join(hero_movie.get('genres', []))}")
            content.append(f"**Availability:** {self._get_platform_availability(hero_movie)}")
            content.append(f"\n**Synopsis:** {hero_movie.get('synopsis', 'No synopsis available.')}")
            if review.get('review'):
                content.append(f"\n**Review:** {review['review']}")
        else:
            content.append("No featured review this week.")
        content.append("")

        # This Week's Highlights
        content.append("## 📽️ This Week's Highlights")
        if reviewed_movies:
            for movie in reviewed_movies[:5]:  # Top 5 highlights
                if movie == hero_movie:  # Skip hero movie
                    continue
                review = movie.get('review', {})
                content.append(f"### {movie['title']} ({movie.get('year', 'TBD')})")
                content.append(f"**RT Score:** {self._fmt_rt_score(movie.get('rt_score'))} | **Genres:** {', '.join(movie.get('genres', []))}")
                if review.get('review'):
                    excerpt = self._truncate_text(review['review'], 200)
                    content.append(f"*{excerpt}*")
                content.append("")
        else:
            content.append("No highlighted movies this week.")

        # By Platform Section
        content.append("## 📺 By Platform")
        if platform_groups:
            for platform, platform_movies in platform_groups.items():
                content.append(f"### {platform} ({len(platform_movies)} movies)")
                for movie in platform_movies[:5]:  # Top 5 per platform
                    content.append(f"- **{movie['title']}** ({movie.get('year', 'TBD')}) - {self._fmt_rt_score(movie.get('rt_score'))}")
                content.append("")
        else:
            content.append("No platform information available.")

        # Quick List
        content.append("## 📋 Quick List")
        content.append("All movies this week:")
        for movie in movies[:20]:  # Top 20
            content.append(f"- {movie['title']} ({movie.get('year', 'TBD')}) - {self._fmt_rt_score(movie.get('rt_score'))}")
        content.append("")

        # Footer
        content.append("---")
        content.append("*Generated by New Release Watcher*")

        return "\n".join(content)

    def generate_html(self, movies: List[Dict[str, Any]], output_date: str) -> str:
        """Generate newsletter in HTML format with inline styles."""
        hero_movie = self.get_hero_review()
        reviewed_movies = self.get_reviewed_movies()
        platform_groups = self.group_by_platform(movies)

        html = []

        # HTML structure with inline styles for email compatibility
        html.append('<!DOCTYPE html>')
        html.append('<html>')
        html.append('<head>')
        html.append('<meta charset="utf-8">')
        html.append('<title>New Release Watcher Newsletter</title>')
        html.append('</head>')
        html.append('<body style="font-family: Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; background-color: #f9f9f9;">')

        # Header
        html.append('<div style="background-color: #2c3e50; color: white; padding: 20px; text-align: center; border-radius: 8px; margin-bottom: 20px;">')
        html.append('<h1 style="margin: 0;">🎬 New Release Watcher Newsletter</h1>')
        html.append(f'<p style="margin: 5px 0 0 0; opacity: 0.8;">Generated on {output_date}</p>')
        html.append('</div>')

        # Hero Review
        html.append('<div style="background-color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">')
        html.append('<h2 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px;">🌟 Hero Review</h2>')
        if hero_movie:
            review = hero_movie.get('review', {})
            html.append(f'<h3 style="color: #2980b9;">{hero_movie["title"]} ({hero_movie.get("year", "TBD")})</h3>')
            html.append(f'<p><strong>RT Score:</strong> {self._fmt_rt_score(hero_movie.get("rt_score"))} | <strong>Director:</strong> {hero_movie.get("crew", {}).get("director", "N/A")}</p>')
            html.append(f'<p><strong>Cast:</strong> {", ".join(hero_movie.get("crew", {}).get("cast", []))}</p>')
            html.append(f'<p><strong>Genres:</strong> {", ".join(hero_movie.get("genres", []))}</p>')
            html.append(f'<p><strong>Availability:</strong> {self._get_platform_availability(hero_movie)}</p>')
            html.append(f'<p><strong>Synopsis:</strong> {html_module.escape(hero_movie.get("synopsis", "No synopsis available."))}</p>')
            if review.get('review'):
                html.append(f'<blockquote style="border-left: 4px solid #3498db; padding-left: 15px; margin: 15px 0; font-style: italic;">{html_module.escape(review["review"])}</blockquote>')
        else:
            html.append('<p>No featured review this week.</p>')
        html.append('</div>')

        # This Week's Highlights
        html.append('<div style="background-color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">')
        html.append('<h2 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px;">📽️ This Week\'s Highlights</h2>')
        if reviewed_movies:
            for movie in reviewed_movies[:5]:
                if movie == hero_movie:
                    continue
                review = movie.get('review', {})
                html.append(f'<div style="border-bottom: 1px solid #ecf0f1; padding-bottom: 15px; margin-bottom: 15px;">')
                html.append(f'<h4 style="color: #2980b9; margin-bottom: 5px;">{movie["title"]} ({movie.get("year", "TBD")})</h4>')
                html.append(f'<p style="margin: 5px 0;"><strong>RT Score:</strong> {self._fmt_rt_score(movie.get("rt_score"))} | <strong>Genres:</strong> {", ".join(movie.get("genres", []))}</p>')
                if review.get('review'):
                    excerpt = self._truncate_text(review['review'], 200)
                    html.append(f'<p style="font-style: italic; color: #555;">{html_module.escape(excerpt)}</p>')
                html.append('</div>')
        else:
            html.append('<p>No highlighted movies this week.</p>')
        html.append('</div>')

        # By Platform
        html.append('<div style="background-color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">')
        html.append('<h2 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px;">📺 By Platform</h2>')
        if platform_groups:
            for platform, platform_movies in platform_groups.items():
                html.append(f'<h4 style="color: #2980b9;">{platform} ({len(platform_movies)} movies)</h4>')
                html.append('<ul>')
                for movie in platform_movies[:5]:
                    html.append(f'<li><strong>{movie["title"]}</strong> ({movie.get("year", "TBD")}) - {self._fmt_rt_score(movie.get("rt_score"))}</li>')
                html.append('</ul>')
        else:
            html.append('<p>No platform information available.</p>')
        html.append('</div>')

        # Quick List
        html.append('<div style="background-color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">')
        html.append('<h2 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px;">📋 Quick List</h2>')
        html.append('<p>All movies this week:</p>')
        html.append('<ul>')
        for movie in movies[:20]:
            html.append(f'<li>{movie["title"]} ({movie.get("year", "TBD")}) - {self._fmt_rt_score(movie.get("rt_score"))}</li>')
        html.append('</ul>')
        html.append('</div>')

        # Footer
        html.append('<div style="background-color: #34495e; color: white; padding: 15px; text-align: center; border-radius: 8px;">')
        html.append('<p style="margin: 0;">Generated by New Release Watcher</p>')
        html.append('</div>')

        html.append('</body>')
        html.append('</html>')

        return '\n'.join(html)

    def generate_text(self, movies: List[Dict[str, Any]], output_date: str) -> str:
        """Generate newsletter in plain text format."""
        hero_movie = self.get_hero_review()
        reviewed_movies = self.get_reviewed_movies()
        platform_groups = self.group_by_platform(movies)

        content = []
        content.append("=" * 60)
        content.append("NEW RELEASE WATCHER NEWSLETTER")
        content.append(f"Generated on {output_date}")
        content.append("=" * 60)
        content.append("")

        # Hero Review
        content.append("HERO REVIEW")
        content.append("-" * 20)
        if hero_movie:
            review = hero_movie.get('review', {})
            content.append(f"Title: {hero_movie['title']} ({hero_movie.get('year', 'TBD')})")
            content.append(f"RT Score: {self._fmt_rt_score(hero_movie.get('rt_score'))}")
            content.append(f"Director: {hero_movie.get('crew', {}).get('director', 'N/A')}")
            content.append(f"Cast: {', '.join(hero_movie.get('crew', {}).get('cast', []))}")
            content.append(f"Genres: {', '.join(hero_movie.get('genres', []))}")
            content.append(f"Availability: {self._get_platform_availability(hero_movie)}")
            content.append(f"\nSynopsis: {hero_movie.get('synopsis', 'No synopsis available.')}")
            if review.get('review'):
                content.append(f"\nReview: {review['review']}")
        else:
            content.append("No featured review this week.")
        content.append("")

        # This Week's Highlights
        content.append("THIS WEEK'S HIGHLIGHTS")
        content.append("-" * 30)
        if reviewed_movies:
            for i, movie in enumerate(reviewed_movies[:5]):
                if movie == hero_movie:
                    continue
                review = movie.get('review', {})
                content.append(f"{i+1}. {movie['title']} ({movie.get('year', 'TBD')})")
                content.append(f"   RT Score: {self._fmt_rt_score(movie.get('rt_score'))} | Genres: {', '.join(movie.get('genres', []))}")
                if review.get('review'):
                    excerpt = self._truncate_text(review['review'], 200)
                    content.append(f"   Review: {excerpt}")
                content.append("")
        else:
            content.append("No highlighted movies this week.")
            content.append("")

        # By Platform
        content.append("BY PLATFORM")
        content.append("-" * 15)
        if platform_groups:
            for platform, platform_movies in platform_groups.items():
                content.append(f"{platform} ({len(platform_movies)} movies):")
                for movie in platform_movies[:5]:
                    content.append(f"  - {movie['title']} ({movie.get('year', 'TBD')}) - {self._fmt_rt_score(movie.get('rt_score'))}")
                content.append("")
        else:
            content.append("No platform information available.")
            content.append("")

        # Quick List
        content.append("QUICK LIST")
        content.append("-" * 12)
        content.append("All movies this week:")
        for i, movie in enumerate(movies[:20]):
            content.append(f"{i+1:2d}. {movie['title']} ({movie.get('year', 'TBD')}) - {self._fmt_rt_score(movie.get('rt_score'))}")
        content.append("")

        # Footer
        content.append("=" * 60)
        content.append("Generated by New Release Watcher")
        content.append("=" * 60)

        return "\n".join(content)

    def save_newsletter(self, content: str, format_type: str, output_dir: str, date_str: str) -> str:
        """Save newsletter content to file with dated filename."""
        os.makedirs(output_dir, exist_ok=True)

        extensions = {
            'markdown': 'md',
            'html': 'html',
            'text': 'txt'
        }

        extension = extensions.get(format_type, 'txt')
        filename = f"newsletter_{date_str}.{extension}"
        filepath = os.path.join(output_dir, filename)

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return filepath
        except Exception as e:
            print(f"Error saving newsletter: {e}")
            return ""

    def generate_newsletter(self, days: int = 7, format_type: str = "all", output_dir: str = "newsletters/") -> List[str]:
        """Generate newsletter in specified format(s)."""
        # Load data
        if not self.load_data():
            return []

        self.load_reviews()

        # Filter movies by date range
        movies = self.filter_by_date_range(days)

        if not movies:
            print(f"No movies found in the last {days} days.")
            return []

        print(f"Found {len(movies)} movies in the last {days} days.")

        # Generate output
        output_date = datetime.now().strftime("%Y-%m-%d")
        generated_files = []

        formats_to_generate = []
        if format_type == "all":
            formats_to_generate = ["markdown", "html", "text"]
        else:
            formats_to_generate = [format_type]

        for fmt in formats_to_generate:
            if fmt == "markdown":
                content = self.generate_markdown(movies, output_date)
            elif fmt == "html":
                content = self.generate_html(movies, output_date)
            elif fmt == "text":
                content = self.generate_text(movies, output_date)
            else:
                print(f"Unknown format: {fmt}")
                continue

            filepath = self.save_newsletter(content, fmt, output_dir, output_date)
            if filepath:
                generated_files.append(filepath)
                print(f"Generated {fmt} newsletter: {filepath}")

        return generated_files


def main():
    """Main entry point for the newsletter generator."""
    parser = argparse.ArgumentParser(description="Generate movie newsletter from NRW data")
    parser.add_argument("--days", type=int, default=None, help="Number of days to look back (default: 7)")
    parser.add_argument("--format", choices=["markdown", "html", "text", "all"], default="all", help="Output format (default: all)")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: newsletters/)")

    args = parser.parse_args()

    # Create newsletter generator
    generator = NewsletterGenerator()

    # Override defaults with config if available
    newsletter_config = generator.config.get('newsletter', {})
    days = newsletter_config.get('days_back', 7)
    if args.days is not None:
        days = args.days
    output_dir = newsletter_config.get('output_dir', 'newsletters/')
    if args.output_dir is not None:
        output_dir = args.output_dir

    # Generate newsletter
    try:
        generated_files = generator.generate_newsletter(days, args.format, output_dir)
        if generated_files:
            print(f"\nSuccessfully generated {len(generated_files)} newsletter file(s):")
            for filepath in generated_files:
                print(f"  - {filepath}")
        else:
            print("No newsletter files were generated.")
            sys.exit(1)
    except Exception as e:
        print(f"Error generating newsletter: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()