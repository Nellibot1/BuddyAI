"""Versioned, local SQLite persistence for BuddyAI."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = 1


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    id: int
    user_id: int
    memory_type: str
    content: str
    source: str
    confirmation_status: str
    sensitivity: str
    created_at: str
    updated_at: str
    last_accessed_at: str | None


@dataclass(frozen=True, slots=True)
class ConversationRecord:
    id: int
    user_id: int
    title: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class MessageRecord:
    id: int
    conversation_id: int
    role: str
    content: str
    created_at: str


class DatabaseError(RuntimeError):
    """Raised when local persistence cannot safely complete an operation."""


class Database:
    """Small repository layer using one short-lived connection per operation."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fts_enabled = False
        self.initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            yield connection
            connection.commit()
        except sqlite3.Error as exc:
            connection.rollback()
            raise DatabaseError(f"Local database operation failed: {exc}") from exc
        finally:
            connection.close()

    def initialize(self) -> None:
        """Apply forward-only migrations without erasing existing data."""

        with self._connection() as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version > SCHEMA_VERSION:
                raise DatabaseError(
                    f"Database schema {version} is newer than supported version {SCHEMA_VERSION}."
                )
            if version < 1:
                self._migrate_v1(connection)
                connection.execute("PRAGMA user_version = 1")
            connection.execute(
                """
                INSERT OR IGNORE INTO users (id, display_name, created_at, updated_at)
                VALUES (1, 'User', ?, ?)
                """,
                (_utc_now(), _utc_now()),
            )
            self._ensure_default_settings(connection)
            self.fts_enabled = self._initialize_fts(connection)

    @staticmethod
    def _migrate_v1(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                display_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                memory_type TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL,
                confirmation_status TEXT NOT NULL,
                sensitivity TEXT NOT NULL DEFAULT 'normal',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_accessed_at TEXT,
                CHECK (confirmation_status IN ('approved', 'pending'))
            );

            CREATE INDEX memories_user_status_idx
                ON memories(user_id, confirmation_status);

            CREATE TABLE conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL
                    REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX messages_conversation_idx
                ON messages(conversation_id, id);

            CREATE TABLE settings (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, key)
            );
            """
        )

    @staticmethod
    def _ensure_default_settings(connection: sqlite3.Connection) -> None:
        now = _utc_now()
        defaults = {
            "personality": "chill",
            "buddy_name": "Buddy",
            "memory_enabled": "true",
            "history_enabled": "true",
        }
        connection.executemany(
            """
            INSERT OR IGNORE INTO settings (user_id, key, value, updated_at)
            VALUES (1, ?, ?, ?)
            """,
            [(key, value, now) for key, value in defaults.items()],
        )

    @staticmethod
    def _initialize_fts(connection: sqlite3.Connection) -> bool:
        try:
            connection.executescript(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    content,
                    content='memories',
                    content_rowid='id'
                );

                CREATE TRIGGER IF NOT EXISTS memories_fts_insert AFTER INSERT ON memories BEGIN
                    INSERT INTO memory_fts(rowid, content) VALUES (new.id, new.content);
                END;
                CREATE TRIGGER IF NOT EXISTS memories_fts_delete AFTER DELETE ON memories BEGIN
                    INSERT INTO memory_fts(memory_fts, rowid, content)
                    VALUES ('delete', old.id, old.content);
                END;
                CREATE TRIGGER IF NOT EXISTS memories_fts_update AFTER UPDATE OF content ON memories BEGIN
                    INSERT INTO memory_fts(memory_fts, rowid, content)
                    VALUES ('delete', old.id, old.content);
                    INSERT INTO memory_fts(rowid, content) VALUES (new.id, new.content);
                END;
                INSERT INTO memory_fts(memory_fts) VALUES ('rebuild');
                """
            )
            return True
        except sqlite3.OperationalError:
            return False

    def schema_version(self) -> int:
        with self._connection() as connection:
            return int(connection.execute("PRAGMA user_version").fetchone()[0])

    def get_setting(
        self, key: str, default: str | None = None, user_id: int = 1
    ) -> str | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE user_id = ? AND key = ?",
                (user_id, key),
            ).fetchone()
        return str(row["value"]) if row else default

    def set_setting(self, key: str, value: str, user_id: int = 1) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO settings (user_id, key, value, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (user_id, key, value, _utc_now()),
            )

    def create_memory(
        self,
        memory_type: str,
        content: str,
        source: str = "manual_user_entry",
        sensitivity: str = "normal",
        user_id: int = 1,
    ) -> MemoryRecord:
        now = _utc_now()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO memories (
                    user_id, memory_type, content, source, confirmation_status,
                    sensitivity, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'approved', ?, ?, ?)
                """,
                (user_id, memory_type, content, source, sensitivity, now, now),
            )
            memory_id = int(cursor.lastrowid)
        memory = self.get_memory(memory_id, user_id)
        if memory is None:  # pragma: no cover - defensive against external DB mutation
            raise DatabaseError("The saved memory could not be reloaded.")
        return memory

    def get_memory(self, memory_id: int, user_id: int = 1) -> MemoryRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM memories WHERE id = ? AND user_id = ?",
                (memory_id, user_id),
            ).fetchone()
        return self._memory_from_row(row) if row else None

    def list_memories(self, user_id: int = 1) -> list[MemoryRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM memories
                WHERE user_id = ? AND confirmation_status = 'approved'
                ORDER BY updated_at DESC, id DESC
                """,
                (user_id,),
            ).fetchall()
        return [self._memory_from_row(row) for row in rows]

    def update_memory(
        self,
        memory_id: int,
        content: str,
        memory_type: str | None = None,
        source: str = "user_correction",
        user_id: int = 1,
    ) -> MemoryRecord | None:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE memories SET
                    content = ?,
                    memory_type = COALESCE(?, memory_type),
                    source = ?,
                    updated_at = ?
                WHERE id = ? AND user_id = ? AND confirmation_status = 'approved'
                """,
                (content, memory_type, source, _utc_now(), memory_id, user_id),
            )
            changed = cursor.rowcount
        return self.get_memory(memory_id, user_id) if changed else None

    def delete_memory(self, memory_id: int, user_id: int = 1) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM memories WHERE id = ? AND user_id = ?",
                (memory_id, user_id),
            )
            return cursor.rowcount > 0

    def delete_all_memories(self, user_id: int = 1) -> int:
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM memories WHERE user_id = ?", (user_id,)
            )
            return cursor.rowcount

    def search_memories(
        self, query: str, limit: int = 5, user_id: int = 1
    ) -> list[MemoryRecord]:
        tokens = [
            token.lower() for token in re.findall(r"[^\W_]{2,}", query, re.UNICODE)
        ]
        if not tokens or limit <= 0:
            return []
        with self._connection() as connection:
            rows: Sequence[sqlite3.Row]
            if self.fts_enabled:
                expression = " OR ".join(f'"{token}"*' for token in tokens[:12])
                try:
                    rows = connection.execute(
                        """
                        SELECT memories.* FROM memory_fts
                        JOIN memories ON memories.id = memory_fts.rowid
                        WHERE memory_fts MATCH ?
                          AND memories.user_id = ?
                          AND memories.confirmation_status = 'approved'
                        ORDER BY bm25(memory_fts), memories.updated_at DESC
                        LIMIT ?
                        """,
                        (expression, user_id, limit),
                    ).fetchall()
                except sqlite3.OperationalError:
                    rows = []
            else:
                rows = []
            if not rows:
                clauses = " OR ".join("lower(content) LIKE ?" for _ in tokens[:12])
                rows = connection.execute(
                    f"""
                    SELECT * FROM memories
                    WHERE user_id = ? AND confirmation_status = 'approved'
                      AND ({clauses})
                    ORDER BY updated_at DESC LIMIT ?
                    """,
                    (user_id, *[f"%{token}%" for token in tokens[:12]], limit),
                ).fetchall()
        return [self._memory_from_row(row) for row in rows]

    def mark_memories_accessed(
        self, memory_ids: Sequence[int], user_id: int = 1
    ) -> None:
        if not memory_ids:
            return
        placeholders = ",".join("?" for _ in memory_ids)
        with self._connection() as connection:
            connection.execute(
                f"""
                UPDATE memories SET last_accessed_at = ?
                WHERE user_id = ? AND id IN ({placeholders})
                """,
                (_utc_now(), user_id, *memory_ids),
            )

    def create_conversation(
        self, title: str = "New conversation", user_id: int = 1
    ) -> int:
        now = _utc_now()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO conversations (user_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, title, now, now),
            )
            return int(cursor.lastrowid)

    def get_conversation(
        self, conversation_id: int, user_id: int = 1
    ) -> ConversationRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            ).fetchone()
        return self._conversation_from_row(row) if row else None

    def list_conversations(self, user_id: int = 1) -> list[ConversationRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM conversations WHERE user_id = ?
                ORDER BY updated_at DESC, id DESC
                """,
                (user_id,),
            ).fetchall()
        return [self._conversation_from_row(row) for row in rows]

    def update_conversation_title(
        self, conversation_id: int, title: str, user_id: int = 1
    ) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE conversations SET title = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (title, _utc_now(), conversation_id, user_id),
            )
            return cursor.rowcount > 0

    def add_messages(
        self,
        conversation_id: int,
        messages: Sequence[tuple[str, str]],
        user_id: int = 1,
    ) -> None:
        if not messages:
            return
        now = _utc_now()
        with self._connection() as connection:
            exists = connection.execute(
                "SELECT 1 FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            ).fetchone()
            if not exists:
                raise DatabaseError("Conversation does not exist.")
            connection.executemany(
                """
                INSERT INTO messages (conversation_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                [(conversation_id, role, content, now) for role, content in messages],
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )

    def list_messages(
        self, conversation_id: int, user_id: int = 1
    ) -> list[MessageRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT messages.* FROM messages
                JOIN conversations ON conversations.id = messages.conversation_id
                WHERE messages.conversation_id = ? AND conversations.user_id = ?
                ORDER BY messages.id
                """,
                (conversation_id, user_id),
            ).fetchall()
        return [self._message_from_row(row) for row in rows]

    def delete_conversation(self, conversation_id: int, user_id: int = 1) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            )
            return cursor.rowcount > 0

    def delete_all_conversations(self, user_id: int = 1) -> int:
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM conversations WHERE user_id = ?", (user_id,)
            )
            return cursor.rowcount

    @staticmethod
    def _memory_from_row(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(**dict(row))

    @staticmethod
    def _conversation_from_row(row: sqlite3.Row) -> ConversationRecord:
        return ConversationRecord(**dict(row))

    @staticmethod
    def _message_from_row(row: sqlite3.Row) -> MessageRecord:
        return MessageRecord(**dict(row))
