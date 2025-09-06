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

class TMDB:
    def __init__(self, bearer: Optional[str] = None, timeout: float = 10.0):
        self.session = requests.Session()
        # Try bearer → env API key → config.yaml API key
        token = bearer or os.getenv("TMDB_BEARER")
        if not token:
            token = os.getenv("TMDB_API_KEY") or _config_api_key_from_yaml()
        if not token:
            raise RuntimeError("TMDB auth missing: set TMDB_BEARER or TMDB_API_KEY (env or config.yaml)")
        # TMDB v3 key normally goes in query param; we keep header for simplicity.
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        self.timeout = timeout

    def _req(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        last_err: Optional[Exception] = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                r = self.session.get(url, params=params or {}, timeout=self.timeout)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise RuntimeError(f"tmdb {r.status_code}: {r.text[:200]}")
                r.raise_for_status()
                time.sleep(DEFAULT_SLEEP)
                return r.json()
            except Exception as e:
                last_err = e
                if attempt < MAX_RETRIES:
                    time.sleep(DEFAULT_SLEEP * attempt)
        raise RuntimeError(f"TMDB request failed after retries: {last_err}")

def get_release_types(tmdb: TMDB, movie_id: int, region: str) -> List[int]:
    data = tmdb._req(f"https://api.themoviedb.org/3/movie/{movie_id}/release_dates")
    types: List[int] = []
    for entry in data.get("results", []):
        if entry.get("iso_3166_1") == region.upper():
            for r in entry.get("release_dates", []):
                t = r.get("type")
                if isinstance(t, int):
                    types.append(t)
    return types

def get_providers(tmdb: TMDB, movie_id: int, region: str) -> Dict[str, List[Dict[str, Any]]]:
    data = tmdb._req(f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers")
    block = (data.get("results") or {}).get(region.upper()) or {}
    return {
        "rent": block.get("rent") or [],
        "buy": block.get("buy") or [],
        "stream": block.get("flatrate") or [],
    }

def get_details(tmdb: TMDB, movie_id: int) -> Dict[str, Any]:
    return tmdb._req(f"https://api.themoviedb.org/3/movie/{movie_id}")

def get_credits(tmdb: TMDB, movie_id: int) -> Dict[str, Any]:
    return tmdb._req(f"https://api.themoviedb.org/3/movie/{movie_id}/credits")

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
