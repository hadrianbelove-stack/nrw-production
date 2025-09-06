# New Release Wall - Quick Reference

## 🚀 Quick Start

### Run the Working Scraper
```bash
cd ~/Downloads/new-release-wall
python3 new_release_wall_balanced.py --region US --days 45 --max-pages 5
```

### View Results
```bash
open output/site/index.html
```

## 📁 Key Files

| File | Purpose | Status |
|------|---------|--------|
| `new_release_wall_balanced.py` | **Main scraper** (use this) | ✅ Working |
| `new_release_wall.py` | Original scraper | ❌ Too restrictive |
| `config.yaml` | API keys | Required |
| `output/data.json` | Raw movie data | Generated |
| `output/site/index.html` | Movie website | Generated |

## ⚙️ Parameters

| Flag | Default | Purpose |
|------|---------|---------|
| `--region` | US | Country code |
| `--days` | 45 | Days back to search |
| `--max-pages` | 5 | TMDB API pages to fetch |

## 🔧 Key Technical Fix

**Problem**: Using `with_release_type` filter in API query excluded movies with multiple release types

**Solution**: Fetch ALL movies first, then check release types individually

```python
# ❌ OLD (incorrect)
params = {'with_release_type': '2|3|4|6'}

# ✅ NEW (correct)  
# 1. Fetch all movies (no filter)
# 2. Check each movie's release types
movie['has_digital'] = 4 in release_info['types']
```

## 📊 Performance Comparison

| Metric | Old Method | New Method |
|--------|-----------|------------|
| Movies found | 5 | 49 |
| Major releases | Missing | ✅ Included |
| Inclusion rate | ~1% | ~49% |

## 🎯 TMDB Release Types

- **1**: Premiere
- **2**: Theatrical (Limited) 
- **3**: Theatrical
- **4**: Digital ⭐
- **5**: Physical
- **6**: TV ⭐

*⭐ = Target types for digital availability*

## 🏗️ Cache System

| Cache File | Contains | TTL |
|------------|----------|-----|
| `review_cache.json` | OMDb review scores | 7 days |
| `provider_cache.json` | TMDB provider data | 7 days |
| `release_types.json` | Release type info | 7 days |

## 🔍 Troubleshooting

### No movies found
- Check API keys in `config.yaml`
- Increase `--days` parameter
- Increase `--max-pages` parameter

### Missing major releases
- Use `new_release_wall_balanced.py` (not `new_release_wall.py`)
- Check if movie is within date range
- Verify movie has digital release type (4 or 6)

### API rate limits
- Built-in 0.1s delay between requests
- Cache prevents repeated API calls

## 📋 Example Output

Last run found **49 movies** including:
- Superman (2025) - Rentable on 5 platforms
- Smurfs (2025) - Rentable on 6 platforms  
- Osiris (2025) - Rentable on 7 platforms

## 🔗 APIs Used

- **TMDB API**: Movie data, release types, providers
- **OMDb API**: Review scores (RT, Metacritic, IMDB)