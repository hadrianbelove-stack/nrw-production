#!/bin/bash
# Script to properly encode YouTube token.pickle for GitHub Secrets

TOKEN_FILE="youtube_credentials/token.pickle"

if [ ! -f "$TOKEN_FILE" ]; then
    echo "Error: $TOKEN_FILE not found"
    echo "Run youtube_playlist_manager.py locally first to generate credentials"
    exit 1
fi

echo "Encoding $TOKEN_FILE for GitHub Secret..."
echo ""
echo "Copy the output below and paste it into GitHub Secret: YOUTUBE_TOKEN"
echo "=================================================================================="
base64 < "$TOKEN_FILE"
echo "=================================================================================="
echo ""
echo "Instructions:"
echo "1. Go to: https://github.com/hadrianbelove-stack/nrw-production/settings/secrets/actions"
echo "2. Edit secret: YOUTUBE_TOKEN"
echo "3. Paste the ENTIRE base64 string above (including any line breaks)"
echo "4. Save"
