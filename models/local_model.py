"""OpenAI-compatible adapter for local inference servers."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from config import ModelConfig
from models.base_model import BaseModel, Message, ModelError


class _NoRedirectHandler(HTTPRedirectHandler):
    """Prevent a local server from redirecting a request to a remote host."""

    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


_LOCAL_OPENER = build_opener(ProxyHandler({}), _NoRedirectHandler())


def _open_local_request(request: Request, timeout: float) -> Any:
    """Open directly, with environment proxies and redirects disabled."""

    return _LOCAL_OPENER.open(request, timeout=timeout)


class LocalOpenAIModel(BaseModel):
    """Send chat-completion requests to a configured loopback endpoint."""

    def __init__(self, config: ModelConfig) -> None:
        self.config = config

    def generate(self, messages: list[Message]) -> str:
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": False,
        }
        request = Request(
            f"{self.config.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with _open_local_request(request, self.config.timeout_seconds) as response:
                raw_data = response.read()
        except HTTPError as exc:
            detail = self._http_error_detail(exc)
            raise ModelError(
                f"The local {self.config.runtime} server returned HTTP {exc.code}{detail}."
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ModelError(
                f"Could not reach the local {self.config.runtime} server at "
                f"{self.config.base_url}. Check that it is running and that model "
                f"{self.config.model!r} is available."
            ) from exc

        try:
            data: dict[str, Any] = json.loads(raw_data)
            content = data["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise ModelError(
                "The local model server returned an invalid response."
            ) from exc

        if not isinstance(content, str) or not content.strip():
            raise ModelError("The local model server returned an empty response.")
        return content.strip()

    @staticmethod
    def _http_error_detail(exc: HTTPError) -> str:
        try:
            body = exc.read().decode("utf-8", errors="replace")
            data = json.loads(body)
            message = data.get("error", {}).get("message")
            return f": {message}" if isinstance(message, str) else ""
        except (OSError, json.JSONDecodeError, AttributeError):
            return ""
