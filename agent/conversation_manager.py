"""Bounded, in-memory multi-turn conversation history."""

from __future__ import annotations

from dataclasses import dataclass

from models.base_model import Message


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    user: str
    assistant: str


class ConversationManager:
    """Keep complete recent user/assistant turns in RAM only."""

    def __init__(self, max_turns: int = 10) -> None:
        if max_turns <= 0:
            raise ValueError("max_turns must be greater than zero.")
        self.max_turns = max_turns
        self._turns: list[ConversationTurn] = []

    @property
    def turns(self) -> tuple[ConversationTurn, ...]:
        """Return an immutable snapshot of current history."""

        return tuple(self._turns)

    def add_turn(self, user_message: str, assistant_message: str) -> None:
        if not user_message.strip() or not assistant_message.strip():
            raise ValueError("Conversation turns cannot contain empty messages.")
        self._turns.append(
            ConversationTurn(
                user=user_message.strip(), assistant=assistant_message.strip()
            )
        )
        if len(self._turns) > self.max_turns:
            self._turns = self._turns[-self.max_turns :]

    def build_messages(self, system_prompt: str, user_message: str) -> list[Message]:
        messages: list[Message] = [{"role": "system", "content": system_prompt}]
        for turn in self._turns:
            messages.append({"role": "user", "content": turn.user})
            messages.append({"role": "assistant", "content": turn.assistant})
        messages.append({"role": "user", "content": user_message.strip()})
        return messages

    def reset(self) -> None:
        self._turns.clear()

    def load_turns(self, turns: list[tuple[str, str]]) -> None:
        """Replace active context from a previously saved conversation."""

        loaded: list[ConversationTurn] = []
        for user_message, assistant_message in turns:
            if not user_message.strip() or not assistant_message.strip():
                continue
            loaded.append(
                ConversationTurn(user_message.strip(), assistant_message.strip())
            )
        self._turns = loaded[-self.max_turns :]
