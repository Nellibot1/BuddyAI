"""Integration tests for controller personalization and persistence settings."""

from pathlib import Path

from agent.application_controller import BuddyApplication
from config import ModelConfig
from memory.database import Database
from models.base_model import BaseModel, Message


class RecordingModel(BaseModel):
    def __init__(self, response: str = "Generated locally") -> None:
        self.response = response
        self.calls: list[list[Message]] = []

    def generate(self, messages: list[Message]) -> str:
        self.calls.append(messages)
        return self.response


class SequenceModel(BaseModel):
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)

    def generate(self, messages: list[Message]) -> str:
        return next(self.responses)


def make_app(path: Path, model: RecordingModel | None = None) -> BuddyApplication:
    return BuddyApplication(model or RecordingModel(), ModelConfig(), Database(path))


def test_saved_memory_is_used_as_untrusted_user_context(tmp_path: Path) -> None:
    model = RecordingModel()
    app = make_app(tmp_path / "buddy.sqlite3", model)
    app.database.create_memory("interest", "The user enjoys Minecraft.")

    app.send_message("Any ideas for this evening?")

    system_message = model.calls[0][0]["content"]
    current_user_message = model.calls[0][-1]["content"]
    assert "Minecraft" not in system_message
    assert "Minecraft" in current_user_message
    assert "untrusted data" in current_user_message


def test_conversation_can_be_reopened_after_restart(tmp_path: Path) -> None:
    path = tmp_path / "buddy.sqlite3"
    first = make_app(path)
    first.send_message("Tell me something interesting")
    conversation_id = first.current_conversation_id
    assert conversation_id is not None

    restarted = make_app(path)
    history = restarted.open_conversation(conversation_id)

    assert history == [("Tell me something interesting", "Generated locally")]
    assert restarted.agent.conversation.turns[0].user == "Tell me something interesting"


def test_personality_setting_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "buddy.sqlite3"
    first = make_app(path)
    first.set_personality("supportive")

    assert make_app(path).personality_name == "supportive"


def test_history_disabled_prevents_new_message_writes(tmp_path: Path) -> None:
    path = tmp_path / "buddy.sqlite3"
    app = make_app(path)
    app.set_history_enabled(False)

    app.send_message("This should stay in RAM")

    assert app.chat_history == [("This should stay in RAM", "Generated locally")]
    assert app.database.list_conversations() == []


def test_deleted_memory_is_not_used_again(tmp_path: Path) -> None:
    model = RecordingModel()
    app = make_app(tmp_path / "buddy.sqlite3", model)
    saved = app.database.create_memory("interest", "The user enjoys pottery.")
    app.delete_memory(saved.id)

    app.send_message("What could I do?")

    assert "pottery" not in model.calls[0][-1]["content"].casefold()


def test_interaction_automatically_creates_memory(tmp_path: Path) -> None:
    model = SequenceModel(
        [
            "That sounds fun!",
            '{"memory_candidates": [{"type": "interest", "content": "The user enjoys Minecraft.", "source": "explicit_user_statement", "confidence": 0.96}]}',
        ]
    )
    app = BuddyApplication(model, ModelConfig(), Database(tmp_path / "buddy.sqlite3"))

    result = app.send_message("I enjoy Minecraft.")

    assert result.memories_saved == 1
    assert app.list_memories()[0].content == "The user enjoys Minecraft."
