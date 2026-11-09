from __future__ import annotations

import json

import hashlib

import logging

import multiprocessing

import os

import re

import time

import urllib.error

import urllib.request

from dataclasses import dataclass, field

from pathlib import Path

from typing import Any, Literal

from .model_wire import collect_stream, coalesce_stream

from .response_repair import REPAIRABLE_OUTPUT, repair_feedback

from .models import ModelCallError

logger = logging.getLogger(__name__)

_API_KEY_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b", re.IGNORECASE)

_BEARER_PATTERN = re.compile(r"(?i)(Bearer\s+)[^\s'\"\\]+")

ModelProvider = Literal["openai", "deepseek", "dashscope"]

ReasoningEffort = Literal["low", "high", "max"]

@dataclass(frozen=True, slots=True)
class ProviderDefaults:
    model_env: str
    base_url_env: str
    api_key_env: str
    default_model: str = ""
    default_base_url: str = ""

PROVIDER_DEFAULTS: dict[ModelProvider, ProviderDefaults] = {
    "openai": ProviderDefaults(
        model_env="OPENAI_MODEL",
        base_url_env="OPENAI_API_BASE",
        api_key_env="OPENAI_API_KEY",
    ),
    "deepseek": ProviderDefaults(
        model_env="DEEPSEEK_MODEL",
        base_url_env="DEEPSEEK_API_BASE",
        api_key_env="DEEPSEEK_API_KEY",
        default_model="deepseek-v4-flash",
        default_base_url="https://api.deepseek.com",
    ),
    "dashscope": ProviderDefaults(
        model_env="DASHSCOPE_MODEL",
        base_url_env="DASHSCOPE_API_BASE",
        api_key_env="DASHSCOPE_API_KEY",
        # 固定快照避免正式对照实验期间模型静默升级。
        default_model="qwen3.7-plus-2026-05-26",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
}

@dataclass(frozen=True, slots=True)
class RetracModelConfig:
    model_name: str
    base_url: str
    api_key: str
    provider: ModelProvider = "openai"
    temperature: float = 0.2
    top_p: float | None = None
    reasoning_effort: ReasoningEffort = "high"
    solve_reasoning_effort: ReasoningEffort = "max"
    # timeout_seconds 现在表示连续没有收到任何模型数据时的空闲超时；
    # max_wall_time_seconds 是单次请求的绝对总上限，防止服务端持续保活却永久不结束。
    timeout_seconds: int = 120
    max_wall_time_seconds: int = 600
    request_attempts: int = 5
    parse_attempts: int = 3
    retry_interval_seconds: float = 2.0
    max_retry_interval_seconds: float = 30.0
    use_json_response_format: bool = True
    max_commands_per_action: int = 4
    max_command_timeout_seconds: int = 300
    max_observation_chars: int = 8_000
    max_context_chars: int = 14_000
    hard_timeout_process: bool = True
    stream_response: bool = True
    # Explicit paired benchmark override; legacy defaults remain unchanged.
    thinking_enabled: bool = True
    max_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.provider not in PROVIDER_DEFAULTS:
            raise ValueError(f"unsupported model provider: {self.provider}")
        if not self.model_name.strip():
            raise ValueError("model_name cannot be empty")
        if not self.base_url.strip():
            raise ValueError("base_url cannot be empty")
        cleaned_api_key = self.api_key.strip()
        if not cleaned_api_key:
            raise ValueError("api_key cannot be empty")
        # frozen dataclass 仍允许在初始化校验阶段规范化内部值。
        object.__setattr__(self, "api_key", cleaned_api_key)
        for name in (
            "timeout_seconds",
            "max_wall_time_seconds",
            "request_attempts",
            "parse_attempts",
            "max_commands_per_action",
            "max_command_timeout_seconds",
            "max_observation_chars",
            "max_context_chars",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.max_wall_time_seconds < self.timeout_seconds:
            raise ValueError("max_wall_time_seconds must be >= timeout_seconds")
        if self.temperature < 0:
            raise ValueError("temperature must be non-negative")
        if self.top_p is not None and not 0 < self.top_p <= 1:
            raise ValueError("top_p must be in (0, 1]")
        if self.reasoning_effort not in {"low", "high", "max"}:
            raise ValueError("reasoning_effort must be low, high, or max")
        if self.solve_reasoning_effort not in {"low", "high", "max"}:
            raise ValueError("solve_reasoning_effort must be low, high, or max")
        if self.retry_interval_seconds < 0 or self.max_retry_interval_seconds <= 0:
            raise ValueError("retry_interval_seconds must be non-negative and its maximum positive")

    #API Key只从环境变量读取，避免写入配置文件、源码或命令行历史
    @classmethod
    def from_environment(
        cls,
        *,
        provider: ModelProvider = "openai",
        model_name: str | None = None,
        base_url: str | None = None,
        model_env: str | None = None,
        base_url_env: str | None = None,
        api_key_env: str | None = None,
        **kwargs: Any,
    ) -> "RetracModelConfig":
        if provider not in PROVIDER_DEFAULTS:
            raise ValueError(f"unsupported model provider: {provider}")
        defaults = PROVIDER_DEFAULTS[provider]
        resolved_model_env = model_env or defaults.model_env
        resolved_base_url_env = base_url_env or defaults.base_url_env
        resolved_api_key_env = api_key_env or defaults.api_key_env
        resolved_model = model_name or os.getenv(resolved_model_env) or defaults.default_model
        resolved_base_url = (
            base_url
            or os.getenv(resolved_base_url_env)
            or (os.getenv("OPENAI_BASE_URL", "") if provider == "openai" else "")
            or defaults.default_base_url
        )
        resolved_api_key = os.getenv(resolved_api_key_env, "").strip()
        missing = [
            name
            for name, value in (
                (resolved_model_env, resolved_model),
                (resolved_base_url_env, resolved_base_url),
                (resolved_api_key_env, resolved_api_key),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"missing model configuration: {', '.join(missing)}")
        return cls(
            model_name=resolved_model,
            base_url=resolved_base_url,
            api_key=resolved_api_key,
            provider=provider,
            **kwargs,
        )

class _SerializedHTTPError(RuntimeError):
    def __init__(self, code: int, details: str, retry_after: float | None) -> None:
        super().__init__(f"model request failed ({code}): {details}")
        self.code = code
        self.retry_after = retry_after

class _TransportFailure(RuntimeError):
    pass

@dataclass(slots=True)
class OpenAICompatibleJSONClient:
    config: RetracModelConfig
    diagnostics_path: Path | None = None
    model_call_count: int = field(default=0, init=False)
    api_request_count: int = field(default=0, init=False)
    api_response_count: int = field(default=0, init=False)
    prompt_tokens: int = field(default=0, init=False)
    cached_prompt_tokens: int = field(default=0, init=False)
    cache_miss_prompt_tokens: int = field(default=0, init=False)
    cache_write_prompt_tokens: int = field(default=0, init=False)
    completion_tokens: int = field(default=0, init=False)
    usage_missing_responses: int = field(default=0, init=False)
    response_models: set[str] = field(default_factory=set, init=False)
    system_fingerprints: set[str] = field(default_factory=set, init=False)
    last_failure_kind: str | None = field(default=None, init=False)
    last_failure_detail: str | None = field(default=None, init=False)
    failure_counts: dict[str, int] = field(default_factory=dict, init=False)
    _last_content: str = field(default='', init=False, repr=False)

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        reasoning_effort: ReasoningEffort | None = None,
        prompt_cache_key: str | None = None,
        history_messages: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        history = []
        for message in history_messages or []:
            if (not isinstance(message, dict) or set(message) != {'role', 'content'} or
                    message['role'] not in {'assistant', 'user'} or not isinstance(message['content'], str)):
                raise ValueError('history requires assistant/user text messages only')
            history.append(dict(message))
        self.model_call_count += 1
        self.last_failure_kind = None
        self.last_failure_detail = None
        self._last_content = ''
        request_body: dict[str, Any] = {
            "model": self.config.model_name,
            "temperature": self.config.temperature,
            "stream": self.config.stream_response,
            "messages": [
                {"role": "system", "content": system_prompt},
                *history,
                {"role": "user", "content": user_prompt},
            ],
        }
        if self.config.stream_response:
            request_body["stream_options"] = {"include_usage": True}
        # DeepSeek会自动按公共前缀管理缓存，不支持OpenAI的prompt_cache_key。
        if self.config.provider == "openai" and prompt_cache_key:
            request_body["prompt_cache_key"] = prompt_cache_key
        if self.config.top_p is not None:
            request_body["top_p"] = self.config.top_p
        # DeepSeek V4 默认就是高思考；显式声明可避免服务端默认值变化导致评测不可比。
        if self.config.provider == "deepseek":
            request_body["thinking"] = {"type": "enabled" if self.config.thinking_enabled else "disabled"}
            request_body["reasoning_effort"] = (
                reasoning_effort or self.config.reasoning_effort
            )
        elif self.config.provider == "dashscope":
            # 百炼不接受OpenAI的prompt_cache_key，也不使用reasoning_effort。
            # 将现有强度语义映射成千问的混合思考开关；Judge传high，因而显式开启。
            request_body["enable_thinking"] = (
                reasoning_effort or self.config.reasoning_effort
            ) != "low"
        if self.config.use_json_response_format:
            request_body["response_format"] = {"type": "json_object"}

        if self.config.provider == "deepseek" and not self.config.thinking_enabled:
            request_body.pop("reasoning_effort", None)
        if self.config.max_tokens is not None:
            request_body["max_tokens"] = self.config.max_tokens
        encoded = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
        endpoint = self._endpoint()
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None
        failure_kind = "transport"
        for attempt in range(1, self.config.request_attempts + 1):
            self.api_request_count += 1
            failure_kind = "transport"
            retry_after_seconds: float | None = None
            started = time.monotonic()
            raw_response = b''
            content = ''
            response_payload: dict[str, Any] = {}
            failure_detail = 'transport'
            terminal_http = False
            try:
                logger.info(
                    "[API] 正在请求 %s 模型 %s（网络尝试 %d/%d，空闲超时 %d 秒，总上限 %d 秒）",
                    self.config.provider,
                    self.config.model_name,
                    attempt,
                    self.config.request_attempts,
                    self.config.timeout_seconds,
                    self.config.max_wall_time_seconds,
                )
                raw_response = self._request_bytes(
                    endpoint=endpoint,
                    encoded=encoded,
                    headers=headers,
                )
                if not raw_response.strip():
                    failure_detail = 'empty_http_body'
                    raise ValueError("model HTTP response body is empty")
                failure_detail = 'invalid_response_envelope'
                response_payload = json.loads(raw_response.decode("utf-8"))
                if not isinstance(response_payload, dict):
                    response_payload = {}
                    raise ValueError('model HTTP response must be an object')
                self._record_usage(response_payload)
                content = self._message_text(response_payload)
                self._last_content = content
                integrity = response_payload.get('_stream_integrity')
                if integrity is not None and (not isinstance(integrity, dict) or not integrity.get('done') or integrity.get('error')
                                              or integrity.get('unexpected_lines')):
                    failure_detail = 'incomplete_stream'
                    raise _TransportFailure('incomplete or invalid SSE stream; response rejected')
                reason = response_payload['choices'][0].get('finish_reason')
                if integrity is not None and reason is None:
                    failure_detail = 'missing_finish_reason'
                    raise _TransportFailure('SSE stream has no finish_reason; response rejected')
                failure_kind = "model_output"
                if reason not in (None, 'stop'):
                    failure_detail = 'output_length' if reason == 'length' else 'nonstop_finish'
                    raise ValueError(f'model finish_reason={reason}; response rejected')
                failure_detail = 'empty_content'
                if not content.strip():
                    raise ValueError("model message content is empty")
                failure_detail = 'json_syntax'
                payload = json.loads(_strip_json_fence(content))
                failure_detail = 'json_root_type'
                if not isinstance(payload, dict):
                    raise ValueError("model response must be a JSON object")
                logger.info(
                    "[API] 模型响应已收到并解析为JSON，耗时%.2f秒，请求字符%d",
                    time.monotonic() - started,
                    sum(len(m['content']) for m in request_body['messages']),
                )
                self.last_failure_kind = None
                self.last_failure_detail = None
                return payload
            except _SerializedHTTPError as error:
                last_error = error
                logger.warning("[API] HTTP请求失败：状态码=%d", error.code)
                retry_after_seconds = error.retry_after
                failure_detail = f'http_{error.code}'
                terminal_http = 400 <= error.code < 500 and error.code != 429
            except urllib.error.HTTPError as error:
                details = error.read().decode("utf-8", errors="replace")
                last_error = RuntimeError(f"model request failed ({error.code}): {details}")
                logger.warning("[API] HTTP请求失败：状态码=%d", error.code)
                retry_after_seconds = _retry_after_seconds(error)
                failure_detail = f'http_{error.code}'
                #鉴权、参数等4xx错误重试没有意义；限流错误除外
                terminal_http = 400 <= error.code < 500 and error.code != 429
            except (
                urllib.error.URLError,
                _TransportFailure,
                TimeoutError,
                json.JSONDecodeError,
                KeyError,
                IndexError,
                TypeError,
                ValueError,
            ) as error:
                last_error = error
                logger.warning("[API] 本次模型请求未成功：%s", self._redact(str(error))[:240])
            self.last_failure_detail = failure_detail
            self._record_failure(failure_detail, content or raw_response.decode('utf-8', errors='replace'),
                                 response_payload, last_error)
            if terminal_http:
                break
            if failure_detail in REPAIRABLE_OUTPUT:
                # Same bounded request budget for both methods. No semantic guidance,
                # no substring extraction and no execution of malformed output.
                feedback = '\n\n' + repair_feedback(failure_detail, self.config.max_tokens)
                request_body['messages'][-1]['content'] = user_prompt + feedback
                encoded = json.dumps(request_body, ensure_ascii=False).encode('utf-8')
            if attempt < self.config.request_attempts:
                exponential_delay = min(
                    self.config.retry_interval_seconds * (2 ** (attempt - 1)),
                    self.config.max_retry_interval_seconds,
                )
                delay = min(
                    max(exponential_delay, retry_after_seconds or 0.0),
                    self.config.max_retry_interval_seconds,
                )
                logger.info("[API] %.1f秒后重试", delay)
                time.sleep(delay)
        safe_last_error = (
            self._redact(str(last_error))[:240] if last_error is not None else "unknown error"
        )
        self.last_failure_kind = failure_kind
        raise ModelCallError(
            f"model did not return usable JSON: {safe_last_error}"
        ) from last_error

    def usage_summary(self) -> dict[str, Any]:
        cache_denominator = self.cached_prompt_tokens + self.cache_miss_prompt_tokens
        cache_hit_rate = (
            self.cached_prompt_tokens / cache_denominator
            if cache_denominator
            else 0.0
        )
        return {
            "model_calls": self.model_call_count,
            "api_requests": self.api_request_count,
            "api_responses": self.api_response_count,
            "prompt_tokens": self.prompt_tokens,
            "cached_prompt_tokens": self.cached_prompt_tokens,
            "cache_miss_prompt_tokens": self.cache_miss_prompt_tokens,
            "cache_write_prompt_tokens": self.cache_write_prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cache_hit_rate": round(cache_hit_rate, 6),
            "usage_missing_responses": self.usage_missing_responses,
            "response_models": sorted(self.response_models),
            "system_fingerprints": sorted(self.system_fingerprints),
            "last_failure_kind": self.last_failure_kind,
            "last_failure_detail": self.last_failure_detail,
            "failure_counts": dict(self.failure_counts),
            "usage_unreported_requests": self.api_request_count - self.api_response_count + self.usage_missing_responses,
        }

    def _redact(self, text: str) -> str:
        text = text.replace(self.config.api_key, '[REDACTED]') if self.config.api_key else text
        return _API_KEY_PATTERN.sub('[REDACTED]', _BEARER_PATTERN.sub(r'\1[REDACTED]', text))

    def _record_failure(self, detail: str, content: str, payload: dict[str, Any], error: Any) -> None:
        self.failure_counts[detail] = self.failure_counts.get(detail, 0) + 1
        if self.diagnostics_path is None:
            return
        choices = payload.get('choices')
        choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        safe = self._redact(content)
        record = {'time': time.time(), 'model_call': self.model_call_count, 'api_request': self.api_request_count,
                  'detail': detail, 'error': self._redact(str(error))[:500],
                  'finish_reason': choice.get('finish_reason'), 'stream_integrity': payload.get('_stream_integrity'),
                  'content_chars': len(content), 'redacted_content_sha256': hashlib.sha256(safe.encode()).hexdigest(),
                  'content_head': safe[:6000], 'content_tail': safe[-2000:] if len(safe) > 6000 else '',
                  'content_truncated': len(safe) > 8000}
        try:
            self.diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.diagnostics_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, 'a', encoding='utf-8') as stream:
                # Redact the serialized record too (including metadata and escaped strings).
                stream.write(self._redact(json.dumps(record, ensure_ascii=False)) + '\n')
        except OSError:
            logger.warning('[API] Could not write failure diagnostics (response still rejected)')

    def record_schema_failure(self, error: Exception) -> None:
        self.last_failure_detail = 'schema_validation'
        self._record_failure('schema_validation', self._last_content, {}, error)

    def _record_usage(self, response_payload: dict[str, Any]) -> None:
        self.api_response_count += 1
        if isinstance(response_payload.get("model"), str):
            self.response_models.add(response_payload["model"])
        if isinstance(response_payload.get("system_fingerprint"), str):
            self.system_fingerprints.add(response_payload["system_fingerprint"])
        usage = response_payload.get("usage")
        if not isinstance(usage, dict):
            self.usage_missing_responses += 1
            return
        prompt_tokens = _nonnegative_int(usage.get("prompt_tokens"))
        completion_tokens = _nonnegative_int(usage.get("completion_tokens"))
        details = usage.get("prompt_tokens_details")
        details = details if isinstance(details, dict) else {}
        if self.config.provider == "deepseek":
            cached_tokens = _nonnegative_int(usage.get("prompt_cache_hit_tokens"))
            miss_tokens = _nonnegative_int(usage.get("prompt_cache_miss_tokens"))
        else:
            cached_tokens = _nonnegative_int(details.get("cached_tokens"))
            miss_tokens = max(0, prompt_tokens - cached_tokens)
        cache_write_tokens = _nonnegative_int(details.get("cache_write_tokens"))
        if prompt_tokens == 0 and cached_tokens + miss_tokens:
            prompt_tokens = cached_tokens + miss_tokens
        if miss_tokens == 0 and prompt_tokens > cached_tokens:
            miss_tokens = prompt_tokens - cached_tokens
        self.prompt_tokens += prompt_tokens
        self.cached_prompt_tokens += cached_tokens
        self.cache_miss_prompt_tokens += miss_tokens
        self.cache_write_prompt_tokens += cache_write_tokens
        self.completion_tokens += completion_tokens
        denominator = cached_tokens + miss_tokens
        hit_rate = cached_tokens / denominator if denominator else 0.0
        logger.info(
            "[API缓存] provider=%s，输入=%d，命中=%d，未命中=%d，写入=%d，命中率=%.1f%%",
            self.config.provider,
            prompt_tokens,
            cached_tokens,
            miss_tokens,
            cache_write_tokens,
            hit_rate * 100,
        )

    def _request_bytes(
        self,
        *,
        endpoint: str,
        encoded: bytes,
        headers: dict[str, str],
    ) -> bytes:
        if self.config.hard_timeout_process:
            return _request_bytes_with_hard_timeout(
                endpoint=endpoint,
                encoded=encoded,
                headers=headers,
                timeout_seconds=self.config.timeout_seconds,
                max_wall_time_seconds=self.config.max_wall_time_seconds,
                stream_response=self.config.stream_response,
            )
        request = urllib.request.Request(
            endpoint,
            data=encoded,
            method="POST",
            headers=headers,
        )
        with urllib.request.urlopen(
            request,
            timeout=self.config.timeout_seconds,
        ) as response:
            raw = response.read()
        return _coalesce_streaming_body(raw) if self.config.stream_response else raw

    def _endpoint(self) -> str:
        base = self.config.base_url.rstrip("/")
        return base if base.endswith("/chat/completions") else f"{base}/chat/completions"

    @staticmethod
    def _message_text(payload: dict[str, Any]) -> str:
        content = payload["choices"][0]["message"]["content"]
        if isinstance(content, str):
            return content
        #少数兼容服务使用多段content，统一拼成文本后再解析JSON
        if isinstance(content, list):
            parts = [
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict) and item.get("type") in {None, "text", "output_text"}
            ]
            return "".join(parts)
        raise ValueError("model message content is not text")

def _request_bytes_with_hard_timeout(
    *,
    endpoint: str,
    encoded: bytes,
    headers: dict[str, str],
    timeout_seconds: int,
    max_wall_time_seconds: int | None = None,
    stream_response: bool = False,
) -> bytes:
    wall_limit = max_wall_time_seconds or max(timeout_seconds, 600)
    if wall_limit < timeout_seconds:
        raise ValueError("max_wall_time_seconds must be >= timeout_seconds")
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(
        target=_request_bytes_worker,
        args=(
            send,
            endpoint,
            encoded,
            headers,
            timeout_seconds,
            stream_response,
        ),
        daemon=True,
    )
    process.start()
    send.close()
    try:
        started = time.monotonic()
        last_activity = started
        last_progress_log = started
        while True:
            now = time.monotonic()
            idle_remaining = timeout_seconds - (now - last_activity)
            wall_remaining = wall_limit - (now - started)
            if wall_remaining <= 0:
                _terminate_request_process(process)
                raise TimeoutError(
                    f"model request exceeded maximum wall-clock time of {wall_limit} seconds"
                )
            if idle_remaining <= 0:
                _terminate_request_process(process)
                raise TimeoutError(
                    f"model request had no activity for {timeout_seconds} seconds"
                )
            if not receive.poll(min(idle_remaining, wall_remaining)):
                continue
            try:
                result = receive.recv()
            except EOFError as error:
                raise _TransportFailure(
                    "model request worker exited without a response"
                ) from error
            if result[0] == "activity":
                last_activity = time.monotonic()
                if last_activity - last_progress_log >= 30.0:
                    logger.info(
                        "[API] 已收到流式活动，模型仍在思考（已等待%.0f秒）",
                        last_activity - started,
                    )
                    last_progress_log = last_activity
                continue
            break
    finally:
        receive.close()
        if process.is_alive():
            process.join(timeout=0.2)
        if process.is_alive():
            _terminate_request_process(process)

    kind = result[0]
    if kind == "ok":
        return result[1]
    if kind == "http_error":
        raise _SerializedHTTPError(result[1], result[2], result[3])
    raise _TransportFailure(f"{result[1]}: {result[2]}")

def _request_bytes_worker(
    send: Any,
    endpoint: str,
    encoded: bytes,
    headers: dict[str, str],
    timeout_seconds: int,
    stream_response: bool,
) -> None:
    try:
        request = urllib.request.Request(
            endpoint,
            data=encoded,
            method="POST",
            headers=headers,
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            if stream_response:
                send.send(("ok", _read_streaming_response(response, send)))
            else:
                send.send(("ok", response.read()))
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        send.send(("http_error", error.code, details, _retry_after_seconds(error)))
    except Exception as error:
        send.send(("error", type(error).__name__, _safe_error_text(error)))
    finally:
        send.close()

def _read_streaming_response(response: Any, send: Any) -> bytes:
    return collect_stream(response, send)

def _coalesce_streaming_body(raw: bytes) -> bytes:
    return coalesce_stream(raw)

def _terminate_request_process(process: Any) -> None:
    if process.is_alive():
        process.terminate()
    process.join(timeout=2.0)
    if process.is_alive() and hasattr(process, "kill"):
        process.kill()
        process.join(timeout=1.0)

def _nonnegative_int(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0

def _strip_json_fence(content: str) -> str:
    content = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", content, flags=re.DOTALL | re.IGNORECASE)
    return fenced.group(1).strip() if fenced else content

def _safe_error_text(error: Exception) -> str:
    text = str(error).replace("\r", " ").replace("\n", " ")
    text = _BEARER_PATTERN.sub(r"\1[REDACTED]", text)
    text = _API_KEY_PATTERN.sub("sk-[REDACTED]", text)
    return text[:240]

def _retry_after_seconds(error: urllib.error.HTTPError) -> float | None:
    value = error.headers.get("Retry-After") if error.headers is not None else None
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None
