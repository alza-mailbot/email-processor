"""Unit tests for the Firestore-backed state store. The client is mocked."""

from unittest.mock import MagicMock

from google.api_core.exceptions import AlreadyExists

from email_processor.core.state import FirestoreStateStore


def _store() -> tuple[FirestoreStateStore, MagicMock]:
    """Return a FirestoreStateStore over a fully mocked Firestore client."""
    client = MagicMock()
    return FirestoreStateStore(client), client


class TestHistoryPointer:
    """Tests for the last history id round trip."""

    def test_missing_document_yields_none(self) -> None:
        """Verify a fresh project without the state document reports no pointer."""
        store, client = _store()
        client.document.return_value.get.return_value.exists = False

        assert store.get_last_history_id() is None

    def test_reads_pointer_from_state_document(self) -> None:
        """Verify the pointer is read from the state/gmail document."""
        store, client = _store()
        snapshot = client.document.return_value.get.return_value
        snapshot.exists = True
        snapshot.to_dict.return_value = {"last_history_id": "123"}

        assert store.get_last_history_id() == "123"
        client.document.assert_called_with("state/gmail")

    def test_writes_pointer_with_merge(self) -> None:
        """Verify the pointer write merges into the state/gmail document."""
        store, client = _store()

        store.set_last_history_id("456")

        client.document.assert_called_with("state/gmail")
        client.document.return_value.set.assert_called_with({"last_history_id": "456"}, merge=True)


class TestClaimMessage:
    """Tests for atomic message claims."""

    def test_first_claim_creates_document_and_wins(self) -> None:
        """Verify a claim creates processed_messages/{id} and returns True."""
        store, client = _store()

        assert store.claim_message("abc") is True

        client.collection.assert_called_with("processed_messages")
        client.collection.return_value.document.assert_called_with("abc")
        client.collection.return_value.document.return_value.create.assert_called_once()

    def test_existing_claim_returns_false(self) -> None:
        """Verify AlreadyExists (claimed by another instance) maps to False."""
        store, client = _store()
        client.collection.return_value.document.return_value.create.side_effect = AlreadyExists(
            "claimed"
        )

        assert store.claim_message("abc") is False
