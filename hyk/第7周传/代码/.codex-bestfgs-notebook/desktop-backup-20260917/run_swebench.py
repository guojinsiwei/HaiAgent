"""用当前 BestFGS 模型运行 SWE-bench Verified 随机子集。

执行流程：读取公开问题描述 -> 在该实例的官方 Docker 镜像中调用模型 ->
提取模型产生的 git patch -> 交给 SWE-bench 官方 harness -> 显示解决率。

本文件不会读取 gold patch 或 test patch，也不会把参考答案交给模型。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import secrets
import shlex
import subprocess
import sys
import time
import uuid
import threading
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from benchmark_metrics import (
    print_official_interaction_summary,
    summarize_official_interactions,
    swe_official_outcomes,
    print_research_metrics,
    summarize_interaction_rounds,
    summarize_research_metrics,
)
from benchmark_selection import development_selection
from benchmark_runtime import (
    atomic_write_json,
    atomic_write_text,
    base_manifest,
    canonical_sha256,
    public_endpoint,
)
from benchmark_splits import (
    FrozenTestSetError,
    frozen_swebench_ids,
    reject_frozen_overlap,
)


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DOCKER_EXECUTABLE = (
    r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
)
DEFAULT_DATASET = "SWE-bench/SWE-bench_Verified"
DEFAULT_SAMPLE_FRACTION = 0.1
MAX_SIMULTANEOUS_AGENT_LOGS = 2
_CONSOLE_LOCK = threading.Lock()
_ACTIVE_PROCESS_LOCK = threading.Lock()
_ACTIVE_PROCESSES: set[subprocess.Popen[str]] = set()

# 旧版固定子集仅保留给外部代码兼容；默认入口改为从完整数据集随机抽样。
DEFAULT_INSTANCE_IDS = (
    "astropy__astropy-12907",
    "django__django-11099",
    "matplotlib__matplotlib-22865",
    "pallets__flask-5014",
    "psf__requests-2317",
    "pydata__xarray-4356",
    "pytest-dev__pytest-7432",
    "scikit-learn__scikit-learn-14087",
    "sphinx-doc__sphinx-8551",
    "sympy__sympy-20590",
    "astropy__astropy-13033",
    "django__django-10914",
    "matplotlib__matplotlib-22719",
    "mwaskom__seaborn-3069",
    "psf__requests-6028",
    "pydata__xarray-4075",
    "pylint-dev__pylint-4551",
    "sympy__sympy-12419",
)


def _random_sample(
    population: list[str] | tuple[str, ...],
    *,
    fraction: float,
    seed: int,
    sample_size: int | None = None,
) -> list[str]:
    """按稳定全集顺序随机抽样；同一seed可精确复现实验题目与执行顺序。"""
    if not 0 < fraction <= 1:
        raise ValueError("sample fraction must be in (0, 1]")
    unique = sorted(dict.fromkeys(population))
    if not unique:
        raise ValueError("sample population must not be empty")
    selected_size = (
        sample_size
        if sample_size is not None
        else max(1, math.ceil(len(unique) * fraction))
    )
    if not 1 <= selected_size <= len(unique):
        raise ValueError(
            f"sample size must be between 1 and {len(unique)}"
        )
    return random.Random(seed).sample(unique, selected_size)


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _console_print(
    message: str,
    *,
    prefix: str = "",
    file=None,
    end: str = "\n",
) -> None:
    """Keep each concurrent task log line atomic and identifiable."""

    with _CONSOLE_LOCK:
        print(prefix + message, file=file, end=end, flush=True)


def _terminate_active_processes() -> None:
    """Stop worker-owned Docker exec processes when the user presses Ctrl+C."""

    with _ACTIVE_PROCESS_LOCK:
        processes = tuple(_ACTIVE_PROCESSES)
    for process in processes:
        if process.poll() is None:
            process.terminate()


def _validate_name(value: str, label: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
        raise argparse.ArgumentTypeError(
            f"{label} 只能包含字母、数字、下划线、点和连字符"
        )
    return value


def _wsl_command(distro: str, script: str) -> list[str]:
    return ["wsl.exe", "-d", distro, "--", "bash", "-lc", script]


def _run_capture(
    command: list[str],
    *,
    input_text: str | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )


def _preflight_runtime(args: argparse.Namespace) -> dict[str, Any]:
    """Fail before any API call when Docker/WSL/the official harness is unusable."""

    host = _run_capture(
        [args.docker_executable, "version", "--format", "{{.Server.Version}}"]
    )
    if host.returncode != 0 or not host.stdout.strip():
        raise RuntimeError(
            "Windows Docker daemon不可用："
            + (host.stderr.strip() or host.stdout.strip() or "docker version失败")
        )
    probe = (
        "import importlib.metadata as m, json; "
        "import docker, swebench; "
        "client=docker.from_env(); client.ping(); "
        "print(json.dumps({'swebench': m.version('swebench'), "
        "'docker_server': client.version().get('Version', 'unknown')}))"
    )
    shell = (
        f"cd {shlex.quote(args.repo)} && "
        "test -x .venv/bin/python && "
        f".venv/bin/python -c {shlex.quote(probe)}"
    )
    wsl = _run_capture(_wsl_command(args.distro, shell))
    if wsl.returncode != 0:
        raise RuntimeError(
            "WSL中的SWE-bench harness或Docker连接不可用："
            + (wsl.stderr.strip() or wsl.stdout.strip() or "preflight失败")
        )
    try:
        details = json.loads(wsl.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise RuntimeError("WSL preflight未返回有效版本信息") from exc
    return {
        "windows_docker_server": host.stdout.strip(),
        "wsl_swebench": details.get("swebench"),
        "wsl_docker_server": details.get("docker_server"),
    }


def _run_streaming(
    command: list[str], *, input_text: str | None = None, line_prefix: str = ""
) -> tuple[int, list[str]]:
    """实时显示子进程输出；API Key 可经 stdin 传入而不出现在命令行。"""
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE if input_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    with _ACTIVE_PROCESS_LOCK:
        _ACTIVE_PROCESSES.add(process)
    if input_text is not None:
        assert process.stdin is not None
        # Windows 的文本流默认把 \n 写成 CRLF；Docker 会把残留的 \r
        # 一并传给 Linux bash，最终污染 Authorization 请求头。
        process.stdin.reconfigure(newline="\n")
        process.stdin.write(input_text)
        process.stdin.close()

    lines: list[str] = []
    assert process.stdout is not None
    try:
        for line in process.stdout:
            lines.append(line)
            _console_print(line, prefix=line_prefix, end="")
        return process.wait(), lines
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        raise
    finally:
        with _ACTIVE_PROCESS_LOCK:
            _ACTIVE_PROCESSES.discard(process)
        process.stdout.close()


def _docker_image(instance_id: str, namespace: str, arch: str) -> str:
    normalized = instance_id.lower().replace("__", "_1776_")
    return f"{namespace}/sweb.eval.{arch}.{normalized}:latest"


def _docker_image_exists(docker_executable: str, image: str) -> bool:
    return (
        _run_capture(
            [docker_executable, "image", "inspect", image]
        ).returncode
        == 0
    )


def _pull_image(
    args: argparse.Namespace,
    image: str,
    *,
    log_prefix: str = "",
) -> bool:
    if _docker_image_exists(args.docker_executable, image):
        _console_print("本地镜像已存在。", prefix=log_prefix)
        return True
    if args.skip_image_pull:
        _console_print(
            "本地镜像不存在，且已设置 --skip-image-pull。",
            prefix=log_prefix,
            file=sys.stderr,
        )
        return False

    for attempt in range(1, args.image_pull_attempts + 1):
        _console_print(
            f"镜像拉取尝试 {attempt}/{args.image_pull_attempts}",
            prefix=log_prefix,
        )
        code, _ = _run_streaming(
            [args.docker_executable, "pull", image],
            line_prefix=log_prefix,
        )
        if code == 0:
            return True
        if attempt < args.image_pull_attempts:
            delay = min(2**attempt, 30)
            _console_print(f"{delay}秒后重新拉取", prefix=log_prefix)
            time.sleep(delay)
    return False


def _to_wsl_path(distro: str, path: Path) -> str:
    resolved = str(path.resolve())
    drive_match = re.fullmatch(r"([A-Za-z]):[\\/](.*)", resolved)
    if drive_match:
        drive, remainder = drive_match.groups()
        return f"/mnt/{drive.lower()}/{remainder.replace(chr(92), '/')}"

    # 非盘符路径再交给 WSL 处理，例如用户主动传入的 UNC 路径。
    completed = _run_capture(
        [
            "wsl.exe",
            "-d",
            distro,
            "--",
            "wslpath",
            "-a",
            resolved,
        ],
        check=True,
    )
    return completed.stdout.strip()


def _load_public_tasks(
    args: argparse.Namespace, instance_ids: list[str]
) -> dict[str, str]:
    """只读取 instance_id 与公开 problem_statement，不读取参考补丁。"""
    code = "\n".join(
        [
            "import json",
            "from datasets import load_dataset",
            f"wanted = set(json.loads({json.dumps(json.dumps(instance_ids))}))",
            f"dataset = load_dataset({args.dataset!r}, split='test')",
            (
                "records = [{'instance_id': row['instance_id'], "
                "'problem_statement': row['problem_statement']} "
                "for row in dataset if row['instance_id'] in wanted]"
            ),
            "print(json.dumps(records, ensure_ascii=False))",
        ]
    )
    shell = (
        f"cd {shlex.quote(args.repo)} && "
        f".venv/bin/python -c {shlex.quote(code)}"
    )
    completed = _run_capture(_wsl_command(args.distro, shell))
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    records = json.loads(completed.stdout)
    mapping = {item["instance_id"]: item["problem_statement"] for item in records}
    missing = [instance_id for instance_id in instance_ids if instance_id not in mapping]
    if missing:
        raise RuntimeError(f"数据集中找不到实例：{missing}")
    return mapping


def _load_all_instance_ids(args: argparse.Namespace) -> list[str]:
    """从公开test split读取完整instance_id清单，不接触参考补丁字段。"""
    code = "\n".join(
        [
            "import json",
            "from datasets import load_dataset",
            f"dataset = load_dataset({args.dataset!r}, split='test')",
            "print(json.dumps([row['instance_id'] for row in dataset]))",
        ]
    )
    shell = (
        f"cd {shlex.quote(args.repo)} && "
        f".venv/bin/python -c {shlex.quote(code)}"
    )
    completed = _run_capture(_wsl_command(args.distro, shell))
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    instance_ids = json.loads(completed.stdout)
    if not isinstance(instance_ids, list) or not all(
        isinstance(item, str) and item for item in instance_ids
    ):
        raise RuntimeError("SWE-bench数据集返回了无效的instance_id清单")
    if len(instance_ids) != len(set(instance_ids)):
        raise RuntimeError("SWE-bench数据集包含重复instance_id")
    return instance_ids


def _model_defaults(provider: str) -> tuple[str, str, str]:
    if provider == "deepseek":
        return (
            os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            "DEEPSEEK_API_KEY",
        )
    if provider == "dashscope":
        return (
            os.getenv("DASHSCOPE_MODEL", "qwen3.7-plus-2026-05-26"),
            os.getenv(
                "DASHSCOPE_API_BASE",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
            "DASHSCOPE_API_KEY",
        )
    return (
        os.getenv("OPENAI_MODEL", "gpt-4o"),
        os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "OPENAI_API_KEY",
    )


def _clean_api_key(value: str | None) -> str:
    """清除复制粘贴和 Windows CRLF 传输产生的首尾空白。"""
    return (value or "").strip()


def _agent_shell_command(
    args: argparse.Namespace,
    *,
    problem_statement: str,
    provider: str,
    model: str,
    base_url: str,
    key_name: str,
    judge_provider: str | None = None,
    judge_model: str | None = None,
    judge_base_url: str | None = None,
    judge_key_name: str = "SUCCESS_JUDGE_API_KEY",
) -> str:
    """生成容器内命令；Key 从 stdin 第一行读取，不拼入命令字符串。"""
    # 一些测试或外部调用会用精简的 Namespace；这里保留向后兼容默认值。
    temperature = getattr(args, "temperature", 0.2)
    top_p = getattr(args, "top_p", None)
    reasoning_effort = getattr(args, "reasoning_effort", "high")
    solve_reasoning_effort = getattr(args, "solve_reasoning_effort", "max")
    budget_multiplier = getattr(args, "budget_multiplier", 1.0)
    base_children_per_node = getattr(args, "base_children_per_node", 3)
    max_children_per_node = getattr(args, "max_children_per_node", 6)
    disable_semantic_node_merge = getattr(args, "disable_semantic_node_merge", False)
    semantic_merge_fact_threshold = getattr(args, "semantic_merge_fact_threshold", 0.90)
    semantic_merge_issue_threshold = getattr(args, "semantic_merge_issue_threshold", 0.80)
    success_judge_mode = getattr(args, "success_judge_mode", "required")
    success_judge_max_calls = getattr(args, "success_judge_max_calls", 3)
    cli_args = [
        "-m",
        "bestfgs",
        "--provider",
        provider,
        "--model",
        model,
        "--base-url",
        base_url,
        "--goal",
        problem_statement,
        "--success-criterion",
        "修复问题描述中的缺陷，同时保持现有行为与测试兼容",
        "--constraint",
        "只修改 /testbed 中的实现代码，不读取参考补丁，不修改测试来伪造通过",
        "--workspace",
        "/testbed",
        "--run-root",
        "/tmp/bestfgs/swebench-task",
        "--max-iterations",
        str(args.max_iterations),
        "--max-tool-calls",
        str(args.max_tool_calls),
        "--budget-multiplier",
        str(budget_multiplier),
        "--model-timeout",
        str(args.model_timeout),
        "--model-max-wall-time",
        str(args.model_max_wall_time),
        "--model-request-attempts",
        str(args.model_request_attempts),
        "--model-parse-attempts",
        str(args.model_parse_attempts),
        "--temperature",
        str(temperature),
        "--reasoning-effort",
        reasoning_effort,
        "--solve-reasoning-effort",
        solve_reasoning_effort,
        "--base-children-per-node",
        str(base_children_per_node),
        "--max-children-per-node",
        str(max_children_per_node),
        "--semantic-merge-fact-threshold",
        str(semantic_merge_fact_threshold),
        "--semantic-merge-issue-threshold",
        str(semantic_merge_issue_threshold),
        "--success-judge-mode",
        success_judge_mode,
        "--success-judge-max-calls",
        str(success_judge_max_calls),
    ]
    if success_judge_mode != "off":
        cli_args.extend(
            [
                "--success-judge-provider",
                judge_provider or provider,
                "--success-judge-model",
                judge_model or model,
                "--success-judge-base-url",
                judge_base_url or base_url,
                "--success-judge-api-key-env",
                judge_key_name,
            ]
        )
    if disable_semantic_node_merge:
        cli_args.append("--disable-semantic-node-merge")
    if top_p is not None:
        cli_args.extend(["--top-p", str(top_p)])
    quoted_args = " ".join(shlex.quote(item) for item in cli_args)
    return "\n".join(
        [
            "set +e",
            "IFS= read -r RETRAC_API_KEY",
            "RETRAC_API_KEY=${RETRAC_API_KEY//$'\\r'/}",
            f"export {key_name}=\"$RETRAC_API_KEY\"",
            "IFS= read -r SUCCESS_AUDIT_KEY",
            "SUCCESS_AUDIT_KEY=${SUCCESS_AUDIT_KEY//$'\\r'/}",
            f"export {judge_key_name}=\"$SUCCESS_AUDIT_KEY\"",
            (
                "PYTHON_BIN=''\n"
                "for candidate in python3.13 python3.12 python3.11 python3.10 python3; do\n"
                "  if command -v \"$candidate\" >/dev/null 2>&1 && "
                "\"$candidate\" -c 'import sys; raise SystemExit("
                "sys.version_info < (3, 10))' 2>/dev/null; then\n"
                "    PYTHON_BIN=$(command -v \"$candidate\")\n"
                "    break\n"
                "  fi\n"
                "done"
            ),
            (
                "if [ -z \"$PYTHON_BIN\" ]; then "
                "echo '实例镜像中没有 Python 3.10+，无法运行 Agent' >&2; exit 86; fi"
            ),
            (
                "PYTHONPATH=/installed-agent/src \"$PYTHON_BIN\" "
                f"{quoted_args} > /tmp/retrac_result.json"
            ),
            "agent_code=$?",
            (
                "if [ ! -s /tmp/retrac_result.json ] && "
                "[ -s /tmp/bestfgs/swebench-task/search_checkpoint.json ]; then "
                "cp /tmp/bestfgs/swebench-task/search_checkpoint.json "
                "/tmp/retrac_result.json; fi"
            ),
            (
                "if [ ! -s /tmp/retrac_result.json ]; then exit $agent_code; fi"
            ),
            # 即使 checkpoint 可用，也保留 Agent 的真实退出码。宿主会先提取
            # checkpoint/补丁，再把这次执行标成可恢复异常，避免把崩溃伪装成完成。
            "exit $agent_code",
        ]
    )


def _container_result(
    docker_executable: str, container_name: str
) -> dict[str, Any]:
    completed = _run_capture(
        [docker_executable, "exec", container_name, "cat", "/tmp/retrac_result.json"]
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "模型结果文件不存在")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"模型结果不是合法 JSON：{exc}") from exc


def _extract_patch(
    docker_executable: str,
    container_name: str,
    best_workspace: str,
) -> str:
    # intent-to-add 让 git diff 同时包含模型新建但尚未跟踪的文件。
    add_result = _run_capture(
        [
            docker_executable,
            "exec",
            container_name,
            "git",
            "-C",
            best_workspace,
            "add",
            "-N",
            ".",
        ]
    )
    if add_result.returncode != 0:
        raise RuntimeError(add_result.stderr.strip() or "git add -N 失败")
    diff_result = _run_capture(
        [
            docker_executable,
            "exec",
            container_name,
            "git",
            "-C",
            best_workspace,
            "diff",
            "--binary",
            "--no-ext-diff",
        ]
    )
    if diff_result.returncode != 0:
        raise RuntimeError(diff_result.stderr.strip() or "git diff 失败")
    return diff_result.stdout


def _run_one_instance(
    args: argparse.Namespace,
    *,
    index: int,
    total: int,
    instance_id: str,
    problem_statement: str,
    provider: str,
    model: str,
    base_url: str,
    key_name: str,
    api_key: str,
    judge_provider: str,
    judge_model: str,
    judge_base_url: str,
    judge_api_key: str,
) -> tuple[dict[str, str], dict[str, Any]]:
    image = _docker_image(instance_id, args.namespace, args.arch)
    container_name = f"best-fgs-swe-{index}-{uuid.uuid4().hex[:8]}"
    log_prefix = f"[SWE {index:02d}/{total} {instance_id}] "
    prediction = {
        "instance_id": instance_id,
        "model_name_or_path": f"best-fgs/{provider}/{model}",
        "model_patch": "",
    }
    metadata: dict[str, Any] = {
        "instance_id": instance_id,
        "image": image,
        "agent_succeeded": False,
        "agent_interaction_rounds": None,
        "patch_chars": 0,
        "agent_exit_code": None,
    }

    _console_print("========== Agent启动 ==========", prefix=log_prefix)
    _console_print(f"镜像：{image}", prefix=log_prefix)
    if not _pull_image(args, image, log_prefix=log_prefix):
        metadata["error"] = "实例镜像不可用"
        metadata["execution_status"] = "retryable_error"
        metadata["retryable"] = True
        return prediction, metadata

    try:
        create = _run_capture(
            [
                args.docker_executable,
                "create",
                "--name",
                container_name,
                "--user",
                "root",
                "--entrypoint",
                "tail",
                image,
                "-f",
                "/dev/null",
            ]
        )
        if create.returncode != 0:
            raise RuntimeError(create.stderr.strip() or "docker create 失败")
        start = _run_capture(
            [args.docker_executable, "start", container_name]
        )
        if start.returncode != 0:
            raise RuntimeError(start.stderr.strip() or "docker start 失败")

        mkdir = _run_capture(
            [
                args.docker_executable,
                "exec",
                container_name,
                "mkdir",
                "-p",
                "/installed-agent",
            ]
        )
        if mkdir.returncode != 0:
            raise RuntimeError(mkdir.stderr.strip() or "创建 Agent 目录失败")
        copy = _run_capture(
            [
                args.docker_executable,
                "cp",
                str(PROJECT_ROOT / "src"),
                f"{container_name}:/installed-agent/",
            ]
        )
        if copy.returncode != 0:
            raise RuntimeError(copy.stderr.strip() or "复制 Agent 源码失败")

        shell = _agent_shell_command(
            args,
            problem_statement=problem_statement,
            provider=provider,
            model=model,
            base_url=base_url,
            key_name=key_name,
            judge_provider=judge_provider,
            judge_model=judge_model,
            judge_base_url=judge_base_url,
        )
        _console_print(
            "开始调用当前 BestFGS；下面实时显示模型进度",
            prefix=log_prefix,
        )
        agent_code, _ = _run_streaming(
            [
                args.docker_executable,
                "exec",
                "-i",
                "--user",
                "root",
                container_name,
                "bash",
                "-lc",
                shell,
            ],
            input_text=(
                _clean_api_key(api_key)
                + "\n"
                + _clean_api_key(judge_api_key)
                + "\n"
            ),
            line_prefix=log_prefix,
        )
        metadata["agent_exit_code"] = agent_code
        # 非零退出时也先读取结果/checkpoint；只要 best_workspace 仍在，就能
        # 保存当前最好补丁，供官方 harness 评测和后续恢复使用。
        result = _container_result(args.docker_executable, container_name)
        metadata.update(
            {
                "agent_succeeded": bool(result.get("succeeded")),
                "agent_stop_reason": result.get("stop_reason"),
                "agent_interaction_rounds": result.get(
                    "interaction_rounds",
                    result.get("transitions_completed"),
                ),
                "agent_tool_calls": result.get("total_tool_calls"),
                "agent_model_usage": result.get("model_usage"),
                "agent_candidate_success_count": result.get("candidate_success_count", 0),
                "agent_model_success_claim_count": result.get(
                    "model_task_success_claim_count", 0
                ),
                "success_judge_mode": result.get("success_judge_mode"),
                "success_judge_provider": result.get("success_judge_provider"),
                "success_judge_model": result.get("success_judge_model"),
                "success_judge_calls": result.get("success_judge_calls", 0),
                "success_judge_usage": result.get("success_judge_usage"),
                "success_judge_decisions": result.get("success_judge_decisions", []),
                "search_algorithm": result.get("search_algorithm"),
                "scheduling_trace": result.get("scheduling_trace", []),
                "max_children_per_node": result.get("max_children_per_node"),
                "base_children_per_node": result.get("base_children_per_node"),
                "frontier_max_entries_per_direction": result.get(
                    "frontier_max_entries_per_direction"
                ),
                "frontier_stale_after_iterations": result.get(
                    "frontier_stale_after_iterations"
                ),
                "frontier_stale_min_attempts": result.get(
                    "frontier_stale_min_attempts"
                ),
                "effective_iteration_budget": result.get("effective_iteration_budget"),
                "effective_tool_call_budget": result.get("effective_tool_call_budget"),
                "hard_iteration_budget": result.get("hard_iteration_budget"),
                "hard_tool_call_budget": result.get("hard_tool_call_budget"),
                "semantic_coverage_rate": result.get("semantic_coverage_rate"),
                "post_hoc_indicators": result.get("post_hoc_indicators"),
                "result_source": (
                    "checkpoint"
                    if result.get("stop_reason")
                    in {"running", "runtime_error_with_checkpoint"}
                    else "final_result"
                ),
            }
        )
        best_workspace = result.get("best_workspace")
        if not isinstance(best_workspace, str) or not best_workspace:
            raise RuntimeError("模型结果中没有 best_workspace")
        patch = _extract_patch(
            args.docker_executable, container_name, best_workspace
        )
        prediction["model_patch"] = patch
        metadata["patch_chars"] = len(patch)
        if agent_code != 0:
            #CLI用退出码1表达“正常结束但尚未verified_success”。只要结果中有
            #明确终止原因和最佳工作区，就属于已完成求解，不是可恢复环境错误。
            metadata["agent_nonzero_exit"] = agent_code
            if not result.get("stop_reason"):
                metadata["error"] = f"Agent 容器进程退出码为 {agent_code}"
        _console_print(
            f"[补丁] 已提取 {len(patch)} 个字符；"
            f"模型成功声明={metadata.get('agent_model_success_claim_count', 0)}次；"
            f"候选成功={metadata.get('agent_candidate_success_count', 0)}次；"
            f"独立审计调用={metadata.get('success_judge_calls', 0)}次；"
            f"verified_success={metadata['agent_succeeded']}；"
            f"交互轮次={metadata['agent_interaction_rounds']}",
            prefix=log_prefix,
        )
    except (OSError, RuntimeError) as exc:
        metadata["error"] = str(exc)
        _console_print(f"失败：{exc}", prefix=log_prefix, file=sys.stderr)
    finally:
        if not args.keep_containers:
            _run_capture(
                [args.docker_executable, "rm", "-f", container_name]
            )
    metadata["execution_status"] = _classify_swe_execution(metadata, prediction)
    metadata["retryable"] = metadata["execution_status"].startswith("retryable_")
    _console_print(
        f"========== Agent结束：{metadata['execution_status']} ==========",
        prefix=log_prefix,
    )
    return prediction, metadata


def _classify_swe_execution(
    metadata: dict[str, Any],
    prediction: dict[str, Any],
) -> str:
    """分类 Agent 执行状态；它与官方 Resolved 是两个独立维度。"""

    stop_reason = str(metadata.get("agent_stop_reason") or "").strip()
    patch = str(prediction.get("model_patch") or "")
    has_patch = bool(patch.strip())
    has_error = bool(metadata.get("error"))
    interrupted_reasons = {
        "running",
        "runtime_error_with_checkpoint",
        "model_unavailable",
    }
    if has_error or stop_reason in interrupted_reasons:
        return "retryable_checkpoint" if has_patch else "retryable_error"
    if stop_reason or metadata.get("agent_succeeded"):
        return "completed" if has_patch else "completed_no_candidate"
    # 兼容旧结果：已有非空预测但旧 metadata 没有 stop_reason。
    if has_patch:
        return "completed_legacy"
    return "retryable_incomplete"


def _upsert_instance_row(rows: list[dict[str, Any]], row: dict[str, Any]) -> None:
    instance_id = row.get("instance_id")
    for index, existing in enumerate(rows):
        if existing.get("instance_id") == instance_id:
            rows[index] = row
            return
    rows.append(row)


def _execution_summary(
    instance_ids: list[str],
    predictions: list[dict[str, Any]],
    metadata_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    predictions_by_id = {
        row.get("instance_id"): row for row in predictions if row.get("instance_id")
    }
    metadata_by_id = {
        row.get("instance_id"): row for row in metadata_rows if row.get("instance_id")
    }
    statuses: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    for instance_id in instance_ids:
        prediction = predictions_by_id.get(instance_id, {})
        metadata = metadata_by_id.get(instance_id, {})
        status = str(
            metadata.get("execution_status")
            or _classify_swe_execution(metadata, prediction)
        )
        statuses[status] = statuses.get(status, 0) + 1
        rows.append(
            {
                "instance_id": instance_id,
                "execution_status": status,
                "retryable": status.startswith("retryable_"),
                "has_patch": bool(str(prediction.get("model_patch") or "").strip()),
                "agent_stop_reason": metadata.get("agent_stop_reason"),
                "agent_exit_code": metadata.get("agent_exit_code"),
                "error": metadata.get("error"),
            }
        )
    completed = sum(
        count for status, count in statuses.items() if status.startswith("completed")
    )
    return {
        "selected_task_count": len(instance_ids),
        "agent_completed_count": completed,
        "agent_retryable_count": len(instance_ids) - completed,
        "submission_with_patch_count": sum(row["has_patch"] for row in rows),
        "status_counts": statuses,
        "tasks": rows,
    }


def _write_jsonl(path: Path, rows: list[dict[str, str]]) -> None:
    text = "".join(
        json.dumps(row, ensure_ascii=False) + "\n" for row in rows
    )
    atomic_write_text(path, text)


def _write_metadata(path: Path, rows: list[dict[str, Any]]) -> None:
    atomic_write_json(path, rows)


def _write_interaction_summary(
    path: Path,
    rows: list[dict[str, Any]],
    official_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = summarize_interaction_rounds(
        rows,
        rounds_key="agent_interaction_rounds",
        success_key="agent_succeeded",
    )
    summary["success_basis"] = "agent_internal"
    if official_report is not None:
        summary = summarize_official_interactions(
            rows, swe_official_outcomes(official_report), id_key="instance_id",
            rounds_key="agent_interaction_rounds", success_key="agent_succeeded",
            selected_count=official_report.get("total_instances", len(rows)),
        )
    summary["research_metrics"] = summarize_research_metrics(rows)
    atomic_write_json(path, summary)
    return summary


def _read_existing_metadata(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("agent result metadata must be a list")
    return [row for row in payload if isinstance(row, dict)]


def _read_existing_predictions(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _find_report_path(lines: list[str], repo: str, run_id: str) -> str:
    for line in reversed(lines):
        match = re.search(r"Report written to (.+\.json)\s*$", line)
        if match:
            path = match.group(1).strip()
            return path if path.startswith("/") else f"{repo.rstrip('/')}/{path}"
    return f"{repo.rstrip('/')}/best-fgs.{run_id}.json"


def _read_wsl_json(distro: str, path: str) -> dict[str, Any]:
    completed = _run_capture(
        _wsl_command(distro, f"cat {shlex.quote(path)}"), check=True
    )
    return json.loads(completed.stdout)


def _run_official_harness(
    args: argparse.Namespace,
    *,
    instance_ids: list[str],
    predictions_path: Path,
    run_id: str,
) -> int:
    predictions_wsl = _to_wsl_path(args.distro, predictions_path)
    harness_args = [
        ".venv/bin/python",
        "-m",
        "swebench.harness.run_evaluation",
        "--dataset_name",
        args.dataset,
        "--predictions_path",
        predictions_wsl,
        "--max_workers",
        str(args.max_workers),
        "--instance_ids",
        *instance_ids,
        "--run_id",
        run_id,
        "--cache_level",
        "instance",
        "--clean",
        "False",
        "--timeout",
        str(args.harness_timeout),
    ]
    shell = (
        f"cd {shlex.quote(args.repo)} && "
        + " ".join(shlex.quote(item) for item in harness_args)
    )
    print("\n========== 启动 SWE-bench 官方 harness ==========")
    code, lines = _run_streaming(_wsl_command(args.distro, shell))
    if code != 0:
        print(f"官方 harness 退出码：{code}", file=sys.stderr)
        return code

    report_path = _find_report_path(lines, args.repo, run_id)
    try:
        report = _read_wsl_json(args.distro, report_path)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"无法读取官方结果 JSON：{exc}", file=sys.stderr)
        return 1

    local_report_path = args.results_dir / f"official-report-{run_id}.json"
    atomic_write_json(local_report_path, report)

    total = int(report.get("total_instances", len(instance_ids)))
    completed = int(report.get("completed_instances", 0))
    resolved = int(report.get("resolved_instances", 0))
    rate = resolved / total * 100.0 if total else 0.0
    print("\n========== 当前模型的 SWE-bench Verified 结果 ==========")
    print(f"完成：{completed}/{total}")
    print(f"通过（Resolved）：{resolved}/{total}")
    print(f"通过率：{rate:.1f}%")
    print(f"异常：{report.get('error_instances', 0)}")
    print(f"Resolved IDs：{report.get('resolved_ids', [])}")
    rows = _read_existing_metadata(args.results_dir / f"agent-results-{run_id}.json")
    summary = _write_interaction_summary(
        args.results_dir / f"interaction-summary-{run_id}.json", rows, report,
    )
    print_official_interaction_summary(summary)
    print(f"结果文件（WSL）：{report_path}")
    print(f"结果文件（本机）：{local_report_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="让当前 BestFGS 模型运行多道 SWE-bench Verified。",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--provider",
        choices=("deepseek", "openai", "dashscope"),
        default="deepseek",
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument(
        "--success-judge-mode",
        choices=("off", "audit", "required"),
        default="required",
    )
    parser.add_argument(
        "--success-judge-provider",
        choices=("deepseek", "openai", "dashscope"),
        default=None,
    )
    parser.add_argument("--success-judge-model", default=None)
    parser.add_argument("--success-judge-base-url", default=None)
    parser.add_argument(
        "--success-judge-api-key-env",
        default="SUCCESS_JUDGE_API_KEY",
    )
    parser.add_argument("--success-judge-max-calls", type=int, default=3,
                        help="有效审计次数；每次最多一次格式修正，总客户端调用不超过此值的2倍")
    parser.add_argument("--distro", default="Ubuntu")
    parser.add_argument("--repo", default="/home/research/SWE-bench")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--instance-id", action="append", default=None)
    parser.add_argument(
        "--allow-frozen-test-set",
        action="store_true",
        help="仅供冻结测试集专用入口使用；普通开发运行不要设置",
    )
    parser.add_argument(
        "--sample-fraction",
        type=float,
        default=DEFAULT_SAMPLE_FRACTION,
        help="未显式指定实例时，从排除冻结测试题后的开发池随机抽取的比例（默认0.1）",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="可选的固定抽样题数；设置后覆盖sample-fraction",
    )
    parser.add_argument(
        "--sample-seed",
        type=int,
        default=None,
        help="随机抽样种子；省略时每次生成新种子并写入selection文件",
    )
    parser.add_argument(
        "--selection-file", type=Path, default=None,
        help="开发题抽样清单：不存在时抽样保存，存在时直接复用；dry-run也保存清单",
    )
    parser.add_argument("--namespace", default="swebench")
    parser.add_argument("--arch", default="x86_64")
    parser.add_argument("--max-iterations", type=int, default=24)
    parser.add_argument("--max-tool-calls", type=int, default=80)
    parser.add_argument(
        "--budget-multiplier", type=float, default=1.0,
        help="弹性续算上限倍数；默认1，不自动续算；大于1会提高潜在API消耗",
    )
    parser.add_argument(
        "--model-timeout",
        type=int,
        default=90,
        help="模型连续无SSE数据或保活消息时的空闲超时秒数",
    )
    parser.add_argument(
        "--model-max-wall-time",
        type=int,
        default=600,
        help="单次模型请求的绝对总上限秒数",
    )
    parser.add_argument("--model-request-attempts", type=int, default=4)
    parser.add_argument("--model-parse-attempts", type=int, default=5)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--top-p", type=float, default=None)
    parser.add_argument(
        "--reasoning-effort",
        choices=("low", "high", "max"),
        default="high",
    )
    parser.add_argument(
        "--solve-reasoning-effort",
        choices=("low", "high", "max"),
        default="max",
    )
    parser.add_argument(
        "--base-children-per-node",
        type=int,
        default=3,
        help="无额外语义压力时的基础树宽",
    )
    parser.add_argument(
        "--max-children-per-node",
        type=int,
        default=6,
        help="语义需求驱动树宽的硬上限，不随访问次数增长",
    )
    parser.add_argument("--disable-semantic-node-merge", action="store_true")
    parser.add_argument("--semantic-merge-fact-threshold", type=float, default=0.90)
    parser.add_argument("--semantic-merge-issue-threshold", type=float, default=0.80)
    parser.add_argument(
        "--max-workers",
        type=int,
        default=2,
        help=(
            "并发度：官方harness使用该值；Agent求解最多并发2题，"
            "并以题号前缀实时交错输出日志（默认2）"
        ),
    )
    parser.add_argument("--harness-timeout", type=int, default=1800)
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=PROJECT_ROOT / "benchmark_results" / "swebench",
    )
    parser.add_argument("--docker-executable", default=DEFAULT_DOCKER_EXECUTABLE)
    parser.add_argument(
        "--image-pull-attempts",
        type=int,
        default=10,
        help="单个缺失镜像的最大拉取次数（默认10次，退避等待最多30秒）",
    )
    parser.add_argument("--skip-image-pull", action="store_true")
    parser.add_argument("--keep-containers", action="store_true")
    parser.add_argument("--skip-evaluation", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--allow-resume-config-drift",
        action="store_true",
        help="显式允许用不同模型/预算/代码继续旧运行；会破坏严格可比性",
    )
    parser.add_argument(
        "--evaluation-only",
        action="store_true",
        help="只用既有 predictions 重跑官方 harness，不调用模型；需同时指定 --resume 和 --run-id",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只显示计划，不调用模型、不启动 Docker/harness",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="跳过Docker/WSL/harness启动前检查（不推荐）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_console()
    args = build_parser().parse_args(argv)
    run_id = args.run_id or datetime.now().strftime("best-fgs-swe-%Y%m%d-%H%M%S-%f")
    try:
        _validate_name(run_id, "run-id")
        _validate_name(args.arch, "arch")
    except argparse.ArgumentTypeError as exc:
        print(f"参数错误：{exc}", file=sys.stderr)
        return 2

    positive_values = (
        args.max_iterations,
        args.max_tool_calls,
        args.model_timeout,
        args.model_max_wall_time,
        args.model_request_attempts,
        args.model_parse_attempts,
        args.max_workers,
        args.harness_timeout,
        args.image_pull_attempts,
        args.budget_multiplier,
        args.base_children_per_node,
        args.max_children_per_node,
    )
    if min(positive_values) < 1:
        print("所有预算、超时、重试与并发参数必须 >= 1", file=sys.stderr)
        return 2
    if args.model_max_wall_time < args.model_timeout:
        print("model-max-wall-time 必须大于或等于 model-timeout", file=sys.stderr)
        return 2
    if not math.isfinite(args.budget_multiplier):
        print("budget-multiplier 必须是有限数", file=sys.stderr)
        return 2
    if args.base_children_per_node > args.max_children_per_node:
        print("base-children-per-node 不能大于 max-children-per-node", file=sys.stderr)
        return 2
    if args.temperature < 0 or (args.top_p is not None and not 0 < args.top_p <= 1):
        print("temperature必须非负，top-p必须位于(0, 1]", file=sys.stderr)
        return 2

    if not 0 < args.sample_fraction <= 1:
        print("sample-fraction 必须在 (0, 1] 范围内", file=sys.stderr)
        return 2
    if args.sample_size is not None and args.sample_size < 1:
        print("sample-size 必须 >= 1", file=sys.stderr)
        return 2
    if args.evaluation_only and (not args.resume or args.run_id is None):
        print("--evaluation-only 必须同时指定 --resume 和原来的 --run-id", file=sys.stderr)
        return 2
    if args.evaluation_only and args.skip_evaluation:
        print("--evaluation-only 不能与 --skip-evaluation 同时使用", file=sys.stderr)
        return 2

    try:
        frozen_instance_ids = set(frozen_swebench_ids())
    except FrozenTestSetError as exc:
        print(f"冻结测试集不可用：{exc}", file=sys.stderr)
        return 1

    selection_path = args.results_dir / f"selection-{run_id}.json"
    if args.selection_file and (args.instance_id or args.allow_frozen_test_set):
        print("selection-file 仅用于开发抽样，不能与指定实例或冻结测试开关混用", file=sys.stderr)
        return 2
    if args.selection_file and args.selection_file.resolve() == selection_path.resolve():
        print("开发题抽样清单与单次运行记录不能使用同一路径", file=sys.stderr)
        return 2
    saved_run = None
    if args.resume:
        if args.run_id is None:
            print("--resume 必须同时指定原来的 --run-id", file=sys.stderr)
            return 2
        try:
            saved_run = json.loads(selection_path.read_text(encoding="utf-8"))
            if not isinstance(saved_run, dict) or saved_run.get("dataset") != args.dataset:
                raise ValueError("恢复记录的数据集不匹配")
            saved_ids = saved_run.get("instance_ids")
            if (
                not isinstance(saved_ids, list) or not saved_ids
                or not all(isinstance(item, str) and item for item in saved_ids)
                or len(saved_ids) != len(set(saved_ids))
            ):
                raise ValueError("恢复记录中的题目清单无效")
            if args.sample_size is not None and len(saved_ids) != args.sample_size:
                raise ValueError("恢复记录的题数与当前入口要求不一致")
            if args.sample_seed is not None and args.sample_seed != saved_run.get("sample_seed"):
                raise ValueError("恢复时不能修改抽样seed")
            if args.selection_file and not args.selection_file.is_file():
                raise ValueError("恢复运行缺少原开发题抽样清单，不自动重新抽题")
        except (OSError, ValueError) as exc:
            print(f"无法恢复运行：{exc}", file=sys.stderr)
            return 1
    elif not args.dry_run:
        artifact_names = (
            f"selection-{run_id}.json", f"predictions-{run_id}.jsonl",
            f"agent-results-{run_id}.json", f"interaction-summary-{run_id}.json",
            f"execution-report-{run_id}.json", f"official-report-{run_id}.json",
            f"run-manifest-{run_id}.json",
        )
        if any((args.results_dir / name).exists() for name in artifact_names):
            print("run-id 已有结果；请更换运行名，或使用 --resume 恢复，不覆盖旧结果", file=sys.stderr)
            return 2
    sample_seed: int | None = None
    dataset_size: int | None = None
    sample_plan = None
    if args.selection_file:
        try:
            sample_plan = development_selection(
                path=args.selection_file,
                benchmark="swebench", dataset=args.dataset,
                protected=frozen_instance_ids,
                discover=lambda: _load_all_instance_ids(args),
                seed=args.sample_seed, sample_size=args.sample_size,
                fraction=None if args.sample_size is not None else args.sample_fraction,
            )
            instance_ids = sample_plan["task_ids"]
            sample_seed = sample_plan["sample_seed"]
            dataset_size = sample_plan["dataset_size"]
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"读取或生成开发抽样清单失败：{exc}", file=sys.stderr)
            return 1
    elif args.instance_id:
        instance_ids = list(dict.fromkeys(args.instance_id))
    elif saved_run is not None:
        instance_ids = saved_run["instance_ids"]
        sample_seed = saved_run.get("sample_seed")
        dataset_size = saved_run.get("dataset_size")
    else:
        try:
            all_instance_ids = _load_all_instance_ids(args)
            dataset_size = len(all_instance_ids)
            development_instance_ids = [
                item for item in all_instance_ids if item not in frozen_instance_ids
            ]
            sample_seed = (
                args.sample_seed
                if args.sample_seed is not None
                else secrets.randbits(64)
            )
            instance_ids = _random_sample(
                development_instance_ids,
                fraction=args.sample_fraction,
                seed=sample_seed,
                sample_size=args.sample_size,
            )
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            print(f"生成SWE-bench随机抽样失败：{exc}", file=sys.stderr)
            return 1

    if saved_run is not None and instance_ids != saved_run["instance_ids"]:
        print("恢复运行的题目/顺序与原记录不一致，拒绝混用结果", file=sys.stderr)
        return 2
    if saved_run is not None and sample_plan is not None:
        original_hash = saved_run.get("development_selection_sha256")
        if original_hash and original_hash != sample_plan["selection_sha256"]:
            print("恢复运行使用的开发抽样清单与原记录不一致", file=sys.stderr)
            return 2
    try:
        reject_frozen_overlap(
            instance_ids,
            benchmark="swebench",
            allow_frozen_test_set=args.allow_frozen_test_set,
        )
    except FrozenTestSetError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    model_default, base_url_default, key_name = _model_defaults(args.provider)
    model = args.model or model_default
    base_url = args.base_url or base_url_default
    judge_provider = args.success_judge_provider or args.provider
    judge_model_default, judge_base_default, judge_provider_key_name = _model_defaults(
        judge_provider
    )
    judge_model = args.success_judge_model or (
        model if judge_provider == args.provider else judge_model_default
    )
    judge_base_url = args.success_judge_base_url or (
        base_url if judge_provider == args.provider else judge_base_default
    )
    experiment_config = {
        "dataset": args.dataset,
        "provider": args.provider,
        "model": model,
        "base_url": public_endpoint(base_url),
        "success_judge": {
            "mode": args.success_judge_mode,
            "provider": judge_provider,
            "model": judge_model,
            "base_url": public_endpoint(judge_base_url),
            "max_calls": args.success_judge_max_calls,
        },
        "search": {
            "max_iterations": args.max_iterations,
            "max_tool_calls": args.max_tool_calls,
            "budget_multiplier": args.budget_multiplier,
            "base_children_per_node": args.base_children_per_node,
            "max_children_per_node": args.max_children_per_node,
            "semantic_node_merge": not args.disable_semantic_node_merge,
            "semantic_merge_fact_threshold": args.semantic_merge_fact_threshold,
            "semantic_merge_issue_threshold": args.semantic_merge_issue_threshold,
        },
        "sampling": {
            "temperature": args.temperature,
            "top_p": args.top_p,
            "reasoning_effort": args.reasoning_effort,
            "solve_reasoning_effort": args.solve_reasoning_effort,
        },
        "request_policy": {
            "model_timeout": args.model_timeout,
            "model_max_wall_time": args.model_max_wall_time,
            "model_request_attempts": args.model_request_attempts,
            "model_parse_attempts": args.model_parse_attempts,
            "max_workers": args.max_workers,
            "agent_parallelism_cap": MAX_SIMULTANEOUS_AGENT_LOGS,
        },
    }
    experiment_config_sha256 = canonical_sha256(experiment_config)
    manifest = base_manifest(
        benchmark="swebench_verified", run_id=run_id, project_root=PROJECT_ROOT
    )
    manifest.update(
        {
            "experiment_config": experiment_config,
            "experiment_config_sha256": experiment_config_sha256,
            "instance_ids": instance_ids,
            "instance_ids_sha256": canonical_sha256(instance_ids),
            "status": "planned",
        }
    )
    if saved_run is not None and not args.evaluation_only:
        drift: list[str] = []
        saved_config_hash = saved_run.get("experiment_config_sha256")
        saved_implementation_hash = saved_run.get("implementation_sha256")
        if saved_config_hash and saved_config_hash != experiment_config_sha256:
            drift.append("模型、Judge、预算或搜索配置")
        if (
            saved_implementation_hash
            and saved_implementation_hash != manifest["implementation_sha256"]
        ):
            drift.append("BestFGS实现代码")
        if drift and not args.allow_resume_config_drift:
            print(
                "恢复运行检测到配置漂移：" + "、".join(drift)
                + "。请新建run-id；若确需混合结果，显式添加 --allow-resume-config-drift。",
                file=sys.stderr,
            )
            return 2
        if drift:
            print("[恢复警告] 已显式允许配置漂移：" + "、".join(drift), file=sys.stderr)
        if not saved_config_hash:
            print("[恢复提示] 旧运行没有配置指纹，按兼容模式恢复。", file=sys.stderr)
    if args.success_judge_max_calls <= 0:
        print("success-judge-max-calls 必须为正数", file=sys.stderr)
        return 2
    print("========== SWE-bench Verified 当前模型评测 ==========")
    print(f"运行名：{run_id}")
    print(f"Provider/Model：{args.provider}/{model}")
    print(
        "独立成功审计："
        f"mode={args.success_judge_mode}，provider/model={judge_provider}/{judge_model}，"
        f"每题最多{args.success_judge_max_calls}个有效审计，"
        f"含格式修正最多{args.success_judge_max_calls * 2}次客户端调用"
    )
    print("搜索算法：phase_adaptive_semantic_best_first")
    if args.selection_file:
        print(f"固定开发题清单：{args.selection_file.resolve()}（已保存；后续直接复用）")
    if sample_seed is not None:
        print(
            f"随机抽样：全集{dataset_size}题，抽取{len(instance_ids)}题，"
            f"seed={sample_seed}"
        )
        print(
            f"开发抽样已排除冻结测试集：{len(frozen_instance_ids)}题"
        )
    print(f"实例数量：{len(instance_ids)}")
    print(
        "Agent求解并发："
        f"{min(MAX_SIMULTANEOUS_AGENT_LOGS, args.max_workers, len(instance_ids))}；"
        "最多两题同时运行并实时输出带题号前缀的日志"
    )
    print(
        f"每题基础搜索预算：{args.max_iterations}轮/{args.max_tool_calls}次工具；"
        "沿用原项目的0.9x、1.0x或1.35x题面复杂度调度；"
        f"续算={'关闭' if args.budget_multiplier == 1 else '开启'}，"
        f"硬上限倍数={args.budget_multiplier:g}"
    )
    print(
        "搜索策略：阶段自适应语义Best-First全局前沿；"
        "前期偏信息增益，后期优先候选精修/Judge缺口/recommend；"
        f"语义容量={args.base_children_per_node}..{args.max_children_per_node}"
        "（按语义不确定性和候选成熟度变化）"
    )
    print(
        f"模型等待：空闲{args.model_timeout}秒，总上限{args.model_max_wall_time}秒，"
        f"最多{args.model_request_attempts}次"
    )
    print(
        f"模型采样：temperature={args.temperature:g}，"
        f"top_p={args.top_p if args.top_p is not None else 'provider-default'}；"
        f"探索思考={args.reasoning_effort}，求解思考={args.solve_reasoning_effort}"
    )
    for index, instance_id in enumerate(instance_ids, start=1):
        print(f"  {index:>2}. {instance_id}")

    if args.dry_run:
        print("\n[dry-run] 不调用 API、不启动 Docker/SWE-bench harness。")
        return 0
    args.results_dir.mkdir(parents=True, exist_ok=True)
    if not (args.resume and selection_path.is_file()):
        atomic_write_json(
            selection_path,
                {
                    "run_id": run_id,
                    "dataset": args.dataset,
                    "dataset_size": dataset_size or len(instance_ids),
                    "sample_fraction": (
                        None if args.instance_id or args.sample_size is not None else args.sample_fraction
                    ),
                    "sample_size": len(instance_ids),
                    "sample_seed": sample_seed,
                    "instance_ids": instance_ids,
                    "frozen_test_set_excluded": not args.allow_frozen_test_set,
                    "development_selection_file": (
                        str(args.selection_file.resolve()) if args.selection_file else None
                    ),
                    "development_selection_sha256": (
                        sample_plan["selection_sha256"] if sample_plan else None
                    ),
                    "experiment_config_sha256": experiment_config_sha256,
                    "implementation_sha256": manifest["implementation_sha256"],
                    "success_judge": {
                        "mode": args.success_judge_mode,
                        "provider": judge_provider,
                        "model": judge_model,
                        "base_url": public_endpoint(judge_base_url),
                        "max_calls_per_task": args.success_judge_max_calls,
                    },
                },
        )

    predictions_path = args.results_dir / f"predictions-{run_id}.jsonl"
    metadata_path = args.results_dir / f"agent-results-{run_id}.json"
    execution_report_path = args.results_dir / f"execution-report-{run_id}.json"
    interaction_summary_path = (
        args.results_dir / f"interaction-summary-{run_id}.json"
    )
    predictions = (
        _read_existing_predictions(predictions_path) if args.resume else []
    )
    metadata_rows = (
        _read_existing_metadata(metadata_path) if args.resume else []
    )
    predictions_by_id = {
        row.get("instance_id"): row for row in predictions if row.get("instance_id")
    }
    metadata_by_id = {
        row.get("instance_id"): row for row in metadata_rows if row.get("instance_id")
    }
    completed_ids = {
        instance_id
        for instance_id in instance_ids
        if (
            str(
                metadata_by_id.get(instance_id, {}).get("execution_status")
                or _classify_swe_execution(
                    metadata_by_id.get(instance_id, {}),
                    predictions_by_id.get(instance_id, {}),
                )
            ).startswith("completed")
        )
    }
    pending_ids = [item for item in instance_ids if item not in completed_ids]

    manifest_path = args.results_dir / f"run-manifest-{run_id}.json"
    needs_runtime = bool(pending_ids) or not args.skip_evaluation
    if needs_runtime and not args.skip_preflight:
        print("[预检] 验证Windows Docker、WSL Docker与SWE-bench harness")
        try:
            manifest["runtime_preflight"] = _preflight_runtime(args)
            manifest["status"] = "ready"
            print(
                "[预检] 通过：Windows Docker="
                f"{manifest['runtime_preflight']['windows_docker_server']}，"
                "WSL Docker="
                f"{manifest['runtime_preflight']['wsl_docker_server']}，"
                "SWE-bench="
                f"{manifest['runtime_preflight']['wsl_swebench']}"
            )
        except (OSError, RuntimeError) as exc:
            manifest["status"] = "preflight_failed"
            manifest["preflight_error"] = str(exc)
            atomic_write_json(manifest_path, manifest)
            print(f"启动前检查失败：{exc}", file=sys.stderr)
            return 1
    elif args.skip_preflight:
        manifest["status"] = "ready_preflight_skipped"
        print("[预检警告] 已跳过运行环境检查。", file=sys.stderr)
    else:
        manifest["status"] = "ready_no_runtime_needed"
    atomic_write_json(manifest_path, manifest)

    if args.evaluation_only:
        missing_ids = [item for item in instance_ids if item not in predictions_by_id]
        if missing_ids:
            print(
                "evaluation-only 缺少预测记录：" + ", ".join(missing_ids),
                file=sys.stderr,
            )
            return 1
        print("[evaluation-only] 跳过 Agent/API，仅重跑官方 harness。")
        try:
            return _run_official_harness(
                args,
                instance_ids=instance_ids,
                predictions_path=predictions_path,
                run_id=run_id,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"启动官方 harness 失败：{exc}", file=sys.stderr)
            return 1

    public_tasks: dict[str, str] = {}
    api_key = ""
    judge_api_key = ""
    if pending_ids:
        api_key = _clean_api_key(os.getenv(key_name))
        if not api_key:
            print(f"缺少环境变量：{key_name}", file=sys.stderr)
            return 2
        if args.success_judge_mode != "off":
            judge_api_key = _clean_api_key(
                os.getenv(args.success_judge_api_key_env)
            )
            if not judge_api_key and judge_provider == args.provider:
                judge_api_key = api_key
            if not judge_api_key:
                judge_api_key = _clean_api_key(os.getenv(judge_provider_key_name))
            if not judge_api_key:
                print(
                    "缺少独立成功审计凭据："
                    f"{args.success_judge_api_key_env} 或 {judge_provider_key_name}",
                    file=sys.stderr,
                )
                return 2
        try:
            public_tasks = _load_public_tasks(args, pending_ids)
        except (OSError, RuntimeError, json.JSONDecodeError) as exc:
            print(f"读取 SWE-bench 公开任务失败：{exc}", file=sys.stderr)
            return 1
    elif args.resume:
        print("[恢复] 所有 Agent 任务均已正常收尾；不检查 API Key，直接汇总/评测。")

    def persist_instance_result(
        instance_id: str,
        prediction: dict[str, Any],
        metadata: dict[str, Any],
    ) -> None:
        nonlocal predictions, metadata_rows
        # 所有结果文件只由主线程写。工作线程仅运行独立容器并返回内存结果，
        # 从而既获得真实并发，又不会并发覆盖 JSON/JSONL。
        previous_prediction = predictions_by_id.get(instance_id, {})
        previous_patch = str(previous_prediction.get("model_patch") or "")
        if (
            previous_patch.strip()
            and not str(prediction.get("model_patch") or "").strip()
            and str(metadata.get("execution_status") or "").startswith("retryable_")
        ):
            prediction = dict(previous_prediction)
            metadata["preserved_previous_patch"] = True
            metadata["patch_chars"] = len(previous_patch)
            metadata["execution_status"] = "retryable_checkpoint"
            metadata["retryable"] = True
        _upsert_instance_row(predictions, prediction)
        _upsert_instance_row(metadata_rows, metadata)
        predictions_by_id[instance_id] = prediction
        metadata_by_id[instance_id] = metadata
        order = {item: position for position, item in enumerate(instance_ids)}
        predictions.sort(key=lambda row: order.get(str(row.get("instance_id")), len(order)))
        metadata_rows.sort(key=lambda row: order.get(str(row.get("instance_id")), len(order)))
        _write_jsonl(predictions_path, predictions)
        _write_metadata(metadata_path, metadata_rows)
        _write_interaction_summary(interaction_summary_path, metadata_rows)

    try:
        jobs: list[dict[str, Any]] = []
        for index, instance_id in enumerate(instance_ids, start=1):
            if instance_id in completed_ids:
                print(f"[恢复] 跳过已正常收尾：{instance_id}")
                continue
            if instance_id in predictions_by_id:
                old_status = _classify_swe_execution(
                    metadata_by_id.get(instance_id, {}),
                    predictions_by_id[instance_id],
                )
                print(f"[恢复] 重跑未正常收尾：{instance_id}（{old_status}）")
            jobs.append(
                {
                    "index": index,
                    "instance_id": instance_id,
                    "problem_statement": public_tasks[instance_id],
                }
            )

        agent_workers = min(
            MAX_SIMULTANEOUS_AGENT_LOGS,
            args.max_workers,
            len(jobs),
        )
        if jobs:
            print(
                f"[并发] Agent工作线程={agent_workers}；"
                "最多两道题同时运行，日志按[SWE 题号/总数 实例ID]区分"
            )
            with ThreadPoolExecutor(
                max_workers=agent_workers,
                thread_name_prefix="swe-agent",
            ) as executor:
                future_jobs: dict[Future, dict[str, Any]] = {}
                for job in jobs:
                    future = executor.submit(
                        _run_one_instance,
                        args,
                        index=job["index"],
                        total=len(instance_ids),
                        instance_id=job["instance_id"],
                        problem_statement=job["problem_statement"],
                        provider=args.provider,
                        model=model,
                        base_url=base_url,
                        key_name=key_name,
                        api_key=api_key,
                        judge_provider=judge_provider,
                        judge_model=judge_model,
                        judge_base_url=judge_base_url,
                        judge_api_key=judge_api_key,
                    )
                    future_jobs[future] = job
                try:
                    for future in as_completed(future_jobs):
                        job = future_jobs[future]
                        prediction, metadata = future.result()
                        persist_instance_result(
                            str(job["instance_id"]), prediction, metadata
                        )
                except KeyboardInterrupt:
                    for future in future_jobs:
                        future.cancel()
                    _terminate_active_processes()
                    raise
    except KeyboardInterrupt:
        print("\n用户中止；已保留当前 predictions JSONL。", file=sys.stderr)
        return 130

    interaction_summary = _write_interaction_summary(
        interaction_summary_path,
        metadata_rows,
    )
    execution_summary = _execution_summary(
        instance_ids,
        predictions,
        metadata_rows,
    )
    atomic_write_json(execution_report_path, execution_summary)
    print(f"\n模型预测文件：{predictions_path}")
    print(f"Agent 过程摘要：{metadata_path}")
    print(f"Agent 执行状态：{execution_report_path}")
    print(f"交互轮次摘要：{interaction_summary_path}")
    print(
        "平均交互轮次："
        f"{interaction_summary['average_interaction_rounds']}；"
        "Agent验证成功任务平均交互轮次："
        f"{interaction_summary['average_successful_interaction_rounds']}"
    )
    print(
        f"交互轮次有效记录：{interaction_summary['recorded_task_count']}/{len(instance_ids)}；"
        "内部 verified_success 不等同于官方 Resolved。"
    )
    print_research_metrics(interaction_summary["research_metrics"])
    print(
        "Agent正常收尾："
        f"{execution_summary['agent_completed_count']}/{len(instance_ids)}；"
        "可恢复异常/未完成："
        f"{execution_summary['agent_retryable_count']}；"
        "有补丁可提交："
        f"{execution_summary['submission_with_patch_count']}"
    )
    print(
        "执行状态分布："
        + json.dumps(execution_summary["status_counts"], ensure_ascii=False)
    )
    print(f"随机抽样清单：{selection_path}")
    if args.skip_evaluation:
        print("已设置 --skip-evaluation，暂不调用官方 harness。")
        return 0
    try:
        return _run_official_harness(
            args,
            instance_ids=instance_ids,
            predictions_path=predictions_path,
            run_id=run_id,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"启动官方 harness 失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
