"""Unit tests for Pub/Sub push envelope decoding."""

import base64
import json
from pathlib import Path
from typing import Any

import pytest

from email_processor.models.pubsub import GmailNotification, InvalidNotificationError

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "pubsub"


def _envelope() -> dict[str, Any]:
    """Load the recorded push envelope fixture."""
    return json.loads((_FIXTURES / "push_envelope.json").read_text())


class TestFromPushEnvelope:
    """Tests for GmailNotification.from_push_envelope."""

    def test_decodes_real_envelope(self) -> None:
        """Verify address and history id are extracted from the base64 payload."""
        notification = GmailNotification.from_push_envelope(_envelope())

        assert notification.email_address == "techmailbot6@gmail.com"
        assert notification.history_id == "1683240"

    def test_urlsafe_base64_without_padding_decodes(self) -> None:
        """Verify the urlsafe alphabet and stripped padding are tolerated."""
        envelope = _envelope()
        payload = json.dumps({"emailAddress": "a@b.cz", "historyId": 7}).encode()
        envelope["message"]["data"] = base64.urlsafe_b64encode(payload).decode().rstrip("=")

        notification = GmailNotification.from_push_envelope(envelope)

        assert notification.history_id == "7"

    def test_missing_message_raises(self) -> None:
        """Verify an envelope without a message is rejected."""
        with pytest.raises(InvalidNotificationError):
            GmailNotification.from_push_envelope({"subscription": "projects/p/subscriptions/s"})

    def test_invalid_base64_raises(self) -> None:
        """Verify undecodable data is rejected."""
        envelope = _envelope()
        envelope["message"]["data"] = "!!!not-base64!!!"

        with pytest.raises(InvalidNotificationError):
            GmailNotification.from_push_envelope(envelope)

    def test_non_json_payload_raises(self) -> None:
        """Verify decoded data that is not JSON is rejected."""
        envelope = _envelope()
        envelope["message"]["data"] = base64.b64encode(b"hello").decode()

        with pytest.raises(InvalidNotificationError):
            GmailNotification.from_push_envelope(envelope)

    def test_missing_history_id_raises(self) -> None:
        """Verify a payload without historyId is rejected."""
        envelope = _envelope()
        payload = json.dumps({"emailAddress": "a@b.cz"}).encode()
        envelope["message"]["data"] = base64.b64encode(payload).decode()

        with pytest.raises(InvalidNotificationError):
            GmailNotification.from_push_envelope(envelope)
