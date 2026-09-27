"""Unit tests for state store selection from settings."""

from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from email_processor.config import Settings
from email_processor.core.state import FileStateStore, FirestoreStateStore, create_state_store


class TestCreateStateStore:
    """Tests for the create_state_store factory."""

    def test_file_backend_uses_configured_path(self, tmp_path: Path) -> None:
        """Verify the file backend stores state at the configured path."""
        path = tmp_path / "state.json"
        settings = Settings(state_backend="file", state_file_path=str(path))

        store = create_state_store(settings)

        assert isinstance(store, FileStateStore)
        store.set_last_history_id("123")
        assert path.exists()

    def test_firestore_backend_builds_client(self) -> None:
        """Verify the firestore backend wraps a default ADC client."""
        settings = Settings(state_backend="firestore")
        with patch("email_processor.core.state.firestore.Client") as client_cls:
            store = create_state_store(settings)

        assert isinstance(store, FirestoreStateStore)
        client_cls.assert_called_once_with()

    def test_backend_defaults_to_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify local development never hits Firestore by accident."""
        monkeypatch.delenv("STATE_BACKEND", raising=False)

        assert Settings(_env_file=None).state_backend == "file"

    def test_unknown_backend_is_rejected(self) -> None:
        """Verify an unsupported backend name fails settings validation."""
        with pytest.raises(ValidationError):
            Settings(state_backend="redis")  # ty: ignore[invalid-argument-type]
