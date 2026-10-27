"""Configuration for BuddyAI's local model runtime."""

from __future__ import annotations

import ipaddress
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

RUNTIME_DEFAULTS: dict[str, dict[str, str]] = {
    "ollama": {
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "qwen2.5:3b",
    },
    "llama.cpp": {
        "base_url": "http://127.0.0.1:8080/v1",
        "model": "local-model",
    },
    "lm-studio": {
        "base_url": "http://127.0.0.1:1234/v1",
        "model": "local-model",
    },
}

RUNTIME_ALIASES = {
    "llamacpp": "llama.cpp",
    "llama_cpp": "llama.cpp",
    "lmstudio": "lm-studio",
    "lm_studio": "lm-studio",
}


class ConfigurationError(ValueError):
    """Raised when BuddyAI receives an unsafe or invalid configuration."""


def default_data_dir() -> Path:
    """Return a platform-appropriate directory outside the source tree."""

    configured = os.getenv("BUDDY_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "BuddyAI"
    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "BuddyAI"
    base = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "buddy-ai"


def default_database_path() -> Path:
    """Return the configured local SQLite database path."""

    return default_data_dir() / "buddyai.sqlite3"


def normalize_runtime(value: str) -> str:
    """Return a canonical runtime name or raise for an unsupported runtime."""

    runtime = value.strip().lower()
    runtime = RUNTIME_ALIASES.get(runtime, runtime)
    if runtime not in RUNTIME_DEFAULTS:
        choices = ", ".join(RUNTIME_DEFAULTS)
        raise ConfigurationError(
            f"Unsupported runtime {value!r}. Choose one of: {choices}."
        )
    return runtime


def validate_local_base_url(base_url: str) -> str:
    """Validate and normalize an HTTP URL that points only to loopback.

    BuddyAI deliberately rejects remote hosts in Phase 1 so conversation text
    cannot be sent to a cloud endpoint through accidental configuration.
    """

    url = base_url.strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme != "http":
        raise ConfigurationError("The model endpoint must use local HTTP.")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ConfigurationError("The model endpoint must have a valid local host.")
    if parsed.query or parsed.fragment:
        raise ConfigurationError(
            "The model endpoint cannot contain a query or fragment."
        )

    host = parsed.hostname.lower()
    if host != "localhost":
        try:
            if not ipaddress.ip_address(host).is_loopback:
                raise ConfigurationError(
                    "Remote model endpoints are disabled; use localhost or a loopback IP."
                )
        except ValueError as exc:
            raise ConfigurationError(
                "Remote model endpoints are disabled; use localhost or a loopback IP."
            ) from exc

    # Accessing .port also catches malformed/out-of-range port values.
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ConfigurationError(f"Invalid model endpoint port: {exc}") from exc
    return url


def _read_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero.")
    return value


def _read_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number.") from exc
    return value


@dataclass(frozen=True, slots=True)
class ModelConfig:
    """Settings shared by all OpenAI-compatible local runtimes."""

    runtime: str = "ollama"
    base_url: str | None = None
    model: str | None = None
    temperature: float = 0.7
    max_tokens: int = 350
    timeout_seconds: float = 120.0
    history_turns: int = 10

    def __post_init__(self) -> None:
        runtime = normalize_runtime(self.runtime)
        object.__setattr__(self, "runtime", runtime)
        base_url = self.base_url or RUNTIME_DEFAULTS[runtime]["base_url"]
        model = (
            self.model if self.model is not None else RUNTIME_DEFAULTS[runtime]["model"]
        )
        object.__setattr__(self, "base_url", validate_local_base_url(base_url))
        object.__setattr__(self, "model", model)
        if not model.strip():
            raise ConfigurationError("A model identifier is required.")
        if not math.isfinite(self.temperature) or not 0.0 <= self.temperature <= 2.0:
            raise ConfigurationError("Temperature must be between 0 and 2.")
        if (
            self.max_tokens <= 0
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
            or self.history_turns <= 0
        ):
            raise ConfigurationError(
                "max_tokens, timeout_seconds, and history_turns must be positive."
            )

    @classmethod
    def from_env(cls) -> ModelConfig:
        """Build configuration from ``BUDDY_*`` environment variables."""

        runtime = normalize_runtime(os.getenv("BUDDY_RUNTIME", "ollama"))
        defaults = RUNTIME_DEFAULTS[runtime]
        return cls(
            runtime=runtime,
            base_url=os.getenv("BUDDY_BASE_URL", defaults["base_url"]),
            model=os.getenv("BUDDY_MODEL", defaults["model"]),
            temperature=_read_float("BUDDY_TEMPERATURE", 0.7),
            max_tokens=_read_int("BUDDY_MAX_TOKENS", 350),
            timeout_seconds=_read_float("BUDDY_TIMEOUT_SECONDS", 120.0),
            history_turns=_read_int("BUDDY_HISTORY_TURNS", 10),
        )
