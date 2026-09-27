"""HTTP client for the chatbot service's v1 contract.

The only module that knows the chatbot API shape.
"""

import json

import httpx
from pydantic import BaseModel

from email_processor.models.email import IncomingEmail, ThreadMessage
from email_processor.utils.logger import logger


class Attachment(BaseModel):
    """Downloaded attachment ready to be forwarded to the chatbot.

    Attributes:
        filename: Original file name.
        mime_type: Declared mime type.
        data: Raw file content.
    """

    filename: str
    mime_type: str
    data: bytes


class ChatbotClient:
    """Async client for POST /v1/chat."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        """Wrap a configured HTTP client.

        Args:
            client: AsyncClient with the chatbot base_url and timeout set.
        """
        self._client = client

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def get_reply(
        self,
        email: IncomingEmail,
        thread: list[ThreadMessage],
        attachments: list[Attachment],
    ) -> str:
        """Ask the chatbot for a reply to the given email.

        Args:
            email: The email being answered.
            thread: Prior conversation, oldest first, without the email itself.
            attachments: Downloaded attachments of the email.

        Returns:
            str: The generated reply text.
        """
        data = {"subject": email.subject, "body": email.body}
        if thread:
            data["thread"] = json.dumps(
                [{"role": message.role, "text": message.text} for message in thread]
            )
        files = [
            ("files", (attachment.filename, attachment.data, attachment.mime_type))
            for attachment in attachments
        ]
        logger.info(
            "[CHATBOT] Requesting reply, thread length %d, %d attachment(s)",
            len(thread),
            len(attachments),
        )
        response = await self._client.post("/v1/chat", data=data, files=files)
        return response.json()["reply"]
