"""Unit tests for the chatbot HTTP client. Requests are captured by MockTransport."""

import json
from typing import Any

import httpx
import pytest

from email_processor.core.chatbot import (
    Attachment,
    ChatbotClient,
    ChatbotUnavailableError,
    UnsupportedContentError,
)
from email_processor.models.email import IncomingEmail, ThreadMessage


def _incoming_email(**overrides: Any) -> IncomingEmail:
    """Build an IncomingEmail with sensible defaults."""
    defaults: dict[str, Any] = {
        "message_id": "msg1",
        "thread_id": "thr1",
        "sender_name": "Pavel Dvořák",
        "sender_address": "zakaznik@example.com",
        "subject": "Dotaz na zboží",
        "rfc_message_id": "<original@mail.example.com>",
        "body": "Dobrý den, máte skladem?",
        "attachments": [],
    }
    return IncomingEmail(**{**defaults, **overrides})


def _client(response: httpx.Response, requests: list[httpx.Request]) -> ChatbotClient:
    """Return a ChatbotClient whose transport records requests and replies with response."""

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return response

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://chatbot.test")
    return ChatbotClient(http)


class TestGetReply:
    """Tests for ChatbotClient.get_reply request building."""

    async def test_sends_full_multipart_request(self) -> None:
        """Verify subject, body, thread JSON and files reach the v1 contract."""
        requests: list[httpx.Request] = []
        client = _client(httpx.Response(200, json={"reply": "Ano, máme."}), requests)
        thread = [
            ThreadMessage(message_id="m1", role="user", text="Dobrý den"),
            ThreadMessage(message_id="m2", role="assistant", text="Zdravím"),
        ]
        attachments = [
            Attachment(filename="purchase.pdf", mime_type="application/pdf", data=b"%PDF-1.4")
        ]

        reply = await client.get_reply(_incoming_email(), thread, attachments)

        assert reply == "Ano, máme."
        request = requests[0]
        assert request.method == "POST"
        assert str(request.url) == "http://chatbot.test/v1/chat"
        content = request.content
        assert b'name="subject"' in content
        assert "Dotaz na zboží".encode() in content
        assert b'name="body"' in content
        assert b'name="thread"' in content
        assert (
            json.dumps(
                [{"role": "user", "text": "Dobrý den"}, {"role": "assistant", "text": "Zdravím"}]
            ).encode()
            in content
        )
        assert b'filename="purchase.pdf"' in content
        assert b"application/pdf" in content
        assert b"%PDF-1.4" in content

    async def test_minimal_request_omits_thread_and_files(self) -> None:
        """Verify an email without context sends only subject and body."""
        requests: list[httpx.Request] = []
        client = _client(httpx.Response(200, json={"reply": "Ok"}), requests)

        reply = await client.get_reply(_incoming_email(), [], [])

        assert reply == "Ok"
        content = requests[0].content
        assert b"thread" not in content
        assert b"filename=" not in content


def _failing_client(exception: Exception) -> ChatbotClient:
    """Return a ChatbotClient whose transport raises the given exception."""

    def handler(_request: httpx.Request) -> httpx.Response:
        raise exception

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://chatbot.test")
    return ChatbotClient(http)


class TestGetReplyErrors:
    """Tests for error mapping of ChatbotClient.get_reply."""

    async def test_422_raises_unsupported_content_with_detail(self) -> None:
        """Verify a contract rejection surfaces the detail for the apology reply."""
        client = _client(
            httpx.Response(422, json={"detail": "Unsupported attachment type: application/zip"}),
            [],
        )

        with pytest.raises(UnsupportedContentError, match="application/zip"):
            await client.get_reply(_incoming_email(), [], [])

    async def test_413_raises_unsupported_content(self) -> None:
        """Verify an oversized payload maps to the permanent error too."""
        client = _client(httpx.Response(413, json={"detail": "File too large"}), [])

        with pytest.raises(UnsupportedContentError, match="too large"):
            await client.get_reply(_incoming_email(), [], [])

    async def test_5xx_raises_unavailable(self) -> None:
        """Verify a server error maps to the retryable error."""
        client = _client(httpx.Response(502, json={"detail": "LLM upstream failed"}), [])

        with pytest.raises(ChatbotUnavailableError):
            await client.get_reply(_incoming_email(), [], [])

    async def test_timeout_raises_unavailable(self) -> None:
        """Verify a timeout maps to the retryable error."""
        client = _failing_client(httpx.ReadTimeout("timed out"))

        with pytest.raises(ChatbotUnavailableError):
            await client.get_reply(_incoming_email(), [], [])

    async def test_connect_error_raises_unavailable(self) -> None:
        """Verify an unreachable chatbot maps to the retryable error."""
        client = _failing_client(httpx.ConnectError("connection refused"))

        with pytest.raises(ChatbotUnavailableError):
            await client.get_reply(_incoming_email(), [], [])

    async def test_missing_reply_field_raises_unavailable(self) -> None:
        """Verify a 200 without the reply field is treated as a broken chatbot."""
        client = _client(httpx.Response(200, json={"message": "oops"}), [])

        with pytest.raises(ChatbotUnavailableError):
            await client.get_reply(_incoming_email(), [], [])

    async def test_invalid_json_raises_unavailable(self) -> None:
        """Verify a 200 with a non-JSON body is treated as a broken chatbot."""
        client = _client(httpx.Response(200, content=b"<html>gateway</html>"), [])

        with pytest.raises(ChatbotUnavailableError):
            await client.get_reply(_incoming_email(), [], [])

    @pytest.mark.parametrize("reply", ["", "   ", None, 42])
    async def test_empty_or_invalid_reply_raises_unavailable(self, reply: object) -> None:
        """Verify a blank or non-string reply is never returned to the caller."""
        client = _client(httpx.Response(200, json={"reply": reply}), [])

        with pytest.raises(ChatbotUnavailableError):
            await client.get_reply(_incoming_email(), [], [])
