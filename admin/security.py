"""Admin panel security middleware."""

import os
from flask import request, redirect


def security_headers():
    """Enforce security policies before each request."""
    # HTTPS enforcement in production
    if os.environ.get('FLASK_ENV') == 'production' and not request.is_secure:
        return redirect(request.url.replace('http://', 'https://'), code=301)


def apply_security_headers(response):
    """Apply security headers to all responses."""
    # Prevent clickjacking
    response.headers['X-Frame-Options'] = 'DENY'
    # Prevent content type sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # XSS protection
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # Referrer policy
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

    # CSP for admin panel (strict)
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-src https://www.youtube.com; "
        "media-src 'self' https:"
    )
    response.headers['Content-Security-Policy'] = csp

    return response


def register_security(app):
    """Register security middleware on the Flask app."""
    app.before_request(security_headers)
    app.after_request(apply_security_headers)
