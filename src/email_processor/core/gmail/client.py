"""Gmail API client wrapping the dynamic googleapiclient service resource."""

import base64
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Any

from googleapiclient.errors import HttpError

from email_processor.core.gmail.parsing import extract_body, parse_sender
from email_processor.models.email import IncomingEmail, ThreadMessage
from email_processor.utils.logger import logger


class HistoryExpiredError(Exception):
    """Raised when the stored history id is older than Gmail's retained history."""


class GmailClient:
    """Synchronous Gmail operations for the bot mailbox.

    All googleapiclient calls are blocking; callers in async code run them
    via asyncio.to_thread.
    """

    def __init__(self, service: Any) -> None:
        """Wrap an authenticated Gmail service resource.

        Args:
            service: Resource built by build_gmail_service.
        """
        self._service = service

    def get_message(self, message_id: str) -> dict[str, Any] | None:
        """Fetch a full message resource.

        Args:
            message_id: Gmail message id.

        Returns:
            dict | None: The message, or None when it no longer exists
            (history can reference messages deleted in the meantime).

        Raises:
            HttpError: For API failures other than 404.
        """
        try:
            return self._service.users().messages().get(userId="me", id=message_id).execute()
        except HttpError as exc:
            if exc.resp.status == 404:
                logger.info("[GMAIL] Message %s no longer exists, skipping", message_id)
                return None
            raise

    def list_new_message_ids(self, start_history_id: str) -> list[str]:
        """List ids of messages added after the given history point.

        Args:
            start_history_id: History id to list changes from (exclusive).

        Returns:
            list[str]: Message ids in delivery order, deduplicated.

        Raises:
            HistoryExpiredError: When Gmail no longer retains the start point.
            HttpError: For other API failures.
        """
        seen: set[str] = set()
        ids: list[str] = []
        page_token: str | None = None
        while True:
            try:
                response = (
                    self._service.users()
                    .history()
                    .list(
                        userId="me",
                        startHistoryId=start_history_id,
                        historyTypes=["messageAdded"],
                        pageToken=page_token,
                    )
                    .execute()
                )
            except HttpError as exc:
                if exc.resp.status == 404:
                    raise HistoryExpiredError(
                        f"History id {start_history_id!r} is no longer retained by Gmail"
                    ) from exc
                raise
            for record in response.get("history", []):
                for item in record.get("messagesAdded", []):
                    message_id = item["message"]["id"]
                    if message_id not in seen:
                        seen.add(message_id)
                        ids.append(message_id)
            page_token = response.get("nextPageToken")
            if not page_token:
                return ids

    def download_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Download attachment data.

        Args:
            message_id: Gmail message id the attachment belongs to.
            attachment_id: Gmail attachment id.

        Returns:
            bytes: Raw attachment content.
        """
        attachment = (
            self._service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
            .execute()
        )
        data = attachment["data"]
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))

    def send_reply(self, email: IncomingEmail, reply_text: str) -> None:
        """Send a plain-text reply within the original thread.

        Args:
            email: The message being replied to.
            reply_text: Body of the reply.
        """
        mime = MIMEText(reply_text)
        # formataddr RFC-2047-encodes a non-ASCII display name on its own;
        # encoding the whole header value would corrupt the address
        mime["To"] = formataddr((email.sender_name, email.sender_address))
        subject = email.subject
        mime["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        if email.rfc_message_id:
            mime["In-Reply-To"] = email.rfc_message_id
            mime["References"] = email.rfc_message_id
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        self._service.users().messages().send(
            userId="me", body={"raw": raw, "threadId": email.thread_id}
        ).execute()
        logger.info("[GMAIL] Reply sent to %s", email.sender_address)

    def setup_watch(self, topic_name: str) -> str:
        """Register (or renew) inbox change notifications to a Pub/Sub topic.

        Args:
            topic_name: Fully qualified Pub/Sub topic name.

        Returns:
            str: The mailbox history id at registration time.
        """
        response = (
            self._service.users()
            .watch(userId="me", body={"topicName": topic_name, "labelIds": ["INBOX"]})
            .execute()
        )
        history_id = response["historyId"]
        logger.info("[GMAIL] Watch established, history id %s", history_id)
        return history_id

    def get_thread_messages(self, thread_id: str, *, bot_address: str) -> list[ThreadMessage]:
        """Fetch a thread as role-mapped plain-text messages.

        Args:
            thread_id: Gmail thread id.
            bot_address: Address of the bot mailbox; its messages map to the
                assistant role, everything else to user.

        Returns:
            list[ThreadMessage]: Messages in chronological order.
        """
        thread = self._service.users().threads().get(userId="me", id=thread_id).execute()
        messages = []
        for msg in thread.get("messages", []):
            payload = msg.get("payload", {})
            _, sender_address = parse_sender(payload)
            role = "assistant" if sender_address == bot_address else "user"
            messages.append(
                ThreadMessage(message_id=msg["id"], role=role, text=extract_body(payload))
            )
        return messages
