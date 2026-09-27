"""Unit tests for the Gmail API client. The service resource is mocked."""

import base64
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from email_processor.core.gmail.client import GmailClient, HistoryExpiredError

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "gmail"

BOT_ADDRESS = "techmailbot6@gmail.com"


def _load(name: str) -> dict[str, Any]:
    """Load a Gmail message fixture by name."""
    return json.loads((_FIXTURES / f"{name}.json").read_text())


def _http_error(status: int) -> HttpError:
    """Build an HttpError carrying the given status code."""
    return HttpError(MagicMock(status=status, reason="test"), b"error")


def _client() -> tuple[GmailClient, MagicMock]:
    """Return a GmailClient over a fully mocked service resource."""
    service = MagicMock()
    return GmailClient(service), service


class TestGetMessage:
    """Tests for GmailClient.get_message."""

    def test_returns_full_message(self) -> None:
        """Verify the message resource is fetched and returned."""
        client, service = _client()
        message = _load("simple_text")
        service.users().messages().get.return_value.execute.return_value = message

        result = client.get_message("abc")

        assert result == message
        service.users().messages().get.assert_called_with(userId="me", id="abc")

    def test_missing_message_returns_none(self) -> None:
        """Verify a 404 (message deleted meanwhile) yields None instead of raising."""
        client, service = _client()
        service.users().messages().get.return_value.execute.side_effect = _http_error(404)

        assert client.get_message("gone") is None

    def test_other_errors_propagate(self) -> None:
        """Verify non-404 API errors are not swallowed."""
        client, service = _client()
        service.users().messages().get.return_value.execute.side_effect = _http_error(500)

        with pytest.raises(HttpError):
            client.get_message("abc")


class TestListNewMessageIds:
    """Tests for GmailClient.list_new_message_ids."""

    def test_collects_ids_across_history_records(self) -> None:
        """Verify messagesAdded ids are flattened over all history entries."""
        client, service = _client()
        service.users().history().list.return_value.execute.return_value = {
            "history": [
                {"messagesAdded": [{"message": {"id": "m1"}}]},
                {"messagesAdded": [{"message": {"id": "m2"}}, {"message": {"id": "m3"}}]},
            ]
        }

        assert client.list_new_message_ids("1683") == ["m1", "m2", "m3"]

    def test_deduplicates_repeated_ids(self) -> None:
        """Verify the same message appearing in two records is returned once."""
        client, service = _client()
        service.users().history().list.return_value.execute.return_value = {
            "history": [
                {"messagesAdded": [{"message": {"id": "m1"}}]},
                {"messagesAdded": [{"message": {"id": "m1"}}]},
            ]
        }

        assert client.list_new_message_ids("1683") == ["m1"]

    def test_follows_pagination(self) -> None:
        """Verify nextPageToken pages are fetched and merged in order."""
        client, service = _client()
        service.users().history().list.return_value.execute.side_effect = [
            {"history": [{"messagesAdded": [{"message": {"id": "m1"}}]}], "nextPageToken": "t2"},
            {"history": [{"messagesAdded": [{"message": {"id": "m2"}}]}]},
        ]

        result = client.list_new_message_ids("1683")

        assert result == ["m1", "m2"]
        second_call = service.users().history().list.call_args_list[-1]
        assert second_call.kwargs["pageToken"] == "t2"

    def test_empty_history_yields_empty_list(self) -> None:
        """Verify a response without history entries returns no ids."""
        client, service = _client()
        service.users().history().list.return_value.execute.return_value = {}

        assert client.list_new_message_ids("1683") == []

    def test_expired_start_id_raises_history_expired(self) -> None:
        """Verify a 404 on history.list maps to HistoryExpiredError."""
        client, service = _client()
        service.users().history().list.return_value.execute.side_effect = _http_error(404)

        with pytest.raises(HistoryExpiredError):
            client.list_new_message_ids("1")


class TestDownloadAttachment:
    """Tests for GmailClient.download_attachment."""

    def test_decodes_base64url_data(self) -> None:
        """Verify attachment data is decoded to raw bytes."""
        client, service = _client()
        data = base64.urlsafe_b64encode(b"%PDF-1.4 payload").decode().rstrip("=")
        service.users().messages().attachments().get.return_value.execute.return_value = {
            "data": data
        }

        result = client.download_attachment("msg1", "att1")

        assert result == b"%PDF-1.4 payload"
        service.users().messages().attachments().get.assert_called_with(
            userId="me", messageId="msg1", id="att1"
        )


class TestGetThreadMessages:
    """Tests for GmailClient.get_thread_messages."""

    def test_maps_roles_by_bot_address(self) -> None:
        """Verify thread messages keep order and map sender to user/assistant roles."""
        client, service = _client()
        thread = {
            "messages": [
                _load("thread_original"),
                _load("thread_bot_reply"),
                _load("thread_customer_reply"),
            ]
        }
        service.users().threads().get.return_value.execute.return_value = thread

        messages = client.get_thread_messages("thr1", bot_address=BOT_ADDRESS)

        assert [m.role for m in messages] == ["user", "assistant", "user"]
        assert messages[0].message_id == _load("thread_original")["id"]
        assert "ledničku" in messages[0].text
        service.users().threads().get.assert_called_with(userId="me", id="thr1")

    def test_empty_thread_yields_empty_list(self) -> None:
        """Verify a thread without messages returns an empty list."""
        client, service = _client()
        service.users().threads().get.return_value.execute.return_value = {}

        assert client.get_thread_messages("thr1", bot_address=BOT_ADDRESS) == []
