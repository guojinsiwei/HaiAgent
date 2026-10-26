"""从 Terminal-Bench 2 非冻结开发池固定随机抽题，默认2题。"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from benchmark_selection import development_selection
from benchmark_splits import FrozenTestSetError, frozen_terminal_task_names
import run_terminal_bench as terminal_runner
from run_terminal_bench_tenth import _bare_task_name, _load_all_task_names


DEFAULT_SAMPLE_SIZE = 2


def build_parser():
    parser = terminal_runner.build_parser()
    parser.description = (
        "从 Terminal-Bench 2 非冻结开发池随机抽题（默认2题）；首次保存清单，"
        "后续复用同一题目和顺序。"
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=DEFAULT_SAMPLE_SIZE,
        help="从非冻结开发池抽取的题数（默认2）",
    )
    parser.add_argument(
        "--sample-seed",
        type=int,
        default=None,
        help="首次抽样种子；清单存在时必须与原seed一致，省略则沿用清单",
    )
    parser.add_argument(
        "--selection-file",
        type=Path,
        default=None,
        help="抽样清单路径；默认按题数保存为dev-N-selection.json",
    )
    parser.set_defaults(n_tasks=None, max_iterations=24, max_tool_calls=80)
    for action in parser._actions:
        if action.dest in {"n_tasks", "task_name", "allow_frozen_test_set"}:
            action.help = "本入口禁止指定；题数请使用--sample-size"
    return parser


def main(argv: list[str] | None = None) -> int:
    terminal_runner._configure_console()
    args = build_parser().parse_args(argv)
    if args.task_name or args.n_tasks is not None or args.allow_frozen_test_set:
        print(
            "本入口从非冻结开发池随机抽题，不允许直接指定任务或启用冻结测试集。",
            file=sys.stderr,
        )
        return 2
    if args.sample_size < 1:
        print("sample-size必须是正整数。", file=sys.stderr)
        return 2
    if args.dataset != terminal_runner.DEFAULT_DATASET:
        print("本入口只运行 terminal-bench/terminal-bench-2。", file=sys.stderr)
        return 2
    if args.selection_file is None:
        args.selection_file = (
            Path(__file__).resolve().parent
            / "benchmark_results"
            / "terminal-bench"
            / f"dev-{args.sample_size}-selection.json"
        )
    try:
        frozen = set(frozen_terminal_task_names())
        sample_plan = development_selection(
            path=args.selection_file,
            benchmark="terminal-bench",
            dataset=args.dataset,
            protected=frozen,
            discover=lambda: _load_all_task_names(args),
            seed=args.sample_seed,
            sample_size=args.sample_size,
        )
        task_names = [_bare_task_name(item) for item in sample_plan["task_ids"]]
        args.development_selection = sample_plan
    except (FrozenTestSetError, OSError, RuntimeError, ValueError) as exc:
        print(f"生成Terminal-Bench抽样失败：{exc}", file=sys.stderr)
        return 1

    if args.job_name is None:
        args.job_name = datetime.now().strftime(
            f"best-fgs-tb2-{args.sample_size}-%Y%m%d-%H%M%S-%f"
        )
    selection_summary = (
        f"随机抽样：全集{sample_plan['dataset_size']}题，冻结测试集{len(frozen)}题，"
        f"开发池{sample_plan['development_pool_size']}题，抽取{args.sample_size}题，"
        f"seed={sample_plan['sample_seed']}\n"
        f"固定开发题清单：{args.selection_file.resolve()}（已保存；后续直接复用）\n"
        f"抽样清单SHA256：{sample_plan['selection_sha256']}"
    )
    return terminal_runner.run(
        args,
        task_names=task_names,
        selection_summary=selection_summary,
    )


if __name__ == "__main__":
    raise SystemExit(main())
