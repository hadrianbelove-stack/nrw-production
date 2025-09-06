import os, yaml

def load_config():
    cfg = {}
    try:
        with open("config.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except FileNotFoundError:
        pass
    return cfg

def get_tmdb_creds():
    cfg = load_config()
    tmdb = cfg.get("tmdb") or {}
    return {
        "bearer": os.getenv("TMDB_BEARER") or tmdb.get("bearer"),
        "api_key": os.getenv("TMDB_API_KEY") or tmdb.get("api_key"),
    }