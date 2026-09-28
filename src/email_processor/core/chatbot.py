"""HTTP client for the chatbot service's v1 contract.

The only module that knows the chatbot API shape.
"""

import asyncio
import json

import httpx
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from pydantic import BaseModel

from email_processor.models.email import IncomingEmail, ThreadMessage
from email_processor.utils.logger import logger


class UnsupportedContentError(Exception):
    """Permanent rejection by the chatbot; retrying cannot help."""


class ChatbotUnavailableError(Exception):
    """Transient chatbot failure; the notification should be retried."""


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

    def __init__(self, client: httpx.AsyncClient, *, auth_audience: str | None = None) -> None:
        """Wrap a configured HTTP client.

        Args:
            client: AsyncClient with the chatbot base_url and timeout set.
            auth_audience: When set, every request carries a Google-signed
                identity token for this audience (the chatbot's Cloud Run
                URL); None keeps requests unauthenticated for local use.
        """
        self._client = client
        self._auth_audience = auth_audience

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

        Raises:
            UnsupportedContentError: The chatbot rejected the content (422/413).
            ChatbotUnavailableError: Transport failure, 5xx, or a malformed response.
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
        headers = {}
        if self._auth_audience:
            token = await asyncio.to_thread(id_token.fetch_id_token, Request(), self._auth_audience)
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = await self._client.post("/v1/chat", data=data, files=files, headers=headers)
        except httpx.HTTPError as exc:
            raise ChatbotUnavailableError(f"Chatbot request failed: {exc}") from exc
        if response.status_code in (413, 422):
            raise UnsupportedContentError(_detail(response))
        if response.status_code != 200:
            raise ChatbotUnavailableError(f"Chatbot returned {response.status_code}")
        try:
            reply = response.json()["reply"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ChatbotUnavailableError("Malformed chatbot response") from exc
        if not isinstance(reply, str) or not reply.strip():
            raise ChatbotUnavailableError("Empty or invalid reply from chatbot")
        return reply


def _detail(response: httpx.Response) -> str:
    """Extract the error detail from a contract error response."""
    try:
        return str(response.json().get("detail", response.text))
    except ValueError:
        return response.text
