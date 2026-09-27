"""Integration tests for the watch renewal route. All clients are mocked."""

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from googleapiclient.errors import HttpError

from email_processor.core.processor import IncompleteProcessingError
from email_processor.main import app


@pytest.fixture()
def stack() -> Iterator[tuple[MagicMock, MagicMock, MagicMock]]:
    """Install mocked gmail, processor and state store on the app."""
    gmail = MagicMock()
    gmail.setup_watch.return_value = "5000"
    processor = MagicMock()
    processor.run = AsyncMock()
    processor.bot_address = "techmailbot6@gmail.com"
    state = MagicMock()
    state.get_last_history_id.return_value = "1000"
    app.state.gmail = gmail
    app.state.processor = processor
    app.state.state_store = state
    yield gmail, processor, state
    del app.state.gmail
    del app.state.processor
    del app.state.state_store


class TestRenewWatch:
    """Tests for POST /renew-watch."""

    def test_renewal_runs_a_synthetic_notification(
        self, client: TestClient, stack: tuple[MagicMock, MagicMock, MagicMock]
    ) -> None:
        """Verify the fresh watch history id is processed like a notification."""
        gmail, processor, state = stack

        response = client.post("/renew-watch")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "history_id": "5000"}
        notification = processor.run.await_args.args[0]
        assert notification.history_id == "5000"
        state.set_last_history_id.assert_not_called()

    def test_empty_state_is_baselined_without_processing(
        self, client: TestClient, stack: tuple[MagicMock, MagicMock, MagicMock]
    ) -> None:
        """Verify the first run only stores the pointer."""
        gmail, processor, state = stack
        state.get_last_history_id.return_value = None

        response = client.post("/renew-watch")

        assert response.status_code == 200
        assert response.json() == {"status": "baselined", "history_id": "5000"}
        state.set_last_history_id.assert_called_once_with("5000")
        processor.run.assert_not_awaited()

    def test_gmail_failure_returns_502(
        self, client: TestClient, stack: tuple[MagicMock, MagicMock, MagicMock]
    ) -> None:
        """Verify a watch API error maps to a bad gateway."""
        gmail, _, _ = stack
        gmail.setup_watch.side_effect = HttpError(MagicMock(status=500, reason="x"), b"err")

        response = client.post("/renew-watch")

        assert response.status_code == 502

    def test_incomplete_batch_returns_500(
        self, client: TestClient, stack: tuple[MagicMock, MagicMock, MagicMock]
    ) -> None:
        """Verify a transient batch failure surfaces for the scheduler retry."""
        _, processor, _ = stack
        processor.run = AsyncMock(side_effect=IncompleteProcessingError("m1"))

        response = client.post("/renew-watch")

        assert response.status_code == 500
