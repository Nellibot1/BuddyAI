"""Tests for automatic extraction, deduplication, conflicts, and retrieval."""

from pathlib import Path

import pytest

from memory.database import Database
from memory.memory_extractor import (
    MemoryCandidate,
    MemoryExtractionError,
    MemoryExtractor,
)
from memory.memory_manager import MemoryManager


class StubExtractor:
    def __init__(self, candidates: list[MemoryCandidate]) -> None:
        self.candidates = candidates

    def extract(self, user_message: str) -> list[MemoryCandidate]:
        return self.candidates


def candidate(content: str, memory_type: str = "preference") -> MemoryCandidate:
    return MemoryCandidate(
        memory_type=memory_type,
        content=content,
        source="explicit_user_statement",
        confidence=0.91,
    )


def test_memory_extraction_parses_valid_json_and_fences() -> None:
    parsed = MemoryExtractor.parse(
        """```json
        {"memory_candidates": [{"type": "interest", "content": "The user enjoys basketball.", "source": "explicit_user_statement", "confidence": 0.94}]}
        ```"""
    )

    assert len(parsed) == 1
    assert parsed[0].memory_type == "interest"
    assert parsed[0].content == "The user enjoys basketball."
    assert parsed[0].confidence == 0.94


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "{}",
        '{"memory_candidates": [{"type": "secret", "content": "x", "source": "explicit_user_statement", "confidence": 1}]}',
        '{"memory_candidates": [{"type": "interest", "content": "x", "confidence": 1}]}',
    ],
)
def test_memory_extraction_rejects_invalid_output(raw: str) -> None:
    with pytest.raises(MemoryExtractionError):
        MemoryExtractor.parse(raw)


def test_sensitive_candidate_is_not_stored() -> None:
    parsed = MemoryExtractor.parse(
        '{"memory_candidates": [{"type": "profile", "content": "The user password is example.", "source": "explicit_user_statement", "confidence": 0.99}]}'
    )

    assert parsed == []


def test_valid_candidate_is_saved_automatically(tmp_path: Path) -> None:
    database = Database(tmp_path / "buddy.sqlite3")
    manager = MemoryManager(
        database,
        StubExtractor([candidate("The user prefers concise responses.")]),  # type: ignore[arg-type]
    )

    captured = manager.capture_from_message("I prefer concise responses.")

    assert len(captured) == 1
    assert not captured[0].replaced_existing
    assert captured[0].memory.content == "The user prefers concise responses."
    assert database.list_memories() == [captured[0].memory]


def test_deduplication_does_not_save_another_memory(tmp_path: Path) -> None:
    database = Database(tmp_path / "buddy.sqlite3")
    original = database.create_memory("interest", "The user enjoys playing basketball.")
    manager = MemoryManager(
        database,
        StubExtractor([candidate("The user enjoys playing basketball!", "interest")]),  # type: ignore[arg-type]
    )

    assert manager.capture_from_message("I enjoy playing basketball") == []
    assert database.list_memories() == [original]


def test_duplicate_model_candidates_create_only_one_memory(tmp_path: Path) -> None:
    database = Database(tmp_path / "buddy.sqlite3")
    repeated = candidate("The user likes tea.", "interest")
    manager = MemoryManager(database, StubExtractor([repeated, repeated]))  # type: ignore[arg-type]

    assert len(manager.capture_from_message("I like tea")) == 1
    assert len(database.list_memories()) == 1


def test_conflicting_preference_is_replaced_automatically(tmp_path: Path) -> None:
    database = Database(tmp_path / "buddy.sqlite3")
    original = database.create_memory(
        "preference", "The user prefers long, detailed responses."
    )
    manager = MemoryManager(
        database,
        StubExtractor([candidate("The user prefers shorter responses now.")]),  # type: ignore[arg-type]
    )

    captured = manager.capture_from_message("Actually, I prefer shorter responses now.")

    assert len(captured) == 1
    assert captured[0].replaced_existing
    assert captured[0].memory.id == original.id
    assert captured[0].memory.content == "The user prefers shorter responses now."
    assert len(database.list_memories()) == 1


def test_retrieval_and_memory_disabled_behavior(tmp_path: Path) -> None:
    database = Database(tmp_path / "buddy.sqlite3")
    database.create_memory("interest", "The user enjoys building in Minecraft.")
    manager = MemoryManager(database, StubExtractor([]))  # type: ignore[arg-type]

    assert "Minecraft" in manager.retrieve_relevant("Any Minecraft ideas?")[0].content
    manager.set_enabled(False)
    assert manager.retrieve_relevant("Minecraft") == []
    assert manager.capture_from_message("I like Minecraft") == []
