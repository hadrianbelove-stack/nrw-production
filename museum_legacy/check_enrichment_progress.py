#!/usr/bin/env python3
"""Monitor enrichment progress by checking enrichment_state.json"""
import json

# Count enriched movies
with open('enrichment_state.json') as f:
    state = json.load(f)

# Movie IDs are at root level, not under a wrapper key
enriched_count = sum(1 for movie_id, data in state.items()
                     if isinstance(data, dict) and data.get('enriched') == True)

print(f"Total enriched movies in cache: {enriched_count}")

# Count unenriched available movies
with open('movie_tracking.json') as f:
    tracking = json.load(f)

available_movies = [mid for mid, movie in tracking['movies'].items()
                   if movie['status'] == 'available']

unenriched = [mid for mid in available_movies if mid not in state]

print(f"Total available movies: {len(available_movies)}")
print(f"Unenriched available movies: {len(unenriched)}")

# Baseline was 400 enriched
baseline = 400
new_enrichments = enriched_count - baseline if enriched_count > baseline else 0
print(f"\nBatch 1 progress: {new_enrichments} new enrichments (baseline was {baseline})")
