"""Notebook-native orchestration; no Docker daemon, WSL, or platform API."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import uuid
from urllib.parse import urlsplit

from benchmark_runtime import atomic_write_json, atomic_write_text, canonical_sha256, implementation_sha256
from benchmark_splits import reject_frozen_overlap

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from bestfgs.__main__ import build_parser as agent_parser
from bestfgs.retrac_adapter import PROVIDER_DEFAULTS, RetracModelConfig
from bestfgs.submission import SubmissionError, inspect_git_submission


def tree_digest(root: Path) -> str:
    """Include dependency/seed changes when deciding whether a run is reusable."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError(f"Seed symlink escapes workspace: {path}")
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(b"\0symlink\0" + os.readlink(path).encode() + b"\0")
            continue
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(b"\0")
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            digest.update(b"\0")
    return digest.hexdigest()


def load_tasks(path: Path, output: Path) -> tuple[str, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Manifest requires schema_version=1")
    benchmark = data.get("benchmark", "custom")
    if benchmark not in {"custom", "swebench", "terminal-bench"}:
        raise ValueError("Unknown benchmark")
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("Manifest requires a nonempty tasks list")
    seen = set()
    normalized = []
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError("Each task must be an object")
        task = dict(task)
        identity = task.get("id", "")
        if not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,159}", identity):
            raise ValueError("Task id must be a safe directory name")
        if identity in seen:
            raise ValueError(f"Duplicate task id: {identity}")
        seen.add(identity)
        if not isinstance(task.get("goal"), str) or not task["goal"].strip():
            raise ValueError(f"Missing goal: {identity}")
        for key in ("success_criteria", "constraints"):
            value = task.setdefault(key, [])
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError(f"{key} must contain strings")
        raw_workspace = task.get("workspace")
        if not isinstance(raw_workspace, str) or not raw_workspace:
            raise ValueError(f"Missing workspace: {identity}")
        seed = Path(raw_workspace)
        seed = (path.parent / seed).resolve() if not seed.is_absolute() else seed.resolve()
        if not seed.is_dir():
            raise ValueError(f"Prepared workspace does not exist: {seed}")
        if seed == Path(seed.anchor):
            raise ValueError("A filesystem root cannot be a task workspace")
        if seed == output or seed in output.parents or output in seed.parents:
            raise ValueError("Seeds and output root must not contain each other")
        task["workspace"] = str(seed)
        task["seed_sha256"] = tree_digest(seed)
        if benchmark == "swebench":
            if not (seed / ".git").is_dir():
                raise ValueError("SWE-bench requires a standalone Git clone, not a worktree/subdirectory")
            commit = task.get("base_commit")
            if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
                raise ValueError("SWE-bench tasks require a full base_commit")
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=seed, capture_output=True, text=True, check=True).stdout.strip()
            dirty = subprocess.run(["git", "status", "--porcelain"], cwd=seed, capture_output=True, text=True, check=True).stdout
            prepared = task.get('prepared_commit', commit)
            if not isinstance(prepared, str) or not re.fullmatch(r'[0-9a-fA-F]{40}', prepared):
                raise ValueError('Invalid prepared_commit')
            if prepared != commit:
                subprocess.run(['git', 'merge-base', '--is-ancestor', commit, prepared], cwd=seed, check=True, capture_output=True)
            if head.lower() != prepared.lower() or dirty.strip():
                raise ValueError("SWE-bench seed must be clean and checked out at base_commit")
        normalized.append(task)
    if benchmark != "custom":
        reject_frozen_overlap(list(seen), benchmark=benchmark, allow_frozen_test_set=False)
    return benchmark, normalized


def agent_arguments(task: dict, run_root: Path, extra: list[str]) -> list[str]:
    parser = agent_parser()
    parser.allow_abbrev = False
    reserved = {"--goal", "--workspace", "--run-root", "--success-criterion", "--constraint"}
    if any(arg.split("=", 1)[0] in reserved for arg in extra):
        raise ValueError("Task fields/run-root must be configured through the manifest, not agent arguments")
    args = ["--goal", task["goal"], "--workspace", task["workspace"], "--run-root", str(run_root)]
    for field, flag in (("success_criteria", "--success-criterion"), ("constraints", "--constraint")):
        for value in task[field]:
            args.extend([flag, value])
    args.extend(extra)
    parser.parse_args(args)
    return args


def method_arguments(method: str, extra: list[str]) -> tuple[str, list[str]]:
    """Freeze the four causal arms instead of relying on ad-hoc CLI choices."""
    if method == "bestfgs":
        return "bestfgs", list(extra)
    if method == "evidence_custom":
        # Development-only sequential controller used by the blocker ablation.
        return "bestfgs", list(extra)
    if method == "raw":
        return "bestfgs.raw_baseline", list(extra)
    controlled = {
        "--engine", "--experience-mode", "--disable-evidence-branching",
        "--blocking-memory",
    }
    if any(item.split("=", 1)[0] in controlled for item in extra):
        raise ValueError(
            f"{method} fixes engine/experience/branching; remove conflicting agent flags"
        )
    if method == "memory_only":
        return "bestfgs", [
            *extra, "--engine", "evidence", "--experience-mode", "conditioned",
            "--disable-evidence-branching", "--blocking-memory", "off",
        ]
    if method == "search_only":
        return "bestfgs", [
            *extra, "--engine", "graph", "--experience-mode", "off",
            "--blocking-memory", "off",
        ]
    raise ValueError(f"Unknown method: {method}")


def child_environment(python: Path, task_python: Path | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    # The agent is launched with an explicit >=3.11 executable; task commands
    # named python/python3 and /usr/bin/env python use the prepared task runtime.
    task_bin = str(task_python.parent) + os.pathsep if task_python else ""
    env["PATH"] = task_bin + str(python.parent) + os.pathsep + env.get("PATH", "")
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


@contextmanager
def run_lock(root: Path):
    """OS lock releases on crashes; two runners cannot share the same output root."""
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".runner.lock").open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "posix":
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise ValueError("Another runner owns this output root") from exc
        try:
            yield
        finally:
            if os.name == "posix":
                fcntl.flock(stream, fcntl.LOCK_UN)
            else:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def stop_child(process: subprocess.Popen) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif process.poll() is None:
        process.kill()
    process.wait()


def execute(command: list[str], directory: Path, env: dict, timeout: float) -> int:
    # Logs stream directly to persistent files, not an unbounded memory buffer.
    with (directory / "agent-result.json").open("w", encoding="utf-8") as stdout, (directory / "agent.log").open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr, env=env, cwd=PROJECT_ROOT, start_new_session=os.name == "posix")
        try:
            return process.wait(timeout=timeout)
        finally:
            # Also terminate background descendants after a normally exiting agent.
            stop_child(process)


def export_swe_patch(candidate: Path | None, base_commit: str, attempt: Path, *, delivery: dict | None = None) -> str:
    """Export the same task-base artifact that the runtime inspects."""
    target = attempt / "model.patch"
    if candidate is not None and target.resolve().is_relative_to(candidate.resolve()):
        raise SubmissionError("Patch output must be outside the candidate workspace")
    patch_bytes = inspect_git_submission(candidate, base_commit).patch if candidate is not None else b""
    patch_sha256 = hashlib.sha256(patch_bytes).hexdigest()
    if delivery is not None:
        if bool(patch_bytes) != delivery["has_patch"]:
            raise ValueError("Runtime delivery/exported patch presence disagree")
        declared_hash = delivery.get("patch_sha256")
        if (patch_bytes or declared_hash is not None) and declared_hash != patch_sha256:
            raise ValueError("Runtime delivery/exported patch hash disagree")
    # Validate before publishing, and write exactly the bytes whose hash matched.
    target.write_bytes(patch_bytes)
    return patch_bytes.decode("utf-8", errors="surrogateescape")


def validate_result_artifact(result: dict, *, code: int | None, attempt: Path, benchmark: str, task: dict) -> tuple[dict, str | None]:
    """Use one path/type/hash gate for normal results and rescued checkpoints."""
    if not isinstance(result, dict) or not isinstance(result.get("succeeded"), bool):
        raise ValueError("Agent result must contain a boolean succeeded field")
    if result.get("official_resolved") is not None:
        raise ValueError("Local result cannot declare official_resolved")
    delivery = result.get("delivery")
    if "delivery" in result and (
        not isinstance(delivery, dict)
        or not isinstance(delivery.get("has_patch"), bool)
        or not isinstance(delivery.get("status"), str)
    ):
        raise ValueError("delivery must identify artifact status and has_patch")
    if delivery is None and code is not None and (code == 0) != result["succeeded"]:
        raise ValueError("Agent exit code/result disagree")
    candidate = result.get("best_workspace")
    if candidate is not None and not isinstance(candidate, str):
        raise ValueError("best_workspace must be a path string or null")
    if candidate:
        candidate_path = Path(candidate).resolve()
        snapshot_root = (attempt / "snapshots").resolve()
        if (candidate_path == snapshot_root or not candidate_path.is_relative_to(snapshot_root)
                or not candidate_path.is_relative_to(attempt.resolve())):
            raise ValueError("Candidate is outside this task's snapshots")
        if not candidate_path.is_dir():
            raise ValueError("Candidate directory is missing")
    if result["succeeded"] and not candidate:
        raise ValueError("Successful result requires a candidate directory")
    details = {"agent_succeeded": result["succeeded"], "best_workspace": candidate}
    if delivery is not None:
        if delivery.get("official_resolved") is not None:
            raise ValueError("Local delivery cannot declare official_resolved")
        if delivery["has_patch"] and not candidate:
            raise ValueError("Delivered artifact requires a candidate directory")
        if code == 0 and not delivery["has_patch"]:
            raise ValueError("Normal delivery exit requires a nonempty artifact")
        if delivery["status"] == "submitted" and not delivery["has_patch"]:
            raise ValueError("Submitted delivery requires a nonempty artifact")
        submitted = result.get("submitted", delivery["status"] == "submitted")
        if not isinstance(submitted, bool) or submitted != (delivery["status"] == "submitted"):
            raise ValueError("Submitted flag/delivery status disagree")
        local_validation = delivery.get("local_validation_passed", False)
        if not isinstance(local_validation, bool):
            raise ValueError("local_validation_passed must be boolean")
        details.update(delivery=delivery, submitted=submitted,
                       local_validation_passed=local_validation, official_resolved=None)
    patch = None
    if benchmark == "swebench":
        patch = export_swe_patch(Path(candidate) if candidate else None,
                                 task.get("prepared_commit", task["base_commit"]), attempt,
                                 delivery=delivery)
        details["patch_sha256"] = hashlib.sha256((attempt / "model.patch").read_bytes()).hexdigest()
    return details, patch


def load_rescue_checkpoint(attempt: Path, original_error: str) -> dict:
    """Read only this attempt's checkpoint and demote it to an interrupted draft."""
    checkpoint = attempt / "snapshots" / "search_checkpoint.json"
    if not checkpoint.resolve().is_relative_to(attempt.resolve()):
        raise ValueError("Checkpoint is outside this task's attempt")
    result = json.loads(checkpoint.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError("Checkpoint must be an object")
    delivery = result.get("delivery")
    if (not isinstance(delivery, dict) or delivery.get("has_patch") is not True
            or not isinstance(delivery.get("patch_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", delivery["patch_sha256"])):
        raise ValueError("Checkpoint requires a nonempty artifact and its runtime hash")
    if result.get("official_resolved") is not None or delivery.get("official_resolved") is not None:
        raise ValueError("Checkpoint cannot declare official_resolved")
    result["checkpoint_stop_reason"] = result.get("stop_reason")
    result.update(succeeded=False, verified_success=False, submitted=False,
                  official_resolved=None, stop_reason="runtime_error_with_checkpoint",
                  error=original_error, checkpoint_path=str(checkpoint))
    delivery.update(status="draft", submitted=False, official_resolved=None)
    # Other fields, including any recorded model_usage, remain checkpoint evidence.
    return result


def run(args: argparse.Namespace, extra: list[str]) -> int:
    output = args.output_root.resolve()
    benchmark, tasks = load_tasks(args.task_manifest.resolve(), output)
    python = args.python.resolve()
    if not python.is_file():
        raise ValueError(f"Python interpreter not found: {python}")
    if not math.isfinite(args.task_timeout) or args.task_timeout <= 0:
        raise ValueError("task-timeout must be finite and positive")
    task_python = args.task_python.resolve() if args.task_python else None
    if task_python and not task_python.is_file():
        raise ValueError(f"Task Python interpreter not found: {task_python}")
    env = child_environment(python, task_python)
    module, effective_extra = method_arguments(args.method, extra)
    validated = agent_parser().parse_args(
        agent_arguments(tasks[0], output / "plan", effective_extra)
    )
    if args.method == "bestfgs" and (
        validated.engine != "graph"
        or validated.experience_mode != "conditioned"
        or validated.blocking_memory != "off"
    ):
        raise ValueError(
            "bestfgs arm requires graph engine, conditioned experience, and blocking memory off"
        )
    for task in tasks[1:]:
        agent_arguments(task, output / "plan", effective_extra)
    # Only nonsecret model settings enter provenance. Credentials stay in environment.
    model_environment = {name: env.get(name) for name in (
        "OPENAI_MODEL", "DEEPSEEK_MODEL", "DASHSCOPE_MODEL",
        "OPENAI_API_BASE", "OPENAI_BASE_URL", "DEEPSEEK_API_BASE", "DASHSCOPE_API_BASE"
    )}
    for url in [validated.base_url, *[value for name, value in model_environment.items() if name.endswith(("API_BASE", "BASE_URL"))]]:
        if url and (urlsplit(url).username or urlsplit(url).query or urlsplit(url).fragment):
            raise ValueError("API URLs must not contain credentials/query tokens; use API key environment variables")
    provenance = {
        "benchmark": benchmark, "tasks": tasks, "agent_args": effective_extra,
        "python": str(python), "implementation_sha256": implementation_sha256(PROJECT_ROOT),
        "task_python": str(task_python) if task_python else None,
        "task_timeout": args.task_timeout, "model_environment": model_environment,
        "execution_backend": "notebook-local", "official_evaluation": False,
        "success_judge_mode": "off",
    }
    if getattr(args, "method", "bestfgs") != "bestfgs":
        provenance["method"] = args.method
    if args.dry_run:
        print(json.dumps(provenance, ensure_ascii=False, indent=2))
        return 0
    probe = subprocess.run([str(python), "-c", "import sys,bestfgs; assert sys.version_info >= (3,11), 'Python >=3.11 required'; print(sys.version)"], env=env, capture_output=True, text=True, timeout=30)
    if probe.returncode:
        raise ValueError(f"Notebook Python preflight failed: {probe.stderr.strip()}")
    if task_python:
        task_probe = subprocess.run([str(task_python), "-c", "import sys; print(sys.version)"], env=env, capture_output=True, text=True, timeout=30)
        if task_probe.returncode:
            raise ValueError(f"Task Python preflight failed: {task_probe.stderr.strip()}")
    key_name = validated.api_key_env or PROVIDER_DEFAULTS[validated.provider].api_key_env
    if not env.get(key_name):
        raise ValueError(f"Missing API key environment variable: {key_name}")
    config = RetracModelConfig.from_environment(provider=validated.provider, model_name=validated.model, base_url=validated.base_url, api_key_env=validated.api_key_env)
    fingerprint = canonical_sha256(provenance)
    with run_lock(output):
        manifest_path = output / "notebook-run.json"
        if manifest_path.exists():
            previous = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not args.resume or previous.get("fingerprint") != fingerprint:
                raise ValueError("Existing run: use --resume with unchanged seeds/code/config, or a new output-root")
        elif args.resume:
            raise ValueError("No existing run to resume")
        atomic_write_json(manifest_path, {**provenance, "fingerprint": fingerprint})
        summary = []
        predictions = []
        for task in tasks:
            task_root = output / task["id"]
            state_path = task_root / "status.json"
            state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
            prior_result = Path(state.get("attempt", "")) / "agent-result.json"
            reusable = (prior_result.is_file() and state.get("result_sha256") == hashlib.sha256(prior_result.read_bytes()).hexdigest()
                        and (not state.get("best_workspace") or Path(state["best_workspace"]).is_dir())
                        and (benchmark != "swebench" or (
                            (Path(state.get("attempt", "")) / "model.patch").is_file()
                            and (not state.get("patch_sha256") or state["patch_sha256"] == hashlib.sha256(
                                (Path(state["attempt"]) / "model.patch").read_bytes()).hexdigest()))))
            if args.resume and state.get("status") == "completed" and reusable:
                print(f"[skip] {task['id']}", flush=True)
                summary.append(state)
                if benchmark == "swebench":
                    predictions.append({"instance_id": task["id"], "model_name_or_path": config.model_name, "model_patch": (Path(state["attempt"]) / "model.patch").read_bytes().decode("utf-8", errors="surrogateescape")})
                continue
            attempt = task_root / ("attempt-" + uuid.uuid4().hex)
            attempt.mkdir(parents=True)
            state = {"id": task["id"], "status": "running", "attempt": str(attempt), "official_evaluation": False}
            atomic_write_json(state_path, state)
            print(f"[run] {task['id']} | log: {attempt / 'agent.log'}", flush=True)
            command = [str(python), "-m", module,
                       *agent_arguments(task, attempt / "snapshots", effective_extra)]
            code = None
            try:
                code = execute(command, attempt, env, args.task_timeout)
                if code not in (0, 1):
                    raise ValueError(f"Agent failed with exit code {code}; see agent.log")
                result = json.loads((attempt / "agent-result.json").read_text(encoding="utf-8"))
                details, patch = validate_result_artifact(
                    result, code=code, attempt=attempt, benchmark=benchmark, task=task,
                )
                state.update(details)
                state.update(status="completed", exit_code=code,
                             result_sha256=hashlib.sha256((attempt / "agent-result.json").read_bytes()).hexdigest())
                if result.get("stop_reason") == "runtime_error_with_checkpoint":
                    state.update(status="error", error="Agent runtime error; checkpoint/candidate preserved, see agent.log")
                if result.get("stop_reason") == "model_unavailable":
                    if result.get("model_usage", {}).get("last_failure_kind") == "model_output":
                        state["model_output_failure"] = True
                    else:
                        state.update(status="error", error="Model unavailable; explicit resume may retry this infrastructure failure")
                if benchmark == "swebench":
                    prediction = {"instance_id": task["id"], "model_name_or_path": config.model_name, "model_patch": patch}
                    if state["status"] == "error":
                        prediction.update(status="error", error=state["error"])
                    predictions.append(prediction)
            except KeyboardInterrupt:
                state.update(status="interrupted")
                atomic_write_json(state_path, state)
                raise
            except (OSError, ValueError, SubmissionError, subprocess.SubprocessError) as exc:
                original_error = str(exc)
                state.update(status="error", error=original_error, exit_code=code,
                             stop_reason="process_timeout" if isinstance(exc, subprocess.TimeoutExpired)
                             else "process_exit_error" if code not in (None, 0, 1) else "runner_error")
                try:
                    result = load_rescue_checkpoint(attempt, original_error)
                    details, patch = validate_result_artifact(
                        result, code=None, attempt=attempt, benchmark=benchmark, task=task,
                    )
                    # Keep partial/invalid stdout as evidence before publishing the
                    # checkpoint under the existing result-file contract.
                    result_path = attempt / "agent-result.json"
                    if result_path.exists():
                        result_path.replace(attempt / "agent-result.process-output.txt")
                    atomic_write_json(result_path, result)
                    state.update(details, artifact_rescued=True,
                                 checkpoint_path=result["checkpoint_path"],
                                 result_sha256=hashlib.sha256(result_path.read_bytes()).hexdigest())
                    if "model_usage" in result:
                        state["model_usage"] = result["model_usage"]
                    if benchmark == "swebench":
                        predictions.append({"instance_id": task["id"], "model_name_or_path": config.model_name,
                                            "model_patch": patch, "status": "error", "error": original_error})
                except (OSError, ValueError, SubmissionError, subprocess.SubprocessError) as recovery_error:
                    state["checkpoint_recovery_error"] = str(recovery_error)
            atomic_write_json(state_path, state)
            summary.append(state)
            atomic_write_json(output / "summary.json", summary)
            if benchmark == "swebench":
                atomic_write_text(output / "predictions.jsonl", "".join(json.dumps(item, ensure_ascii=True) + "\n" for item in predictions))
        atomic_write_json(output / "summary.json", summary)
        if benchmark == "swebench":
            atomic_write_text(output / "predictions.jsonl", "".join(json.dumps(item, ensure_ascii=True) + "\n" for item in predictions))
    return 2 if any(item["status"] != "completed" for item in summary) else 0


def main(argv: list[str] | None = None, *, expected_benchmark: str | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run prepared tasks inside a Cube-Studio Notebook; no nested Docker", allow_abbrev=False)
    parser.add_argument("--task-manifest", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path, help="Persistent /mnt/<NETID>/... directory, outside seeds")
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--task-python", type=Path, help="Optional separate Python for task commands; the BestFGS agent still uses --python >=3.11")
    parser.add_argument("--task-timeout", type=float, default=14400)
    parser.add_argument(
        "--method", choices=("bestfgs", "raw", "memory_only", "search_only", "evidence_custom"),
        default="bestfgs",
        help="Frozen 2x2 arm: graph+memory, sequential bare, memory only, or graph only",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("agent_args", nargs=argparse.REMAINDER, help="After --, pass the existing BestFGS model/search flags")
    args = parser.parse_args(argv)
    extra = args.agent_args[1:] if args.agent_args[:1] == ["--"] else args.agent_args
    previous_term = None
    if os.name == "posix":
        def terminate(signum, frame):
            raise KeyboardInterrupt
        previous_term = signal.signal(signal.SIGTERM, terminate)
    try:
        if expected_benchmark:
            data = json.loads(args.task_manifest.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("benchmark") != expected_benchmark:
                raise ValueError(f"This launcher requires benchmark={expected_benchmark}")
        return run(args, extra)
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"[notebook error] {exc}", file=sys.stderr)
        return 2
    finally:
        if previous_term is not None:
            signal.signal(signal.SIGTERM, previous_term)


if __name__ == "__main__":
    raise SystemExit(main())
