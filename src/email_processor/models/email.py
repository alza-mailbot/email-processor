"""Internal representation of an incoming email."""

from pydantic import BaseModel


class AttachmentRef(BaseModel):
    """Reference to an attachment stored by Gmail.

    Attributes:
        filename: Original file name of the attachment.
        mime_type: Declared mime type of the attachment.
        attachment_id: Gmail id used to download the attachment data.
    """

    filename: str
    mime_type: str
    attachment_id: str


class IncomingEmail(BaseModel):
    """Parsed incoming email, decoupled from the Gmail payload shape.

    Attributes:
        message_id: Gmail message id.
        thread_id: Gmail thread id the message belongs to.
        sender_name: Display name of the sender (may be empty).
        sender_address: Email address of the sender.
        subject: Subject line (empty when the header is missing).
        rfc_message_id: RFC 5322 Message-ID header, used for reply threading.
        body: Plain-text body.
        attachments: References to attachments, in payload order.
    """

    message_id: str
    thread_id: str
    sender_name: str
    sender_address: str
    subject: str
    rfc_message_id: str | None
    body: str
    attachments: list[AttachmentRef]
