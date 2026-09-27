"""Unit tests for the chatbot HTTP client. Requests are captured by MockTransport."""

import json
from typing import Any

import httpx

from email_processor.core.chatbot import Attachment, ChatbotClient
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
