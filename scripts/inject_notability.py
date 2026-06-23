#!/usr/bin/env python3
"""Compute the Selects-guesser Buzz score for every film in data.json.

Runs in the nightly cycle AFTER the capsule research has produced notability
facts for the day's fresh arrivals. The in-build injection (generator.py) runs
before those facts exist, so without this step a brand-new arrival would have no
Buzz until the next day's build. Reuses pipeline.display.inject_notability_into
so there is one source of the scoring logic.

Buzz feeds the Selects ranking in /curate. It never auto-selects anything, it is
read-only at curate time, and the slop classifier never reads it.
"""
import json
import sys

sys.path.insert(0, '.')
from pipeline.display import inject_notability_into

DATA = 'data.json'


def main():
    with open(DATA) as f:
        data = json.load(f)
    movies = data['movies'] if isinstance(data, dict) else data
    n = inject_notability_into(movies)
    with open(DATA, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"inject_notability: Buzz set for {n} movies in {DATA}")


if __name__ == '__main__':
    main()
