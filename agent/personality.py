"""Personality presets layered on BuddyAI's core behavior."""

from __future__ import annotations

PERSONALITY_PRESETS: dict[str, str] = {
    "chill": (
        "Use a relaxed, casual, and easygoing tone. Keep the conversation light "
        "and comfortable without sounding dismissive."
    ),
    "playful": (
        "Be energetic and lighthearted. Use gentle humor when it fits, but never "
        "joke at the user's expense or make light of serious concerns."
    ),
    "supportive": (
        "Be especially warm, attentive, patient, and emotionally considerate. "
        "Acknowledge difficulties without diagnosing or overinterpreting them."
    ),
    "thoughtful": (
        "Be curious and reflective, with an interest in meaningful conversation. "
        "Offer considered observations while staying concise and approachable."
    ),
}


class InvalidPersonalityError(ValueError):
    """Raised when a requested personality preset does not exist."""


class PersonalityManager:
    """Validate and expose BuddyAI's current personality preset."""

    def __init__(self, personality: str = "chill") -> None:
        self._name = ""
        self.set(personality)

    @property
    def name(self) -> str:
        return self._name

    @property
    def instructions(self) -> str:
        return PERSONALITY_PRESETS[self._name]

    @property
    def available(self) -> tuple[str, ...]:
        return tuple(PERSONALITY_PRESETS)

    def set(self, personality: str) -> None:
        normalized = personality.strip().lower()
        if normalized not in PERSONALITY_PRESETS:
            choices = ", ".join(PERSONALITY_PRESETS)
            raise InvalidPersonalityError(
                f"Unknown personality {personality!r}. Choose one of: {choices}."
            )
        self._name = normalized
