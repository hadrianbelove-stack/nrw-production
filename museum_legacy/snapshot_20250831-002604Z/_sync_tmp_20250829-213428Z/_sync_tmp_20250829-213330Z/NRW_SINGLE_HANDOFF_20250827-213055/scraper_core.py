import os, time, requests, re
from typing import Dict, Any, List, Optional
from tmdb_auth import resolve_tmdb_auth

DEFAULT_SLEEP = 0.1
MAX_RETRIES = 3

# --- TMDB auth-aware request helper (additive) ---
def request_tmdb(url, params=None, method="GET", timeout=20, **kwargs):
    """
    Centralized TMDB request with hybrid auth.
    Usage: response = request_tmdb(url, params={'page':1})
    """
    params = dict(params or {})
    headers, auth_params = resolve_tmdb_auth()
    # auth params take precedence only if key not already provided per-call
    for k, v in auth_params.items():
        params.setdefault(k, v)
    return requests.request(method=method, url=url, headers=headers, params=params, timeout=timeout, **kwargs)

def _config_api_key_from_yaml() -> Optional[str]:
    # Minimal, dependency-free pull of TMDB_API_KEY from config.yaml if present
    try:
        with open("config.yaml", "r", encoding="utf-8") as f:
            txt = f.read()
        m = re.search(r'(?im)^\s*TMDB_API_KEY\s*:\s*["\']?([A-Za-z0-9._-]+)["\']?', txt)
        if not m:
            m = re.search(r'(?im)^\s*tmdb_api_key\s*:\s*["\']?([A-Za-z0-9._-]+)["\']?', txt)
        return m.group(1) if m else None
    except Exception:
        return None

def get_release_types(tmdb, movie_id: int, region: str) -> List[int]:
    data = get_tmdb_json(f"https://api.themoviedb.org/3/movie/{movie_id}/release_dates")
    types: List[int] = []
    for entry in data.get("results", []):
        if entry.get("iso_3166_1") == region.upper():
            for r in entry.get("release_dates", []):
                t = r.get("type")
                if isinstance(t, int):
                    types.append(t)
    return types

def get_providers(tmdb, movie_id: int, region: str) -> Dict[str, List[Dict[str, Any]]]:
    data = get_tmdb_json(f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers")
    block = (data.get("results") or {}).get(region.upper()) or {}
    return {
        "rent": block.get("rent") or [],
        "buy": block.get("buy") or [],
        "stream": block.get("flatrate") or [],
    }

def get_details(tmdb, movie_id: int) -> Dict[str, Any]:
    response = request_tmdb(f"https://api.themoviedb.org/3/movie/{movie_id}")
    return response.json()

def get_credits(tmdb, movie_id: int) -> Dict[str, Any]:
    response = request_tmdb(f"https://api.themoviedb.org/3/movie/{movie_id}/credits")
    return response.json()

def normalize_record(
    movie: Dict[str, Any],
    providers: Dict[str, List[Dict[str, Any]]],
    release_types: List[int],
    details: Dict[str, Any],
    credits: Dict[str, Any],
) -> Dict[str, Any]:
    year: Optional[int] = None
    try:
        rd = (movie.get("release_date") or "")[:4]
        if rd.isdigit():
            year = int(rd)
    except Exception:
        year = None
    directors = [p.get("name") for p in credits.get("crew", []) if p.get("job") == "Director"][:2]
    cast = [p.get("name") for p in credits.get("cast", [])][:2]
    prod_companies = details.get("production_companies") or []
    studio = prod_companies[0].get("name") if prod_companies else None
    poster_path = movie.get("poster_path")
    return {
        "id": movie.get("id"),
        "title": movie.get("title") or movie.get("name"),
        "year": year,
        "providers": {
            "rent": providers.get("rent", []),
            "buy": providers.get("buy", []),
            "stream": providers.get("stream", []),
        },
        "has_digital": (4 in release_types) or (6 in release_types) or any(
            providers.get(k) for k in ("rent", "buy", "stream")
        ),
        "release_types": release_types,
        "theatrical_date": None,
        "digital_date": None,
        "credits": {"director": directors, "cast": cast},
        "runtime": details.get("runtime"),
        "studio": studio,
        "overview": details.get("overview"),
        "poster_url": f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None,
    }

# ===== TMDB JSON cache + backoff =====
import hashlib, json, random, pathlib

CACHE_DIR = pathlib.Path("cache/tmdb")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL_SECS = 7 * 24 * 3600  # 7 days

def _cache_key(url: str, params: Optional[dict]) -> str:
    base = url + "?" + json.dumps(params or {}, sort_keys=True, separators=(",",":"))
    return hashlib.sha256(base.encode("utf-8")).hexdigest()

def _cache_get(key: str):
    f = CACHE_DIR / f"{key}.json"
    if not f.exists():
        return None
    try:
        if (time.time() - f.stat().st_mtime) > CACHE_TTL_SECS:
            return None
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None

def _cache_put(key: str, payload: dict):
    f = CACHE_DIR / f"{key}.json"
    try:
        f.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

def get_tmdb_json(url: str, params: Optional[dict] = None, timeout: float = 20.0, max_retries: int = 4) -> dict:
    # auth params
    headers, auth_params = resolve_tmdb_auth()
    merged = dict(auth_params)
    if params:
        merged.update(params)
    key = _cache_key(url, merged)
    hit = _cache_get(key)
    if hit is not None:
        return hit

    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(url, headers=headers, params=merged, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504):
                raise RuntimeError(f"tmdb {r.status_code}: {r.text[:200]}")
            r.raise_for_status()
            data = r.json()
            _cache_put(key, data)
            time.sleep(0.05)
            return data
        except Exception as e:
            last_err = e
            # exponential backoff with jitter
            sleep = min(8.0, 0.5 * (2 ** (attempt - 1))) + random.uniform(0, 0.3)
            time.sleep(sleep)
    raise RuntimeError(f"TMDB request failed after retries: {last_err}")

