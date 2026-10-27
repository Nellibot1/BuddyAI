"""Tests for versioned SQLite persistence."""

from pathlib import Path

from memory.database import SCHEMA_VERSION, Database


def test_database_initialization_and_default_settings(tmp_path: Path) -> None:
    database = Database(tmp_path / "buddy.sqlite3")

    assert database.schema_version() == SCHEMA_VERSION
    assert database.get_setting("personality") == "chill"
    assert database.get_setting("memory_enabled") == "true"
    assert database.path.exists()


def test_memory_crud_survives_database_restart(tmp_path: Path) -> None:
    path = tmp_path / "buddy.sqlite3"
    first = Database(path)
    created = first.create_memory("interest", "The user enjoys Minecraft.")

    restarted = Database(path)
    loaded = restarted.get_memory(created.id)
    assert loaded is not None
    assert loaded.content == "The user enjoys Minecraft."

    updated = restarted.update_memory(
        created.id, "The user enjoys creative Minecraft builds.", "interest"
    )
    assert updated is not None
    assert "creative" in updated.content
    assert restarted.delete_memory(created.id)
    assert restarted.list_memories() == []


def test_conversation_messages_persist_and_cascade_on_delete(tmp_path: Path) -> None:
    path = tmp_path / "buddy.sqlite3"
    database = Database(path)
    conversation_id = database.create_conversation("A saved chat")
    database.add_messages(
        conversation_id,
        [("user", "Hello"), ("assistant", "Hi there")],
    )

    restarted = Database(path)
    assert [message.role for message in restarted.list_messages(conversation_id)] == [
        "user",
        "assistant",
    ]
    assert restarted.delete_conversation(conversation_id)
    assert restarted.list_messages(conversation_id) == []


def test_settings_persist(tmp_path: Path) -> None:
    path = tmp_path / "buddy.sqlite3"
    database = Database(path)
    database.set_setting("personality", "thoughtful")

    assert Database(path).get_setting("personality") == "thoughtful"
