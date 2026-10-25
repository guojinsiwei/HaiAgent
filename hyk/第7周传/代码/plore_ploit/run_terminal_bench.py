"""用当前 RE-TRAC + MCTS 模型运行 Terminal-Bench 2 子集。

本文件同时提供：
1. ``RetracHarborAgent``：Harbor 0.20 可导入的自定义 Agent；
2. Windows 启动入口：选择多道 TB2 任务、调用 Harbor、显示官方通过率。

模型在每道题自己的 Docker 容器内运行，最终工作区交给 Harbor verifier，
不使用 oracle solution。
"""

from __future__ import annotations

import argparse
import json
import math
import logging
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from benchmark_metrics import (
    print_research_metrics,
    summarize_interaction_rounds,
    summarize_research_metrics,
)
from benchmark_splits import FrozenTestSetError, reject_frozen_overlap


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = "terminal-bench/terminal-bench-2"
DEFAULT_DOCKER_EXECUTABLE = (
    r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
)
DEFAULT_IMAGE_NAMESPACE = "alexgshaw"
DEFAULT_IMAGE_TAG = "20251031"
PYTHON_DISCOVERY_COMMAND = """
for candidate in /installed-agent/bin/python3.11 python3.13 python3.12 python3.11 python3.10 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && \
     "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' 2>/dev/null; then
    command -v "$candidate"
    exit 0
  fi
done
exit 1
""".strip()

# 固定子集便于不同模型、不同参数之间重复比较。
DEFAULT_TASK_NAMES = (
    "make-mips-interpreter",
    "circuit-fibsqrt",
    "build-pov-ray",
    "overfull-hbox",
    "video-processing",
    "distribution-search",
    "break-filter-js-from-html",
    "protein-assembly",
    "path-tracing",
    "compile-compcert",
)


# Windows 运行启动器时没有 Harbor 包；Harbor 在 WSL 导入本文件时才定义 Agent。
try:
    from harbor.agents.base import BaseAgent
    from harbor.environments.base import BaseEnvironment
    from harbor.models.agent.context import AgentContext
except ModuleNotFoundError:
    BaseAgent = None  # type: ignore[assignment,misc]


if BaseAgent is not None:

    class RetracHarborAgent(BaseAgent):  # type: ignore[misc,valid-type]
        """在 Harbor 任务容器中运行本项目的真实模型与 MCTS。"""

        @staticmethod
        def name() -> str:
            return "plore-ploit"

        def version(self) -> str:
            return "0.2.0"

        def __init__(
            self,
            logs_dir: Path,
            model_name: str | None = None,
            provider: str = "deepseek",
            base_url: str | None = None,
            max_iterations: int | str = 24,
            max_tool_calls: int | str = 80,
            model_timeout: int | str = 90,
            model_max_wall_time: int | str = 600,
            model_request_attempts: int | str = 4,
            model_parse_attempts: int | str = 5,
            temperature: float | str = 0.2,
            top_p: float | str | None = None,
            reasoning_effort: str = "high",
            solve_reasoning_effort: str = "max",
            selection_mode: str = "plore_ploit",
            hybrid_root_interval: int | str = 4,
            budget_multiplier: float | str = 1.0,
            base_children_per_node: int | str = 3,
            max_children_per_node: int | str = 6,
            disable_semantic_node_merge: bool | str = False,
            semantic_merge_fact_threshold: float | str = 0.90,
            semantic_merge_issue_threshold: float | str = 0.80,
            agent_timeout_sec: float | None = None,
            **kwargs: Any,
        ) -> None:
            super().__init__(
                logs_dir=logs_dir,
                model_name=model_name,
                **kwargs,
            )
            if provider not in {"deepseek", "openai"}:
                raise ValueError(f"unsupported provider: {provider}")
            self.provider = provider
            self.base_url = base_url or None
            self.max_iterations = int(max_iterations)
            self.max_tool_calls = int(max_tool_calls)
            self.model_timeout = int(model_timeout)
            self.model_max_wall_time = int(model_max_wall_time)
            self.model_request_attempts = int(model_request_attempts)
            self.model_parse_attempts = int(model_parse_attempts)
            self.temperature = float(temperature)
            self.top_p = float(top_p) if top_p not in {None, "", "None"} else None
            if reasoning_effort not in {"low", "high", "max"}:
                raise ValueError("reasoning_effort must be low, high, or max")
            if solve_reasoning_effort not in {"low", "high", "max"}:
                raise ValueError("solve_reasoning_effort must be low, high, or max")
            self.reasoning_effort = reasoning_effort
            self.solve_reasoning_effort = solve_reasoning_effort
            if selection_mode not in {"root", "working", "hybrid", "exploit", "plore_ploit"}:
                raise ValueError(
                    "selection_mode must be root, working, hybrid, exploit, or plore_ploit"
                )
            self.selection_mode = selection_mode
            self.hybrid_root_interval = int(hybrid_root_interval)
            if self.hybrid_root_interval <= 0:
                raise ValueError("hybrid_root_interval must be positive")
            self.budget_multiplier = float(budget_multiplier)
            self.base_children_per_node = int(base_children_per_node)
            self.max_children_per_node = int(max_children_per_node)
            if not math.isfinite(self.budget_multiplier) or self.budget_multiplier < 1:
                raise ValueError("budget_multiplier must be at least 1")
            if self.base_children_per_node <= 0 or self.max_children_per_node <= 0:
                raise ValueError(
                    "child width limits must be positive"
                )
            if self.base_children_per_node > self.max_children_per_node:
                raise ValueError("base child width must not exceed maximum child width")
            self.disable_semantic_node_merge = str(
                disable_semantic_node_merge
            ).casefold() in {"1", "true", "yes", "on"}
            self.semantic_merge_fact_threshold = float(
                semantic_merge_fact_threshold
            )
            self.semantic_merge_issue_threshold = float(
                semantic_merge_issue_threshold
            )
            self.agent_timeout_sec = agent_timeout_sec

        async def setup(self, environment: BaseEnvironment) -> None:
            await environment.exec(
                command="mkdir -p /installed-agent /logs/agent",
                user="root",
            )
            python_check = await environment.exec(
                command=PYTHON_DISCOVERY_COMMAND,
                user="root",
            )
            if python_check.return_code != 0:
                logging.getLogger(__name__).info(
                    "任务镜像没有Python 3.10+，正在安装独立Agent运行时"
                )
                bootstrap = await environment.exec(
                    command="""
set -e
if command -v apt-get >/dev/null 2>&1; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y python3 curl ca-certificates
elif command -v apk >/dev/null 2>&1; then
  apk add --no-cache python3 curl ca-certificates
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y python3 curl ca-certificates
fi
if ! sh -c 'for p in python3.13 python3.12 python3.11 python3.10 python3 python; do command -v "$p" >/dev/null 2>&1 && "$p" -c "import sys; raise SystemExit(sys.version_info < (3, 10))" 2>/dev/null && exit 0; done; exit 1'; then
  if ! command -v curl >/dev/null 2>&1; then
    echo '无法安装Agent运行时：容器中没有curl或受支持的包管理器' >&2
    exit 86
  fi
  curl -LsSf https://astral.sh/uv/0.9.5/install.sh | env UV_INSTALL_DIR=/installed-agent/bin sh
  /installed-agent/bin/uv python install 3.11
  ln -sf "$(/installed-agent/bin/uv python find 3.11)" /installed-agent/bin/python3.11
fi
""".strip(),
                    user="root",
                    timeout_sec=600,
                )
                if bootstrap.return_code != 0:
                    raise RuntimeError(
                        "failed to install Python runtime for cli_retrac_mcts: "
                        f"{bootstrap.stderr}"
                    )
                python_check = await environment.exec(
                    command=PYTHON_DISCOVERY_COMMAND,
                    user="root",
                )
            if python_check.return_code != 0:
                raise RuntimeError(
                    "Terminal-Bench task image still has no usable Python 3.10+"
                )
            self.python_executable = python_check.stdout.strip().splitlines()[-1]
            logging.getLogger(__name__).info(
                "Agent使用Python运行时：%s", self.python_executable
            )

            await environment.upload_dir(
                source_dir=PROJECT_ROOT / "src",
                target_dir="/installed-agent/src",
            )

        async def run(
            self,
            instruction: str,
            environment: BaseEnvironment,
            context: AgentContext,
        ) -> None:
            del context
            python_executable = getattr(self, "python_executable", "python3")
            key_name = (
                "DEEPSEEK_API_KEY"
                if self.provider == "deepseek"
                else "OPENAI_API_KEY"
            )
            api_key = os.environ.get(key_name)
            if not api_key:
                raise RuntimeError(f"missing model credential: {key_name}")

            model = self.model_name or ""
            if "/" in model:
                model = model.split("/", 1)[1]
            if not model:
                model = (
                    "deepseek-v4-flash"
                    if self.provider == "deepseek"
                    else "gpt-4o"
                )

            result_path = "/logs/agent/retrac_result.json"
            progress_path = "/logs/agent/retrac_progress.log"
            checkpoint_path = "/tmp/cli_retrac_mcts/harbor-task/search_checkpoint.json"
            cli_args = [
                python_executable,
                "-m",
                "cli_retrac_mcts",
                "--provider",
                self.provider,
                "--model",
                model,
                "--goal",
                instruction,
                "--success-criterion",
                "完成任务要求，使 Terminal-Bench 官方 verifier 通过",
                "--constraint",
                "只修改当前隔离工作区中的任务实现，不读取/solution或隐藏verifier答案；命令使用相对路径",
                "--workspace",
                "/app",
                "--run-root",
                "/tmp/cli_retrac_mcts/harbor-task",
                "--max-iterations",
                str(self.max_iterations),
                "--max-tool-calls",
                str(self.max_tool_calls),
                "--budget-multiplier",
                str(self.budget_multiplier),
                "--model-timeout",
                str(self.model_timeout),
                "--model-max-wall-time",
                str(self.model_max_wall_time),
                "--model-request-attempts",
                str(self.model_request_attempts),
                "--model-parse-attempts",
                str(self.model_parse_attempts),
                "--temperature",
                str(self.temperature),
                "--reasoning-effort",
                self.reasoning_effort,
                "--solve-reasoning-effort",
                self.solve_reasoning_effort,
                "--selection-mode",
                self.selection_mode,
                "--hybrid-root-interval",
                str(self.hybrid_root_interval),
                "--base-children-per-node",
                str(self.base_children_per_node),
                "--max-children-per-node",
                str(self.max_children_per_node),
                "--semantic-merge-fact-threshold",
                str(self.semantic_merge_fact_threshold),
                "--semantic-merge-issue-threshold",
                str(self.semantic_merge_issue_threshold),
            ]
            if self.disable_semantic_node_merge:
                cli_args.append("--disable-semantic-node-merge")
            if self.top_p is not None:
                cli_args.extend(["--top-p", str(self.top_p)])
            if self.base_url:
                cli_args.extend(["--base-url", self.base_url])

            copy_best_code = (
                "import json, shutil; "
                "from pathlib import Path; "
                f"result=Path({result_path!r}); checkpoint=Path({checkpoint_path!r}); "
                "source=result if result.is_file() and result.stat().st_size else checkpoint; "
                "data=json.loads(source.read_text(encoding='utf-8')); "
                "src=Path(data['best_workspace']); dst=Path('/app'); "
                "shutil.copytree(src, dst, dirs_exist_ok=True, "
                "ignore=lambda _p,names: {n for n in names if n == '.git'})"
            )
            command_text = " ".join(shlex.quote(item) for item in cli_args)
            shell_command = "\n".join(
                [
                    "set +e",
                    (
                        "PYTHONPATH=/installed-agent/src "
                        f"{command_text} > {shlex.quote(result_path)} "
                        f"2> >(tee {shlex.quote(progress_path)} >&2)"
                    ),
                    "agent_code=$?",
                    (
                        f"if [ ! -s {shlex.quote(result_path)} ] && "
                        f"[ ! -s {shlex.quote(checkpoint_path)} ]; then exit $agent_code; fi"
                    ),
                    "set -e",
                    f"{shlex.quote(python_executable)} -c {shlex.quote(copy_best_code)}",
                    "exit 0",
                ]
            )
            result = await environment.exec(
                command=shell_command,
                cwd="/app",
                env={key_name: api_key},
                timeout_sec=(
                    int(self.agent_timeout_sec)
                    if self.agent_timeout_sec is not None
                    else None
                ),
            )
            if result.return_code != 0:
                raise RuntimeError(
                    "cli_retrac_mcts failed inside the task container: "
                    f"return_code={result.return_code}; stderr={result.stderr}"
                )


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _validate_name(value: str, label: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
        raise argparse.ArgumentTypeError(
            f"{label} 只能包含字母、数字、下划线、点和连字符"
        )
    return value


def _run_streaming(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    agent_log_command: list[str] | None = None,
    agent_log_lines: int = 0,
) -> tuple[int, list[str]]:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )
    agent_log_process: subprocess.Popen[str] | None = None
    agent_log_thread: threading.Thread | None = None
    if agent_log_command is not None and agent_log_lines > 0:
        try:
            agent_log_process = subprocess.Popen(
                agent_log_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            agent_log_thread = threading.Thread(
                target=_relay_agent_progress,
                args=(agent_log_process, agent_log_lines),
                daemon=True,
            )
            agent_log_thread.start()
        except OSError as exc:
            print(f"[日志] 无法启动Agent日志跟随器：{exc}", file=sys.stderr)

    lines: list[str] = []
    assert process.stdout is not None
    try:
        for line in process.stdout:
            lines.append(line)
            print(line, end="", flush=True)
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
        process.stdout.close()
        if agent_log_process is not None:
            # Harbor主进程结束时，旁路跟随器可能还有最后一批日志尚未来得及轮询。
            # 留出一个轮询周期，把任务收尾、检查点和最终模型响应同步到PowerShell。
            time.sleep(1.2)
            agent_log_process.terminate()
            try:
                agent_log_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                agent_log_process.kill()
                agent_log_process.wait()
            if agent_log_thread is not None:
                agent_log_thread.join(timeout=1)


def _should_show_agent_progress(line: str) -> bool:
    """转发Agent产生的全部结构化日志，行为与SWE运行器的直接输出一致。"""

    # 只接受logging统一生成的“时间 | [模块] 内容”行，避免Harbor警告和
    # 大段第三方堆栈淹没终端；API重试、流式活动和所有执行阶段均会保留。
    return re.match(r"^\d{2}:\d{2}:\d{2} \| \[[^\]]+\] ", line) is not None


def _relay_agent_progress(
    process: subprocess.Popen[str], max_lines_per_trial: int
) -> None:
    """把WSL旁路跟随器输出的日志转发到当前PowerShell。"""

    counts: dict[str, int] = {}
    limit_reported: set[str] = set()
    if process.stdout is None:
        return
    try:
        for raw_line in process.stdout:
            trial_name, separator, line = raw_line.rstrip("\r\n").partition("\t")
            if not separator or not _should_show_agent_progress(line):
                continue
            count = counts.get(trial_name, 0)
            if count < max_lines_per_trial:
                print(f"[Agent:{trial_name}] {line}", flush=True)
                counts[trial_name] = count + 1
            elif trial_name not in limit_reported:
                print(
                    f"[Agent:{trial_name}] 已达到实时日志上限 "
                    f"{max_lines_per_trial} 行；完整日志仍保存在结果目录。",
                    flush=True,
                )
                limit_reported.add(trial_name)
    finally:
        process.stdout.close()


def _agent_log_tail_script(job_dir: str) -> str:
    """生成在WSL中持续读取各Trial新增进度行的轻量脚本。"""

    quoted_job_dir = shlex.quote(job_dir.rstrip("/"))
    return f"""
job_dir={quoted_job_dir}
declare -A seen_lines
while true; do
  for progress_file in "$job_dir"/*/agent/retrac_progress.log; do
    [ -f "$progress_file" ] || continue
    total_lines=$(wc -l < "$progress_file")
    previous_lines=${{seen_lines["$progress_file"]:-0}}
    if [ "$total_lines" -lt "$previous_lines" ]; then
      previous_lines=0
    fi
    if [ "$total_lines" -gt "$previous_lines" ]; then
      trial_name=${{progress_file#"$job_dir"/}}
      trial_name=${{trial_name%%/*}}
      sed -n "$((previous_lines + 1)),${{total_lines}}p" "$progress_file" |
        while IFS= read -r progress_line; do
          printf '%s\\t%s\\n' "$trial_name" "$progress_line"
        done
      seen_lines["$progress_file"]=$total_lines
    fi
  done
  sleep 1
done
""".strip()


def _wsl_command(distro: str, script: str) -> list[str]:
    return ["wsl.exe", "-d", distro, "--", "bash", "-lc", script]


def _to_wsl_path(distro: str, path: Path) -> str:
    resolved = str(path.resolve())
    drive_match = re.fullmatch(r"([A-Za-z]):[\\/](.*)", resolved)
    if drive_match:
        drive, remainder = drive_match.groups()
        return f"/mnt/{drive.lower()}/{remainder.replace(chr(92), '/')}"

    # 非盘符路径再交给 WSL 处理，例如用户主动传入的 UNC 路径。
    completed = subprocess.run(
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
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout.strip()


def _read_wsl_json(distro: str, path: str) -> dict[str, Any]:
    completed = subprocess.run(
        _wsl_command(distro, f"cat {shlex.quote(path)}"),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return json.loads(completed.stdout)


def _read_terminal_agent_results(
    distro: str,
    job_dir: str,
) -> list[dict[str, Any]]:
    code = "\n".join(
        [
            "import json, sys",
            "from pathlib import Path",
            "rows = []",
            "for path in sorted(Path(sys.argv[1]).glob('*/agent/retrac_result.json')):",
            "    try:",
            "        row = json.loads(path.read_text(encoding='utf-8'))",
            "    except (OSError, json.JSONDecodeError):",
            "        continue",
            "    if isinstance(row, dict):",
            "        row['trial_name'] = path.parents[1].name",
            "        rows.append(row)",
            "print(json.dumps(rows, ensure_ascii=False))",
        ]
    )
    completed = subprocess.run(
        ["wsl.exe", "-d", distro, "--", "python3", "-c", code, job_dir],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    payload = json.loads(completed.stdout)
    if not isinstance(payload, list):
        raise ValueError("terminal agent results must be a list")
    return [row for row in payload if isinstance(row, dict)]


def _write_wsl_json(
    distro: str,
    path: str,
    payload: dict[str, Any],
) -> None:
    code = (
        "import sys; from pathlib import Path; "
        "p=Path(sys.argv[1]); p.parent.mkdir(parents=True, exist_ok=True); "
        "p.write_text(sys.argv[2], encoding='utf-8')"
    )
    subprocess.run(
        [
            "wsl.exe",
            "-d",
            distro,
            "--",
            "python3",
            "-c",
            code,
            path,
            json.dumps(payload, ensure_ascii=False, indent=2),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _wsl_job_directory_exists(distro: str, workdir: str, job_name: str) -> bool:
    """判断同名Harbor job目录是否已经存在。"""

    job_dir = f"{workdir.rstrip('/')}/jobs/{job_name}"
    completed = subprocess.run(
        ["wsl.exe", "-d", distro, "--", "test", "-e", job_dir],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return completed.returncode == 0


def _ensure_unique_job_name(distro: str, workdir: str, job_name: str) -> str:
    """重名时创建新名称，避免Harbor把不同配置误当成续跑任务。"""

    if not _wsl_job_directory_exists(distro, workdir, job_name):
        return job_name

    suffix = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    candidate = f"{job_name}-retry-{suffix}-{os.getpid()}"
    sequence = 2
    while _wsl_job_directory_exists(distro, workdir, candidate):
        candidate = f"{job_name}-retry-{suffix}-{os.getpid()}-{sequence}"
        sequence += 1
    print(
        f"[准备] job目录 {job_name} 已存在；为保留旧结果，"
        f"本次自动改用：{candidate}"
    )
    return candidate


def _cleanup_job_containers(distro: str, workdir: str, job_name: str) -> list[str]:
    """只停止当前Harbor job及其trial容器，不触碰其他历史或并行任务。"""

    job_dir = f"{workdir.rstrip('/')}/jobs/{job_name}"
    script = (
        f"job_dir={shlex.quote(job_dir)}\n"
        f"job_name={shlex.quote(job_name)}\n"
        "for proc in /proc/[0-9]*; do\n"
        "  [ -r \"$proc/comm\" ] && [ -r \"$proc/cmdline\" ] || continue\n"
        "  comm=$(cat \"$proc/comm\")\n"
        "  case \"$comm\" in python*) ;; *) continue;; esac\n"
        "  command=$(tr '\\0' ' ' < \"$proc/cmdline\")\n"
        "  case \"$command\" in\n"
        "    *\"/harbor run \"*\"--job-name $job_name\"*) "
        "kill -TERM \"${proc##*/}\" 2>/dev/null && echo \"harbor:${proc##*/}\";;\n"
        "  esac\n"
        "done\n"
        "sleep 1\n"
        "for proc in /proc/[0-9]*; do\n"
        "  [ -r \"$proc/comm\" ] && [ -r \"$proc/cmdline\" ] || continue\n"
        "  comm=$(cat \"$proc/comm\")\n"
        "  case \"$comm\" in python*) ;; *) continue;; esac\n"
        "  command=$(tr '\\0' ' ' < \"$proc/cmdline\")\n"
        "  case \"$command\" in\n"
        "    *\"/harbor run \"*\"--job-name $job_name\"*) "
        "kill -KILL \"${proc##*/}\" 2>/dev/null && echo \"harbor-kill:${proc##*/}\";;\n"
        "  esac\n"
        "done\n"
        "[ -d \"$job_dir\" ] || exit 0\n"
        "docker ps -a --format '{{.Names}}' | while IFS= read -r name; do\n"
        "  for trial_dir in \"$job_dir\"/*; do\n"
        "    [ -d \"$trial_dir\" ] || continue\n"
        "    trial=$(basename \"$trial_dir\" | tr '[:upper:]' '[:lower:]')\n"
        "    case \"$name\" in\n"
        "      \"${trial}__env-\"*) docker rm -f -- \"$name\" >/dev/null && echo \"$name\";;\n"
        "    esac\n"
        "  done\n"
        "done"
    )
    #脚本通过stdin直接交给bash，避免Windows/WSL命令行边界提前展开$proc等变量
    completed = subprocess.run(
        ["wsl.exe", "-d", distro, "--", "bash", "-s", "--"],
        input=script.encode("utf-8"),
        check=False,
        capture_output=True,
    )
    # 真实 subprocess 返回 bytes；单元测试和部分包装器可能直接返回 str。
    stdout = (
        completed.stdout.decode("utf-8", errors="replace")
        if isinstance(completed.stdout, bytes)
        else str(completed.stdout or "")
    )
    stderr = (
        completed.stderr.decode("utf-8", errors="replace")
        if isinstance(completed.stderr, bytes)
        else str(completed.stderr or "")
    )
    if completed.returncode != 0:
        print(
            f"[清理] 当前job容器清理失败：{stderr.strip()}",
            file=sys.stderr,
        )
        return []
    return [line for line in stdout.splitlines() if line.strip()]


def _docker_image_exists(docker_executable: str, image: str) -> bool:
    return (
        subprocess.run(
            [docker_executable, "image", "inspect", image],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )


def _prepare_images(args: argparse.Namespace, task_names: list[str]) -> int:
    if args.skip_image_pull:
        return 0
    print("[准备] 检查任务镜像")
    for index, task_name in enumerate(task_names, start=1):
        image = f"{DEFAULT_IMAGE_NAMESPACE}/{task_name}:{DEFAULT_IMAGE_TAG}"
        print(f"[镜像 {index}/{len(task_names)}] {image}")
        if _docker_image_exists(args.docker_executable, image):
            print("  本地已存在。")
            continue
        for attempt in range(1, args.image_pull_attempts + 1):
            print(f"  拉取尝试 {attempt}/{args.image_pull_attempts}")
            code, _ = _run_streaming([args.docker_executable, "pull", image])
            if code == 0:
                break
            if attempt == args.image_pull_attempts:
                return code
            delay = min(2**attempt, 30)
            print(f"  {delay}秒后重新拉取")
            time.sleep(delay)
    return 0


def _model_defaults(provider: str) -> tuple[str, str, str]:
    if provider == "deepseek":
        return (
            os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            "DEEPSEEK_API_KEY",
        )
    return (
        os.getenv("OPENAI_MODEL", "gpt-4o"),
        os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "OPENAI_API_KEY",
    )


def _wsl_env_with_secret(secret_name: str) -> dict[str, str]:
    env = os.environ.copy()
    current = [item for item in env.get("WSLENV", "").split(":") if item]
    entry = f"{secret_name}/u"
    if entry not in current:
        current.append(entry)
    env["WSLENV"] = ":".join(current)
    return env


def _print_summary(
    result: dict[str, Any],
    result_path: str,
    *,
    interaction_summary: dict[str, Any] | None = None,
    interaction_summary_path: str | None = None,
) -> None:
    stats = result.get("stats", {})
    evals = stats.get("evals", {})
    selected_total = int(result.get("n_total_trials", 0))
    total_passed = 0
    print("\n========== 当前模型的 Terminal-Bench 2 结果 ==========")
    print(f"完成 Trial：{stats.get('n_completed_trials', 0)}")
    print(f"异常 Trial：{stats.get('n_errored_trials', 0)}")
    for eval_name, eval_result in evals.items():
        total = int(eval_result.get("n_trials", 0))
        rewards = eval_result.get("reward_stats", {}).get("reward", {})
        passed = len(rewards.get("1.0", []))
        total_passed += passed
        rate = (passed / total * 100.0) if total else 0.0
        print(f"评测配置：{eval_name}")
        print(f"进入verifier后通过：{passed}/{total}")
        print(f"verifier通过率：{rate:.1f}%")
        print(f"Reward 分布：{json.dumps(rewards, ensure_ascii=False)}")
    end_to_end_rate = (
        total_passed / selected_total * 100.0 if selected_total else 0.0
    )
    print(f"端到端通过：{total_passed}/{selected_total}")
    print(f"端到端通过率：{end_to_end_rate:.1f}%")
    if interaction_summary is not None:
        print(
            "平均交互轮次："
            f"{interaction_summary.get('average_interaction_rounds')}"
        )
        print(
            "Agent验证成功任务平均交互轮次："
            f"{interaction_summary.get('average_successful_interaction_rounds')}"
        )
        print(
            f"交互轮次有效记录：{interaction_summary.get('recorded_task_count', 0)}/{selected_total}；"
            "内部 verified_success 不等同于官方 verifier 通过。"
        )
        if "research_metrics" in interaction_summary:
            print_research_metrics(interaction_summary["research_metrics"])
        if interaction_summary_path:
            print(f"交互轮次摘要（WSL）：{interaction_summary_path}")
    print(f"结果文件（WSL）：{result_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="让当前 RE-TRAC+MCTS 模型运行多道 Terminal-Bench 2 任务。",
        allow_abbrev=False,
    )
    parser.add_argument("--provider", choices=("deepseek", "openai"), default="deepseek")
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--distro", default="Ubuntu")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--n-tasks", type=int, default=2)
    parser.add_argument(
        "--task-name",
        action="append",
        default=None,
        help="显式选择单题或多题（使用不带terminal-bench/前缀的名称，可重复）",
    )
    parser.add_argument(
        "--allow-frozen-test-set",
        action="store_true",
        help="仅供冻结测试集专用入口使用；普通开发运行不要设置",
    )
    parser.add_argument("--n-concurrent", type=int, default=1)
    parser.add_argument("--max-retries", type=int, default=0,
                        help="Harbor整题重试次数；沿用原.cmd测试入口，默认0，避免整题重复消耗")
    parser.add_argument("--max-iterations", type=int, default=24)
    parser.add_argument("--max-tool-calls", type=int, default=80)
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
    parser.add_argument("--agent-timeout-multiplier", type=float, default=20.0)
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
        "--selection-mode",
        choices=("root", "working", "hybrid", "exploit", "plore_ploit"),
        default="plore_ploit",
        help="先探索，后优先利用recommend；无可用推荐时恢复探索",
    )
    parser.add_argument("--hybrid-root-interval", type=int, default=4)
    parser.add_argument(
        "--budget-multiplier", type=float, default=1.0,
        help="弹性续算上限倍数；默认1，不自动续算；大于1会提高潜在API消耗",
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
        "--workdir",
        default="/home/research/benchmark-runs/terminal-bench",
    )
    parser.add_argument("--job-name", default=None)
    parser.add_argument("--docker-executable", default=DEFAULT_DOCKER_EXECUTABLE)
    parser.add_argument(
        "--image-pull-attempts",
        type=int,
        default=10,
        help="单个缺失镜像的最大拉取次数（默认10次，退避等待最多30秒）",
    )
    parser.add_argument("--skip-image-pull", action="store_true")
    parser.add_argument(
        "--agent-log-lines",
        type=int,
        default=2000,
        help="每个Trial在PowerShell中最多显示的结构化Agent日志行数；0表示关闭",
    )
    parser.add_argument(
        "--keep-containers",
        action="store_true",
        help="调试时保留当前job容器；默认在正常结束或中断后清理",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只显示计划，不调用模型、不启动评测",
    )
    return parser


def run(
    args: argparse.Namespace,
    *,
    task_names: list[str] | None = None,
    selection_summary: str | None = None,
) -> int:
    """执行一次Harbor评测；外部入口可以传入自己选出的任务清单。"""
    _configure_console()
    if task_names is None:
        if args.task_name:
            task_names = list(dict.fromkeys(args.task_name))
        else:
            if not 1 <= args.n_tasks <= len(DEFAULT_TASK_NAMES):
                print(
                    f"n-tasks 必须在 1 到 {len(DEFAULT_TASK_NAMES)} 之间",
                    file=sys.stderr,
                )
                return 2
            task_names = list(DEFAULT_TASK_NAMES[: args.n_tasks])
    else:
        task_names = list(task_names)
        if not task_names or any(not item for item in task_names):
            print("任务清单不能为空", file=sys.stderr)
            return 2
        if len(task_names) != len(set(task_names)):
            print("任务清单不能包含重复任务", file=sys.stderr)
            return 2
    try:
        for task_name in task_names:
            _validate_name(task_name, "task-name")
    except argparse.ArgumentTypeError as exc:
        print(f"参数错误：{exc}", file=sys.stderr)
        return 2
    try:
        reject_frozen_overlap(
            task_names,
            benchmark="terminal-bench",
            allow_frozen_test_set=getattr(args, "allow_frozen_test_set", False),
        )
    except FrozenTestSetError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if min(
        args.n_concurrent,
        args.max_iterations,
        args.max_tool_calls,
        args.model_timeout,
        args.model_max_wall_time,
        args.agent_timeout_multiplier,
        args.model_request_attempts,
        args.model_parse_attempts,
        args.image_pull_attempts,
        args.budget_multiplier,
        args.base_children_per_node,
        args.max_children_per_node,
    ) < 1:
        print("所有预算、超时和并发参数必须 >= 1", file=sys.stderr)
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
    if args.agent_log_lines < 0:
        print("agent-log-lines 必须 >= 0", file=sys.stderr)
        return 2

    job_name = args.job_name or datetime.now().strftime(
        "plore-ploit-tb2-%Y%m%d-%H%M%S-%f"
    )
    try:
        _validate_name(job_name, "job-name")
    except argparse.ArgumentTypeError as exc:
        print(f"参数错误：{exc}", file=sys.stderr)
        return 2

    default_model, default_base_url, key_name = _model_defaults(args.provider)
    model = args.model or default_model
    base_url = args.base_url or default_base_url

    print("========== Terminal-Bench 2 当前模型评测 ==========")
    print(f"运行名：{job_name}")
    print(f"Provider/Model：{args.provider}/{model}")
    if selection_summary:
        print(selection_summary)
    print(f"任务数：{len(task_names)}，并发：{args.n_concurrent}")
    print(
        f"每题基础搜索预算：{args.max_iterations}轮，"
        f"初始最多{args.max_tool_calls}次工具调用；沿用原项目题面复杂度调度；"
        f"续算={'关闭' if args.budget_multiplier == 1 else '开启'}，"
        f"硬上限倍数={args.budget_multiplier:g}；整题重试={args.max_retries}"
    )
    if args.selection_mode in {"exploit", "plore_ploit"}:
        print(
            "搜索策略：先探索，求解时recommend优先，无可用推荐则探索；"
            f"模式={args.selection_mode}，语义树宽={args.base_children_per_node}.."
            f"{args.max_children_per_node}（与访问次数无关）"
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
    print(f"Harbor 单题超时倍率：{args.agent_timeout_multiplier:g}x")
    print(f"每题实时Agent日志上限：{args.agent_log_lines}行")
    for index, task_name in enumerate(task_names, start=1):
        print(f"  {index:>2}. terminal-bench/{task_name}")

    if args.dry_run:
        print("\n[dry-run] 不调用 API、不启动 Docker/Harbor。")
        return 0
    if not os.getenv(key_name):
        print(f"缺少环境变量：{key_name}", file=sys.stderr)
        return 2

    try:
        job_name = _ensure_unique_job_name(args.distro, args.workdir, job_name)
    except OSError as exc:
        print(f"无法检查Harbor job目录：{exc}", file=sys.stderr)
        return 1

    image_code = _prepare_images(args, task_names)
    if image_code != 0:
        print(f"任务镜像准备失败，退出码：{image_code}", file=sys.stderr)
        return image_code

    try:
        project_wsl = _to_wsl_path(args.distro, PROJECT_ROOT)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"无法把项目路径转换为 WSL 路径：{exc}", file=sys.stderr)
        return 1

    harbor_args = [
        "harbor",
        "run",
        "--dataset",
        args.dataset,
    ]
    for task_name in task_names:
        harbor_args.extend(
            ["--include-task-name", f"terminal-bench/{task_name}"]
        )
    harbor_args.extend(
        [
            "--agent",
            "run_terminal_bench:RetracHarborAgent",
            "--model",
            f"{args.provider}/{model}",
            "--agent-kwarg",
            f"provider={args.provider}",
            "--agent-kwarg",
            f"base_url={base_url}",
            "--agent-kwarg",
            f"max_iterations={args.max_iterations}",
            "--agent-kwarg",
            f"max_tool_calls={args.max_tool_calls}",
            "--agent-kwarg",
            f"budget_multiplier={args.budget_multiplier}",
            "--agent-kwarg",
            f"model_timeout={args.model_timeout}",
            "--agent-kwarg",
            f"model_max_wall_time={args.model_max_wall_time}",
            "--agent-kwarg",
            f"model_request_attempts={args.model_request_attempts}",
            "--agent-kwarg",
            f"model_parse_attempts={args.model_parse_attempts}",
            "--agent-kwarg",
            f"temperature={args.temperature}",
            "--agent-kwarg",
            f"reasoning_effort={args.reasoning_effort}",
            "--agent-kwarg",
            f"solve_reasoning_effort={args.solve_reasoning_effort}",
            "--agent-kwarg",
            f"selection_mode={args.selection_mode}",
            "--agent-kwarg",
            f"hybrid_root_interval={args.hybrid_root_interval}",
            "--agent-kwarg",
            "base_children_per_node="
            f"{args.base_children_per_node}",
            "--agent-kwarg",
            "max_children_per_node="
            f"{args.max_children_per_node}",
            "--agent-kwarg",
            f"disable_semantic_node_merge={args.disable_semantic_node_merge}",
            "--agent-kwarg",
            f"semantic_merge_fact_threshold={args.semantic_merge_fact_threshold}",
            "--agent-kwarg",
            f"semantic_merge_issue_threshold={args.semantic_merge_issue_threshold}",
            "--allow-agent-host",
            urlparse(base_url).hostname or "api.deepseek.com",
            "--allow-agent-host",
            "astral.sh",
            "--allow-agent-host",
            "github.com",
            "--allow-agent-host",
            "objects.githubusercontent.com",
            "--allow-agent-host",
            "release-assets.githubusercontent.com",
            "--n-concurrent",
            str(args.n_concurrent),
            "--agent-timeout-multiplier",
            str(args.agent_timeout_multiplier),
            "--job-name",
            job_name,
            "--max-retries",
            str(args.max_retries),
            "--yes",
        ]
    )
    if args.top_p is not None:
        insertion = harbor_args.index("--allow-agent-host")
        harbor_args[insertion:insertion] = [
            "--agent-kwarg",
            f"top_p={args.top_p}",
        ]
    shell_script = (
        f"mkdir -p {shlex.quote(args.workdir)} && "
        f"cd {shlex.quote(project_wsl)} && "
        f"PYTHONPATH={shlex.quote(project_wsl)} "
        + " ".join(shlex.quote(item) for item in harbor_args)
        + f" --jobs-dir {shlex.quote(args.workdir.rstrip('/') + '/jobs')}"
    )
    job_dir = f"{args.workdir.rstrip('/')}/jobs/{job_name}"
    print("\n[运行] Harbor 将把每道题交给 RetracHarborAgent。")
    if args.agent_log_lines > 0:
        print(
            "[日志] 将实时显示完整结构化Agent日志；原始日志位于："
            f"{job_dir}/<trial>/agent/retrac_progress.log"
        )
    try:
        try:
            code, _ = _run_streaming(
                _wsl_command(args.distro, shell_script),
                env=_wsl_env_with_secret(key_name),
                agent_log_command=(
                    _wsl_command(args.distro, _agent_log_tail_script(job_dir))
                    if args.agent_log_lines > 0
                    else None
                ),
                agent_log_lines=args.agent_log_lines,
            )
        except KeyboardInterrupt:
            print("\n用户中止评测。", file=sys.stderr)
            return 130
    finally:
        if not args.keep_containers:
            removed = _cleanup_job_containers(args.distro, args.workdir, job_name)
            if removed:
                print(f"[清理] 已移除当前job残留容器：{', '.join(removed)}")
    if code != 0:
        print(f"Harbor 运行失败，退出码：{code}", file=sys.stderr)
        return code

    result_path = f"{args.workdir.rstrip('/')}/jobs/{job_name}/result.json"
    try:
        official_result = _read_wsl_json(args.distro, result_path)
        interaction_summary_path = (
            f"{args.workdir.rstrip('/')}/jobs/{job_name}/interaction-summary.json"
        )
        interaction_summary: dict[str, Any] | None = None
        try:
            agent_results = _read_terminal_agent_results(args.distro, job_dir)
            interaction_summary = summarize_interaction_rounds(agent_results)
            interaction_summary["research_metrics"] = summarize_research_metrics(agent_results)
            if getattr(args, "development_selection", None) is not None:
                interaction_summary["development_selection"] = args.development_selection
            _write_wsl_json(
                args.distro,
                interaction_summary_path,
                interaction_summary,
            )
        except (OSError, subprocess.CalledProcessError, ValueError, json.JSONDecodeError) as exc:
            print(f"无法汇总Agent交互轮次：{exc}", file=sys.stderr)
        _print_summary(
            official_result,
            result_path,
            interaction_summary=interaction_summary,
            interaction_summary_path=(
                interaction_summary_path if interaction_summary is not None else None
            ),
        )
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"无法读取 Harbor 结果：{exc}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    """保留原有固定子集入口；``--n-tasks 1``仍运行原来的一题。"""
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
