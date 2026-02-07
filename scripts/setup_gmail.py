#!/usr/bin/env python3
"""Setup script for Gmail OAuth authentication."""
import logging
import sys
from pathlib import Path

from scripts.bootstrap import settings
from src.gmail.auth import GmailAuth
from src.logging_config import setup_logging

logger = logging.getLogger(__name__)


def main():
    """Run Gmail OAuth setup."""
    setup_logging()

    print("Gmail OAuth Setup")
    print("=" * 50)
    print()

    credentials_path = Path(settings.gmail_credentials_file)
    token_path = Path(settings.gmail_token_file)

    # Check for credentials file
    if not credentials_path.exists():
        logger.error("credentials.json not found!")
        print()
        print("To set up Gmail integration:")
        print("1. Go to https://console.cloud.google.com")
        print("2. Create a new project (or use existing)")
        print("3. Enable the Gmail API")
        print("4. Go to Credentials > Create Credentials > OAuth 2.0 Client ID")
        print("5. Choose 'Desktop app' as application type")
        print("6. Download the JSON and save as 'credentials.json'")
        print("7. Place it in: %s" % credentials_path.absolute())
        return 1

    logger.info("Found credentials file: %s", credentials_path)
    print()

    # Initialize auth
    auth = GmailAuth(
        credentials_file=str(credentials_path),
        token_file=str(token_path),
    )

    # Check if already authenticated
    if token_path.exists():
        logger.info("Existing token found. Testing...")
        if auth.is_authenticated():
            logger.info("Already authenticated! Gmail is ready to use.")
            return 0
        else:
            logger.warning("Token expired or invalid. Re-authenticating...")

    # Run OAuth flow
    print()
    print("Starting OAuth flow...")
    print("A browser window will open for authentication.")
    print()

    credentials = auth.get_credentials()

    if credentials:
        logger.info("Authentication successful!")
        logger.info("Token saved to: %s", token_path)
        print()
        print("Gmail integration is now ready.")
        print("You can run the email importer to fetch job-related emails.")
        return 0
    else:
        logger.error("Authentication failed!")
        print("Please check your credentials and try again.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
