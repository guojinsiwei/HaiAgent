"""SUZ transport, complete role accounting, and isolated Node controller bridge."""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
from .shared_budget import SharedBudget

ROOT = Path(__file__).resolve().parents[1]


class RunStop(BaseException):
    """Escape the upstream agent's Exception retry loop without another paid call."""


class ControllerBridge:
    def __init__(self, directory, task_id, instruction, config, node="node"):
        self.directory = Path(directory)
        self.process = subprocess.Popen([node, str(ROOT / "src" / "rpc.mjs")],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1)
        self.messages = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        # Drain stderr to prevent child pipe backpressure; no model content is printed.
        self.error_reader = threading.Thread(target=lambda: self.process.stderr.read(), daemon=True)
        self.error_reader.start()
        self.call("init", directory=str(self.directory), config={
            "taskId": task_id, "instruction": instruction,
            "visualWarnings": config.get("visual_warnings", True),
            "monitorEvery": config.get("monitor_every", 2), "routeWindow": config.get("route_window", 8)})

    def _read(self):
        for line in self.process.stdout:
            self.messages.put(line)
        self.messages.put(None)

    def call(self, op, **kwargs):
        try:
            self.process.stdin.write(json.dumps({"op": op, **kwargs}, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
            line = self.messages.get(timeout=30)
        except (OSError, queue.Empty) as exc:
            raise RunStop("controller unavailable") from exc
        if line is None:
            raise RunStop("controller exited")
        message = json.loads(line)
        if not message["ok"]:
            raise ValueError(message["error"])
        return message["result"]

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=5)
        self.reader.join(timeout=2)
        self.error_reader.join(timeout=2)
        self.process.stdout.close()
        self.process.stderr.close()


class MeteredClient:
    """One endpoint, all roles. Reserve the declared worst-case token cost first.

    Interrupted/unknown requests retain their reservation. No automatic network
    retries. Reopening a ledger reconstructs reservations before admitting calls.
    Prices are explicitly configured CNY per million tokens, with no assumed discount.
    """
    def __init__(self, config, directory, sender=None):
        self.config = config
        self.path = Path(directory) / "cost-ledger.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.calls = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                event = json.loads(line)
                self.calls[event["id"]] = event
        self.sender = sender or self._send
        self.testing = sender is not None
        self.verified_models = set()
        self.shared = SharedBudget(config['shared_budget']) if config.get('shared_budget') else None
        for name in ("budget_cny", "input_cny_per_million", "output_cny_per_million"):
            value = config.get(name)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError("Explicit nonnegative " + name + " required")
        for name in ("max_requests", "max_input_tokens", "max_output_tokens"):
            if not isinstance(config.get(name), int) or config[name] < 1:
                raise ValueError("Positive " + name + " required")
        self.max_seconds = config.get("max_seconds", 7200)
        if not isinstance(self.max_seconds, (int, float)) or not math.isfinite(self.max_seconds) or self.max_seconds <= 0:
            raise ValueError("Positive max_seconds required")
        self.start = time.monotonic()

    @property
    def spent(self):
        return sum(row["charge_cny"] for row in self.calls.values())

    def _record(self, event):
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self.calls[event["id"]] = event

    def _send(self, payload):
        if self.config.get("allow_live") is not True:
            raise RunStop("live model calls disabled; configure an authorized endpoint and budget")
        base = self.config["base_url"].rstrip("/")
        parsed = urlparse(base)
        if parsed.username or parsed.password or parsed.query:
            raise RunStop("endpoint must not embed credentials")
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}):
            raise RunStop("use HTTPS or a local SSH tunnel endpoint")
        key = os.environ.get(self.config.get("api_key_env", "SUZ_API_KEY"), "")
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        request = urllib.request.Request(base + "/chat/completions",
            data=json.dumps(payload).encode(), headers=headers, method="POST")
        try:
            if payload['model'] not in self.verified_models:
                # For the first version we require a vLLM-compatible server that exposes
                # its enforced context bound. The whole context bounds input tokens;
                # reserve output separately, conservatively, even though they overlap.
                metadata = urllib.request.Request(base + '/models', headers=headers)
                with urllib.request.urlopen(metadata, timeout=20) as response:
                    models = json.load(response).get('data', [])
                model = next((m for m in models if m.get('id') == payload['model']), None)
                bound = model.get('max_model_len', model.get('contextLen')) if model else None
                contract = self.config.get('provider_contract', {})
                if bound is None and model is not None:
                    if (contract.get('model') == payload['model'] and
                        contract.get('base_url', '').rstrip('/') == base and
                        contract.get('source_url', '').startswith('https://')):
                        bound = contract.get('max_context_tokens')
                if not isinstance(bound, int) or not 0 < bound <= self.config['max_input_tokens']:
                    raise RunStop('endpoint context bound unavailable or too large; configure max_input_tokens >= server max_model_len')
                self.verified_models.add(payload['model'])
            with urllib.request.urlopen(request, timeout=self.config.get("request_timeout", 120)) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            body=exc.read().decode('utf-8',errors='replace')
            if key: body=body.replace(key,'[REDACTED]')
            # Diagnostic only; response bodies never include request headers or images.
            (self.path.parent/'transport-error.json').write_text(json.dumps({
                'status':exc.code,'message':body[:2000]},ensure_ascii=False),encoding='utf-8')
            raise RunStop('model transport failed; charge remains reserved: HTTP '+str(exc.code)) from None
        except Exception as exc:
            # Do not log endpoint responses, auth headers, or keys.
            raise RunStop("model transport failed; charge remains reserved: " + type(exc).__name__) from None

    def complete(self, role, payload):
        payload = dict(payload)
        payload.setdefault('max_tokens', self.config.get('initial_output_tokens', self.config['max_output_tokens']))
        try:
            return self._complete_once(role, payload)
        except OutputTruncated:
            recovery = self.config.get('truncation_recovery_tokens', 0)
            if not payload['max_tokens'] < recovery <= self.config['max_output_tokens']:
                raise RunStop('incomplete model output; no recovery allowance') from None
            # Exactly one additional paid request, through the same cumulative ledger.
            # Partial output is never executed. Unknown transport results never retry.
            payload['max_tokens'] = recovery
            try:
                return self._complete_once(role, payload)
            except OutputTruncated:
                raise RunStop('incomplete model output after bounded recovery') from None

    def _complete_once(self, role, payload):
        cfg = self.config
        with self.lock:
            if time.monotonic() - self.start >= self.max_seconds:
                raise RunStop("wall-time limit reached")
            if len(self.calls) >= cfg["max_requests"]:
                raise RunStop("all-role model request limit reached")
            if not self.testing and cfg.get("allow_live") is not True:
                raise RunStop("live model calls disabled")
            tokens = payload.get("max_tokens", cfg["max_output_tokens"])
            if not isinstance(tokens, int) or not 0 < tokens <= cfg["max_output_tokens"]:
                raise RunStop("output cap exceeds configured limit")
            reserve = (cfg["max_input_tokens"] * cfg["input_cny_per_million"] +
                       tokens * cfg["output_cny_per_million"]) / 1_000_000
            if cfg["budget_cny"] <= 0 or self.spent + reserve > cfg["budget_cny"] + 1e-12:
                raise RunStop("all-role budget cannot reserve next request")
            shared_id = None
            if self.shared:
                try:
                    shared_id = self.shared.reserve(role, reserve)
                except ValueError as exc:
                    raise RunStop(str(exc)) from None
            call_id = len(self.calls) + 1
            event = {"id": call_id, "role": role, "status": "reserved", "charge_cny": reserve,
                     "reserved_cny": reserve, "timestamp": time.time(), "shared_id": shared_id}
            self._record(event)
        started = time.monotonic()
        response = self.sender(payload)  # On failure retain reservation and never blind-retry.
        usage = response.get("usage", {})
        pi, co = usage.get("prompt_tokens"), usage.get("completion_tokens")
        if not all(isinstance(x, int) and not isinstance(x, bool) and x >= 0 for x in (pi, co)):
            raise RunStop("missing complete token usage; reservation retained")
        charge = (pi * cfg["input_cny_per_million"] + co * cfg["output_cny_per_million"]) / 1_000_000
        row = {**event, "status": "settled", "charge_cny": charge, "usage": usage,
               "elapsed_seconds": time.monotonic()-started}
        with self.lock:
            if self.shared:
                self.shared.settle(shared_id, charge)
            self._record(row)
        if pi > cfg["max_input_tokens"] or co > tokens:
            raise RunStop("provider exceeded configured token bound; stop and reconcile pricing/caps")
        choices = response.get("choices", [])
        with (self.path.parent/'model-responses.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps({'id':call_id,'role':role,'max_tokens':tokens,'choices':choices},ensure_ascii=False)+'\n')
        if choices and choices[0].get('finish_reason') == 'length':
            raise OutputTruncated('output truncated')
        if not choices or choices[0].get("finish_reason") != "stop":
            raise RunStop("incomplete model output; cost recorded, no automatic retry")
        content = choices[0].get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise RunStop("empty model output; cost recorded")
        return content


class OutputTruncated(RunStop):
    pass


def parse_json(text):
    stripped = text.strip()
    if stripped.startswith("```json") and stripped.endswith("```"):
        stripped = stripped[7:-3].strip()
    elif stripped.startswith("```") and stripped.endswith("```"):
        stripped = stripped[3:-3].strip()
    obj = json.loads(stripped)
    if not isinstance(obj, dict):
        raise ValueError("role response must be a JSON object")
    return obj
