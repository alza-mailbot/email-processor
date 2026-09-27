"""Application entry point building the FastAPI app."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from email_processor.api.deps import gmail_from_app
from email_processor.api.routes_admin import renew_watch_now
from email_processor.api.routes_admin import router as admin_router
from email_processor.api.routes_health import router as health_router
from email_processor.api.routes_webhook import router as webhook_router
from email_processor.config import get_settings
from email_processor.core.chatbot import ChatbotClient
from email_processor.core.state import create_state_store
from email_processor.utils.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run startup and shutdown work around the application's lifetime.

    Yields:
        None: Control while the application serves requests.
    """
    settings = get_settings()
    app.state.state_store = create_state_store(settings)
    app.state.chatbot = ChatbotClient(
        httpx.AsyncClient(base_url=settings.chatbot_url, timeout=settings.chatbot_timeout_seconds)
    )
    logger.info("[APP] Starting up, state backend: %s", settings.state_backend)
    if settings.renew_watch_on_startup:
        try:
            await renew_watch_now(app, await gmail_from_app(app))
        except Exception:
            # local convenience only; the daily scheduler is the authority
            logger.exception("[APP] Startup watch renewal failed")
    yield
    await app.state.chatbot.aclose()
    logger.info("[APP] Shutting down")


app = FastAPI(title="Email processor", lifespan=lifespan)
app.include_router(health_router, tags=["Health"])
app.include_router(webhook_router, tags=["Webhook"])
app.include_router(admin_router, tags=["Admin"])
