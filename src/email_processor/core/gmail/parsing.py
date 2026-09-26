"""Pure functions turning Gmail API payload structures into our models.

No I/O happens here; every function takes already-fetched payload dicts.
"""

import base64
import html
import re
from collections.abc import Iterator
from email.utils import parseaddr
from typing import Any

from email_processor.models.email import AttachmentRef, IncomingEmail


def _header(payload: dict[str, Any], name: str) -> str | None:
    """Return a header value by case-insensitive name, or None."""
    for header in payload.get("headers", []):
        if header.get("name", "").lower() == name.lower():
            return header.get("value")
    return None


def _decode_body_data(data: str) -> str:
    """Decode Gmail's base64url body data, tolerating missing padding."""
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _walk_parts(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield the payload and all nested parts, depth-first."""
    yield payload
    for part in payload.get("parts", []):
        yield from _walk_parts(part)


def _strip_html(markup: str) -> str:
    """Reduce HTML to readable text: drop tags, unescape entities."""
    text = re.sub(r"<[^>]+>", " ", markup)
    return html.unescape(re.sub(r"[ \t]+", " ", text)).strip()


def parse_sender(payload: dict[str, Any]) -> tuple[str, str]:
    """Parse the From header into a display name and an address.

    Args:
        payload: Gmail message payload.

    Returns:
        tuple[str, str]: (display name, address); empty strings when absent.
    """
    return parseaddr(_header(payload, "From") or "")


def parse_subject(payload: dict[str, Any]) -> str:
    """Return the Subject header, or an empty string when missing.

    Args:
        payload: Gmail message payload.

    Returns:
        str: The subject line.
    """
    return _header(payload, "Subject") or ""


def parse_rfc_message_id(payload: dict[str, Any]) -> str | None:
    """Return the RFC 5322 Message-ID header used for reply threading.

    Args:
        payload: Gmail message payload.

    Returns:
        str | None: The Message-ID value, or None when missing.
    """
    return _header(payload, "Message-ID")


def extract_body(payload: dict[str, Any]) -> str:
    """Extract a plain-text body from the payload tree.

    Prefers a text/plain part anywhere in the tree; falls back to the first
    text/html part with tags stripped.

    Args:
        payload: Gmail message payload.

    Returns:
        str: The body text, or an empty string when nothing is decodable.
    """
    html_fallback = ""
    for part in _walk_parts(payload):
        data = part.get("body", {}).get("data")
        if not data:
            continue
        mime = part.get("mimeType", "")
        if mime == "text/plain":
            return _decode_body_data(data)
        if mime == "text/html" and not html_fallback:
            html_fallback = _strip_html(_decode_body_data(data))
    return html_fallback


def list_attachment_refs(payload: dict[str, Any]) -> list[AttachmentRef]:
    """List downloadable attachments anywhere in the payload tree.

    Parts with an attachmentId but no filename (inline images) are skipped.

    Args:
        payload: Gmail message payload.

    Returns:
        list[AttachmentRef]: Attachment references in payload order.
    """
    refs = []
    for part in _walk_parts(payload):
        filename = part.get("filename")
        attachment_id = part.get("body", {}).get("attachmentId")
        if filename and attachment_id:
            refs.append(
                AttachmentRef(
                    filename=filename,
                    mime_type=part.get("mimeType", ""),
                    attachment_id=attachment_id,
                )
            )
    return refs


def parse_message(msg: dict[str, Any]) -> IncomingEmail:
    """Compose a full IncomingEmail from a Gmail message resource.

    Args:
        msg: Gmail message as returned by messages.get (full format).

    Returns:
        IncomingEmail: The parsed message.
    """
    payload = msg.get("payload", {})
    sender_name, sender_address = parse_sender(payload)
    return IncomingEmail(
        message_id=msg["id"],
        thread_id=msg["threadId"],
        sender_name=sender_name,
        sender_address=sender_address,
        subject=parse_subject(payload),
        rfc_message_id=parse_rfc_message_id(payload),
        body=extract_body(payload),
        attachments=list_attachment_refs(payload),
    )
