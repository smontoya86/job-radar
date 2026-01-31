"""Gmail OAuth2 authentication."""
import os
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Gmail API scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.labels",
]


class GmailAuth:
    """Handle Gmail OAuth2 authentication."""

    def __init__(
        self,
        credentials_file: str = "credentials.json",
        token_file: str = "token.json",
    ):
        """
        Initialize Gmail authentication.

        Args:
            credentials_file: Path to OAuth credentials JSON file
            token_file: Path to store/load OAuth token
        """
        self.credentials_file = Path(credentials_file)
        self.token_file = Path(token_file)
        self._credentials: Optional[Credentials] = None

    def get_credentials(self) -> Optional[Credentials]:
        """
        Get valid credentials, refreshing or prompting for auth if needed.

        Returns:
            Valid Credentials object or None if authentication fails
        """
        if self._credentials and self._credentials.valid:
            return self._credentials

        # Try to load existing token
        if self.token_file.exists():
            self._credentials = Credentials.from_authorized_user_file(
                str(self.token_file),
                SCOPES,
            )

        # If credentials invalid, refresh or re-authenticate
        if not self._credentials or not self._credentials.valid:
            if self._credentials and self._credentials.expired and self._credentials.refresh_token:
                try:
                    self._credentials.refresh(Request())
                except Exception as e:
                    print(f"Token refresh failed: {e}")
                    self._credentials = None
            else:
                self._credentials = self._run_oauth_flow()

        # Save credentials for next time
        if self._credentials:
            self._save_token()

        return self._credentials

    def _run_oauth_flow(self) -> Optional[Credentials]:
        """Run the OAuth2 flow to get new credentials."""
        if not self.credentials_file.exists():
            print(f"Credentials file not found: {self.credentials_file}")
            print("Please download OAuth credentials from Google Cloud Console")
            return None

        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.credentials_file),
                SCOPES,
            )
            credentials = flow.run_local_server(port=0)
            return credentials

        except Exception as e:
            print(f"OAuth flow failed: {e}")
            return None

    def _save_token(self) -> None:
        """Save credentials to token file."""
        if self._credentials:
            with open(self.token_file, "w") as f:
                f.write(self._credentials.to_json())

    def is_authenticated(self) -> bool:
        """Check if valid credentials exist."""
        creds = self.get_credentials()
        return creds is not None and creds.valid

    def revoke(self) -> bool:
        """Revoke credentials and delete token file."""
        if self.token_file.exists():
            try:
                if self._credentials:
                    # Revoke the token
                    import requests
                    requests.post(
                        "https://oauth2.googleapis.com/revoke",
                        params={"token": self._credentials.token},
                        headers={"content-type": "application/x-www-form-urlencoded"},
                    )
                self.token_file.unlink()
                self._credentials = None
                return True
            except Exception as e:
                print(f"Revoke failed: {e}")
                return False
        return True
