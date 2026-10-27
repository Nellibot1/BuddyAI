"""Local-LLM extraction of automatically stored memory candidates."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from models.base_model import BaseModel, Message

ALLOWED_MEMORY_TYPES = {"preference", "profile", "interest", "episodic"}
ALLOWED_SOURCES = {"explicit_user_statement", "user_request"}
SENSITIVE_PATTERNS = (
    "password",
    "passcode",
    "credit card",
    "social security",
    "bank account",
    "private key",
    "api key",
    "medical diagnosis",
)


class MemoryExtractionError(ValueError):
    """Raised when model output is malformed or unsafe to propose."""


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    memory_type: str
    content: str
    source: str
    confidence: float


class MemoryExtractor:
    """Ask the configured local model for strict, validated JSON candidates."""

    def __init__(self, model: BaseModel, prompt_path: Path | None = None) -> None:
        path = prompt_path or (
            Path(__file__).resolve().parent.parent / "prompts" / "memory_extraction.txt"
        )
        self._prompt = path.read_text(encoding="utf-8").strip()
        self._model = model

    def extract(self, user_message: str) -> list[MemoryCandidate]:
        messages: list[Message] = [
            {"role": "system", "content": self._prompt},
            {"role": "user", "content": user_message.strip()},
        ]
        return self.parse(self._model.generate(messages))

    @classmethod
    def parse(cls, raw_output: str) -> list[MemoryCandidate]:
        text = raw_output.strip()
        fenced = re.fullmatch(
            r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE
        )
        if fenced:
            text = fenced.group(1)
        try:
            data: Any = json.loads(text)
        except json.JSONDecodeError as exc:
            raise MemoryExtractionError(
                "Memory extraction returned invalid JSON."
            ) from exc
        if not isinstance(data, dict) or not isinstance(
            data.get("memory_candidates"), list
        ):
            raise MemoryExtractionError("Memory extraction JSON has an invalid schema.")

        candidates: list[MemoryCandidate] = []
        for item in data["memory_candidates"]:
            if not isinstance(item, dict):
                raise MemoryExtractionError("Each memory candidate must be an object.")
            candidate = cls._validate_candidate(item)
            if candidate is not None:
                candidates.append(candidate)
        return candidates[:5]

    @staticmethod
    def _validate_candidate(item: dict[str, Any]) -> MemoryCandidate | None:
        memory_type = item.get("type")
        content = item.get("content")
        source = item.get("source")
        confidence = item.get("confidence")
        if memory_type not in ALLOWED_MEMORY_TYPES:
            raise MemoryExtractionError("Unsupported memory type.")
        if (
            not isinstance(content, str)
            or not content.strip()
            or len(content.strip()) > 500
        ):
            raise MemoryExtractionError("Memory content must be 1 to 500 characters.")
        if source not in ALLOWED_SOURCES:
            raise MemoryExtractionError(
                "Memory source must describe an explicit user statement."
            )
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            raise MemoryExtractionError("Memory confidence must be numeric.")
        if not 0 <= float(confidence) <= 1:
            raise MemoryExtractionError("Memory confidence must be between 0 and 1.")
        normalized = content.casefold()
        if any(pattern in normalized for pattern in SENSITIVE_PATTERNS):
            return None
        return MemoryCandidate(
            memory_type=memory_type,
            content=content.strip(),
            source=source,
            confidence=float(confidence),
        )
