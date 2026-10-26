"""从排除冻结测试集后的 Terminal-Bench 2 开发池随机抽取 1/10。

本文件只负责发现和抽样任务，Harbor Agent、日志转发、镜像准备与结果汇总
全部复用 ``run_terminal_bench.py``，避免两个评测入口逐渐产生行为差异。
"""

from __future__ import annotations

import argparse
import json
import math
import random
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from benchmark_selection import development_selection
from benchmark_splits import FrozenTestSetError, frozen_terminal_task_names
import run_terminal_bench as terminal_runner


SAMPLE_FRACTION = 0.1


def _random_sample(
    population: list[str] | tuple[str, ...], *, seed: int
) -> list[str]:
    """按固定seed随机抽取传入题库的10%，不足整数时向上取整。"""
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
        "从排除冻结测试集后的 Terminal-Bench 2 开发池随机抽取1/10；"
        "首次保存题目清单，后续复用同一清单。"
    )
    parser.add_argument(
        "--sample-seed",
        type=int,
        default=None,
        help="首次抽样种子；清单存在时必须与原seed一致，省略则沿用清单",
    )
    parser.add_argument(
        "--selection-file", type=Path,
        default=Path(__file__).resolve().parent / "benchmark_results" / "terminal-bench" / "dev-tenth-selection.json",
        help="开发题抽样清单：不存在时保存，存在时复用；dry-run也保存清单",
    )
    parser.set_defaults(n_tasks=None)
    for action in parser._actions:
        if action.dest in {"n_tasks", "task_name", "allow_frozen_test_set"}:
            action.help = "本入口禁止指定；固定从非冻结开发池抽取1/10"
    return parser


def main(argv: list[str] | None = None) -> int:
    terminal_runner._configure_console()
    args = build_parser().parse_args(argv)
    if args.task_name or args.n_tasks is not None or args.allow_frozen_test_set:
        print("本入口固定从非冻结开发池抽取1/10，不允许指定任务/题数或启用冻结测试集。", file=sys.stderr)
        return 2
    if args.dataset != terminal_runner.DEFAULT_DATASET:
        print("本入口只运行 terminal-bench/terminal-bench-2。", file=sys.stderr)
        return 2
    try:
        frozen_task_names = set(frozen_terminal_task_names())
        sample_plan = development_selection(
            path=args.selection_file,
            benchmark="terminal-bench", dataset=args.dataset,
            protected=frozen_task_names,
            discover=lambda: _load_all_task_names(args),
            seed=args.sample_seed, fraction=SAMPLE_FRACTION,
        )
        bare_task_names = [_bare_task_name(item) for item in sample_plan["task_ids"]]
        args.development_selection = sample_plan
    except (FrozenTestSetError, OSError, RuntimeError, ValueError) as exc:
        print(f"生成Terminal-Bench随机抽样失败：{exc}")
        return 1

    if args.job_name is None:
        args.job_name = datetime.now().strftime("plore-ploit-tb2-tenth-%Y%m%d-%H%M%S-%f")
    selection_summary = (
        f"随机抽样：全集{sample_plan['dataset_size']}题，冻结测试集"
        f"{len(frozen_task_names)}题，开发池{sample_plan['development_pool_size']}题，"
        f"抽取{len(bare_task_names)}题，seed={sample_plan['sample_seed']}\n"
        f"固定开发题清单：{args.selection_file.resolve()}（已保存；后续直接复用）\n"
        f"抽样清单SHA256：{sample_plan['selection_sha256']}"
    )
    return terminal_runner.run(
        args,
        task_names=bare_task_names,
        selection_summary=selection_summary,
    )


if __name__ == "__main__":
    raise SystemExit(main())
