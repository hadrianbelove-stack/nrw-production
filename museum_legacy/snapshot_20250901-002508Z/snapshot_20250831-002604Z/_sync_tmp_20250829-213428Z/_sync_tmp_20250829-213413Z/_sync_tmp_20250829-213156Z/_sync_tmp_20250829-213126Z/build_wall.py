#!/usr/bin/env python3
"""
Build wall from curator approvals.
Filters current_releases.json based on curated_selections.json to create output/data.json
"""

import json, os

SRC = "current_releases.json"
CUR = "curated_selections.json"
OUT = "output/data.json"

def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default

def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)

def main():
    # Load data
    items = load_json(SRC, [])
    curations = load_json(CUR, {})
    
    print(f"Loaded {len(items)} items from {SRC}")
    print(f"Loaded {len(curations)} curations from {CUR}")
    
    # Filter by curator approvals
    approved = []
    featured = []
    
    for item in items:
        item_id = str(item.get("id", ""))
        status = curations.get(item_id, "unreviewed")
        
        if status in ("approve", "feature"):
            # Convert format to match generate_site.py expectations
            wall_item = {
                "title": item.get("title", ""),
                "year": str(item.get("year", "")),
                "release_date": item.get("digital_date", "")[:10] if item.get("digital_date") else "",
                "poster": f"https://image.tmdb.org/t/p/w500{item.get('poster_path')}" if item.get("poster_path") else "",
                "tmdb_id": item.get("id"),
                "tmdb_vote": item.get("vote_average", 0),
                "rt_score": None,  # Will be populated by generate_site.py if available
                "providers": [],  # Will be formatted from providers dict
                "overview": item.get("overview", ""),
                "inclusion_reason": f"Curator {status}",
                "has_digital": True,
                "digital_date": item.get("digital_date"),
                "theatrical_date": None,
                "justwatch_url": f"https://www.themoviedb.org/movie/{item.get('id')}/watch?locale=US",
                "director": None,
                "cast": "",
                "runtime": item.get("runtime"),
                "studio": None,
                "rating": "NR",
                "tmdb_url": f"https://www.themoviedb.org/movie/{item.get('id')}",
                "rt_url": f"https://www.rottentomatoes.com/search?search={item.get('title', '').replace(' ', '%20')}",
                "wikipedia_url": f"https://en.wikipedia.org/wiki/{item.get('title', '').replace(' ', '_')}_(film)",
                "review_data": {
                    "rt_score": None,
                    "imdb_rating": None
                }
            }
            
            # Format providers to match generate_site.py expectations
            providers_dict = {"rent": [], "buy": [], "stream": []}
            
            if item.get("providers"):
                if isinstance(item["providers"], dict):
                    # Legacy format: {rent: [], buy: [], flatrate: []}
                    providers_dict = {
                        "rent": item["providers"].get("rent", []),
                        "buy": item["providers"].get("buy", []),
                        "stream": item["providers"].get("flatrate", [])
                    }
                elif isinstance(item["providers"], list):
                    # Enhanced format: [{name: "Netflix", type: "flatrate"}]
                    for p in item["providers"]:
                        name = p.get("name", "")
                        ptype = p.get("type", "flatrate")
                        if ptype == "rent":
                            providers_dict["rent"].append(name)
                        elif ptype == "buy":
                            providers_dict["buy"].append(name)
                        else:  # flatrate or stream
                            providers_dict["stream"].append(name)
            
            wall_item["providers"] = providers_dict
            
            if status == "feature":
                featured.append(wall_item)
            else:
                approved.append(wall_item)
    
    # Combine featured first, then approved
    wall_items = featured + approved
    
    print(f"Built wall with {len(wall_items)} items ({len(featured)} featured, {len(approved)} approved)")
    
    # Save to output
    save_json(OUT, wall_items)
    print(f"Saved curated wall to {OUT}")
    
    # Show sample
    if wall_items:
        print(f"\nSample items:")
        for i, item in enumerate(wall_items[:3]):
            status = "⭐ FEATURED" if i < len(featured) else "✓ APPROVED"
            providers = ", ".join(list(item["providers"]["stream"][:2]) + list(item["providers"]["rent"][:1]))
            print(f"  {status}: {item['title']} ({item['year']}) - {providers}")

if __name__ == "__main__":
    main()