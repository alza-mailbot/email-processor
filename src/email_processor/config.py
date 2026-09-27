"""Application settings loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration read from the environment and an optional .env file.

    Attributes:
        log_level: Logging level name for the application logger.
        port: TCP port the HTTP server listens on.
        gmail_token_path: Path to the Gmail OAuth token file.
        state_backend: Where processing state lives; file locally, firestore in cloud.
        state_file_path: State file location for the file backend.
        chatbot_url: Base URL of the chatbot service.
        chatbot_timeout_seconds: Budget for one chatbot call.
        pubsub_topic: Fully qualified Pub/Sub topic Gmail publishes to.
        renew_watch_on_startup: Also renew the Gmail watch when the app boots.
    """

    model_config = SettingsConfigDict(env_file=".env")

    log_level: str = "INFO"
    port: int = 8080
    gmail_token_path: str
    state_backend: Literal["file", "firestore"] = "file"
    state_file_path: str = ".state.json"
    chatbot_url: str
    chatbot_timeout_seconds: float = 120
    pubsub_topic: str
    renew_watch_on_startup: bool = False


@lru_cache
def get_settings() -> Settings:
    """Return the application settings, created once and cached.

    Returns:
        Settings: The shared settings instance.
    """
    return Settings()
