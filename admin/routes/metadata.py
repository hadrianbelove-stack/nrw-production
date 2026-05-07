"""Admin panel metadata routes — pending changes, delta summary, filter data, site serving."""

import os

from flask import Blueprint, request, jsonify, send_file, send_from_directory, Response
from typing import Union

from admin.config import DATA_FILE, FEATURED_FILE, SITE_ROOT
from admin.logging_setup import logger
from admin.health import compute_delta_summary
from admin.utils import load_json, has_pending_changes

bp = Blueprint('metadata', __name__)


@bp.route('/pending-changes', methods=['GET'])
def pending_changes() -> dict:
    """Check if there are pending changes that need to be saved."""
    return jsonify({
        'has_pending_changes': has_pending_changes(),
        'pending_change_count': 0  # Draft system removed - always 0
    })


@bp.route('/delta-summary', methods=['GET'])
def delta_summary() -> Union[Response, tuple[Response, int]]:
    """Get current delta summary for preview."""
    try:
        delta = compute_delta_summary()

        return jsonify({
            'success': True,
            'delta': delta
        })

    except Exception as e:
        logger.error(f"Error computing delta summary: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error computing delta summary: {str(e)}'
        }), 500


@bp.route('/filter-data', methods=['GET'])
def filter_data() -> dict:
    """Get featured movie IDs for frontend filtering."""
    try:
        # Load featured movies
        featured_ids = []
        if os.path.exists(FEATURED_FILE):
            try:
                with open(FEATURED_FILE, 'r') as f:
                    import json
                    featured_ids = json.load(f)
            except (json.JSONDecodeError, TypeError):
                featured_ids = []

        return jsonify({
            'success': True,
            'featured': featured_ids
        })

    except Exception as e:
        logger.error(f"Error loading filter data: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error loading filter data: {str(e)}'
        }), 500


# Serve the public site from /site/ path
@bp.route('/site/')
def serve_site_index():
    """Serve the main site index.html."""
    return send_file(os.path.join(SITE_ROOT, 'index.html'))

@bp.route('/site/<path:filename>')
def serve_site_files(filename):
    """Serve static site files (assets, data.json, etc.)."""
    return send_from_directory(SITE_ROOT, filename)
