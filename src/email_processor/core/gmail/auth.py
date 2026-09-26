"""Gmail credentials loading. Strictly non-interactive: the token file is
created once by scripts/authorize.py and only refreshed here."""

from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]


class GmailAuthError(Exception):
    """Raised when usable Gmail credentials cannot be obtained."""


def load_credentials(path: str) -> Credentials:
    """Load OAuth credentials from a token file, refreshing them if expired.

    Args:
        path: Path to the JSON token file.

    Returns:
        Credentials: Valid credentials for the Gmail API.

    Raises:
        GmailAuthError: If the file is missing or holds credentials that are
            neither valid nor refreshable.
    """
    if not Path(path).exists():
        raise GmailAuthError(
            f"Token file {path!r} not found; run 'uv run python scripts/authorize.py' to create it"
        )
    creds = Credentials.from_authorized_user_file(path, SCOPES)
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        return creds
    raise GmailAuthError(f"Token file {path!r} holds no valid or refreshable credentials")


def build_gmail_service(creds: Credentials) -> Any:
    """Build a Gmail API service client.

    Args:
        creds: Valid credentials for the Gmail API.

    Returns:
        Any: The googleapiclient service resource for Gmail v1.
    """
    return build("gmail", "v1", credentials=creds)
