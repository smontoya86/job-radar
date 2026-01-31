#!/usr/bin/env python3
"""Setup script for Gmail OAuth authentication."""
import sys
from pathlib import Path

from scripts.bootstrap import settings
from src.gmail.auth import GmailAuth


def main():
    """Run Gmail OAuth setup."""
    print("Gmail OAuth Setup")
    print("=" * 50)
    print()

    credentials_path = Path(settings.gmail_credentials_file)
    token_path = Path(settings.gmail_token_file)

    # Check for credentials file
    if not credentials_path.exists():
        print("ERROR: credentials.json not found!")
        print()
        print("To set up Gmail integration:")
        print("1. Go to https://console.cloud.google.com")
        print("2. Create a new project (or use existing)")
        print("3. Enable the Gmail API")
        print("4. Go to Credentials > Create Credentials > OAuth 2.0 Client ID")
        print("5. Choose 'Desktop app' as application type")
        print("6. Download the JSON and save as 'credentials.json'")
        print(f"7. Place it in: {credentials_path.absolute()}")
        return 1

    print(f"Found credentials file: {credentials_path}")
    print()

    # Initialize auth
    auth = GmailAuth(
        credentials_file=str(credentials_path),
        token_file=str(token_path),
    )

    # Check if already authenticated
    if token_path.exists():
        print("Existing token found. Testing...")
        if auth.is_authenticated():
            print("Already authenticated! Gmail is ready to use.")
            return 0
        else:
            print("Token expired or invalid. Re-authenticating...")

    # Run OAuth flow
    print()
    print("Starting OAuth flow...")
    print("A browser window will open for authentication.")
    print()

    credentials = auth.get_credentials()

    if credentials:
        print()
        print("Authentication successful!")
        print(f"Token saved to: {token_path}")
        print()
        print("Gmail integration is now ready.")
        print("You can run the email importer to fetch job-related emails.")
        return 0
    else:
        print()
        print("Authentication failed!")
        print("Please check your credentials and try again.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
