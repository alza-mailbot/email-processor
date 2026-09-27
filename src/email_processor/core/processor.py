"""Orchestration of one Gmail notification: new messages in, replies out."""

import asyncio

from email_processor.core.chatbot import (
    Attachment,
    ChatbotClient,
    UnsupportedContentError,
)
from email_processor.core.gmail.client import GmailClient, HistoryExpiredError
from email_processor.core.gmail.parsing import parse_message
from email_processor.core.state import StateStore
from email_processor.models.pubsub import GmailNotification
from email_processor.utils.logger import logger

APOLOGY_TEMPLATE = (
    "Dobrý den,\n\n"
    "vaši zprávu se bohužel nepodařilo zpracovat: {detail}\n\n"
    "Zkuste ji prosím poslat znovu v jiném formátu.\n\n"
    "S pozdravem\nTechmailbot"
)


class IncompleteProcessingError(Exception):
    """Raised when at least one message failed transiently and needs a retry."""


class EmailProcessor:
    """Pipeline turning Gmail notifications into replies in the mailbox."""

    def __init__(
        self,
        *,
        gmail: GmailClient,
        chatbot: ChatbotClient,
        state: StateStore,
        bot_address: str,
    ) -> None:
        """Bind the processor to its collaborators.

        Args:
            gmail: Gmail client for the bot mailbox.
            chatbot: Client of the chatbot service.
            state: Persistent pointer and claim store.
            bot_address: Address of the bot mailbox, for the self-loop guard.
        """
        self._gmail = gmail
        self._chatbot = chatbot
        self._state = state
        self._bot_address = bot_address

    async def run(self, notification: GmailNotification) -> None:
        """Process a Gmail notification.

        The stored history pointer advances to the notification's history id
        only after the whole batch succeeds, so a retry re-reads the same
        window.

        Args:
            notification: Decoded Gmail push notification.

        Raises:
            IncompleteProcessingError: At least one message failed transiently;
                the caller should make Pub/Sub redeliver the notification.
        """
        last_history_id = self._state.get_last_history_id()
        if last_history_id is None:
            logger.warning("[PROCESSOR] No stored history pointer, baselining")
            self._state.set_last_history_id(notification.history_id)
            return
        if int(notification.history_id) <= int(last_history_id):
            logger.info("[PROCESSOR] Stale notification %s, ignoring", notification.history_id)
            return

        try:
            message_ids = await asyncio.to_thread(self._gmail.list_new_message_ids, last_history_id)
        except HistoryExpiredError:
            logger.error(
                "[PROCESSOR] History %s expired, re-baselining to %s; unprocessed "
                "messages in between are lost",
                last_history_id,
                notification.history_id,
            )
            self._state.set_last_history_id(notification.history_id)
            return

        failed_ids = []
        for message_id in message_ids:
            if not self._state.claim_message(message_id):
                logger.info("[PROCESSOR] Message %s already claimed, skipping", message_id)
                continue
            try:
                await self._process_message(message_id)
            except Exception:
                logger.exception("[PROCESSOR] Message %s failed, releasing claim", message_id)
                self._state.release_claim(message_id)
                failed_ids.append(message_id)

        if failed_ids:
            raise IncompleteProcessingError(f"Messages failed transiently: {failed_ids}")
        self._state.set_last_history_id(notification.history_id)

    async def _process_message(self, message_id: str) -> None:
        """Run the pipeline for one claimed message.

        Args:
            message_id: Gmail id of the claimed message.
        """
        raw = await asyncio.to_thread(self._gmail.get_message, message_id)
        if raw is None:
            return
        email = parse_message(raw)
        if email.sender_address == self._bot_address:
            logger.info("[PROCESSOR] Message %s is our own reply, skipping", message_id)
            return

        thread = await asyncio.to_thread(
            self._gmail.get_thread_messages, email.thread_id, bot_address=self._bot_address
        )
        thread = [message for message in thread if message.message_id != email.message_id]
        attachments = [
            Attachment(
                filename=ref.filename,
                mime_type=ref.mime_type,
                data=await asyncio.to_thread(
                    self._gmail.download_attachment, message_id, ref.attachment_id
                ),
            )
            for ref in email.attachments
        ]

        try:
            reply = await self._chatbot.get_reply(email, thread, attachments)
        except UnsupportedContentError as exc:
            logger.warning("[PROCESSOR] Message %s rejected by chatbot: %s", message_id, exc)
            reply = APOLOGY_TEMPLATE.format(detail=exc)

        await asyncio.to_thread(self._gmail.send_reply, email, reply)
        try:
            await asyncio.to_thread(self._gmail.mark_processed, message_id)
        except Exception:
            # the reply is already out; failing here would trigger a retry
            # and a duplicate reply over a cosmetic label update
            logger.exception("[PROCESSOR] Could not mark %s as read", message_id)
        logger.info("[PROCESSOR] Message %s answered", message_id)
