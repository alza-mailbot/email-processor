"""Persistent processing state: history pointer and message deduplication."""

import json
from pathlib import Path
from typing import Protocol

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore

from email_processor.config import Settings
from email_processor.utils.logger import logger


class StateStore(Protocol):
    """Persistence of the history pointer and processed-message claims."""

    def get_last_history_id(self) -> str | None:
        """Return the stored history pointer, or None on first run."""
        ...

    def set_last_history_id(self, history_id: str) -> None:
        """Persist the history pointer."""
        ...

    def claim_message(self, message_id: str) -> bool:
        """Atomically claim a message for processing.

        Returns:
            bool: True when this call claimed the message, False when it
            was already claimed earlier.
        """
        ...


class FileStateStore:
    """JSON-file store for local development; not safe across instances."""

    def __init__(self, path: Path | str) -> None:
        """Bind the store to a JSON file.

        Args:
            path: Location of the state file; created on first write.
        """
        self._path = Path(path)

    def _read(self) -> dict[str, object]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text())
        except json.JSONDecodeError, UnicodeDecodeError:
            logger.warning("[STATE] Corrupted state file %s, resetting", self._path)
            return {}

    def _write(self, state: dict[str, object]) -> None:
        self._path.write_text(json.dumps(state))

    def get_last_history_id(self) -> str | None:
        """Return the stored history pointer, or None on first run."""
        history_id = self._read().get("last_history_id")
        return history_id if isinstance(history_id, str) else None

    def set_last_history_id(self, history_id: str) -> None:
        """Persist the history pointer.

        Args:
            history_id: Gmail history id to store.
        """
        state = self._read()
        state["last_history_id"] = history_id
        self._write(state)

    def claim_message(self, message_id: str) -> bool:
        """Claim a message for processing.

        Args:
            message_id: Gmail message id.

        Returns:
            bool: True when this call claimed the message, False when it
            was already claimed earlier.
        """
        state = self._read()
        claimed = state.setdefault("claimed_messages", [])
        if not isinstance(claimed, list) or message_id in claimed:
            return False
        claimed.append(message_id)
        self._write(state)
        return True


class FirestoreStateStore:
    """Firestore-backed store, shared by all service instances."""

    def __init__(self, client: firestore.Client) -> None:
        """Bind the store to a Firestore client.

        Args:
            client: Authenticated Firestore client.
        """
        self._client = client

    def get_last_history_id(self) -> str | None:
        """Return the stored history pointer, or None on first run."""
        snapshot = self._client.document("state/gmail").get()
        if not snapshot.exists:
            return None
        history_id = (snapshot.to_dict() or {}).get("last_history_id")
        return history_id if isinstance(history_id, str) else None

    def set_last_history_id(self, history_id: str) -> None:
        """Persist the history pointer.

        Args:
            history_id: Gmail history id to store.
        """
        self._client.document("state/gmail").set({"last_history_id": history_id}, merge=True)

    def claim_message(self, message_id: str) -> bool:
        """Atomically claim a message via create-if-absent.

        Args:
            message_id: Gmail message id.

        Returns:
            bool: True when this call claimed the message, False when it
            was already claimed by an earlier call or another instance.
        """
        document = self._client.collection("processed_messages").document(message_id)
        try:
            document.create({"claimed_at": firestore.SERVER_TIMESTAMP})
        except AlreadyExists:
            return False
        return True


def create_state_store(settings: Settings) -> StateStore:
    """Build the state store selected by the settings.

    Args:
        settings: Application settings naming the backend.

    Returns:
        StateStore: FileStateStore or FirestoreStateStore.
    """
    if settings.state_backend == "firestore":
        # No-arg Client resolves credentials and project via ADC: the gcloud
        # user login locally, the service account metadata server on Cloud Run
        return FirestoreStateStore(firestore.Client())
    return FileStateStore(settings.state_file_path)
