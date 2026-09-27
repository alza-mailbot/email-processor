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
    """

    model_config = SettingsConfigDict(env_file=".env")

    log_level: str = "INFO"
    port: int = 8080
    gmail_token_path: str
    state_backend: Literal["file", "firestore"] = "file"
    state_file_path: str = ".state.json"


@lru_cache
def get_settings() -> Settings:
    """Return the application settings, created once and cached.

    Returns:
        Settings: The shared settings instance.
    """
    return Settings()
