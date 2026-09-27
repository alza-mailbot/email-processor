"""Live smoke test against a locally running chatbot service.

Start the chatbot first (just run in the chatbot repo), then:
uv run pytest -m live
"""

import httpx
import pytest

from email_processor.core.chatbot import ChatbotClient
from email_processor.models.email import IncomingEmail


@pytest.mark.live
class TestLiveChatbot:
    """Smoke test exercising the real v1 contract end to end."""

    async def test_real_reply_for_simple_email(self) -> None:
        """Verify a real chatbot call returns a non-empty reply."""
        http = httpx.AsyncClient(base_url="http://localhost:8080", timeout=120)
        client = ChatbotClient(http)
        email = IncomingEmail(
            message_id="live1",
            thread_id="thr1",
            sender_name="Pavel Dvořák",
            sender_address="zakaznik@example.com",
            subject="Store hours",
            rfc_message_id=None,
            body="Hello, what are your typical store opening hours? Reply briefly.",
            attachments=[],
        )

        try:
            reply = await client.get_reply(email, [], [])
        finally:
            await client.aclose()

        assert reply.strip()
