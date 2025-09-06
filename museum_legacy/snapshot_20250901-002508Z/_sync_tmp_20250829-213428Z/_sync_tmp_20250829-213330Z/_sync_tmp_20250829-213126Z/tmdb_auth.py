import os
import yaml

def _load_cfg():
    try:
        with open('config.yaml', 'r') as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}

def _first_nonempty(*vals):
    for v in vals:
        if isinstance(v, str):
            v = v.strip()
        if v:
            return v
    return None

def resolve_tmdb_auth():
    """
    Order:
      1) TMDB_BEARER env
      2) TMDB_API_KEY env
      3) config.yaml: tmdb.bearer
      4) config.yaml: tmdb.api_key
    Returns: (headers_dict, params_dict)
    """
    cfg = _load_cfg()
    tmdb = (cfg.get('tmdb') or {})
    bearer = _first_nonempty(os.getenv('TMDB_BEARER'), tmdb.get('bearer'))
    api_key = _first_nonempty(os.getenv('TMDB_API_KEY'),
                              tmdb.get('api_key'),
                              tmdb.get('tmdb_api_key'),
                              cfg.get('tmdb_api_key'),
                              cfg.get('api_key'))
    if bearer:
        return {"Authorization": f"Bearer {bearer}"}, {}
    if api_key:
        return {}, {"api_key": api_key}
    raise RuntimeError("TMDB auth missing: set TMDB_BEARER or TMDB_API_KEY or config.yaml tmdb.{bearer|api_key}")