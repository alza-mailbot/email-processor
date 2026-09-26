"""Unit tests for Gmail payload parsing. Fixtures are anonymized real payloads."""

import base64
import json
from pathlib import Path
from typing import Any

from email_processor.core.gmail.parsing import (
    extract_body,
    list_attachment_refs,
    parse_message,
    parse_rfc_message_id,
    parse_sender,
    parse_subject,
)
from email_processor.models.email import AttachmentRef

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "gmail"


def _load(name: str) -> dict[str, Any]:
    """Load a Gmail message fixture by name."""
    return json.loads((_FIXTURES / f"{name}.json").read_text())


def _b64(text: str) -> str:
    """Encode text the way Gmail encodes body data."""
    return base64.urlsafe_b64encode(text.encode()).decode()


class TestParseSender:
    """Tests for parse_sender."""

    def test_parses_name_and_address_with_diacritics(self) -> None:
        """Verify a display name with diacritics splits cleanly from the address."""
        payload = _load("simple_text")["payload"]

        name, address = parse_sender(payload)

        assert name == "Pavel Dvořák"
        assert address == "zakaznik@example.com"

    def test_missing_from_header_yields_empty_values(self) -> None:
        """Verify a payload without a From header parses to empty strings."""
        name, address = parse_sender({"headers": []})

        assert (name, address) == ("", "")


class TestParseSubject:
    """Tests for parse_subject."""

    def test_reads_subject_header(self) -> None:
        """Verify the subject comes back verbatim."""
        payload = _load("simple_text")["payload"]

        assert parse_subject(payload) == "Dotaz na zboží"

    def test_missing_subject_is_empty_string(self) -> None:
        """Verify a missing Subject header parses to an empty string."""
        assert parse_subject({"headers": []}) == ""


class TestParseRfcMessageId:
    """Tests for parse_rfc_message_id."""

    def test_reads_message_id_header(self) -> None:
        """Verify the RFC Message-ID header is found case-insensitively."""
        payload = _load("thread_customer_reply")["payload"]

        rfc_id = parse_rfc_message_id(payload)

        assert rfc_id is not None
        assert rfc_id.startswith("<")

    def test_missing_header_yields_none(self) -> None:
        """Verify a payload without Message-ID parses to None."""
        assert parse_rfc_message_id({"headers": []}) is None


class TestExtractBody:
    """Tests for extract_body."""

    def test_prefers_text_plain_in_multipart_alternative(self) -> None:
        """Verify the plain-text part wins over the HTML sibling."""
        payload = _load("simple_text")["payload"]

        body = extract_body(payload)

        assert "máte na skladě" in body
        assert "<" not in body

    def test_finds_text_in_nested_multipart_mixed(self) -> None:
        """Verify text nested under mixed/alternative is found."""
        payload = _load("with_pdf_attachment")["payload"]

        assert "celková cena" in extract_body(payload)

    def test_single_part_plain_message(self) -> None:
        """Verify a non-multipart text/plain payload decodes directly."""
        payload = {"mimeType": "text/plain", "body": {"data": _b64("Ahoj světe")}, "headers": []}

        assert extract_body(payload) == "Ahoj světe"

    def test_html_only_message_is_stripped_to_text(self) -> None:
        """Verify an HTML-only message falls back to tag-stripped text."""
        payload = {
            "mimeType": "text/html",
            "body": {"data": _b64("<p>Dobrý <b>den</b> &amp; ahoj</p>")},
            "headers": [],
        }

        body = extract_body(payload)

        assert "Dobrý den" in body
        assert "& ahoj" in body
        assert "<" not in body

    def test_message_without_body_is_empty_string(self) -> None:
        """Verify a payload with no decodable content parses to an empty string."""
        payload = {"mimeType": "text/plain", "body": {"size": 0}, "headers": []}

        assert extract_body(payload) == ""


class TestListAttachmentRefs:
    """Tests for list_attachment_refs."""

    def test_finds_pdf_in_nested_structure(self) -> None:
        """Verify the PDF attachment is found with filename, mime and id."""
        payload = _load("with_pdf_attachment")["payload"]

        refs = list_attachment_refs(payload)

        assert len(refs) == 1
        ref = refs[0]
        assert ref == AttachmentRef(
            filename="purchase.pdf",
            mime_type="application/pdf",
            attachment_id=ref.attachment_id,
        )
        assert ref.attachment_id

    def test_message_without_attachments_yields_empty_list(self) -> None:
        """Verify a plain message has no attachment refs."""
        assert list_attachment_refs(_load("simple_text")["payload"]) == []

    def test_part_without_filename_is_ignored(self) -> None:
        """Verify inline parts with an attachmentId but no filename are skipped."""
        payload = {
            "mimeType": "multipart/mixed",
            "headers": [],
            "parts": [
                {
                    "mimeType": "image/png",
                    "filename": "",
                    "body": {"attachmentId": "abc", "size": 10},
                }
            ],
        }

        assert list_attachment_refs(payload) == []


class TestParseMessage:
    """Tests for parse_message composing the full IncomingEmail."""

    def test_parses_thread_reply_completely(self) -> None:
        """Verify all fields of a real reply message are populated."""
        msg = _load("thread_customer_reply")

        email = parse_message(msg)

        assert email.message_id == msg["id"]
        assert email.thread_id == msg["threadId"]
        assert email.sender_address == "zakaznik@example.com"
        assert email.subject == "Re: Dotaz na zboží"
        assert "Kolik má" in email.body
        assert email.attachments == []
        assert email.rfc_message_id is not None

    def test_parses_message_with_attachment(self) -> None:
        """Verify a message with a PDF reports the attachment ref."""
        email = parse_message(_load("with_pdf_attachment"))

        assert [a.filename for a in email.attachments] == ["purchase.pdf"]
