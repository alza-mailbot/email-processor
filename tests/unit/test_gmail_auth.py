"""Unit tests for Gmail credentials loading. The google-auth SDK is mocked."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from email_processor.core.gmail.auth import (
    SCOPES,
    GmailAuthError,
    build_gmail_service,
    load_credentials,
)


def _token_file(tmp_path: Path) -> str:
    """Create an empty placeholder token file and return its path."""
    path = tmp_path / "token.json"
    path.write_text("{}")
    return str(path)


class TestLoadCredentials:
    """Tests for load_credentials."""

    @patch("email_processor.core.gmail.auth.Credentials")
    def test_valid_token_is_returned_as_is(
        self, mock_credentials: MagicMock, tmp_path: Path
    ) -> None:
        """Verify a valid token loads without a refresh."""
        path = _token_file(tmp_path)
        creds = MagicMock(valid=True)
        mock_credentials.from_authorized_user_file.return_value = creds

        result = load_credentials(path)

        assert result is creds
        mock_credentials.from_authorized_user_file.assert_called_once_with(path, SCOPES)
        creds.refresh.assert_not_called()

    @patch("email_processor.core.gmail.auth.Request")
    @patch("email_processor.core.gmail.auth.Credentials")
    def test_expired_token_is_refreshed(
        self, mock_credentials: MagicMock, mock_request: MagicMock, tmp_path: Path
    ) -> None:
        """Verify an expired token with a refresh token gets refreshed."""
        creds = MagicMock(valid=False, expired=True, refresh_token="refresh")
        mock_credentials.from_authorized_user_file.return_value = creds

        result = load_credentials(_token_file(tmp_path))

        assert result is creds
        creds.refresh.assert_called_once_with(mock_request.return_value)

    def test_missing_file_raises_with_hint(self, tmp_path: Path) -> None:
        """Verify a missing token file fails with a pointer to the authorize script."""
        with pytest.raises(GmailAuthError) as exc_info:
            load_credentials(str(tmp_path / "missing.json"))

        assert "authorize.py" in str(exc_info.value)

    @patch("email_processor.core.gmail.auth.Credentials")
    def test_expired_token_without_refresh_token_raises(
        self, mock_credentials: MagicMock, tmp_path: Path
    ) -> None:
        """Verify an unrefreshable token fails instead of any interactive fallback."""
        creds = MagicMock(valid=False, expired=True, refresh_token=None)
        mock_credentials.from_authorized_user_file.return_value = creds

        with pytest.raises(GmailAuthError):
            load_credentials(_token_file(tmp_path))

        creds.refresh.assert_not_called()


class TestBuildGmailService:
    """Tests for build_gmail_service."""

    @patch("email_processor.core.gmail.auth.build")
    def test_builds_gmail_v1_service(self, mock_build: MagicMock) -> None:
        """Verify the Gmail v1 service is built with the given credentials."""
        creds = MagicMock()

        service = build_gmail_service(creds)

        assert service is mock_build.return_value
        mock_build.assert_called_once_with("gmail", "v1", credentials=creds)
