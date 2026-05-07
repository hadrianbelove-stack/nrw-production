"""Allow running the admin panel via `python3 -m admin`."""

import os
import load_env  # noqa: F401 — Load .env into os.environ

from admin import create_app

if __name__ == '__main__':
    port = int(os.environ.get('ADMIN_PORT', 5556))
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=port)
