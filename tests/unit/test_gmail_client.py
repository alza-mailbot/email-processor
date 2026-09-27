"""Unit tests for the Gmail API client. The service resource is mocked."""

import base64
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from email import message_from_bytes
from email.header import decode_header, make_header
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from email_processor.core.gmail.client import GmailClient, HistoryExpiredError
from email_processor.models.email import IncomingEmail

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


def _incoming_email(**overrides: Any) -> IncomingEmail:
    """Build an IncomingEmail with sensible defaults for reply tests."""
    defaults: dict[str, Any] = {
        "message_id": "msg1",
        "thread_id": "thr1",
        "sender_name": "Pavel Dvořák",
        "sender_address": "zakaznik@example.com",
        "subject": "Dotaz na zboží",
        "rfc_message_id": "<original@mail.example.com>",
        "body": "Dobrý den...",
        "attachments": [],
    }
    return IncomingEmail(**{**defaults, **overrides})


def _sent_mime(service: MagicMock) -> tuple[Any, dict[str, Any]]:
    """Decode the MIME message and body passed to messages().send."""
    body = service.users().messages().send.call_args.kwargs["body"]
    raw = body["raw"]
    mime = message_from_bytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    return mime, body


class TestSendReply:
    """Tests for GmailClient.send_reply."""

    def test_builds_threaded_reply_with_encoded_name(self) -> None:
        """Verify threading fields and RFC 2047 encoding of a non-ASCII name."""
        client, service = _client()
        email = _incoming_email()

        client.send_reply(email, "Dobrý den, ano, máme.")

        mime, body = _sent_mime(service)
        assert body["threadId"] == "thr1"
        assert "zakaznik@example.com" in mime["To"]
        assert "=?utf-8?" in mime["To"]
        assert str(make_header(decode_header(mime["Subject"]))) == "Re: Dotaz na zboží"
        assert mime["In-Reply-To"] == "<original@mail.example.com>"
        assert mime["References"] == "<original@mail.example.com>"
        assert "Dobrý den, ano" in mime.get_payload(decode=True).decode()
        assert service.users().messages().send.call_args.kwargs["userId"] == "me"

    def test_ascii_sender_name_stays_plain(self) -> None:
        """Verify an ASCII display name is not needlessly encoded."""
        client, service = _client()

        client.send_reply(_incoming_email(sender_name="John Doe"), "Hello")

        mime, _ = _sent_mime(service)
        assert mime["To"] == "John Doe <zakaznik@example.com>"

    def test_existing_re_prefix_is_not_duplicated(self) -> None:
        """Verify a subject already marked as a reply keeps a single prefix."""
        client, service = _client()

        client.send_reply(_incoming_email(subject="RE: Dotaz"), "Ano.")

        mime, _ = _sent_mime(service)
        assert mime["Subject"] == "RE: Dotaz"

    def test_missing_rfc_message_id_omits_threading_headers(self) -> None:
        """Verify absent Message-ID leaves threading to threadId only."""
        client, service = _client()

        client.send_reply(_incoming_email(rfc_message_id=None), "Ano.")

        mime, body = _sent_mime(service)
        assert mime["In-Reply-To"] is None
        assert mime["References"] is None
        assert body["threadId"] == "thr1"


class TestSetupWatch:
    """Tests for GmailClient.setup_watch."""

    def test_registers_inbox_watch_and_returns_history_id(self) -> None:
        """Verify the watch request targets the topic and INBOX only."""
        client, service = _client()
        service.users().watch.return_value.execute.return_value = {"historyId": "1683"}

        result = client.setup_watch("projects/p/topics/t")

        assert result == "1683"
        service.users().watch.assert_called_with(
            userId="me", body={"topicName": "projects/p/topics/t", "labelIds": ["INBOX"]}
        )


class TestMarkProcessed:
    """Tests for GmailClient.mark_processed."""

    def test_removes_unread_label(self) -> None:
        """Verify the message is marked read via label removal."""
        client, service = _client()

        client.mark_processed("msg1")

        service.users().messages().modify.assert_called_with(
            userId="me", id="msg1", body={"removeLabelIds": ["UNREAD"]}
        )

    def test_api_error_propagates(self) -> None:
        """Verify modify failures are not swallowed."""
        client, service = _client()
        service.users().messages().modify.return_value.execute.side_effect = _http_error(500)

        with pytest.raises(HttpError):
            client.mark_processed("msg1")


class TestThreadSafety:
    """Tests for serialization of the non-thread-safe service resource."""

    def test_concurrent_calls_do_not_overlap(self) -> None:
        """Verify two threads never execute service calls at the same time."""
        client, service = _client()
        active = threading.Semaphore(1)

        def slow_execute() -> dict[str, Any]:
            assert active.acquire(blocking=False), "service used by two threads at once"
            time.sleep(0.02)
            active.release()
            return {"id": "m1", "threadId": "t1", "payload": {}}

        service.users().messages().get.return_value.execute.side_effect = slow_execute

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: client.get_message("m1"), range(4)))

        assert all(r is not None for r in results)


class TestGetProfileAddress:
    """Tests for GmailClient.get_profile_address."""

    def test_returns_mailbox_address(self) -> None:
        """Verify the authenticated mailbox address is read from the profile."""
        client, service = _client()
        service.users().getProfile.return_value.execute.return_value = {
            "emailAddress": "techmailbot6@gmail.com",
            "historyId": "1683",
        }

        assert client.get_profile_address() == "techmailbot6@gmail.com"
        service.users().getProfile.assert_called_with(userId="me")


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
