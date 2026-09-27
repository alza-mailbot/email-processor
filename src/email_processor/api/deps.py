"""Request dependencies building the Gmail stack lazily on first use.

Lazy construction keeps startup and tests free of token I/O; the built
instances are cached on app.state, where tests may also inject mocks.
"""

import asyncio

from fastapi import FastAPI, Request

from email_processor.config import get_settings
from email_processor.core.gmail.auth import build_gmail_service, load_credentials
from email_processor.core.gmail.client import GmailClient
from email_processor.core.processor import EmailProcessor


async def gmail_from_app(app: FastAPI) -> GmailClient:
    """Return the shared GmailClient, building it on first use.

    Args:
        app: The FastAPI application carrying shared state.

    Returns:
        GmailClient: Client bound to the bot mailbox token.
    """
    if getattr(app.state, "gmail", None) is None:
        settings = get_settings()
        credentials = await asyncio.to_thread(load_credentials, settings.gmail_token_path)
        app.state.gmail = GmailClient(build_gmail_service(credentials))
    return app.state.gmail


async def processor_from_app(app: FastAPI) -> EmailProcessor:
    """Return the shared EmailProcessor, building it on first use.

    Args:
        app: The FastAPI application carrying shared state.

    Returns:
        EmailProcessor: Processor wired to the shared clients and state store.
    """
    if getattr(app.state, "processor", None) is None:
        gmail = await gmail_from_app(app)
        bot_address = await asyncio.to_thread(gmail.get_profile_address)
        app.state.processor = EmailProcessor(
            gmail=gmail,
            chatbot=app.state.chatbot,
            state=app.state.state_store,
            bot_address=bot_address,
        )
    return app.state.processor


async def get_gmail(request: Request) -> GmailClient:
    """FastAPI dependency variant of gmail_from_app."""
    return await gmail_from_app(request.app)


async def get_processor(request: Request) -> EmailProcessor:
    """FastAPI dependency variant of processor_from_app."""
    return await processor_from_app(request.app)
