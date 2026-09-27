"""Application entry point building the FastAPI app."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from email_processor.api.routes_health import router as health_router
from email_processor.config import get_settings
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
    logger.info("[APP] Starting up, state backend: %s", settings.state_backend)
    yield
    logger.info("[APP] Shutting down")


app = FastAPI(title="Email processor", lifespan=lifespan)
app.include_router(health_router, tags=["Health"])
