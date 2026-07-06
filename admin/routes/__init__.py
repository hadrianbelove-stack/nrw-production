"""Admin panel route blueprints."""

from admin.routes.today import bp as today_bp
from admin.routes.main import bp as main_bp
from admin.routes.curation import bp as curation_bp
from admin.routes.curate_flow import bp as curate_flow_bp
from admin.routes.movies import bp as movies_bp
from admin.routes.generation import bp as generation_bp
from admin.routes.pull_quotes import bp as pull_quotes_bp
from admin.routes.metadata import bp as metadata_bp

ALL_BLUEPRINTS = [
    today_bp,
    main_bp,
    curation_bp,
    curate_flow_bp,
    movies_bp,
    generation_bp,
    pull_quotes_bp,
    metadata_bp,
]
