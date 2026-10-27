"""Automatic deduplication, conflict updates, and retrieval for personal memory."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from threading import RLock

from memory.database import Database, MemoryRecord
from memory.memory_extractor import MemoryCandidate, MemoryExtractor
from memory.memory_retriever import MemoryRetriever


@dataclass(frozen=True, slots=True)
class MemoryCaptureResult:
    """Describe one automatically created or replaced memory."""

    memory: MemoryRecord
    replaced_existing: bool


class MemoryManager:
    """Automatically store validated local-model extractions when enabled."""

    def __init__(
        self,
        database: Database,
        extractor: MemoryExtractor,
        retriever: MemoryRetriever | None = None,
        user_id: int = 1,
    ) -> None:
        self.database = database
        self.extractor = extractor
        self.retriever = retriever or MemoryRetriever(database, user_id)
        self.user_id = user_id
        self._lock = RLock()

    @property
    def enabled(self) -> bool:
        return (
            self.database.get_setting("memory_enabled", "true", self.user_id) == "true"
        )

    def set_enabled(self, enabled: bool) -> None:
        self.database.set_setting("memory_enabled", str(enabled).lower(), self.user_id)

    def capture_from_message(self, user_message: str) -> list[MemoryCaptureResult]:
        """Extract and immediately store useful memories from one completed turn."""

        if not self.enabled:
            return []
        candidates = self.extractor.extract(user_message)
        results: list[MemoryCaptureResult] = []
        processed: list[MemoryCandidate] = []

        with self._lock:
            existing = self.database.list_memories(self.user_id)
            for candidate in candidates:
                if self._find_duplicate(candidate, existing) is not None:
                    continue
                if any(
                    self._candidates_are_duplicates(candidate, other)
                    for other in processed
                ):
                    continue

                conflict = self._find_conflict(candidate, existing)
                if conflict is not None:
                    saved = self.database.update_memory(
                        conflict.id,
                        candidate.content,
                        candidate.memory_type,
                        "automatic_conflict_replacement",
                        self.user_id,
                    )
                    if saved is None:  # pragma: no cover - concurrent external deletion
                        continue
                    replaced = True
                else:
                    saved = self.database.create_memory(
                        candidate.memory_type,
                        candidate.content,
                        candidate.source,
                        user_id=self.user_id,
                    )
                    replaced = False

                results.append(MemoryCaptureResult(saved, replaced))
                processed.append(candidate)
                existing = self.database.list_memories(self.user_id)
        return results

    def retrieve_relevant(
        self, user_message: str, limit: int = 5
    ) -> list[MemoryRecord]:
        if not self.enabled:
            return []
        return self.retriever.retrieve_relevant(user_message, limit)

    @classmethod
    def _find_duplicate(
        cls, candidate: MemoryCandidate, existing: list[MemoryRecord]
    ) -> MemoryRecord | None:
        normalized = cls._normalize(candidate.content)
        candidate_tokens = set(normalized.split())
        for memory in existing:
            other = cls._normalize(memory.content)
            other_tokens = set(other.split())
            overlap = (
                len(candidate_tokens & other_tokens)
                / len(candidate_tokens | other_tokens)
                if candidate_tokens | other_tokens
                else 1.0
            )
            if (
                normalized == other
                or SequenceMatcher(None, normalized, other).ratio() >= 0.88
            ):
                return memory
            if candidate.memory_type == memory.memory_type and overlap >= 0.8:
                return memory
        return None

    @classmethod
    def _candidates_are_duplicates(
        cls, first: MemoryCandidate, second: MemoryCandidate
    ) -> bool:
        first_normalized = cls._normalize(first.content)
        second_normalized = cls._normalize(second.content)
        if first_normalized == second_normalized:
            return True
        return (
            first.memory_type == second.memory_type
            and SequenceMatcher(None, first_normalized, second_normalized).ratio()
            >= 0.88
        )

    @classmethod
    def _find_conflict(
        cls, candidate: MemoryCandidate, existing: list[MemoryRecord]
    ) -> MemoryRecord | None:
        key = cls._conflict_key(candidate.memory_type, candidate.content)
        if key is None:
            return None
        for memory in existing:
            if cls._conflict_key(memory.memory_type, memory.content) == key:
                return memory
        return None

    @staticmethod
    def _conflict_key(memory_type: str, content: str) -> str | None:
        text = content.casefold()
        if memory_type == "preference":
            if re.search(
                r"\b(short|shorter|brief|concise|long|longer|detailed)\b", text
            ) and re.search(
                r"\b(response|responses|reply|replies|answer|answers)\b", text
            ):
                return "preference:response_length"
            if (
                re.search(r"\b(casual|formal|friendly|professional)\b", text)
                and "tone" in text
            ):
                return "preference:tone"
        if memory_type == "profile" and re.search(
            r"\b(name is|called|call me)\b", text
        ):
            return "profile:preferred_name"
        return None

    @staticmethod
    def _normalize(content: str) -> str:
        return " ".join(re.findall(r"[^\W_]+", content.casefold(), flags=re.UNICODE))
