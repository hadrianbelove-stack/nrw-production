#!/usr/bin/env python3
"""
DEPRECATED: movie_tracker.py has been replaced by production discovery in generate_data.py

This file is maintained only as a stub to redirect users to the new production discovery path.
The legacy implementation has been moved to museum_legacy/legacy_movie_tracker.py for reference.
"""

import sys

def main():
    print("❌ DEPRECATED: movie_tracker.py is no longer supported")
    print()
    print("The movie tracking functionality has been integrated into the production discovery system.")
    print("Please use the following commands instead:")
    print()
    print("  For daily discovery:")
    print("    python3 generate_data.py --discover")
    print()
    print("  For full data generation:")
    print("    python3 generate_data.py")
    print()
    print("  For the complete daily pipeline:")
    print("    python3 daily_orchestrator.py")
    print()
    print("The legacy implementation is available at:")
    print("    museum_legacy/legacy_movie_tracker.py")
    print()
    print("For more information, see README.md and DAILY_CONTEXT.md")

    # Exit with error code to indicate deprecation
    sys.exit(1)


if __name__ == "__main__":
    main()