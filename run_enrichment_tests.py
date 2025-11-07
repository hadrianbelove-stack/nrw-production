#!/usr/bin/env python3
"""
Enrichment workflow test runner for CI/CD.

This script runs the enrichment workflow tests as a pre-flight check
before data generation to prevent performance regressions.
"""

import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """Run enrichment workflow tests."""
    try:
        # Try the simplified version first (better for CI)
        try:
            from tests.test_enrichment_workflow_simple import run_enrichment_tests
            print("🔍 Running enrichment workflow pre-flight checks (simplified version)...")
        except ImportError:
            # Fallback to comprehensive version
            from tests.test_enrichment_workflow import run_enrichment_tests
            print("🔍 Running enrichment workflow pre-flight checks (comprehensive version)...")

        success = run_enrichment_tests()

        if success:
            print("\n✅ Pre-flight checks passed - enrichment workflow is healthy")
            return 0
        else:
            print("\n❌ Pre-flight checks failed - enrichment workflow has issues")
            print("🚨 STOPPING: Do not proceed with data generation")
            return 1

    except ImportError as e:
        print(f"❌ Failed to import test modules: {e}")
        print("💡 Ensure you're running from the project root directory")
        return 1
    except Exception as e:
        print(f"💥 Unexpected error running tests: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())