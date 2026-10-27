"""Deterministic local retrieval of a small relevant memory set."""

from __future__ import annotations

import re

from memory.database import Database, MemoryRecord


class MemoryRetriever:
    def __init__(self, database: Database, user_id: int = 1) -> None:
        self.database = database
        self.user_id = user_id

    def retrieve_relevant(
        self, user_message: str, limit: int = 5
    ) -> list[MemoryRecord]:
        """Combine FTS/keyword matches with a small number of stable preferences."""

        if limit <= 0:
            return []
        matched = self.database.search_memories(user_message, limit, self.user_id)
        seen = {memory.id for memory in matched}
        all_memories = self.database.list_memories(self.user_id)

        # Preferences affect style or suggestions even when vocabulary does not overlap.
        # Other memories are ranked by deterministic token overlap and recency.
        query_tokens = self._tokens(user_message)
        remaining = [memory for memory in all_memories if memory.id not in seen]
        remaining.sort(
            key=lambda memory: (
                memory.memory_type in {"preference", "interest"},
                len(query_tokens & self._tokens(memory.content)),
                memory.updated_at,
            ),
            reverse=True,
        )
        selected = (matched + remaining)[:limit]
        self.database.mark_memories_accessed(
            [memory.id for memory in selected], self.user_id
        )
        return selected

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {
            token.casefold()
            for token in re.findall(r"[^\W_]{3,}", text, flags=re.UNICODE)
        }
