"""Unit tests for the notification processor. All clients are mocked."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from email_processor.core.chatbot import ChatbotUnavailableError, UnsupportedContentError
from email_processor.core.gmail.client import HistoryExpiredError
from email_processor.core.processor import EmailProcessor, IncompleteProcessingError
from email_processor.models.email import ThreadMessage
from email_processor.models.pubsub import GmailNotification

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "gmail"

BOT_ADDRESS = "techmailbot6@gmail.com"


def _load(name: str) -> dict[str, Any]:
    """Load a Gmail message fixture by name."""
    return json.loads((_FIXTURES / f"{name}.json").read_text())


def _notification(history_id: str = "2000") -> GmailNotification:
    """Build a notification for the bot mailbox."""
    return GmailNotification(email_address=BOT_ADDRESS, history_id=history_id)


def _deps() -> tuple[MagicMock, MagicMock, MagicMock]:
    """Return (gmail, chatbot, state) mocks preset for a one-message happy path."""
    gmail = MagicMock()
    gmail.list_new_message_ids.return_value = ["1a0df8b813c620b8"]
    gmail.get_message.return_value = _load("simple_text")
    gmail.get_thread_messages.return_value = []
    gmail.download_attachment.return_value = b"%PDF-1.4"
    chatbot = MagicMock()
    chatbot.get_reply = AsyncMock(return_value="Dobrý den, odpověď.")
    state = MagicMock()
    state.get_last_history_id.return_value = "1000"
    state.claim_message.return_value = True
    return gmail, chatbot, state


async def _run(
    gmail: MagicMock,
    chatbot: MagicMock,
    state: MagicMock,
    notification: GmailNotification | None = None,
) -> None:
    """Run an EmailProcessor over the mocks for one notification."""
    processor = EmailProcessor(gmail=gmail, chatbot=chatbot, state=state, bot_address=BOT_ADDRESS)
    await processor.run(notification or _notification())


class TestHappyPath:
    """Tests for successful processing of new messages."""

    async def test_single_message_full_pipeline(self) -> None:
        """Verify claim, fetch, chatbot, reply, mark and pointer advance in order."""
        gmail, chatbot, state = _deps()

        await _run(gmail, chatbot, state)

        gmail.list_new_message_ids.assert_called_once_with("1000")
        state.claim_message.assert_called_once_with("1a0df8b813c620b8")
        email = chatbot.get_reply.call_args.args[0]
        assert email.sender_address == "zakaznik@example.com"
        gmail.send_reply.assert_called_once()
        assert gmail.send_reply.call_args.args[1] == "Dobrý den, odpověď."
        gmail.mark_processed.assert_called_once_with("1a0df8b813c620b8")
        state.set_last_history_id.assert_called_once_with("2000")

    async def test_two_messages_both_processed(self) -> None:
        """Verify every listed message goes through the pipeline."""
        gmail, chatbot, state = _deps()
        gmail.list_new_message_ids.return_value = ["1a0df8b813c620b8", "1a0df8d3e35cce4e"]
        gmail.get_message.side_effect = [_load("simple_text"), _load("with_pdf_attachment")]

        await _run(gmail, chatbot, state)

        assert chatbot.get_reply.await_count == 2
        assert gmail.send_reply.call_count == 2
        assert gmail.mark_processed.call_count == 2
        state.set_last_history_id.assert_called_once_with("2000")

    async def test_attachments_are_downloaded_and_forwarded(self) -> None:
        """Verify attachment bytes reach the chatbot call."""
        gmail, chatbot, state = _deps()
        gmail.list_new_message_ids.return_value = ["1a0df8d3e35cce4e"]
        gmail.get_message.return_value = _load("with_pdf_attachment")

        await _run(gmail, chatbot, state)

        attachments = chatbot.get_reply.call_args.args[2]
        assert len(attachments) == 1
        assert attachments[0].filename == "purchase.pdf"
        assert attachments[0].data == b"%PDF-1.4"

    async def test_thread_excludes_the_message_being_answered(self) -> None:
        """Verify the current message is not duplicated into the thread context."""
        gmail, chatbot, state = _deps()
        gmail.get_thread_messages.return_value = [
            ThreadMessage(message_id="older", role="user", text="Older question"),
            ThreadMessage(message_id="1a0df8b813c620b8", role="user", text="Current"),
        ]

        await _run(gmail, chatbot, state)

        thread = chatbot.get_reply.call_args.args[1]
        assert [m.message_id for m in thread] == ["older"]


class TestSkips:
    """Tests for messages that must be skipped without a chatbot call."""

    async def test_bot_own_message_is_skipped(self) -> None:
        """Verify the self-loop guard: no reply to the bot's own messages."""
        gmail, chatbot, state = _deps()
        gmail.get_message.return_value = _load("thread_bot_reply")

        await _run(gmail, chatbot, state)

        chatbot.get_reply.assert_not_awaited()
        gmail.send_reply.assert_not_called()
        state.set_last_history_id.assert_called_once_with("2000")

    async def test_already_claimed_message_is_skipped(self) -> None:
        """Verify a duplicate delivery does not produce a second reply."""
        gmail, chatbot, state = _deps()
        state.claim_message.return_value = False

        await _run(gmail, chatbot, state)

        gmail.get_message.assert_not_called()
        chatbot.get_reply.assert_not_awaited()
        state.set_last_history_id.assert_called_once_with("2000")

    async def test_vanished_message_is_skipped(self) -> None:
        """Verify a deleted message is skipped without failing the batch."""
        gmail, chatbot, state = _deps()
        gmail.get_message.return_value = None

        await _run(gmail, chatbot, state)

        chatbot.get_reply.assert_not_awaited()
        state.set_last_history_id.assert_called_once_with("2000")


class TestChatbotErrors:
    """Tests for chatbot failure handling."""

    async def test_unsupported_content_sends_apology_and_completes(self) -> None:
        """Verify a permanent rejection turns into an apology reply, not a retry."""
        gmail, chatbot, state = _deps()
        chatbot.get_reply = AsyncMock(
            side_effect=UnsupportedContentError("Unsupported attachment type")
        )

        await _run(gmail, chatbot, state)

        reply_text = gmail.send_reply.call_args.args[1]
        assert "Unsupported attachment type" in reply_text
        gmail.mark_processed.assert_called_once()
        state.release_claim.assert_not_called()
        state.set_last_history_id.assert_called_once_with("2000")

    async def test_unavailable_chatbot_releases_claim_and_signals_failure(self) -> None:
        """Verify a transient failure frees the claim and keeps the pointer."""
        gmail, chatbot, state = _deps()
        gmail.list_new_message_ids.return_value = ["m-fail", "1a0df8b813c620b8"]
        gmail.get_message.side_effect = [_load("simple_text"), _load("simple_text")]
        chatbot.get_reply = AsyncMock(
            side_effect=[ChatbotUnavailableError("down"), "Dobrý den, odpověď."]
        )

        with pytest.raises(IncompleteProcessingError):
            await _run(gmail, chatbot, state)

        state.release_claim.assert_called_once_with("m-fail")
        gmail.send_reply.assert_called_once()
        gmail.mark_processed.assert_called_once_with("1a0df8b813c620b8")
        state.set_last_history_id.assert_not_called()

    async def test_mark_processed_failure_does_not_fail_the_message(self) -> None:
        """Verify a label-update failure after a sent reply never causes a retry."""
        gmail, chatbot, state = _deps()
        gmail.mark_processed.side_effect = RuntimeError("labels API down")

        await _run(gmail, chatbot, state)

        gmail.send_reply.assert_called_once()
        state.release_claim.assert_not_called()
        state.set_last_history_id.assert_called_once_with("2000")

    async def test_send_failure_also_releases_claim(self) -> None:
        """Verify an unexpected send error is treated as transient."""
        gmail, chatbot, state = _deps()
        gmail.send_reply.side_effect = RuntimeError("gmail down")

        with pytest.raises(IncompleteProcessingError):
            await _run(gmail, chatbot, state)

        state.release_claim.assert_called_once_with("1a0df8b813c620b8")
        state.set_last_history_id.assert_not_called()


class TestHistoryEdgeCases:
    """Tests for pointer and history handling."""

    async def test_expired_history_resets_pointer(self) -> None:
        """Verify an expired start id degrades by re-baselining the pointer."""
        gmail, chatbot, state = _deps()
        gmail.list_new_message_ids.side_effect = HistoryExpiredError("gone")

        await _run(gmail, chatbot, state)

        state.set_last_history_id.assert_called_once_with("2000")
        chatbot.get_reply.assert_not_awaited()

    async def test_stale_notification_is_a_noop(self) -> None:
        """Verify a notification older than the pointer changes nothing."""
        gmail, chatbot, state = _deps()
        state.get_last_history_id.return_value = "3000"

        await _run(gmail, chatbot, state, _notification("2000"))

        gmail.list_new_message_ids.assert_not_called()
        state.set_last_history_id.assert_not_called()

    async def test_missing_pointer_initializes_baseline(self) -> None:
        """Verify the first notification without a stored pointer only baselines."""
        gmail, chatbot, state = _deps()
        state.get_last_history_id.return_value = None

        await _run(gmail, chatbot, state)

        gmail.list_new_message_ids.assert_not_called()
        state.set_last_history_id.assert_called_once_with("2000")
