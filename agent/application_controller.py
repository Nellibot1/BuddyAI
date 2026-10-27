"""Thread-safe application service shared by the GUI and future interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from agent.buddy_agent import BuddyAgent
from agent.prompt_builder import AgentContext
from config import ModelConfig
from memory.database import Database, DatabaseError, MemoryRecord
from memory.memory_extractor import MemoryExtractionError, MemoryExtractor
from memory.memory_manager import MemoryManager
from models.base_model import BaseModel, ModelError


@dataclass(frozen=True, slots=True)
class ChatResult:
    response: str
    memories_saved: int
    warning: str | None = None


class BuddyApplication:
    """Own one active agent session and synchronize it with local persistence."""

    def __init__(
        self,
        model: BaseModel,
        model_config: ModelConfig,
        database: Database,
        memory_manager: MemoryManager | None = None,
        user_id: int = 1,
    ) -> None:
        self.model = model
        self.model_config = model_config
        self.database = database
        self.user_id = user_id
        self._lock = RLock()
        personality = database.get_setting("personality", "chill", user_id) or "chill"
        self.agent = BuddyAgent(
            model, personality=personality, history_turns=model_config.history_turns
        )
        self.memory_manager = memory_manager or MemoryManager(
            database, MemoryExtractor(model), user_id=user_id
        )
        self.current_conversation_id: int | None = None
        self._chat_history: list[tuple[str, str]] = []

    @property
    def memory_enabled(self) -> bool:
        return self.memory_manager.enabled

    @property
    def history_enabled(self) -> bool:
        return (
            self.database.get_setting("history_enabled", "true", self.user_id) == "true"
        )

    @property
    def buddy_name(self) -> str:
        return self.database.get_setting("buddy_name", "Buddy", self.user_id) or "Buddy"

    @property
    def personality_name(self) -> str:
        return self.agent.personality_name

    @property
    def chat_history(self) -> list[tuple[str, str]]:
        with self._lock:
            return list(self._chat_history)

    def send_message(self, user_message: str) -> ChatResult:
        clean_message = user_message.strip()
        if not clean_message:
            raise ValueError("Please enter a message.")
        with self._lock:
            memories = self.memory_manager.retrieve_relevant(clean_message, limit=5)
            context = AgentContext(
                personal_memories=tuple(memory.content for memory in memories)
            )
            response = self.agent.respond(clean_message, context=context)
            self._chat_history.append((clean_message, response))
            warnings: list[str] = []
            memories_saved = 0

            if self.history_enabled:
                try:
                    is_new = self.current_conversation_id is None
                    if is_new:
                        self.current_conversation_id = (
                            self.database.create_conversation(
                                self._title_from_message(clean_message), self.user_id
                            )
                        )
                    self.database.add_messages(
                        self.current_conversation_id,
                        [("user", clean_message), ("assistant", response)],
                        self.user_id,
                    )
                except DatabaseError as exc:
                    warnings.append(str(exc))

            if self.memory_enabled:
                try:
                    memories_saved = len(
                        self.memory_manager.capture_from_message(clean_message)
                    )
                except (DatabaseError, MemoryExtractionError, ModelError) as exc:
                    warnings.append(f"Automatic memory capture was skipped: {exc}")

            return ChatResult(
                response=response,
                memories_saved=memories_saved,
                warning=" ".join(warnings) or None,
            )

    def new_conversation(self) -> None:
        with self._lock:
            self.current_conversation_id = None
            self._chat_history.clear()
            self.agent.reset_conversation()

    def clear_current_conversation(self) -> None:
        """Delete the active saved conversation, then start an empty session."""

        with self._lock:
            if self.current_conversation_id is not None:
                self.database.delete_conversation(
                    self.current_conversation_id, self.user_id
                )
            self.new_conversation()

    def open_conversation(self, conversation_id: int) -> list[tuple[str, str]]:
        with self._lock:
            conversation = self.database.get_conversation(conversation_id, self.user_id)
            if conversation is None:
                raise KeyError("Conversation no longer exists.")
            messages = self.database.list_messages(conversation_id, self.user_id)
            turns: list[tuple[str, str]] = []
            index = 0
            while index + 1 < len(messages):
                user_message, assistant_message = messages[index], messages[index + 1]
                if (
                    user_message.role == "user"
                    and assistant_message.role == "assistant"
                ):
                    turns.append((user_message.content, assistant_message.content))
                    index += 2
                else:
                    index += 1
            self.current_conversation_id = conversation_id
            self._chat_history = turns
            self.agent.conversation.load_turns(turns)
            return list(turns)

    def conversation_choices(self) -> list[tuple[str, int]]:
        return [
            (f"{conversation.title} · {conversation.updated_at[:10]}", conversation.id)
            for conversation in self.database.list_conversations(self.user_id)
        ]

    def set_personality(self, name: str) -> None:
        with self._lock:
            self.agent.set_personality(name)
            self.database.set_setting(
                "personality", self.agent.personality_name, self.user_id
            )

    def set_buddy_name(self, name: str) -> str:
        clean_name = name.strip()
        if not clean_name or len(clean_name) > 40:
            raise ValueError("Buddy's display name must be 1 to 40 characters.")
        self.database.set_setting("buddy_name", clean_name, self.user_id)
        return clean_name

    def set_memory_enabled(self, enabled: bool) -> None:
        with self._lock:
            self.memory_manager.set_enabled(enabled)

    def set_history_enabled(self, enabled: bool) -> None:
        with self._lock:
            self.database.set_setting(
                "history_enabled", str(bool(enabled)).lower(), self.user_id
            )
            # Avoid attaching a partially persisted continuation to an old record.
            self.new_conversation()

    def list_memories(self) -> list[MemoryRecord]:
        return self.database.list_memories(self.user_id)

    def delete_memory(self, memory_id: int) -> bool:
        with self._lock:
            return self.database.delete_memory(memory_id, self.user_id)

    def delete_all_memories(self) -> int:
        with self._lock:
            return self.database.delete_all_memories(self.user_id)

    def delete_all_conversations(self) -> int:
        with self._lock:
            count = self.database.delete_all_conversations(self.user_id)
            self.new_conversation()
            return count

    @staticmethod
    def _title_from_message(message: str) -> str:
        title = " ".join(message.split())
        return title if len(title) <= 48 else f"{title[:45]}..."
