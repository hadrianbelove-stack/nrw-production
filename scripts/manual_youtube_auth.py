#!/usr/bin/env python3
"""
Manual YouTube OAuth token generator
Handles cases where browser auto-redirect fails
"""

import pickle
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
CREDENTIALS_DIR = Path('youtube_credentials')

def main():
    print("🔐 YouTube API Manual Authentication\n")

    client_secret = CREDENTIALS_DIR / 'client_secret.json'

    if not client_secret.exists():
        print(f"❌ Error: {client_secret} not found")
        return

    print("Starting OAuth flow...\n")
    print("Your browser will open. Steps:")
    print("1. Sign in with newreleasewall@gmail.com")
    print("2. Click 'Continue' and 'Allow'")
    print("3. Browser will try to redirect to localhost (may show error)")
    print("4. When prompted, check the terminal for next steps\n")

    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_secret),
        SCOPES,
        redirect_uri='http://localhost:8080/'
    )

    try:
        # Try automatic flow first
        creds = flow.run_local_server(
            port=8080,
            open_browser=True,
            success_message='✅ Authorization complete! You can close this window.'
        )
    except Exception as e:
        print(f"\n⚠️  Auto-flow failed: {e}")
        print("\nTrying manual flow...\n")

        # Fall back to manual flow
        auth_url, _ = flow.authorization_url(prompt='consent')
        print("Please visit this URL:\n")
        print(auth_url)
        print("\nAfter authorizing, paste the FULL redirect URL here:")
        code_url = input("URL: ").strip()

        # Extract code from URL
        import urllib.parse as urlparse
        parsed = urlparse.urlparse(code_url)
        code = urlparse.parse_qs(parsed.query)['code'][0]

        flow.fetch_token(code=code)
        creds = flow.credentials

    # Save credentials
    token_path = CREDENTIALS_DIR / 'token.pickle'
    with open(token_path, 'wb') as token:
        pickle.dump(creds, token)

    print(f"\n✅ Success! Token saved to {token_path}")
    print("\nNext steps:")
    print("1. Run: bash scripts/encode_youtube_token.sh")
    print("2. Update GitHub secret YOUTUBE_TOKEN with the output")
    print("3. Test: gh workflow run youtube-playlists.yml")

if __name__ == '__main__':
    main()
