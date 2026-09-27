"""Integration tests for the Gmail webhook route. The processor is mocked."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from email_processor.core.processor import IncompleteProcessingError
from email_processor.main import app

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "pubsub"


def _envelope() -> dict[str, Any]:
    """Load the recorded push envelope fixture."""
    return json.loads((_FIXTURES / "push_envelope.json").read_text())


@pytest.fixture()
def processor() -> Iterator[MagicMock]:
    """Install a mocked processor on the app for the duration of a test."""
    mock = MagicMock()
    mock.run = AsyncMock()
    mock.bot_address = "techmailbot6@gmail.com"
    app.state.processor = mock
    yield mock
    del app.state.processor


class TestGmailWebhook:
    """Tests for POST /gmail-webhook."""

    def test_valid_envelope_runs_the_processor(
        self, client: TestClient, processor: MagicMock
    ) -> None:
        """Verify a decodable notification is handed to the processor."""
        response = client.post("/gmail-webhook", json=_envelope())

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        notification = processor.run.await_args.args[0]
        assert notification.history_id == "1683240"

    def test_envelope_without_message_is_acked_and_ignored(
        self, client: TestClient, processor: MagicMock
    ) -> None:
        """Verify a permanently invalid envelope gets a 200 to stop retries."""
        response = client.post("/gmail-webhook", json={"subscription": "s"})

        assert response.status_code == 200
        assert response.json() == {"status": "ignored"}
        processor.run.assert_not_awaited()

    def test_non_json_body_is_acked_and_ignored(
        self, client: TestClient, processor: MagicMock
    ) -> None:
        """Verify a non-JSON body gets a 200 instead of an endless retry loop."""
        response = client.post(
            "/gmail-webhook",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 200
        assert response.json() == {"status": "ignored"}
        processor.run.assert_not_awaited()

    def test_incomplete_processing_returns_500_for_retry(
        self, client: TestClient, processor: MagicMock
    ) -> None:
        """Verify a transient batch failure asks Pub/Sub to redeliver."""
        processor.run = AsyncMock(side_effect=IncompleteProcessingError("m1 failed"))

        response = client.post("/gmail-webhook", json=_envelope())

        assert response.status_code == 500
