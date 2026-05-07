"""NRW Admin Panel — Flask application factory."""

import os
import secrets

from flask import Flask

from admin.filters import register_filters
from admin.security import register_security
from admin.routes import ALL_BLUEPRINTS


def create_app() -> Flask:
    """Create and configure the Flask application.

    Returns:
        Configured Flask app with all blueprints registered.
    """
    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static',
        static_url_path='/admin/static',
    )

    # Configure session security
    app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))

    # Register template filters
    register_filters(app)

    # Register security middleware
    register_security(app)

    # Register all route blueprints
    for bp in ALL_BLUEPRINTS:
        app.register_blueprint(bp)

    return app
