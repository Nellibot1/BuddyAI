"""State synchronization checks for the controller consumed by Gradio."""

from pathlib import Path

from agent.application_controller import BuddyApplication
from config import ModelConfig
from memory.database import Database
from models.base_model import BaseModel, Message
from ui.gradio_app import build_gradio_app


class EchoModel(BaseModel):
    def generate(self, messages: list[Message]) -> str:
        return f"Reply to: {messages[-1]['content'].splitlines()[-1]}"


def test_ui_builder_is_exposed() -> None:
    assert callable(build_gradio_app)


def test_gradio_layout_builds_with_local_controller(tmp_path: Path) -> None:
    app = BuddyApplication(
        EchoModel(), ModelConfig(), Database(tmp_path / "buddy.sqlite3")
    )

    demo = build_gradio_app(app)

    assert len(demo.blocks) >= 40


def test_switching_conversations_replaces_agent_and_ui_state(tmp_path: Path) -> None:
    app = BuddyApplication(
        EchoModel(), ModelConfig(), Database(tmp_path / "buddy.sqlite3")
    )
    app.send_message("First chat")
    first_id = app.current_conversation_id
    app.new_conversation()
    app.send_message("Second chat")
    second_id = app.current_conversation_id
    assert first_id is not None and second_id is not None and first_id != second_id

    visible_history = app.open_conversation(first_id)

    assert visible_history == app.chat_history
    assert app.agent.conversation.turns[-1].user == "First chat"
    assert all("Second chat" not in turn.user for turn in app.agent.conversation.turns)
