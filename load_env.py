"""
Auto-load .env file into os.environ on import.

Usage: Just `import load_env` at the top of any script.
No pip dependencies required.
"""
import os
from pathlib import Path


def _load_env():
    env_path = Path(__file__).parent / '.env'
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            # Don't overwrite existing env vars (explicit env takes precedence)
            if key not in os.environ:
                os.environ[key] = value


_load_env()
