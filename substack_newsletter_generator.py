#!/usr/bin/env python3
"""
Substack Newsletter Generator for New Release Wall
Creates beautiful HTML newsletters from data.json

Usage:
    python3 substack_newsletter_generator.py weekly
    python3 substack_newsletter_generator.py monthly
"""

import json
import sys
from datetime import datetime, timedelta
from collections import Counter
import argparse


class SubstackNewsletterGenerator:
    """Generates formatted newsletters for Substack"""

    def __init__(self):
        self.load_data()

    def load_data(self):
        """Load movie data from data.json"""
        with open('data.json') as f:
            data = json.load(f)
        self.movies = data['movies']

    def get_movies_by_date_range(self, days_back=7):
        """Get movies released in the last N days"""
        cutoff = datetime.now().date() - timedelta(days=days_back)
        movies = []

        for movie in self.movies:
            digital_date = datetime.fromisoformat(movie['digital_date']).date()
            if digital_date >= cutoff:
                movies.append(movie)

        return movies

    def generate_weekly_newsletter(self):
        """Generate weekly newsletter HTML"""
        movies = self.get_movies_by_date_range(days_back=7)

        if not movies:
            return "<p>No new releases this week.</p>"

        # Get date range
        dates = [datetime.fromisoformat(m['digital_date']).date() for m in movies]
        start_date = min(dates)
        end_date = max(dates)

        # Categorize movies
        top_picks = self._get_top_picks(movies, count=5)
        by_genre = self._group_by_genre(movies)
        hidden_gems = self._get_hidden_gems(movies)

        # Generate HTML
        html = self._generate_header(
            f"This Week's New Releases",
            f"{start_date.strftime('%B %d')} - {end_date.strftime('%B %d, %Y')}"
        )

        html += self._generate_intro(len(movies))
        html += self._generate_top_picks_section(top_picks)

        if hidden_gems:
            html += self._generate_hidden_gems_section(hidden_gems)

        html += self._generate_genre_sections(by_genre)
        html += self._generate_full_list(movies)
        html += self._generate_footer()

        return html

    def _get_top_picks(self, movies, count=5):
        """Get top rated movies"""
        rated = []
        for m in movies:
            rt = m.get('rt_score')
            if rt:
                rt_int = self._safe_int_score(rt)
                if rt_int > 0:
                    m['_rt_int'] = rt_int
                    rated.append(m)

        rated.sort(key=lambda x: x['_rt_int'], reverse=True)
        return rated[:count]

    def _get_hidden_gems(self, movies):
        """Get well-rated but lesser-known movies (80-89% RT)"""
        gems = []
        for m in movies:
            rt = m.get('rt_score')
            if rt:
                rt_int = self._safe_int_score(rt)
                if 80 <= rt_int < 90:
                    m['_rt_int'] = rt_int
                    gems.append(m)

        gems.sort(key=lambda x: x['_rt_int'], reverse=True)
        return gems[:3]

    def _group_by_genre(self, movies):
        """Group movies by primary genre"""
        by_genre = {}

        for movie in movies:
            genres = movie.get('genres', [])
            if genres:
                primary_genre = genres[0]
                if primary_genre not in by_genre:
                    by_genre[primary_genre] = []
                by_genre[primary_genre].append(movie)

        # Sort each genre by RT score
        for genre in by_genre:
            by_genre[genre].sort(
                key=lambda x: self._safe_int_score(x.get('rt_score')),
                reverse=True
            )

        return by_genre

    def _safe_int_score(self, score):
        """Safely convert RT score to int"""
        if not score:
            return 0
        try:
            # Remove % if present
            score_str = str(score).replace('%', '').strip()
            return int(score_str)
        except:
            return 0

    def _generate_header(self, title, subtitle):
        """Generate newsletter header"""
        return f"""
<div style="max-width: 600px; margin: 0 auto; font-family: Georgia, serif;">
    <div style="text-align: center; padding: 40px 20px 20px;">
        <h1 style="font-size: 42px; margin: 0; color: #1a1a1a; font-weight: 700;">
            🎬 New Release Wall
        </h1>
        <p style="font-size: 18px; color: #666; margin: 10px 0 0;">
            {subtitle}
        </p>
    </div>

    <div style="border-top: 3px solid #ff6b6b; margin: 20px 0;"></div>

    <div style="padding: 20px;">
        <h2 style="font-size: 32px; color: #1a1a1a; margin: 0 0 10px;">
            {title}
        </h2>
    </div>
"""

    def _generate_intro(self, count):
        """Generate intro paragraph"""
        return f"""
    <div style="padding: 0 20px 30px; line-height: 1.6;">
        <p style="font-size: 18px; color: #333; margin: 0;">
            {count} movies hit digital platforms this week. Here are our top picks, hidden gems, and the full lineup organized by genre.
        </p>
    </div>
"""

    def _generate_top_picks_section(self, movies):
        """Generate top picks section"""
        if not movies:
            return ""

        html = """
    <div style="background: #f8f8f8; padding: 30px 20px; margin: 0 0 30px;">
        <h3 style="font-size: 24px; color: #ff6b6b; margin: 0 0 20px; border-left: 4px solid #ff6b6b; padding-left: 15px;">
            🏆 Top Picks
        </h3>
"""

        for i, movie in enumerate(movies, 1):
            html += self._generate_movie_card(movie, index=i, featured=True)

        html += "    </div>\n"
        return html

    def _generate_hidden_gems_section(self, movies):
        """Generate hidden gems section"""
        if not movies:
            return ""

        html = """
    <div style="background: #fff3cd; padding: 30px 20px; margin: 0 0 30px;">
        <h3 style="font-size: 24px; color: #856404; margin: 0 0 20px; border-left: 4px solid #ffc107; padding-left: 15px;">
            💎 Hidden Gems
        </h3>
        <p style="font-size: 14px; color: #856404; margin: 0 0 20px; font-style: italic;">
            Well-reviewed but under-the-radar releases worth your time
        </p>
"""

        for movie in movies:
            html += self._generate_movie_card(movie, compact=True)

        html += "    </div>\n"
        return html

    def _generate_genre_sections(self, by_genre):
        """Generate sections organized by genre"""
        if not by_genre:
            return ""

        # Focus on top genres
        genre_counts = [(g, len(movies)) for g, movies in by_genre.items()]
        genre_counts.sort(key=lambda x: x[1], reverse=True)

        html = """
    <div style="padding: 30px 20px 0;">
        <h3 style="font-size: 24px; color: #1a1a1a; margin: 0 0 20px;">
            📁 By Genre
        </h3>
    </div>
"""

        # Show top 3-4 genres
        for genre, _ in genre_counts[:4]:
            movies = by_genre[genre]
            html += f"""
    <div style="padding: 0 20px 30px;">
        <h4 style="font-size: 20px; color: #555; margin: 0 0 15px; text-transform: uppercase; letter-spacing: 1px;">
            {genre}
        </h4>
"""

            for movie in movies[:5]:  # Top 5 per genre
                html += self._generate_movie_card(movie, compact=True)

            if len(movies) > 5:
                html += f"""
        <p style="font-size: 14px; color: #999; font-style: italic; margin: 10px 0 0;">
            ...plus {len(movies) - 5} more {genre.lower()} releases
        </p>
"""

            html += "    </div>\n"

        return html

    def _generate_full_list(self, movies):
        """Generate complete alphabetical list"""
        movies_sorted = sorted(movies, key=lambda x: x['title'])

        html = """
    <div style="background: #f9f9f9; padding: 30px 20px; margin: 30px 0 0;">
        <h3 style="font-size: 20px; color: #1a1a1a; margin: 0 0 20px;">
            📋 Complete Alphabetical List
        </h3>
        <div style="column-count: 2; column-gap: 20px; font-size: 14px; line-height: 1.8;">
"""

        for movie in movies_sorted:
            rt = f" • {movie.get('rt_score')}% 🍅" if movie.get('rt_score') else ""
            html += f"""
            <div style="break-inside: avoid; margin-bottom: 5px;">
                <strong>{movie['title']}</strong>{rt}
            </div>
"""

        html += """
        </div>
    </div>
"""

        return html

    def _generate_movie_card(self, movie, index=None, featured=False, compact=False):
        """Generate individual movie card"""
        title = movie['title']
        director = movie.get('crew', {}).get('director', 'Unknown Director')
        rt_score = movie.get('rt_score')
        synopsis = movie.get('synopsis', 'No synopsis available.')
        genres = ', '.join(movie.get('genres', [])[:3])
        runtime = movie.get('runtime')
        trailer_url = movie.get('links', {}).get('trailer')
        rt_url = movie.get('links', {}).get('rt')

        # RT badge
        rt_badge = ""
        if rt_score:
            score = self._safe_int_score(rt_score)
            if score > 0:
                if score >= 90:
                    color = "#2e7d32"  # Green
                    icon = "🍅"
                elif score >= 60:
                    color = "#f57c00"  # Orange
                    icon = "🍅"
                else:
                    color = "#c62828"  # Red
                    icon = "🍅"

                rt_badge = f"""
            <span style="display: inline-block; background: {color}; color: white; padding: 4px 10px; border-radius: 4px; font-size: 14px; font-weight: bold; margin-right: 10px;">
                {icon} {score}%
            </span>
"""

        # Compact version for genre sections
        if compact:
            return f"""
        <div style="border-left: 3px solid #ddd; padding-left: 15px; margin-bottom: 15px;">
            <div style="margin-bottom: 5px;">
                {rt_badge}
                <strong style="font-size: 16px; color: #1a1a1a;">{title}</strong>
            </div>
            <p style="font-size: 13px; color: #666; margin: 5px 0;">
                Dir. {director}{f" • {runtime} min" if runtime else ""}{f" • {genres}" if genres else ""}
            </p>
            <p style="font-size: 14px; color: #333; margin: 5px 0; line-height: 1.5;">
                {synopsis[:150]}{"..." if len(synopsis) > 150 else ""}
            </p>
            <p style="margin: 8px 0 0;">
                {f'<a href="{trailer_url}" style="color: #ff6b6b; text-decoration: none; font-size: 13px; margin-right: 15px;">▶️ Trailer</a>' if trailer_url else ""}
                {f'<a href="{rt_url}" style="color: #ff6b6b; text-decoration: none; font-size: 13px;">🍅 Reviews</a>' if rt_url else ""}
            </p>
        </div>
"""

        # Featured version for top picks
        index_badge = f"""
            <div style="display: inline-block; background: #ff6b6b; color: white; width: 30px; height: 30px; border-radius: 50%; text-align: center; line-height: 30px; font-size: 16px; font-weight: bold; margin-right: 10px;">
                {index}
            </div>
""" if index else ""

        return f"""
        <div style="background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <div style="margin-bottom: 10px;">
                {index_badge}
                {rt_badge}
                <strong style="font-size: 20px; color: #1a1a1a;">{title}</strong>
            </div>
            <p style="font-size: 14px; color: #666; margin: 5px 0;">
                Directed by {director}{f" • {runtime} min" if runtime else ""}{f" • {genres}" if genres else ""}
            </p>
            <p style="font-size: 15px; color: #333; margin: 15px 0; line-height: 1.6;">
                {synopsis}
            </p>
            <div style="margin-top: 15px;">
                {f'<a href="{trailer_url}" style="display: inline-block; background: #ff6b6b; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px; font-size: 14px; margin-right: 10px;">▶️ Watch Trailer</a>' if trailer_url else ""}
                {f'<a href="{rt_url}" style="display: inline-block; background: #333; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px; font-size: 14px;">🍅 Read Reviews</a>' if rt_url else ""}
            </div>
        </div>
"""

    def _generate_footer(self):
        """Generate newsletter footer"""
        today = datetime.now().strftime('%B %d, %Y')

        return f"""
    <div style="border-top: 2px solid #eee; margin: 40px 0 0; padding: 30px 20px; text-align: center;">
        <p style="font-size: 14px; color: #999; margin: 0 0 10px;">
            Generated {today} from <a href="https://newreleasewall.com" style="color: #ff6b6b; text-decoration: none;">New Release Wall</a>
        </p>
        <p style="font-size: 13px; color: #bbb; margin: 0;">
            All movies released digitally this week • RT scores where available
        </p>
    </div>
</div>
"""


def main():
    """CLI interface"""
    parser = argparse.ArgumentParser(description='Generate Substack newsletter HTML')
    parser.add_argument('format', choices=['weekly', 'monthly'],
                       help='Newsletter format')
    parser.add_argument('--output', '-o', help='Output HTML file')

    args = parser.parse_args()

    generator = SubstackNewsletterGenerator()

    if args.format == 'weekly':
        html = generator.generate_weekly_newsletter()
    else:
        print("Monthly format coming soon!")
        sys.exit(1)

    # Output
    if args.output:
        with open(args.output, 'w') as f:
            f.write(html)
        print(f"✅ Newsletter saved to {args.output}")
    else:
        print(html)


if __name__ == '__main__':
    main()
