"""Tests for stable prompt construction and personality selection."""

from __future__ import annotations

import pytest

from agent.personality import (
    PERSONALITY_PRESETS,
    InvalidPersonalityError,
    PersonalityManager,
)
from agent.prompt_builder import PromptBuilder


@pytest.mark.parametrize("name", PERSONALITY_PRESETS)
def test_all_personality_presets_can_be_selected(name: str) -> None:
    manager = PersonalityManager(name.upper())

    assert manager.name == name
    assert manager.instructions == PERSONALITY_PRESETS[name]


def test_invalid_personality_is_rejected() -> None:
    with pytest.raises(InvalidPersonalityError, match="Unknown personality"):
        PersonalityManager("dramatic")


def test_system_prompt_combines_core_boundaries_and_preset() -> None:
    manager = PersonalityManager("supportive")
    prompt = PromptBuilder().build(manager.name, manager.instructions)

    assert "Never claim to be human" in prompt
    assert "Do not encourage emotional dependency" in prompt
    assert "English or German" in prompt
    assert "Current personality preset: Supportive" in prompt
    assert manager.instructions in prompt


def test_prompt_builder_reuses_stable_prompt() -> None:
    manager = PersonalityManager("thoughtful")
    builder = PromptBuilder()

    first = builder.build(manager.name, manager.instructions)
    second = builder.build(manager.name, manager.instructions)

    assert first is second
