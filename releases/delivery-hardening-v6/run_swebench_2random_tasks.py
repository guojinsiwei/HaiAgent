"""从 SWE-bench Verified 非冻结开发池固定随机抽题，默认2题。"""

from __future__ import annotations

import sys
from datetime import datetime

import run_swebench


DEFAULT_SAMPLE_SIZE = 2


def build_parser():
    parser = run_swebench.build_parser()
    parser.description = (
        "从 SWE-bench Verified 非冻结开发池随机抽题（默认2题）；首次保存清单，"
        "后续复用同一题目和顺序。"
    )
    parser.set_defaults(
        sample_size=DEFAULT_SAMPLE_SIZE,
        max_iterations=24,
        max_tool_calls=80,
    )
    for action in parser._actions:
        if action.dest in {"instance_id", "sample_fraction", "allow_frozen_test_set"}:
            action.help = "本入口禁止覆盖；从非冻结开发池按--sample-size随机抽题"
        elif action.dest == "sample_size":
            action.help = "从非冻结开发池抽取的题数（默认2）"
    return parser


def main(argv: list[str] | None = None) -> int:
    forwarded = list(sys.argv[1:] if argv is None else argv)
    forbidden = {
        "--instance-id", "--sample-fraction", "--allow-frozen-test-set"
    }
    if any(item.split("=", 1)[0] in forbidden for item in forwarded):
        print(
            "本入口从非冻结开发池随机抽题，不允许指定题目、比例或启用冻结测试集。",
            file=sys.stderr,
        )
        return 2
    parsed = build_parser().parse_args(forwarded)
    if parsed.dataset != run_swebench.DEFAULT_DATASET:
        print("本入口只运行 SWE-bench/SWE-bench_Verified。", file=sys.stderr)
        return 2
    if parsed.sample_size is None or parsed.sample_size < 1:
        print("sample-size必须是正整数。", file=sys.stderr)
        return 2
    if parsed.resume and parsed.run_id is None:
        print("恢复运行必须指定原来的 --run-id。", file=sys.stderr)
        return 2

    defaults = {
        "--run-id": datetime.now().strftime(
            f"best-fgs-swe-{parsed.sample_size}-%Y%m%d-%H%M%S-%f"
        ),
        "--selection-file": str(
            parsed.results_dir / f"dev-{parsed.sample_size}-selection.json"
        ),
        "--sample-size": str(parsed.sample_size),
        "--max-iterations": "24",
        "--max-tool-calls": "80",
    }
    supplied = {item.split("=", 1)[0] for item in forwarded}
    for flag, value in defaults.items():
        if flag not in supplied:
            forwarded.extend((flag, value))
    return run_swebench.main(forwarded)


if __name__ == "__main__":
    raise SystemExit(main())
