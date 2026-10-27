"""Runtime-independent language model contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal, TypedDict


class Message(TypedDict):
    """A single OpenAI-style chat message."""

    role: Literal["system", "user", "assistant"]
    content: str


class ModelError(RuntimeError):
    """User-facing error raised when local model inference fails."""


class BaseModel(ABC):
    """Common interface implemented by every BuddyAI model adapter."""

    @abstractmethod
    def generate(self, messages: list[Message]) -> str:
        """Generate one assistant response for a chat message sequence."""
