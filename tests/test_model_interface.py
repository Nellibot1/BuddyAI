"""Tests for model configuration and the local HTTP adapter."""

from __future__ import annotations

import json
from typing import Self
from urllib.error import URLError

import pytest

from config import ConfigurationError, ModelConfig, validate_local_base_url
from models.base_model import BaseModel, ModelError
from models.local_model import LocalOpenAIModel
from models.model_factory import create_model


class FakeResponse:
    def __init__(self, data: dict[str, object]) -> None:
        self._data = json.dumps(data).encode("utf-8")

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._data


def test_model_factory_returns_common_interface() -> None:
    model = create_model(ModelConfig())

    assert isinstance(model, BaseModel)
    assert isinstance(model, LocalOpenAIModel)


def test_direct_runtime_selection_uses_matching_defaults() -> None:
    config = ModelConfig(runtime="llama.cpp")

    assert config.base_url == "http://127.0.0.1:8080/v1"
    assert config.model == "local-model"


def test_model_configuration_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUDDY_RUNTIME", "lmstudio")
    monkeypatch.setenv("BUDDY_MODEL", "gemma-local")
    monkeypatch.setenv("BUDDY_TEMPERATURE", "0.5")
    monkeypatch.setenv("BUDDY_HISTORY_TURNS", "7")

    config = ModelConfig.from_env()

    assert config.runtime == "lm-studio"
    assert config.base_url == "http://127.0.0.1:1234/v1"
    assert config.model == "gemma-local"
    assert config.temperature == 0.5
    assert config.history_turns == 7


@pytest.mark.parametrize(
    "url",
    [
        "https://api.example.com/v1",
        "http://api.example.com/v1",
        "http://192.168.1.20:8080/v1",
        "file:///tmp/model",
        "http://localhost.evil.example/v1",
    ],
)
def test_remote_or_unsafe_endpoints_are_rejected(url: str) -> None:
    with pytest.raises(ConfigurationError):
        validate_local_base_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:11434/v1/",
        "http://127.0.0.1:8080/v1",
        "http://127.1.2.3:1234/v1",
        "http://[::1]:8080/v1",
    ],
)
def test_loopback_endpoints_are_accepted(url: str) -> None:
    assert validate_local_base_url(url).endswith("/v1")


def test_local_model_sends_openai_compatible_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request: object, timeout: float) -> FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse(
            {"choices": [{"message": {"role": "assistant", "content": " Hi! "}}]}
        )

    monkeypatch.setattr("models.local_model._open_local_request", fake_urlopen)
    model = LocalOpenAIModel(ModelConfig(model="test-model", max_tokens=123))
    messages = [{"role": "user", "content": "Hello"}]

    assert model.generate(messages) == "Hi!"
    request = captured["request"]
    payload = json.loads(request.data)
    assert request.full_url == "http://127.0.0.1:11434/v1/chat/completions"
    assert payload["model"] == "test-model"
    assert payload["messages"] == messages
    assert payload["max_tokens"] == 123
    assert payload["stream"] is False


def test_failed_model_connection_has_helpful_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise URLError("connection refused")

    monkeypatch.setattr("models.local_model._open_local_request", fail)
    model = LocalOpenAIModel(ModelConfig())

    with pytest.raises(ModelError, match="Could not reach.*ollama"):
        model.generate([{"role": "user", "content": "Hello"}])


def test_invalid_server_response_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "models.local_model._open_local_request",
        lambda *args, **kwargs: FakeResponse({"unexpected": "shape"}),
    )
    model = LocalOpenAIModel(ModelConfig())

    with pytest.raises(ModelError, match="invalid response"):
        model.generate([{"role": "user", "content": "Hello"}])
