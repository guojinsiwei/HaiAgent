"""Synchronous DeepSeek/OpenAI-compatible chat completions transport.

Only HTTP transport is handled here: the engine parses model text and decides
what terminal commands to execute. No model-generated tool call is executed.
"""

from __future__ import annotations

from dataclasses import dataclass
from email.utils import parsedate_to_datetime
import json
import math
import os
import socket
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .audit import redact


@dataclass(frozen=True)
class ModelConfig:
    model_name: str
    base_url: str | None = None
    api_key_env: str = "DEEPSEEK_API_KEY"
    timeout_seconds: float = 120
    max_attempts: int = 3
    max_output_tokens: int = 4096
    temperature: float | None = None
    top_p: float | None = None
    reasoning_effort: str | None = None
    extra_body: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.model_name, str) or not self.model_name.strip():
            raise ValueError("model_name must be a non-empty provider model ID")
        if not self.api_key_env or not isinstance(self.api_key_env, str):
            raise ValueError("api_key_env must name the environment variable containing the API key")
        for label in ("max_attempts", "max_output_tokens"):
            value = getattr(self, label)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{label} must be a positive integer")
        if isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, (int, float)) or not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        for label, upper in (("temperature", 2), ("top_p", 1)):
            value = getattr(self, label)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= upper):
                raise ValueError(f"{label} must be between 0 and {upper}")
        if self.extra_body is not None and not isinstance(self.extra_body, dict):
            raise ValueError("extra_body must be a JSON object")
        reserved = {"model", "messages", "stream"}.intersection(self.extra_body or {})
        if reserved:
            raise ValueError(f"extra_body cannot override: {', '.join(sorted(reserved))}")


@dataclass(frozen=True)
class ModelReply:
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str | None = None


class ModelClientError(RuntimeError):
    """A transport, provider, or response-schema failure with redacted details."""

    def __init__(self, message: str, *, status_code: int | None = None, input_tokens: int = 0, output_tokens: int = 0):
        super().__init__(message)
        self.status_code = status_code
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class ModelDeadlineExceeded(ModelClientError):
    """The run deadline expired before a usable completion could be returned."""


class _NoRedirect(HTTPRedirectHandler):
    """Do not forward bearer credentials to a redirected endpoint."""

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


class OpenAIChatClient:
    """Use a configurable chat-completions endpoint, defaulting to DeepSeek.

    ``opener`` and ``sleep`` are optional test seams. Production defaults use
    the standard library, including its normal HTTPS certificate validation.
    Retries are limited to transient transport/HTTP failures and never change
    the requested model or generation parameters.
    """

    def __init__(
        self,
        config: ModelConfig,
        *,
        opener: Callable[..., Any] | None = None,
        sleep: Callable[[float], Any] | None = None,
    ):
        self.config = config
        self._opener = opener or build_opener(_NoRedirect()).open
        self._sleep = sleep or time.sleep
        base_url = config.base_url or next(
            (
                os.environ[name]
                for name in ("DEEPSEEK_BASE_URL", "DEEPSEEK_API_BASE", "OPENAI_BASE_URL", "OPENAI_API_BASE")
                if os.environ.get(name)
            ),
            "https://api.deepseek.com",
        )
        base_url = base_url.rstrip("/")
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("base_url must be an HTTP(S) URL without credentials, query, or fragment")
        self.endpoint = base_url if base_url.endswith("/chat/completions") else base_url + "/chat/completions"

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        purpose: str,
        deadline_monotonic: float | None = None,
    ) -> ModelReply:
        """Return model text before an optional absolute ``time.monotonic`` deadline.

        The deadline caps each socket timeout and retry delay, and a late reply
        raises ModelDeadlineExceeded carrying any reported token usage. urllib's
        socket timeout cannot kill a response that continuously trickles bytes;
        strict termination needs a process/container supervisor outside this client.
        """
        if deadline_monotonic is not None and (
            isinstance(deadline_monotonic, bool)
            or not isinstance(deadline_monotonic, (int, float))
            or not math.isfinite(deadline_monotonic)
        ):
            raise ValueError("deadline_monotonic must be a finite monotonic timestamp")
        self._remaining(deadline_monotonic)
        if not messages or not isinstance(messages, list) or not all(isinstance(message, dict) for message in messages):
            raise ValueError("messages must be a non-empty list of message objects")
        api_key = os.environ.get(self.config.api_key_env, "").strip()
        if not api_key:
            raise ModelClientError(f"Missing API key: set environment variable {self.config.api_key_env}")
        payload: dict[str, Any] = {
            "model": self.config.model_name,
            "messages": messages,
            "stream": False,
            "max_tokens": self.config.max_output_tokens,
        }
        for name in ("temperature", "top_p", "reasoning_effort"):
            value = getattr(self.config, name)
            if value is not None:
                payload[name] = value
        extra = self.config.extra_body or {}
        if "max_completion_tokens" in extra and "max_tokens" not in extra:
            payload.pop("max_tokens")
        payload.update(extra)
        try:
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (ValueError, TypeError) as exc:
            raise ValueError("Request messages and extra_body must contain valid JSON values") from exc
        request = Request(
            self.endpoint,
            data=body,
            headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        for attempt in range(1, self.config.max_attempts + 1):
            remaining = self._remaining(deadline_monotonic)
            timeout = self.config.timeout_seconds if remaining is None else min(self.config.timeout_seconds, remaining)
            try:
                with self._opener(request, timeout=timeout) as response:
                    raw = response.read()
            except HTTPError as exc:
                detail = self._http_detail(exc, api_key)
                self._remaining(deadline_monotonic)
                retryable = exc.code in {408, 409, 425, 429} or 500 <= exc.code <= 599
                if retryable and attempt < self.config.max_attempts:
                    self._wait_retry(attempt, exc.headers, deadline_monotonic)
                    continue
                safe_purpose = redact(str(purpose), secrets=(api_key,))
                raise ModelClientError(
                    f"Model request ({safe_purpose}) failed with HTTP {exc.code} after {attempt} attempt(s): {detail}",
                    status_code=exc.code,
                ) from None
            except (URLError, TimeoutError, socket.timeout, ConnectionError) as exc:
                self._remaining(deadline_monotonic)
                if attempt < self.config.max_attempts:
                    self._wait_retry(attempt, None, deadline_monotonic)
                    continue
                detail = redact(str(exc), secrets=(api_key,))
                safe_purpose = redact(str(purpose), secrets=(api_key,))
                raise ModelClientError(
                    f"Model request ({safe_purpose}) failed after {attempt} attempt(s): {detail}"
                ) from None
            try:
                reply = self._parse_reply(raw, api_key)
            except ModelClientError as exc:
                self._remaining(deadline_monotonic, usage=exc)
                raise
            self._remaining(deadline_monotonic, usage=reply)
            return reply
        raise AssertionError("Validated max_attempts should make the retry loop non-empty")

    @staticmethod
    def _remaining(deadline: float | None, *, usage: ModelReply | ModelClientError | None = None) -> float | None:
        if deadline is None:
            return None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ModelDeadlineExceeded(
                "Model request exceeded the run deadline",
                input_tokens=usage.input_tokens if usage is not None else 0,
                output_tokens=usage.output_tokens if usage is not None else 0,
            )
        return remaining

    def _wait_retry(self, attempt: int, headers: Any, deadline: float | None) -> None:
        remaining = self._remaining(deadline)
        delay = self._retry_delay(attempt, headers)
        self._sleep(delay if remaining is None else min(delay, remaining))
        self._remaining(deadline)

    @staticmethod
    def _retry_delay(attempt: int, headers: Any) -> float:
        retry_after = headers.get("Retry-After") if headers is not None else None
        if retry_after:
            try:
                delay = float(retry_after)
            except (TypeError, ValueError):
                try:
                    delay = parsedate_to_datetime(retry_after).timestamp() - time.time()
                except (TypeError, ValueError, OverflowError):
                    delay = 0
            if math.isfinite(delay) and delay > 0:
                return min(delay, 30.0)
        return min(2.0 ** min(attempt - 1, 5), 30.0)

    @staticmethod
    def _http_detail(error: HTTPError, api_key: str) -> str:
        try:
            text = error.read(16384).decode("utf-8", errors="replace")
            try:
                parsed = json.loads(text)
                detail = parsed.get("error", parsed) if isinstance(parsed, dict) else parsed
                if isinstance(detail, dict):
                    text = str(detail.get("message", detail.get("code", "Provider error")))
            except (ValueError, TypeError):
                pass
        except Exception:
            text = str(error.reason)
        finally:
            error.close()
        return str(redact(text or str(error.reason), secrets=(api_key,)))[:1000]

    @staticmethod
    def _parse_reply(raw: bytes, api_key: str) -> ModelReply:
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError):
            raise ModelClientError("Provider response is not a valid JSON chat completion") from None
        if not isinstance(data, dict):
            raise ModelClientError("Provider response must be a JSON object")
        usage = data.get("usage") or {}
        if not isinstance(usage, dict):
            usage = {}

        def count(primary: str, alternative: str) -> int:
            value = usage.get(primary, usage.get(alternative, 0))
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return 0
            return int(value) if math.isfinite(value) and value >= 0 else 0

        counts = {"input_tokens": count("prompt_tokens", "input_tokens"), "output_tokens": count("completion_tokens", "output_tokens")}
        if data.get("error"):
            detail = redact(data["error"], secrets=(api_key,))
            raise ModelClientError(f"Provider returned an error: {json.dumps(detail, ensure_ascii=False)[:1000]}", **counts)
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ModelClientError("Provider response has no valid completion choice", **counts)
        choice = choices[0]
        message = choice.get("message")
        if not isinstance(message, dict):
            raise ModelClientError("Provider response has no assistant message", **counts)
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            finish = choice.get("finish_reason")
            safe_finish = redact(repr(finish), secrets=(api_key,))
            raise ModelClientError(f"Provider returned empty or non-text assistant content (finish_reason={safe_finish})", **counts)

        finish = choice.get("finish_reason")
        return ModelReply(
            content=content,
            finish_reason=finish if isinstance(finish, str) else None,
            **counts,
        )
