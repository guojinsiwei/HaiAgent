"""Explicit, external LongCLI-Bench attempts; importing this module runs nothing.

Only an official, completed failure may reach the Meta-Agent. Each attempt uses
one new tb run and therefore a new harness/container context. This module reads
only public actor logs for diagnosis; hidden verifier payloads stay local.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Callable
from urllib.parse import urlsplit
from uuid import uuid4

from .audit import redact
from .evolution import EvolutionError, prepare_trace
from .memory import load_memory, memory_digest, save_memory, validate_memory

LONGCLI_COMMIT = "2015f37b5c458f2562354de6b415e9182c91af64"
_AGENT_IMPORT = "recuris.longcli:RecurisAgent"
_ALLOWED_FAILURE_MODES = {"none", "unset", "agent_timeout"}
_CREDENTIAL_KEY = re.compile(r"api_?key|access_?token|auth_?token|password|passwd|secret|credential|authorization", re.I)


def _has_credential_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_CREDENTIAL_KEY.search(str(key)) or _has_credential_key(item)
                   for key, item in value.items())
    if isinstance(value, list):
        return any(_has_credential_key(item) for item in value)
    return False


class AttemptError(RuntimeError):
    """An absent or untrustworthy outcome; never interpreted as task failure."""


@dataclass
class TTAConfig:
    benchmark_root: Path
    task_id: str
    model_name: str
    output_dir: Path
    mode: str = "adaptation"
    attempts: int = 4
    memory_path: Path | None = None
    agent_kwargs: dict[str, Any] = field(default_factory=dict)
    harness_timeout_seconds: float = 3900
    process_timeout_seconds: float = 4500
    seed_attempt_dir: Path | None = None
    tb_command: tuple[str, ...] = ("tb",)

    def validate(self) -> None:
        if self.mode not in {"adaptation", "frozen"}:
            raise ValueError("mode must be adaptation or frozen")
        if type(self.attempts) is not int or not 1 <= self.attempts <= 4:
            raise ValueError("attempts must be an integer from 1 to 4")
        if not isinstance(self.task_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", self.task_id) or ".." in self.task_id:
            raise ValueError("task_id must be one simple dataset directory name")
        if not isinstance(self.model_name, str) or not self.model_name.strip():
            raise ValueError("model_name must be explicit")
        for value in (self.harness_timeout_seconds, self.process_timeout_seconds):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError("timeouts must be finite positive numbers")
        if self.process_timeout_seconds <= self.harness_timeout_seconds:
            raise ValueError("process timeout must leave time for official verification after the agent timeout")
        if not isinstance(self.agent_kwargs, dict):
            raise ValueError("agent_kwargs must be an object")
        if not self.tb_command or any(not isinstance(x, str) or not x for x in self.tb_command):
            raise ValueError("tb_command must contain executable arguments")
        for key, value in self.agent_kwargs.items():
            if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", key):
                raise ValueError("agent kwarg names must be simple identifiers")
            if key in {"memory_path", "model_name", "model"}:
                raise ValueError("model and memory are managed by the TTA driver")
            if (key != "api_key_env" and _CREDENTIAL_KEY.search(key)) or _has_credential_key(value):
                raise ValueError("pass credential environment names, never credentials, as agent kwargs")
            if key == "api_key_env" and (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value)):
                raise ValueError("api_key_env must be an environment variable name")
            if key == "base_url":
                if not isinstance(value, str):
                    raise ValueError("base_url must be a URL string")
                endpoint = urlsplit(value)
                if endpoint.scheme not in {"http", "https"} or not endpoint.hostname or endpoint.username is not None or endpoint.password is not None or endpoint.query or endpoint.fragment:
                    raise ValueError("base_url must be an HTTP(S) endpoint without credentials, query or fragment")
            if "=" in _kwarg(value) or "\x00" in _kwarg(value):
                raise ValueError("LongCLI agent kwargs cannot contain '=' or NUL")
        if "=" in str(Path(self.output_dir).resolve()):
            raise ValueError("output_dir cannot contain an equals sign because of the pinned LongCLI CLI parser")
        root = Path(self.benchmark_root).resolve()
        task = root / "tasks_long_cli" / self.task_id / "task.yaml"
        if not task.is_file() or not task.resolve().is_relative_to(root / "tasks_long_cli"):
            raise ValueError("selected task.yaml is missing or escapes tasks_long_cli")


def _kwarg(value: Any) -> str:
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("agent kwargs must be finite")
    if not isinstance(value, (str, int, float)):
        raise ValueError("unsupported agent kwarg type")
    return str(value)


def _hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise AttemptError("missing or invalid JSON artifact: " + path.name) from exc


def _write(path: Path, value: Any) -> None:
    """Preserve canonical evidence and candidate bytes for digest verification."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _relative(root: Path, value: str) -> Path:
    if not isinstance(value, str):
        raise AttemptError("artifact path must be a relative string")
    path = (root / value).resolve()
    if Path(value).is_absolute() or not path.is_relative_to(root.resolve()):
        raise AttemptError("artifact path escapes the attempt directory")
    return path


def _verify_checkout(config: TTAConfig, runner: Callable) -> None:
    try:
        result = runner(["git", "-C", str(Path(config.benchmark_root).resolve()), "rev-parse", "HEAD"],
                        capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AttemptError("cannot verify the LongCLI-Bench checkout commit") from exc
    if result.returncode != 0 or result.stdout.strip() != LONGCLI_COMMIT:
        raise AttemptError("LongCLI-Bench must be checked out at " + LONGCLI_COMMIT)


def _provenance(config: TTAConfig, memory: dict) -> dict:
    root = Path(config.benchmark_root).resolve()
    package = Path(__file__).resolve().parent
    code_digest = sha256()
    for path in sorted(package.glob("*.py")):
        code_digest.update(path.name.encode())
        code_digest.update(path.read_bytes())
    # Do not serialize environment credentials. Endpoint identity affects model
    # behaviour and must match when reusing a first attempt.
    endpoint_env = {key: sha256(os.environ.get(key, "").encode("utf-8")).hexdigest() for key in (
        "OPENAI_BASE_URL", "OPENAI_API_BASE", "DEEPSEEK_BASE_URL", "DEEPSEEK_API_BASE")}
    return {"schema_version": 1, "benchmark_commit": LONGCLI_COMMIT,
            "task_id": config.task_id, "task_sha256": _hash(root / "tasks_long_cli" / config.task_id / "task.yaml"),
            "model_name": config.model_name, "agent_import_path": _AGENT_IMPORT,
            "agent_options": [{"name": key, "value": value} for key, value in sorted(config.agent_kwargs.items())], "endpoint_environment": endpoint_env,
            "memory_digest": memory_digest(memory), "adapter_code_digest": code_digest.hexdigest(),
            "harness_timeout_seconds": config.harness_timeout_seconds,
            "process_timeout_seconds": config.process_timeout_seconds,
            "n_attempts": 1, "give_test_output": 1}


def build_command(config: TTAConfig, attempt_dir: Path, run_id: str) -> list[str]:
    """Return argv without invoking a shell. Repeated user harness flags are absent."""
    args = [*config.tb_command, "run", "--agent-import-path", _AGENT_IMPORT,
            "--model", config.model_name, "--dataset-path", str(Path(config.benchmark_root).resolve() / "tasks_long_cli"),
            "--task-id", config.task_id, "--output-path", str(attempt_dir / "tb-output"),
            "--run-id", run_id, "--n-attempts", "1", "--give-test-output", "1", "--n-concurrent", "1",
            "--global-agent-timeout-sec", str(config.harness_timeout_seconds),
            "--agent-kwarg", "memory_path=" + str(attempt_dir / "memory.json")]
    for key, value in sorted(config.agent_kwargs.items()):
        args.extend(["--agent-kwarg", key + "=" + _kwarg(value)])
    return args


def _official_result(path: Path, *, task_id: str, trial_name: str) -> dict:
    result = _json(path)
    if not isinstance(result, dict) or result.get("task_id") != task_id or result.get("trial_name") != trial_name:
        raise AttemptError("official result task/trial identity mismatch")
    if type(result.get("is_resolved")) is not bool:
        raise AttemptError("official outcome is missing or null; no failure bit exists")
    if result.get("failure_mode") not in _ALLOWED_FAILURE_MODES:
        raise AttemptError("official run has a parser, test, or unknown execution error")
    if not result.get("test_started_at") or not result.get("test_ended_at") or not result.get("trial_ended_at"):
        raise AttemptError("official verification has not completed")
    turns = result.get("long_cli_test_turns")
    if not isinstance(turns, list) or len(turns) != 1 or not isinstance(turns[0], dict) or not turns[0]:
        raise AttemptError("expected exactly one completed LongCLI verification round")
    # Do not return hidden test metrics, instruction, expected output, etc.
    return {"official_success": result["is_resolved"], "failure_mode": result["failure_mode"]}


def _actor_artifacts(trial_dir: Path, memory_hash: str) -> tuple[Path, dict, list, dict]:
    candidates = list((trial_dir / "agent-logs" / "recuris").glob("*/context.json"))
    if len(candidates) != 1:
        raise AttemptError("expected one unambiguous Recuris invocation in this trial")
    actor_dir = candidates[0].parent
    context = _json(actor_dir / "context.json")
    if not isinstance(context, dict) or context.get("memory_digest") != memory_hash:
        raise AttemptError("actor memory digest does not match this attempt")
    if not isinstance(context.get("instruction"), str) or not context["instruction"].strip():
        raise AttemptError("actor public instruction is absent")
    try:
        trace = prepare_trace(_json(actor_dir / "trace.json"))
    except ValueError as exc:
        raise AttemptError("actor trace violates the public-evidence schema") from exc
    actor_result = _json(actor_dir / "result.json")
    if not isinstance(actor_result, dict) or actor_result.get("error") is not None:
        raise AttemptError("actor invocation ended with an execution error")
    return actor_dir, context, trace, actor_result


def _seal_attempt(attempt_dir: Path, provenance: dict, run_id: str, attempt_index: int) -> dict:
    task = provenance["task_id"]
    trial_name = f"{task}.1-of-1.{run_id}"
    trial_dir = attempt_dir / "tb-output" / run_id / task / trial_name
    official_path = trial_dir / "results.json"
    outcome = _official_result(official_path, task_id=task, trial_name=trial_name)
    actor_dir, context, trace, actor_result = _actor_artifacts(trial_dir, provenance["memory_digest"])
    paths = {"official_result": official_path, "context": actor_dir / "context.json",
             "trace": actor_dir / "trace.json", "actor_result": actor_dir / "result.json",
             "memory": attempt_dir / "memory.json", "provenance": attempt_dir / "provenance.json"}
    receipt = {"schema_version": 1, "attempt_index": attempt_index, "run_id": run_id, "task_id": task, "trial_name": trial_name,
               **outcome, "artifacts": {key: {"path": path.relative_to(attempt_dir).as_posix(), "sha256": _hash(path)}
                                         for key, path in paths.items()}}
    _write(attempt_dir / "attempt.json", receipt)
    return read_attempt(attempt_dir, expected_provenance=provenance)


def read_attempt(directory: str | Path, expected_provenance: dict | None = None) -> dict:
    """Read a sealed attempt and return only actor-visible evidence plus one bit.

    Hashes detect accidental modification, not forgery by a malicious file owner.
    Callers can use this for offline proposal/gate inputs without opening graders.
    """
    root = Path(directory).resolve()
    receipt = _json(root / "attempt.json")
    if not isinstance(receipt, dict) or receipt.get("schema_version") != 1:
        raise AttemptError("unsupported attempt receipt")
    if type(receipt.get("attempt_index")) is not int or not 1 <= receipt["attempt_index"] <= 4:
        raise AttemptError("attempt receipt has an invalid attempt index")
    artifacts = receipt.get("artifacts")
    required = {"official_result", "context", "trace", "actor_result", "memory", "provenance"}
    if not isinstance(artifacts, dict) or set(artifacts) != required:
        raise AttemptError("attempt receipt is missing its evidence artifacts")
    paths = {}
    for key, artifact in artifacts.items():
        if not isinstance(artifact, dict) or set(artifact) != {"path", "sha256"}:
            raise AttemptError("invalid artifact descriptor")
        path = _relative(root, artifact["path"])
        if not path.is_file() or _hash(path) != artifact["sha256"]:
            raise AttemptError("attempt evidence hash mismatch: " + key)
        paths[key] = path
    provenance = _json(paths["provenance"])
    if not isinstance(provenance, dict) or (expected_provenance is not None and provenance != expected_provenance):
        raise AttemptError("first-attempt provenance does not match task/model/config/memory/code")
    if provenance.get("benchmark_commit") != LONGCLI_COMMIT or provenance.get("n_attempts") != 1 or provenance.get("give_test_output") != 1:
        raise AttemptError("attempt was not generated under the pinned single-round contract")
    if receipt.get("task_id") != provenance.get("task_id"):
        raise AttemptError("attempt receipt and provenance task mismatch")
    run_id = receipt.get("run_id")
    trial_name = f"{receipt['task_id']}.1-of-1.{run_id}"
    if receipt.get("trial_name") != trial_name:
        raise AttemptError("attempt receipt trial name mismatch")
    expected_trial_dir = root / "tb-output" / str(run_id) / receipt["task_id"] / trial_name
    if paths["official_result"] != (expected_trial_dir / "results.json").resolve():
        raise AttemptError("official artifact is not in the expected trial")
    outcome = _official_result(paths["official_result"], task_id=receipt["task_id"], trial_name=trial_name)
    if type(receipt.get("official_success")) is not bool or receipt["official_success"] != outcome["official_success"]:
        raise AttemptError("attempt receipt contradicts the official result")
    memory = load_memory(paths["memory"])
    if memory_digest(memory) != provenance.get("memory_digest"):
        raise AttemptError("attempt memory and provenance disagree")
    actor_dir, context, trace, actor_result = _actor_artifacts(expected_trial_dir, provenance["memory_digest"])
    for key in ("context", "trace", "actor_result"):
        filename = "result.json" if key == "actor_result" else key + ".json"
        if paths[key] != (actor_dir / filename).resolve():
            raise AttemptError("actor artifact does not belong to this trial invocation")
    return {"success": outcome["official_success"], "official_success": outcome["official_success"],
            "run_id": run_id, "trial_name": trial_name,
            "attempt_index": receipt["attempt_index"], "task_id": receipt["task_id"], "instruction": context["instruction"], "trace": trace,
            "memory": memory, "memory_digest": memory_digest(memory), "provenance": provenance,
            "attempt_dir": str(root), "failure_mode": outcome["failure_mode"],
            "actor_usage": {key: actor_result.get(key, 0) for key in ("input_tokens", "output_tokens", "model_calls")}}


def run_tta(config: TTAConfig, meta_agent=None, *, runner: Callable = subprocess.run) -> dict:
    """Execute only when explicitly called by the experiment owner.

    Infrastructure/model/proposal failures stop the campaign as incomplete. They
    are never converted to false official outcomes or silently reused as lessons.
    A valid Meta-Agent no-op keeps the current package for the next fresh trial.
    """
    config.validate()
    if config.mode == "adaptation" and config.attempts > 1 and meta_agent is None:
        raise ValueError("adaptation with multiple attempts requires a MetaAgent")
    memory = load_memory(config.memory_path)
    _verify_checkout(config, runner)
    initial_provenance = _provenance(config, memory)
    root = Path(config.output_dir).resolve()
    root.mkdir(parents=True, exist_ok=False)
    _write(root / "campaign.json", {"initial_provenance": initial_provenance, "mode": config.mode, "attempts": config.attempts})
    summary = {"schema_version": 1, "task_id": config.task_id, "mode": config.mode,
               "attempt_budget": config.attempts, "attempts": [], "status": "running",
               "official_success": None, "passed_at_attempt": None, "error": None}
    _write(root / "summary.json", summary)
    for number in range(1, config.attempts + 1):
        entry = {"attempt": number, "memory_digest": memory_digest(memory), "official_success": None}
        summary["attempts"].append(entry)
        try:
            provenance = _provenance(config, memory)
            expected = {**initial_provenance, "memory_digest": memory_digest(memory)}
            if provenance != expected:
                raise AttemptError("task/model/config/code changed during this campaign")
            if number == 1 and config.seed_attempt_dir is not None:
                attempt = read_attempt(config.seed_attempt_dir, expected_provenance=provenance)
                if attempt["attempt_index"] != 1:
                    raise AttemptError("seed_attempt_dir must identify a first attempt")
                entry.update(attempt_dir=attempt["attempt_dir"], reused=True)
            else:
                attempt_dir = root / f"attempt-{number:02d}"
                attempt_dir.mkdir(exist_ok=False)
                save_memory(memory, attempt_dir / "memory.json")
                _write(attempt_dir / "provenance.json", provenance)
                run_id = "recuris-" + uuid4().hex
                command = build_command(config, attempt_dir, run_id)
                _write(attempt_dir / "command.json", command)
                result = runner(command, cwd=str(Path(config.benchmark_root).resolve()),
                                capture_output=True, text=True, encoding="utf-8", errors="replace",
                                timeout=config.process_timeout_seconds, check=False)
                _write(attempt_dir / "process.json", redact({"returncode": result.returncode,
                        "stdout": result.stdout, "stderr": result.stderr}))
                if result.returncode != 0:
                    raise AttemptError("tb process returned nonzero; attempt is incomplete")
                attempt = _seal_attempt(attempt_dir, provenance, run_id, number)
                entry.update(attempt_dir=str(attempt_dir), reused=False)
            entry.update(official_success=attempt["success"], actor_usage=attempt["actor_usage"])
            if attempt["success"]:
                summary.update(status="succeeded", official_success=True, passed_at_attempt=number)
                break
            if config.mode == "adaptation" and number < config.attempts:
                candidate = meta_agent.propose(memory, attempt["instruction"], attempt["trace"], mode="tta")
                proposed = validate_memory(candidate.candidate_memory)
                if candidate.base_digest != memory_digest(memory) or candidate.candidate_digest != memory_digest(proposed):
                    raise AttemptError("Meta-Agent proposal digest mismatch")
                if any(memory[key] != proposed[key] for key in ("W", "rho", "C")):
                    raise AttemptError("TTA proposal attempted to edit a non-E component")
                if bool(candidate.no_op) != (proposed == memory):
                    raise AttemptError("Meta-Agent no-op declaration contradicts its candidate")
                _write(root / f"proposal-{number:02d}.json", asdict(candidate) if is_dataclass(candidate) else vars(candidate))
                memory = proposed
                entry["candidate_digest"] = memory_digest(memory)
                entry["meta_no_op"] = candidate.no_op
            _write(root / "summary.json", summary)
        except (AttemptError, OSError, subprocess.TimeoutExpired, EvolutionError, ValueError) as exc:
            summary.update(status="incomplete", official_success=None, error=redact(str(exc)))
            entry["error"] = redact(str(exc))
            if isinstance(exc, EvolutionError):
                entry["meta_usage"] = {key: getattr(exc, key) for key in ("input_tokens", "output_tokens", "model_calls")}
            break
    else:
        summary.update(status="exhausted", official_success=False)
    summary["attempts_used"] = sum(type(x["official_success"]) is bool for x in summary["attempts"])
    save_memory(memory, root / "final-memory.json")
    _write(root / "summary.json", summary)
    return summary




