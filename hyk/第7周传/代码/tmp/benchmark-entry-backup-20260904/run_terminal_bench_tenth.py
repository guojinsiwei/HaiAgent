"""从完整 Terminal-Bench 2 数据集随机抽取 1/10 运行当前模型。

本文件只负责发现和抽样任务，Harbor Agent、日志转发、镜像准备与结果汇总
全部复用 ``run_terminal_bench.py``，避免两个评测入口逐渐产生行为差异。
"""

from __future__ import annotations

import argparse
import json
import math
import random
import secrets
import subprocess
from datetime import datetime

from benchmark_splits import FrozenTestSetError, frozen_terminal_task_names
import run_terminal_bench as terminal_runner


SAMPLE_FRACTION = 0.1


def _random_sample(
    population: list[str] | tuple[str, ...], *, seed: int
) -> list[str]:
    """按固定seed随机抽取全集的10%，不足整数时向上取整。"""
    unique = sorted(dict.fromkeys(population))
    if not unique:
        raise ValueError("Terminal-Bench任务全集不能为空")
    sample_size = max(1, math.ceil(len(unique) * SAMPLE_FRACTION))
    return random.Random(seed).sample(unique, sample_size)


def _load_all_task_names(args: argparse.Namespace) -> list[str]:
    """使用Harbor自己的Python读取数据集任务清单，不启动任务容器。"""
    discovery_code = "\n".join(
        [
            "import asyncio",
            "import json",
            "from harbor.models.job.config import DatasetConfig",
            (
                "tasks = asyncio.run(DatasetConfig("
                f"name={args.dataset!r}, ref='latest').get_task_configs())"
            ),
            "print(json.dumps([task.name for task in tasks]))",
        ]
    )
    launcher = subprocess.run(
        terminal_runner._wsl_command(args.distro, "command -v harbor"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if launcher.returncode != 0 or not launcher.stdout.strip():
        raise RuntimeError(launcher.stderr.strip() or "WSL中找不到harbor命令")
    launcher_path = launcher.stdout.strip().splitlines()[-1]
    shebang = subprocess.run(
        [
            "wsl.exe",
            "-d",
            args.distro,
            "--",
            "head",
            "-n",
            "1",
            launcher_path,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    first_line = shebang.stdout.strip()
    if shebang.returncode != 0 or not first_line.startswith("#!/"):
        raise RuntimeError(shebang.stderr.strip() or "无法读取Harbor解释器路径")
    harbor_python = first_line[2:].strip().split()[0]
    completed = subprocess.run(
        [
            "wsl.exe",
            "-d",
            args.distro,
            "--",
            harbor_python,
            "-c",
            discovery_code,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    try:
        task_names = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Harbor返回的任务清单不是合法JSON：{exc}") from exc
    if not isinstance(task_names, list) or not all(
        isinstance(item, str) and item for item in task_names
    ):
        raise RuntimeError("Harbor返回了无效的任务清单")
    if len(task_names) != len(set(task_names)):
        raise RuntimeError("Terminal-Bench数据集包含重复任务")
    return task_names


def _bare_task_name(task_name: str) -> str:
    prefix = "terminal-bench/"
    if not task_name.startswith(prefix) or len(task_name) == len(prefix):
        raise ValueError(f"无法识别Terminal-Bench任务名：{task_name}")
    return task_name[len(prefix) :]


def build_parser() -> argparse.ArgumentParser:
    parser = terminal_runner.build_parser()
    parser.description = (
        "从完整 Terminal-Bench 2 数据集随机抽取1/10，交给当前"
        " RE-TRAC+MCTS 模型。"
    )
    parser.add_argument(
        "--sample-seed",
        type=int,
        default=None,
        help="随机抽样种子；省略时每次自动生成新种子",
    )
    for action in parser._actions:
        if action.dest == "n_tasks":
            action.help = "本入口固定按完整数据集的1/10抽样，此参数不使用"
            break
    return parser


def main(argv: list[str] | None = None) -> int:
    terminal_runner._configure_console()
    args = build_parser().parse_args(argv)
    try:
        all_task_names = _load_all_task_names(args)
        frozen_task_names = set(frozen_terminal_task_names())
        development_task_names = [
            item for item in all_task_names if item not in frozen_task_names
        ]
        sample_seed = (
            args.sample_seed if args.sample_seed is not None else secrets.randbits(64)
        )
        selected_task_names = _random_sample(
            development_task_names,
            seed=sample_seed,
        )
        bare_task_names = [_bare_task_name(item) for item in selected_task_names]
    except (FrozenTestSetError, OSError, RuntimeError, ValueError) as exc:
        print(f"生成Terminal-Bench随机抽样失败：{exc}")
        return 1

    if args.job_name is None:
        args.job_name = datetime.now().strftime("retrac-tb2-tenth-%Y%m%d-%H%M%S")
    selection_summary = (
        f"随机抽样：全集{len(all_task_names)}题，冻结测试集"
        f"{len(frozen_task_names)}题，开发池{len(development_task_names)}题，"
        f"抽取{len(bare_task_names)}题，seed={sample_seed}"
    )
    return terminal_runner.run(
        args,
        task_names=bare_task_names,
        selection_summary=selection_summary,
    )


if __name__ == "__main__":
    raise SystemExit(main())
