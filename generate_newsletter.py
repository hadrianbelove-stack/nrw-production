#!/usr/bin/env python3
"""
Generate newsletter content from recent movie releases.

This script uses NewsletterDataQuery to fetch recent movies and renders
them using Jinja2 templates for both HTML and Markdown output formats.

Usage:
  python3 generate_newsletter.py              # Generate with default 7 days
  python3 generate_newsletter.py --days 14    # Generate with 14 days lookback
  python3 generate_newsletter.py --debug      # Enable debug logging
  python3 generate_newsletter.py --preview    # Preview summary without rendering
  python3 generate_newsletter.py --preview --days 7  # Preview last 7 days
"""

import os
import argparse
import logging
from datetime import datetime, timedelta

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from pipeline.newsletter import NewsletterDataQuery


def show_preview(movies: list, days_back: int, logger: logging.Logger, query: 'NewsletterDataQuery') -> None:
    """
    Display a summary preview of newsletter content without rendering templates.

    Args:
        movies: List of movie dictionaries from NewsletterDataQuery
        days_back: Number of days in the lookback window
        logger: Logger instance for debug output
        query: NewsletterDataQuery instance for RT score parsing
    """
    from datetime import datetime, timedelta
    from collections import Counter

    today = datetime.now()
    start_date = today - timedelta(days=days_back)
    date_range = f"{start_date.strftime('%B %d')} - {today.strftime('%B %d, %Y')}"

    print("\n" + "=" * 60)
    print("📋 NEWSLETTER PREVIEW")
    print("=" * 60)

    # Summary stats
    print(f"\n📅 Date Range: {date_range}")
    print(f"🎬 Total Movies: {len(movies)}")

    # RT score distribution - use centralized parsing from NewsletterDataQuery
    rt_scores = [
        query._parse_rt_score(m.get('rt_score'))
        for m in movies
        if query._parse_rt_score(m.get('rt_score')) is not None
    ]

    if rt_scores:
        print(f"\n🍅 Rotten Tomatoes Score Distribution:")
        fresh = sum(1 for s in rt_scores if s >= 60)
        rotten = sum(1 for s in rt_scores if s < 60)
        no_score = len(movies) - len(rt_scores)
        avg_score = sum(rt_scores) / len(rt_scores)
        print(f"   Fresh (≥60%): {fresh}")
        print(f"   Rotten (<60%): {rotten}")
        print(f"   No Score: {no_score}")
        print(f"   Average Score: {avg_score:.1f}%")
    else:
        print(f"\n🍅 No RT scores available")

    # Platform breakdown
    platforms = Counter()
    for movie in movies:
        movie_platforms = movie.get('platforms', [])
        if isinstance(movie_platforms, list):
            for p in movie_platforms:
                platforms[p] += 1
        elif movie_platforms:
            platforms[str(movie_platforms)] += 1

    if platforms:
        print(f"\n📺 Platform Breakdown:")
        for platform, count in platforms.most_common(10):
            print(f"   {platform}: {count}")

    # Top-rated titles - use centralized parsing from NewsletterDataQuery
    if rt_scores:
        scored_movies = [
            (m.get('title', 'Unknown'), query._parse_rt_score(m.get('rt_score')))
            for m in movies
            if query._parse_rt_score(m.get('rt_score')) is not None
        ]
        scored_movies.sort(key=lambda x: x[1], reverse=True)

        print(f"\n⭐ Top-Rated Titles:")
        for title, score in scored_movies[:5]:
            print(f"   {score}% - {title}")

    print("\n" + "=" * 60)
    print("✅ Preview complete. Run without --preview to generate newsletter.")
    print("=" * 60 + "\n")

    logger.info(f"Preview displayed: {len(movies)} movies, date range: {date_range}")


def setup_logging(debug: bool = False) -> logging.Logger:
    """Set up logging configuration."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


def main():
    """Main entry point for newsletter generation CLI."""
    parser = argparse.ArgumentParser(
        description="Generate newsletter content from recent movie releases"
    )
    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='Number of days to look back for recent releases (default: 7)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    parser.add_argument(
        '--preview',
        action='store_true',
        help='Show summary preview without rendering templates'
    )
    parser.add_argument(
        '--dated-only',
        action='store_true',
        default=True,
        help='Only include movies with actual digital_date (exclude undated discoveries)'
    )
    parser.add_argument(
        '--include-undated',
        action='store_true',
        help='Include movies without digital_date (uses discovery date as fallback)'
    )

    args = parser.parse_args()

    # Set up logging
    logger = setup_logging(debug=args.debug)
    logger.info(f"Starting newsletter generation (days={args.days})")

    # Initialize NewsletterDataQuery
    query = NewsletterDataQuery(logger=logger, config={'days_back': args.days})

    # Fetch recent movies
    require_digital_date = not args.include_undated
    date_filter_msg = "(dated releases only)" if require_digital_date else "(including undated)"
    print(f"📰 Fetching movies from the last {args.days} days {date_filter_msg}...")
    movies = query.get_recent_releases(days_back=args.days, require_digital_date=require_digital_date)

    if not movies:
        print("⚠️  No movies found for the specified date range.")
        logger.warning("No movies found for newsletter generation")
        return

    print(f"✅ Found {len(movies)} movies")
    logger.info(f"Retrieved {len(movies)} movies for newsletter")

    # Preview mode: show summary and exit without rendering
    if args.preview:
        show_preview(movies, days_back=args.days, logger=logger, query=query)
        return

    # Prepare template context
    today = datetime.now()
    start_date = today - timedelta(days=args.days)
    date_range = f"{start_date.strftime('%B %d')} - {today.strftime('%B %d, %Y')}"

    context = {
        'movies': movies,
        'movie_count': len(movies),
        'date_range': date_range,
        'newsletter_title': 'NEW RELEASES WORTH WATCHING',
        'generated_at': today.isoformat()
    }

    # Set up Jinja2 environment
    template_dir = os.path.join(os.path.dirname(__file__), 'templates', 'newsletter')
    if not os.path.exists(template_dir):
        print(f"❌ Template directory not found: {template_dir}")
        logger.error(f"Template directory not found: {template_dir}")
        return

    env = Environment(
        loader=FileSystemLoader(template_dir),  # Point directly to newsletter/
        autoescape=False  # We handle escaping in templates
    )

    # Ensure output directory exists
    output_dir = os.path.join(os.path.dirname(__file__), 'output')
    os.makedirs(output_dir, exist_ok=True)

    # Render HTML template
    print("📝 Rendering HTML template...")
    try:
        html_template = env.get_template('newsletter_base.html')
        html_output = html_template.render(**context)
        html_path = os.path.join(output_dir, 'newsletter.html')
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_output)
        print(f"✅ HTML newsletter written to: {html_path}")
        logger.info(f"HTML newsletter written to: {html_path}")
    except TemplateNotFound as e:
        print(f"❌ HTML template not found: {e}")
        logger.error(f"HTML template not found: {e}")
    except Exception as e:
        print(f"❌ Error rendering HTML template: {e}")
        logger.error(f"Error rendering HTML template: {e}")

    # Render Markdown template
    print("📝 Rendering Markdown template...")
    try:
        md_template = env.get_template('newsletter_base.md')
        md_output = md_template.render(**context)
        md_path = os.path.join(output_dir, 'newsletter.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_output)
        print(f"✅ Markdown newsletter written to: {md_path}")
        logger.info(f"Markdown newsletter written to: {md_path}")
    except TemplateNotFound as e:
        print(f"❌ Markdown template not found: {e}")
        logger.error(f"Markdown template not found: {e}")
    except Exception as e:
        print(f"❌ Error rendering Markdown template: {e}")
        logger.error(f"Error rendering Markdown template: {e}")

    # Print summary
    stats = query.get_stats()
    print(f"\n📊 Newsletter generation complete:")
    print(f"   - Movies included: {len(movies)}")
    print(f"   - Date range: {date_range}")
    print(f"   - Output files: output/newsletter.html, output/newsletter.md")
    logger.info(f"Newsletter generation complete. Stats: {stats}")


if __name__ == "__main__":
    main()
