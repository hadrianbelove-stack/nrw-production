#!/usr/bin/env python3
"""
Admin panel for curating movie selections.
Thin entry point — all logic lives in admin/ package.
"""

import os
import load_env  # Load .env into os.environ

from admin import create_app

if __name__ == '__main__':
    print("\n\U0001f3ac NRW Admin Panel - Local Curation Mode (No Authentication Required) - Port: 5556")
    print("==================================================================")

    port = int(os.environ.get('ADMIN_PORT', 5556))
    debug_mode = True
    host = '0.0.0.0'  # All interfaces for development

    print(f"\U0001f680 Admin panel available at http://localhost:{port}")
    print("\U0001f513 No authentication required - direct access enabled\n")
    print("\nPress Ctrl+C to stop\n")

    # Ensure admin directory exists
    os.makedirs('admin', exist_ok=True)

    app = create_app()
    app.run(debug=debug_mode, host=host, port=port)
