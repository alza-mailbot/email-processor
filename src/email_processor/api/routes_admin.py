"""Administrative endpoint renewing the Gmail watch registration."""

import asyncio

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from googleapiclient.errors import HttpError

from email_processor.api.deps import get_gmail, processor_from_app
from email_processor.config import get_settings
from email_processor.core.gmail.client import GmailClient
from email_processor.core.processor import IncompleteProcessingError
from email_processor.models.pubsub import GmailNotification
from email_processor.utils.logger import logger

router = APIRouter()


async def renew_watch_now(app: FastAPI, gmail: GmailClient) -> dict[str, str]:
    """Renew the watch and catch up on anything the pointer has missed.

    Feeding the fresh history id through the processor keeps the pointer
    younger than Gmail's history retention even for a quiet mailbox, and
    doubles as a sweep for notifications lost by Pub/Sub.

    Args:
        app: The FastAPI application carrying shared state.
        gmail: Gmail client for the bot mailbox.

    Returns:
        dict[str, str]: Renewal outcome and the fresh history id.

    Raises:
        IncompleteProcessingError: The catch-up batch failed transiently.
    """
    history_id = await asyncio.to_thread(gmail.setup_watch, get_settings().pubsub_topic)
    state_store = app.state.state_store
    if state_store.get_last_history_id() is None:
        state_store.set_last_history_id(history_id)
        logger.info("[ADMIN] Watch renewed, pointer baselined at %s", history_id)
        return {"status": "baselined", "history_id": history_id}

    processor = await processor_from_app(app)
    await processor.run(
        GmailNotification(email_address=processor.bot_address, history_id=history_id)
    )
    return {"status": "ok", "history_id": history_id}


@router.post("/renew-watch")
async def renew_watch(request: Request, gmail: GmailClient = Depends(get_gmail)) -> dict[str, str]:
    """Renew the Gmail watch and process the catch-up window.

    Args:
        request: The incoming request.
        gmail: The shared Gmail client.

    Returns:
        dict[str, str]: Renewal outcome and the fresh history id.

    Raises:
        HTTPException: 502 when the watch registration fails, 500 when the
            catch-up batch needs a retry.
    """
    try:
        return await renew_watch_now(request.app, gmail)
    except HttpError as exc:
        raise HTTPException(status_code=502, detail="Gmail watch registration failed") from exc
    except IncompleteProcessingError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
