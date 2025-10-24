#!/usr/bin/env python3
"""
Discovery validation harness - compares discovered titles to ground truth data
"""

import json
import yaml
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import argparse


class DiscoveryValidator:
    def __init__(self, config_path='config.yaml'):
        """Initialize validator with configuration"""
        self.config = self.load_config(config_path)
        self.validation_config = self.config.get('validation', {})

    def load_config(self, config_path):
        """Load configuration from config.yaml"""
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                return yaml.safe_load(f) or {}
        return {}

    def validate_discovery(self, days_back=7, fail_on_threshold=True):
        """
        Validate discovery results against ground truth data

        Args:
            days_back: Number of days to look back for validation
            fail_on_threshold: Whether to fail if recall drops below threshold

        Returns:
            dict: Validation results with recall/precision metrics
        """
        print("🔍 Running discovery validation...")

        # Load data.json
        if not os.path.exists('data.json'):
            print("❌ Error: data.json not found")
            return self._create_error_result("data.json not found")

        with open('data.json', 'r') as f:
            data = json.load(f)

        discovered_movies = data.get('movies', [])
        print(f"📊 Found {len(discovered_movies)} movies in data.json")

        # Get movies from the last N days
        cutoff_date = datetime.now() - timedelta(days=days_back)
        recent_discovered = []

        for movie in discovered_movies:
            if movie.get('digital_date'):
                try:
                    movie_date = datetime.strptime(movie['digital_date'], '%Y-%m-%d')
                    if movie_date >= cutoff_date:
                        recent_discovered.append({
                            'title': movie['title'],
                            'date': movie['digital_date'],
                            'tmdb_id': str(movie['id'])
                        })
                except ValueError:
                    continue

        print(f"🎬 Found {len(recent_discovered)} movies from last {days_back} days")

        # Load ground truth data
        ground_truth = self._load_ground_truth(days_back)
        if not ground_truth:
            print("⚠️  No ground truth data available for validation")
            return self._create_no_ground_truth_result(recent_discovered)

        print(f"📚 Ground truth contains {len(ground_truth)} movies")

        # Calculate metrics
        metrics = self._calculate_metrics(recent_discovered, ground_truth)

        # Check thresholds
        recall_threshold = self.validation_config.get('min_recall', 0.8)
        precision_threshold = self.validation_config.get('min_precision', 0.7)

        validation_passed = True
        if metrics['recall'] < recall_threshold:
            print(f"❌ Recall {metrics['recall']:.2%} below threshold {recall_threshold:.2%}")
            validation_passed = False
        else:
            print(f"✅ Recall {metrics['recall']:.2%} meets threshold {recall_threshold:.2%}")

        if metrics['precision'] < precision_threshold:
            print(f"❌ Precision {metrics['precision']:.2%} below threshold {precision_threshold:.2%}")
            validation_passed = False
        else:
            print(f"✅ Precision {metrics['precision']:.2%} meets threshold {precision_threshold:.2%}")

        # Print detailed results
        self._print_validation_report(metrics, recent_discovered, ground_truth)

        # Fail if thresholds not met and fail_on_threshold is True
        if not validation_passed and fail_on_threshold:
            print("💥 Validation failed - discovery quality below thresholds")
            sys.exit(1)

        return metrics

    def _load_ground_truth(self, days_back):
        """Load ground truth data for the specified time period"""
        # Calculate week number for the period
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        # Try to find ground truth files for the date range
        ground_truth_movies = []

        # Check for weekly ground truth files
        current_date = start_date
        while current_date <= end_date:
            year, week, _ = current_date.isocalendar()
            week_file = f"data_aux/ground_truth/{year:04d}-{week:02d}.yaml"

            if os.path.exists(week_file):
                print(f"📂 Loading ground truth from {week_file}")
                with open(week_file, 'r') as f:
                    week_data = yaml.safe_load(f)
                    if week_data and 'movies' in week_data:
                        ground_truth_movies.extend(week_data['movies'])

            current_date += timedelta(days=7)

        # Remove duplicates based on title
        seen_titles = set()
        unique_movies = []
        for movie in ground_truth_movies:
            title_key = movie.get('title', '').lower().strip()
            if title_key and title_key not in seen_titles:
                seen_titles.add(title_key)
                unique_movies.append(movie)

        return unique_movies

    def _calculate_metrics(self, discovered, ground_truth):
        """Calculate recall and precision metrics"""
        # Create sets for comparison (normalized titles)
        discovered_titles = {self._normalize_title(m['title']) for m in discovered}
        ground_truth_titles = {self._normalize_title(m.get('title', '')) for m in ground_truth if m.get('title')}

        # Calculate intersections
        true_positives = discovered_titles & ground_truth_titles
        false_positives = discovered_titles - ground_truth_titles
        false_negatives = ground_truth_titles - discovered_titles

        # Calculate metrics
        recall = len(true_positives) / len(ground_truth_titles) if ground_truth_titles else 0
        precision = len(true_positives) / len(discovered_titles) if discovered_titles else 0
        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

        return {
            'recall': recall,
            'precision': precision,
            'f1_score': f1_score,
            'true_positives': len(true_positives),
            'false_positives': len(false_positives),
            'false_negatives': len(false_negatives),
            'discovered_count': len(discovered),
            'ground_truth_count': len(ground_truth),
            'true_positive_titles': sorted(list(true_positives)),
            'false_positive_titles': sorted(list(false_positives)),
            'false_negative_titles': sorted(list(false_negatives))
        }

    def _normalize_title(self, title):
        """Normalize movie title for comparison"""
        if not title:
            return ""
        return title.lower().strip().replace(":", "").replace("-", " ").replace("  ", " ")

    def _print_validation_report(self, metrics, discovered, ground_truth):
        """Print detailed validation report"""
        print("\n📋 DISCOVERY VALIDATION REPORT")
        print("=" * 50)
        print(f"Discovered movies: {metrics['discovered_count']}")
        print(f"Ground truth movies: {metrics['ground_truth_count']}")
        print(f"True positives: {metrics['true_positives']}")
        print(f"False positives: {metrics['false_positives']}")
        print(f"False negatives: {metrics['false_negatives']}")
        print(f"Recall: {metrics['recall']:.2%}")
        print(f"Precision: {metrics['precision']:.2%}")
        print(f"F1 Score: {metrics['f1_score']:.2%}")

        if metrics['false_negative_titles']:
            print(f"\n❌ MISSED MOVIES ({len(metrics['false_negative_titles'])}):")
            for title in metrics['false_negative_titles'][:10]:  # Show up to 10
                print(f"  • {title}")
            if len(metrics['false_negative_titles']) > 10:
                print(f"  ... and {len(metrics['false_negative_titles']) - 10} more")

        if metrics['false_positive_titles']:
            print(f"\n⚠️  EXTRA MOVIES ({len(metrics['false_positive_titles'])}):")
            for title in metrics['false_positive_titles'][:10]:  # Show up to 10
                print(f"  • {title}")
            if len(metrics['false_positive_titles']) > 10:
                print(f"  ... and {len(metrics['false_positive_titles']) - 10} more")

        if metrics['true_positive_titles']:
            print(f"\n✅ CORRECTLY FOUND ({len(metrics['true_positive_titles'])}):")
            for title in metrics['true_positive_titles'][:5]:  # Show up to 5
                print(f"  • {title}")
            if len(metrics['true_positive_titles']) > 5:
                print(f"  ... and {len(metrics['true_positive_titles']) - 5} more")

    def _create_error_result(self, error_message):
        """Create error result structure"""
        return {
            'error': error_message,
            'recall': 0,
            'precision': 0,
            'f1_score': 0,
            'validation_passed': False
        }

    def _create_no_ground_truth_result(self, discovered):
        """Create result when no ground truth is available"""
        return {
            'recall': None,
            'precision': None,
            'f1_score': None,
            'discovered_count': len(discovered),
            'ground_truth_count': 0,
            'note': 'No ground truth data available for validation',
            'validation_passed': True  # Don't fail if no ground truth
        }


def main():
    parser = argparse.ArgumentParser(description="Validate discovery results against ground truth")
    parser.add_argument('--days-back', type=int, default=7, help='Number of days to validate (default: 7)')
    parser.add_argument('--no-fail', action='store_true', help='Do not fail on threshold violations')
    parser.add_argument('--config', default='config.yaml', help='Configuration file path')

    args = parser.parse_args()

    validator = DiscoveryValidator(args.config)
    result = validator.validate_discovery(
        days_back=args.days_back,
        fail_on_threshold=not args.no_fail
    )

    # Return success if validation passed or no ground truth
    if result.get('validation_passed', True):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()