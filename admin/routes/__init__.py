"""Admin panel route blueprints."""

from admin.routes.main import bp as main_bp
from admin.routes.curation import bp as curation_bp
from admin.routes.movies import bp as movies_bp
from admin.routes.generation import bp as generation_bp
from admin.routes.pull_quotes import bp as pull_quotes_bp
from admin.routes.metadata import bp as metadata_bp

ALL_BLUEPRINTS = [
    main_bp,
    curation_bp,
    movies_bp,
    generation_bp,
    pull_quotes_bp,
    metadata_bp,
]
