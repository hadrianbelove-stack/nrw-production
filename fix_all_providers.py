# Replace check_providers method in movie_tracker.py
# This properly checks all provider types

import json
import os
import requests
import time
from datetime import datetime, timedelta

# In check_providers method, replace the provider check section:
us = response.json().get('results', {}).get('US', {})

# Get all provider types
rent_providers = us.get('rent', [])
buy_providers = us.get('buy', [])
stream_providers = us.get('flatrate', [])  # This includes Netflix, MUBI, Shudder, etc.

# Extract provider names
rent_names = [p.get('provider_name', '') for p in rent_providers]
buy_names = [p.get('provider_name', '') for p in buy_providers]
stream_names = [p.get('provider_name', '') for p in stream_providers]

# Check if ANY providers exist
has_providers = bool(rent_names or buy_names or stream_names)

if has_providers and not movie['has_providers']:
    movie['has_providers'] = True
    movie['digital_date'] = datetime.now().isoformat()[:10]
    movie['status'] = 'available'
    movie['providers'] = {
        'rent': rent_names,
        'buy': buy_names,
        'streaming': stream_names
    }
    
    # Show which service it appeared on
    first_service = stream_names[0] if stream_names else rent_names[0] if rent_names else buy_names[0]
    print(f"  ✓ {movie['title']} now on {first_service}!")
