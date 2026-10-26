"""运行冻结的Terminal-Bench 2 v1最终测试集。"""

from __future__ import annotations

from datetime import datetime

from benchmark_splits import frozen_terminal_task_names
import run_terminal_bench as terminal_runner


def main(argv: list[str] | None = None) -> int:
    terminal_runner._configure_console()
    args = terminal_runner.build_parser().parse_args(argv)
    args.allow_frozen_test_set = True
    if args.job_name is None:
        args.job_name = datetime.now().strftime(
            "plore-ploit-tb2-frozen-v1-%Y%m%d-%H%M%S-%f"
        )
    task_names = list(frozen_terminal_task_names(bare=True))
    return terminal_runner.run(
        args,
        task_names=task_names,
        selection_summary="冻结测试集v1：9题；仅用于最终评测",
    )


if __name__ == "__main__":
    raise SystemExit(main())
