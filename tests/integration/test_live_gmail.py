"""Live smoke tests against the real Gmail mailbox. Requires token.json.

Run explicitly with: uv run pytest -m live
"""

from pathlib import Path

import pytest

from email_processor.core.gmail.auth import build_gmail_service, load_credentials
from email_processor.core.gmail.client import GmailClient
from email_processor.core.gmail.parsing import parse_message

BOT_ADDRESS = "techmailbot6@gmail.com"


@pytest.fixture(scope="module")
def client() -> GmailClient:
    """Build a GmailClient over the real mailbox, or skip without a token."""
    if not Path("token.json").exists():
        pytest.skip("No token.json; run scripts/authorize.py first")
    return GmailClient(build_gmail_service(load_credentials("token.json")))


@pytest.mark.live
class TestLiveGmail:
    """Smoke tests exercising real read operations end to end."""

    def test_newest_message_parses(self, client: GmailClient) -> None:
        """Verify the newest inbox message fetches and parses into the model."""
        listing = (
            client._service.users()
            .messages()
            .list(userId="me", labelIds=["INBOX"], maxResults=1)
            .execute()
        )
        messages = listing.get("messages", [])
        assert messages, "The inbox is empty; send a test email first"

        raw = client.get_message(messages[0]["id"])
        assert raw is not None
        email = parse_message(raw)

        assert email.message_id == messages[0]["id"]
        assert email.thread_id
        assert "@" in email.sender_address
        assert email.body.strip()

    def test_thread_of_newest_message_maps_roles(self, client: GmailClient) -> None:
        """Verify the newest message's thread returns valid role-mapped messages."""
        listing = (
            client._service.users()
            .messages()
            .list(userId="me", labelIds=["INBOX"], maxResults=1)
            .execute()
        )
        message = client.get_message(listing["messages"][0]["id"])
        assert message is not None
        thread_id = message["threadId"]

        thread = client.get_thread_messages(thread_id, bot_address=BOT_ADDRESS)

        assert thread
        assert all(m.role in ("user", "assistant") for m in thread)
        assert all(m.message_id for m in thread)
