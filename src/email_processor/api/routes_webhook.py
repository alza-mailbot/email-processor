"""Webhook receiving Gmail push notifications from Pub/Sub."""

from fastapi import APIRouter, Depends, HTTPException, Request

from email_processor.api.deps import get_processor
from email_processor.core.processor import EmailProcessor, IncompleteProcessingError
from email_processor.models.pubsub import GmailNotification, InvalidNotificationError
from email_processor.utils.logger import logger

router = APIRouter()


@router.post("/gmail-webhook")
async def gmail_webhook(
    request: Request, processor: EmailProcessor = Depends(get_processor)
) -> dict[str, str]:
    """Process one Pub/Sub push delivery.

    A permanently undecodable request is acknowledged with a 200 so Pub/Sub
    stops redelivering it; only transient processing failures return a 500.

    Args:
        request: The raw push request.
        processor: The shared email processor.

    Returns:
        dict[str, str]: Ack payload for Pub/Sub.

    Raises:
        HTTPException: 500 when part of the batch needs a redelivery.
    """
    try:
        envelope = await request.json()
        notification = GmailNotification.from_push_envelope(envelope)
    except (ValueError, InvalidNotificationError) as exc:
        logger.warning("[WEBHOOK] Ignoring undecodable push request: %s", exc)
        return {"status": "ignored"}

    try:
        await processor.run(notification)
    except IncompleteProcessingError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "ok"}
