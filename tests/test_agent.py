"""Tests for the BuddyAgent controller and in-memory history."""

from __future__ import annotations

import pytest

from agent.buddy_agent import BuddyAgent
from agent.prompt_builder import AgentContext
from models.base_model import BaseModel, Message, ModelError


class MockModel(BaseModel):
    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = responses or ["Mock response"]
        self.calls: list[list[Message]] = []

    def generate(self, messages: list[Message]) -> str:
        self.calls.append(messages)
        return self.responses[len(self.calls) - 1]


class FailingModel(BaseModel):
    def generate(self, messages: list[Message]) -> str:
        raise ModelError("local server unavailable")


def test_agent_uses_model_interface_and_preserves_roles() -> None:
    model = MockModel(["Hello!", "Still here."])
    agent = BuddyAgent(model, personality="chill")

    assert agent.respond("Hi") == "Hello!"
    assert agent.respond("Are you there?") == "Still here."

    assert [message["role"] for message in model.calls[0]] == ["system", "user"]
    assert [message["role"] for message in model.calls[1]] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert model.calls[1][1]["content"] == "Hi"
    assert model.calls[1][2]["content"] == "Hello!"


def test_history_retains_only_complete_recent_turns() -> None:
    model = MockModel(["a1", "a2", "a3"])
    agent = BuddyAgent(model, history_turns=2)

    agent.respond("u1")
    agent.respond("u2")
    agent.respond("u3")

    assert [(turn.user, turn.assistant) for turn in agent.conversation.turns] == [
        ("u2", "a2"),
        ("u3", "a3"),
    ]


def test_reset_removes_conversation_history() -> None:
    model = MockModel(["First answer", "New answer"])
    agent = BuddyAgent(model)
    agent.respond("First conversation")

    agent.reset_conversation()
    agent.respond("Fresh start")

    assert [message["role"] for message in model.calls[1]] == ["system", "user"]
    assert len(agent.conversation.turns) == 1


def test_failed_request_does_not_change_history() -> None:
    agent = BuddyAgent(FailingModel())

    with pytest.raises(ModelError, match="unavailable"):
        agent.respond("Hello?")

    assert agent.conversation.turns == ()


def test_empty_user_message_is_rejected_without_calling_model() -> None:
    model = MockModel()
    agent = BuddyAgent(model)

    with pytest.raises(ValueError, match="non-empty"):
        agent.respond("   ")

    assert model.calls == []


def test_optional_future_context_is_explicit_and_not_persisted() -> None:
    model = MockModel(["Context response", "Normal response"])
    agent = BuddyAgent(model)
    context = AgentContext(
        personal_memories=("The user prefers tea.",),
        facial_expression_cue="possibly smiling",
        conversation_strategy="gently explore the topic",
    )

    agent.respond("Hello", context=context)
    agent.respond("Next")

    contextual_prompt = model.calls[0][0]["content"]
    contextual_user_message = model.calls[0][1]["content"]
    normal_user_message = model.calls[1][-1]["content"]
    assert "prefers tea" in contextual_user_message
    assert "untrusted data" in contextual_user_message
    assert "prefers tea" not in contextual_prompt
    assert "possibly smiling" in contextual_prompt
    assert "uncertain" in contextual_prompt.lower()
    assert "gently explore" in contextual_prompt
    assert "prefers tea" not in normal_user_message
