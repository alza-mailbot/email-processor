"""Decoding of Gmail push notifications delivered by Pub/Sub."""

import base64
import binascii
import json
from typing import Any, Self

from pydantic import BaseModel


class InvalidNotificationError(Exception):
    """Raised when a push envelope cannot be decoded into a notification."""


class GmailNotification(BaseModel):
    """Content of a Gmail watch notification.

    Attributes:
        email_address: The watched mailbox.
        history_id: Mailbox history id at notification time.
    """

    email_address: str
    history_id: str

    @classmethod
    def from_push_envelope(cls, envelope: dict[str, Any]) -> Self:
        """Decode a Pub/Sub push envelope into a notification.

        Args:
            envelope: Parsed JSON body of the push request.

        Returns:
            Self: The decoded notification.

        Raises:
            InvalidNotificationError: When the envelope shape, base64 data or
                JSON payload is not a Gmail notification.
        """
        data = envelope.get("message", {}).get("data")
        if not isinstance(data, str):
            raise InvalidNotificationError("Envelope has no message.data")
        try:
            normalized = data.replace("-", "+").replace("_", "/")
            decoded = base64.b64decode(normalized + "=" * (-len(normalized) % 4))
            payload = json.loads(decoded)
            return cls(
                email_address=payload["emailAddress"],
                history_id=str(payload["historyId"]),
            )
        except (binascii.Error, ValueError, KeyError, TypeError) as exc:
            raise InvalidNotificationError(f"Undecodable notification: {exc}") from exc
