"""Unit tests for the file-backed state store."""

from pathlib import Path

from email_processor.core.state import FileStateStore


class TestHistoryPointer:
    """Tests for the last history id round trip."""

    def test_fresh_store_has_no_history_id(self, tmp_path: Path) -> None:
        """Verify a store without a file reports no pointer."""
        store = FileStateStore(tmp_path / "state.json")

        assert store.get_last_history_id() is None

    def test_history_id_persists_across_instances(self, tmp_path: Path) -> None:
        """Verify the pointer survives a new store over the same file."""
        path = tmp_path / "state.json"
        FileStateStore(path).set_last_history_id("123")

        assert FileStateStore(path).get_last_history_id() == "123"


class TestClaimMessage:
    """Tests for message claim semantics."""

    def test_first_claim_wins_second_loses(self, tmp_path: Path) -> None:
        """Verify a message id can be claimed exactly once."""
        store = FileStateStore(tmp_path / "state.json")

        assert store.claim_message("abc") is True
        assert store.claim_message("abc") is False

    def test_claims_persist_across_instances(self, tmp_path: Path) -> None:
        """Verify a claim recorded by one instance blocks a later one."""
        path = tmp_path / "state.json"
        FileStateStore(path).claim_message("abc")

        assert FileStateStore(path).claim_message("abc") is False

    def test_distinct_ids_claim_independently(self, tmp_path: Path) -> None:
        """Verify claiming one id does not block another."""
        store = FileStateStore(tmp_path / "state.json")
        store.claim_message("abc")

        assert store.claim_message("def") is True


class TestCorruptedFile:
    """Tests for recovery from a broken state file."""

    def test_corrupted_json_resets_store(self, tmp_path: Path) -> None:
        """Verify unparseable content is discarded instead of crashing."""
        path = tmp_path / "state.json"
        path.write_text("{not json")
        store = FileStateStore(path)

        assert store.get_last_history_id() is None
        assert store.claim_message("abc") is True
