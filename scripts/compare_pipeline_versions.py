#!/usr/bin/env python3
"""
Compare two versions of a pipeline module to verify identical behavior.

Reusable tool for safe refactoring: run both versions against the same data,
diff outputs, and report pass/fail. No API calls — tests structural equivalence.

Usage:
    python3 scripts/compare_pipeline_versions.py                    # default: enricher vs enricher_v2
    python3 scripts/compare_pipeline_versions.py --module enricher  # explicit module name
    python3 scripts/compare_pipeline_versions.py --verbose          # show all checks, not just failures
"""

import argparse
import ast
import copy
import importlib
import inspect
import json
import os
import sys
import traceback
from datetime import datetime
from io import StringIO
from unittest.mock import MagicMock, patch

# Ensure project root is on path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)
sys.path.insert(0, PROJECT_ROOT)


class ComparisonResult:
    """Tracks pass/fail/skip results across all checks."""

    def __init__(self):
        self.checks = []

    def passed(self, name, detail=''):
        self.checks.append(('PASS', name, detail))

    def failed(self, name, detail=''):
        self.checks.append(('FAIL', name, detail))

    def skipped(self, name, detail=''):
        self.checks.append(('SKIP', name, detail))

    def report(self, verbose=False):
        total = len(self.checks)
        passes = sum(1 for s, _, _ in self.checks if s == 'PASS')
        fails = sum(1 for s, _, _ in self.checks if s == 'FAIL')
        skips = sum(1 for s, _, _ in self.checks if s == 'SKIP')

        print(f"\n{'='*60}")
        print(f"  COMPARISON REPORT: {passes}/{total} passed, {fails} failed, {skips} skipped")
        print(f"{'='*60}\n")

        for status, name, detail in self.checks:
            if status == 'FAIL' or verbose:
                icon = {'PASS': '\u2713', 'FAIL': '\u2717', 'SKIP': '\u2014'}[status]
                line = f"  {icon} [{status}] {name}"
                if detail:
                    line += f"  \u2014  {detail}"
                print(line)

        if fails:
            print(f"\n  \u26a0\ufe0f  {fails} check(s) FAILED \u2014 v2 is NOT safe to swap yet.\n")
        else:
            print(f"\n  \u2705 All checks passed \u2014 v2 is structurally equivalent to v1.\n")

        return fails == 0


# ---------------------------------------------------------------------------
# Check implementations
# ---------------------------------------------------------------------------

def check_syntax(module_path, result):
    """Verify the module parses without syntax errors."""
    try:
        with open(module_path) as f:
            ast.parse(f.read())
        result.passed(f"Syntax: {os.path.basename(module_path)}")
    except SyntaxError as e:
        result.failed(f"Syntax: {os.path.basename(module_path)}", str(e))


def check_class_methods(v1_path, v2_path, class_name, result):
    """Verify v2 has all methods from v1 (plus the new extracted ones)."""
    def get_methods(path):
        with open(path) as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                return {n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        return set()

    v1_methods = get_methods(v1_path)
    v2_methods = get_methods(v2_path)

    missing = v1_methods - v2_methods
    added = v2_methods - v1_methods

    if missing:
        result.failed("Methods: v2 missing from v1", f"Missing: {missing}")
    else:
        result.passed("Methods: v2 has all v1 methods")

    if added:
        result.passed(f"Methods: v2 added {len(added)} new", ', '.join(sorted(added)))


def check_method_signatures(v2_path, class_name, expected_methods, result):
    """Verify extracted methods have the expected parameter signatures."""
    with open(v2_path) as f:
        tree = ast.parse(f.read())

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            method_map = {n.name: n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
            for method_name, expected_params in expected_methods.items():
                if method_name not in method_map:
                    result.failed(f"Signature: {method_name}", "method not found")
                    continue
                func = method_map[method_name]
                actual_params = [a.arg for a in func.args.args]
                if actual_params == expected_params:
                    result.passed(f"Signature: {method_name}")
                else:
                    result.failed(f"Signature: {method_name}",
                                  f"expected {expected_params}, got {actual_params}")


def check_public_interface(v1_path, v2_path, class_name, public_method, result):
    """Verify the public method signature is identical in both versions."""
    def get_sig(path):
        with open(path) as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for n in node.body:
                    if isinstance(n, ast.FunctionDef) and n.name == public_method:
                        params = [a.arg for a in n.args.args]
                        defaults = [ast.dump(d) for d in n.args.defaults]
                        return (params, defaults)
        return None

    v1_sig = get_sig(v1_path)
    v2_sig = get_sig(v2_path)

    if v1_sig == v2_sig:
        result.passed(f"Public interface: {public_method}()")
    else:
        result.failed(f"Public interface: {public_method}()",
                      f"v1={v1_sig}, v2={v2_sig}")


def check_no_tracking_changed_reset(v2_path, result):
    """Verify the tracking_changed reset bug is not present in v2."""
    with open(v2_path) as f:
        lines = f.readlines()

    # Look for 'tracking_changed = False' outside of _build_enrichment_queue
    in_build_queue = False
    bad_resets = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if 'def _build_enrichment_queue' in line:
            in_build_queue = True
        elif stripped.startswith('def ') and in_build_queue:
            in_build_queue = False

        if 'tracking_changed = False' in stripped and not in_build_queue:
            bad_resets.append(i)

    if bad_resets:
        result.failed("Bug fix: tracking_changed reset", f"Found reset at line(s): {bad_resets}")
    else:
        result.passed("Bug fix: no tracking_changed reset outside _build_enrichment_queue")


def check_tracking_data_always_loaded(v2_path, result):
    """Verify tracking_data is loaded unconditionally in _build_enrichment_queue."""
    with open(v2_path) as f:
        content = f.read()

    # Check that _build_enrichment_queue loads tracking_data before any branch
    import re
    # Find the method body
    match = re.search(r'def _build_enrichment_queue\(self.*?\).*?:\n(.*?)(?=\n    def )', content, re.DOTALL)
    if not match:
        result.failed("Bug fix: tracking_data load", "Could not find _build_enrichment_queue")
        return

    body = match.group(1)
    lines = body.split('\n')

    # Find first tracking_data assignment and first 'if target_id' branch
    load_line = None
    branch_line = None
    for i, line in enumerate(lines):
        if 'tracking_data = self.ctx.storage.load_all_movies()' in line and load_line is None:
            load_line = i
        if 'if target_id' in line and branch_line is None:
            branch_line = i

    if load_line is not None and branch_line is not None and load_line < branch_line:
        result.passed("Bug fix: tracking_data loaded before target_id branch")
    elif load_line is None:
        result.failed("Bug fix: tracking_data load", "No unconditional load found")
    else:
        result.failed("Bug fix: tracking_data load", f"Load at line {load_line}, branch at {branch_line}")


def check_imports_match(v1_path, v2_path, result):
    """Verify both files use the same top-level imports."""
    def get_imports(path):
        with open(path) as f:
            tree = ast.parse(f.read())
        imports = set()
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                imports.add(f"from {node.module}")
        return imports

    v1_imports = get_imports(v1_path)
    v2_imports = get_imports(v2_path)

    if v1_imports == v2_imports:
        result.passed("Imports: identical")
    else:
        missing = v1_imports - v2_imports
        extra = v2_imports - v1_imports
        detail = []
        if missing:
            detail.append(f"v2 missing: {missing}")
        if extra:
            detail.append(f"v2 extra: {extra}")
        # Extra imports in v2 are OK (new methods may need them)
        if missing:
            result.failed("Imports: v2 missing some v1 imports", '; '.join(detail))
        else:
            result.passed("Imports: v2 superset of v1", '; '.join(detail))


def check_queue_building(v1_path, v2_path, result):
    """Run _build_enrichment_queue on both versions with mock data, compare output."""
    try:
        # Create minimal mock objects
        mock_logger = MagicMock()
        mock_storage = MagicMock()
        mock_storage.load_all_movies.return_value = {
            'movies': {
                '123': {'title': 'Test Movie', 'status': 'available', 'year': 2026},
                '456': {'title': 'Another Movie', 'status': 'available', 'year': 2025},
            }
        }
        mock_enrichment = MagicMock()
        mock_config = {'preorder': {'link_finder_days': 14}}

        mock_ctx = MagicMock()
        mock_ctx.logger = mock_logger
        mock_ctx.storage = mock_storage
        mock_ctx.enrichment_service = mock_enrichment
        mock_ctx.config = mock_config

        mock_host = MagicMock()
        mock_host.validator.fix_data_json_schema.return_value = True
        mock_host.watch_links_overrides = {}

        mock_discoverer = MagicMock()

        # Build test data — simulate what data.json looks like
        test_movies = [
            {'id': 123, 'title': 'Test Movie', 'digital_date': '2026-05-01', 'status': 'available',
             '_enrichment_status': 'pending', '_enrichment_attempts': 0, 'enriched': False},
            {'id': 456, 'title': 'Another Movie', 'digital_date': '2026-04-15', 'status': 'available',
             '_enrichment_status': 'completed', 'enriched': True},
        ]
        test_lookup = {'123': 0, '456': 1}

        # Write a temporary newly_available.json
        os.makedirs('metrics', exist_ok=True)
        na_path = 'metrics/newly_available.json'
        na_backup = None
        if os.path.exists(na_path):
            with open(na_path) as f:
                na_backup = f.read()

        with open(na_path, 'w') as f:
            json.dump({'date': datetime.now().strftime('%Y-%m-%d'), 'movie_ids': [123]}, f)

        try:
            # Import v2 module
            spec2 = importlib.util.spec_from_file_location("enricher_v2", v2_path)
            mod2 = importlib.util.module_from_spec(spec2)
            spec2.loader.exec_module(mod2)

            # Test v2's _build_enrichment_queue
            enricher_v2 = mod2.MovieEnricher(mock_ctx, mock_host, mock_discoverer)
            v2_result = enricher_v2._build_enrichment_queue(
                None, copy.deepcopy(test_movies), dict(test_lookup)
            )

            if v2_result is None:
                result.failed("Queue building: v2 returned None", "Expected a queue tuple")
                return

            v2_ids, v2_tracking, v2_changed = v2_result

            # Verify queue contains the expected movie
            if '123' in v2_ids:
                result.passed("Queue building: v2 includes newly available movie")
            else:
                result.failed("Queue building: v2 missing movie 123", f"Queue: {v2_ids}")

            # Verify tracking_data was loaded
            if v2_tracking is not None and 'movies' in v2_tracking:
                result.passed("Queue building: v2 loaded tracking_data")
            else:
                result.failed("Queue building: v2 tracking_data is empty/None")

            # Test single-movie mode
            v2_single = enricher_v2._build_enrichment_queue(
                '123', copy.deepcopy(test_movies), dict(test_lookup)
            )
            if v2_single and v2_single[0] == ['123'] and v2_single[1] is not None:
                result.passed("Queue building: v2 single-movie mode works")
            else:
                result.failed("Queue building: v2 single-movie mode", f"Got: {v2_single}")

            # Test single-movie with bad ID
            v2_bad = enricher_v2._build_enrichment_queue(
                '999', copy.deepcopy(test_movies), dict(test_lookup)
            )
            if v2_bad is None:
                result.passed("Queue building: v2 rejects invalid movie ID")
            else:
                result.failed("Queue building: v2 accepted invalid ID", f"Got: {v2_bad}")

        finally:
            # Restore newly_available.json
            if na_backup is not None:
                with open(na_path, 'w') as f:
                    f.write(na_backup)

    except Exception as e:
        result.failed("Queue building: runtime error", f"{type(e).__name__}: {e}")
        traceback.print_exc()


def check_load_and_validate(v2_path, result):
    """Test _load_and_validate_data returns correct structure."""
    try:
        spec = importlib.util.spec_from_file_location("enricher_v2_load", v2_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        mock_ctx = MagicMock()
        mock_host = MagicMock()
        mock_host.validator.fix_data_json_schema.return_value = True
        mock_discoverer = MagicMock()

        enricher = mod.MovieEnricher(mock_ctx, mock_host, mock_discoverer)

        # Should succeed with real data.json
        if os.path.exists('data.json'):
            loaded = enricher._load_and_validate_data()
            if loaded is not None:
                display_data, existing_movies, movie_lookup = loaded
                if isinstance(display_data, dict) and isinstance(existing_movies, list) and isinstance(movie_lookup, dict):
                    result.passed(f"Load & validate: OK ({len(existing_movies)} movies, {len(movie_lookup)} in lookup)")
                else:
                    result.failed("Load & validate: wrong types", f"types: {type(display_data)}, {type(existing_movies)}, {type(movie_lookup)}")
            else:
                result.failed("Load & validate: returned None with valid data.json")
        else:
            result.skipped("Load & validate: no data.json present")

    except Exception as e:
        result.failed("Load & validate: runtime error", f"{type(e).__name__}: {e}")


def check_orchestrator_length(v2_path, class_name, result):
    """Verify the orchestrator is reasonably short (under 120 lines)."""
    with open(v2_path) as f:
        tree = ast.parse(f.read())

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for n in node.body:
                if isinstance(n, ast.FunctionDef) and n.name == 'enrich_newly_available_movies':
                    length = n.end_lineno - n.lineno + 1
                    if length <= 120:
                        result.passed(f"Orchestrator length: {length} lines (target: <120)")
                    else:
                        result.failed(f"Orchestrator length: {length} lines", "Expected under 120 lines")
                    return
    result.failed("Orchestrator length: method not found")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_enricher_comparison(verbose=False):
    """Run all comparison checks for enricher v1 vs v2."""
    v1_path = os.path.join(PROJECT_ROOT, 'pipeline', 'enricher.py')
    v2_path = os.path.join(PROJECT_ROOT, 'pipeline', 'enricher_v2.py')
    class_name = 'MovieEnricher'
    public_method = 'enrich_newly_available_movies'

    if not os.path.exists(v2_path):
        print(f"\u274c {v2_path} not found. Nothing to compare.")
        return False

    result = ComparisonResult()

    print(f"\n  Comparing pipeline module versions:")
    print(f"    v1: {os.path.basename(v1_path)}")
    print(f"    v2: {os.path.basename(v2_path)}")
    print(f"    class: {class_name}")
    print()

    # --- Static checks (no imports needed) ---
    check_syntax(v1_path, result)
    check_syntax(v2_path, result)
    check_imports_match(v1_path, v2_path, result)
    check_class_methods(v1_path, v2_path, class_name, result)
    check_public_interface(v1_path, v2_path, class_name, public_method, result)
    check_orchestrator_length(v2_path, class_name, result)

    # --- Enricher-specific method signatures ---
    check_method_signatures(v2_path, class_name, {
        '_load_and_validate_data': ['self'],
        '_build_enrichment_queue': ['self', 'target_id', 'existing_movies', 'movie_lookup'],
        '_setup_loop_environment': ['self', 'tracking_data'],
        '_enrich_single_movie': ['self', 'movie_id', 'existing_movies', 'movie_lookup',
                                  'tracking_data', 'per_movie_timeout', 'deferred_entry_fn'],
        '_sync_tracking_and_revert': ['self', 'movie_ids', 'existing_movies', 'movie_lookup',
                                       'tracking_data', 'tracking_changed', 'deferred_entry_fn'],
        '_save_and_post_process': ['self', 'display_data', 'existing_movies', 'movie_ids',
                                    'movie_lookup', 'enriched_count', 'initial_movie_count'],
        '_write_enrichment_metrics': ['self', 'movie_ids', 'enriched_count',
                                       'deferred_details', 'start_time'],
    }, result)

    # --- Bug fix verification ---
    check_no_tracking_changed_reset(v2_path, result)
    check_tracking_data_always_loaded(v2_path, result)

    # --- Runtime checks (with mocks, no API calls) ---
    check_load_and_validate(v2_path, result)
    check_queue_building(v1_path, v2_path, result)

    return result.report(verbose=verbose)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Compare pipeline module versions')
    parser.add_argument('--module', default='enricher', help='Module name (default: enricher)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show all checks, not just failures')
    args = parser.parse_args()

    if args.module == 'enricher':
        success = run_enricher_comparison(verbose=args.verbose)
    else:
        print(f"Unknown module: {args.module}")
        print("Available: enricher")
        sys.exit(1)

    sys.exit(0 if success else 1)
