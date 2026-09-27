"""Live smoke test against real Firestore. Requires ADC and a real GCP project.

Run explicitly with: uv run pytest -m live
"""

import uuid

import pytest
from google.cloud import firestore

from email_processor.core.state import FirestoreStateStore


@pytest.mark.live
class TestLiveFirestore:
    """Smoke test exercising the real claim semantics."""

    def test_claim_is_atomic_and_single_winner(self) -> None:
        """Verify a real claim wins once, loses on repeat, and cleans up."""
        client = firestore.Client()
        store = FirestoreStateStore(client)
        message_id = f"live-test-{uuid.uuid4()}"

        try:
            assert store.claim_message(message_id) is True
            assert store.claim_message(message_id) is False
        finally:
            client.collection("processed_messages").document(message_id).delete()
