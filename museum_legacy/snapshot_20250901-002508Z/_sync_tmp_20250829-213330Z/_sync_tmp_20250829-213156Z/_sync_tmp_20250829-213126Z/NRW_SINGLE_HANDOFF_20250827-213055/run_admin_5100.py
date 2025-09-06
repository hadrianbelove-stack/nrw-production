#!/usr/bin/env python3
import curator_admin

if __name__ == "__main__":
    print("🎬 Starting NRW Curator Admin on port 5100...")
    curator_admin.APP.run(host='0.0.0.0', port=5100, debug=True)