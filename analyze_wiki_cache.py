#!/usr/bin/env python3
import json

cache = json.load(open('wikipedia_cache.json'))
print(f'Total cached: {len(cache)}')

sources = {}
search_fallbacks = 0
for k, v in cache.items():
    if isinstance(v, dict):
        source = v.get('source', 'unknown')
        if source == 'search_fallback':
            search_fallbacks += 1
        sources[source] = sources.get(source, 0) + 1
    else:
        sources['legacy'] = sources.get('legacy', 0) + 1

print('\nSources:')
for k, v in sorted(sources.items()):
    print(f'  {k}: {v}')

print(f'\nSearch fallbacks (failed lookups): {search_fallbacks}')
print(f'Successful lookups: {len(cache) - search_fallbacks}')
print(f'Success rate: {((len(cache) - search_fallbacks) / len(cache) * 100):.1f}%')
