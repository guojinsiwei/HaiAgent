"""从排除冻结测试集后的 SWE-bench Verified 开发池随机抽取18题。"""

from __future__ import annotations

import sys
from datetime import datetime

import run_swebench


def build_parser():
    parser = run_swebench.build_parser()
    parser.description = (
        "从 SWE-bench Verified 非冻结开发池随机抽取18题；首次保存清单，"
        "后续复用。基础预算24轮/80次工具调用，难题调度到33轮/108次工具，默认不额外续算。"
    )
    parser.set_defaults(max_iterations=24, max_tool_calls=80)
    for action in parser._actions:
        if action.dest in {"instance_id", "sample_size", "sample_fraction", "allow_frozen_test_set"}:
            action.help = "本入口禁止覆盖；固定从非冻结开发池抽18题"
        elif action.dest == "sample_seed":
            action.help = "首次抽样种子；清单存在时须与原seed一致，省略则沿用清单"
    return parser


def main(argv: list[str] | None = None) -> int:
    forwarded = list(sys.argv[1:] if argv is None else argv)
    forbidden = {"--instance-id", "--sample-size", "--sample-fraction", "--allow-frozen-test-set"}
    if any(item.split("=", 1)[0] in forbidden for item in forwarded):
        print("本入口固定从非冻结开发池随机抽18题，不允许覆盖题数/题目或启用冻结测试集。", file=sys.stderr)
        return 2
    parsed = build_parser().parse_args(forwarded)
    if parsed.dataset != run_swebench.DEFAULT_DATASET:
        print("本入口只运行 SWE-bench/SWE-bench_Verified。", file=sys.stderr)
        return 2
    defaults = {
        "--run-id": datetime.now().strftime("best-fgs-swe18-%Y%m%d-%H%M%S-%f"),
        "--selection-file": str(parsed.results_dir / "dev18-selection.json"),
        "--max-iterations": "24",
        "--max-tool-calls": "80",
    }
    if parsed.resume and parsed.run_id is None:
        print("恢复运行必须指定原来的 --run-id。", file=sys.stderr)
        return 2
    supplied = {item.split("=", 1)[0] for item in forwarded}
    for flag, value in defaults.items():
        if flag not in supplied:
            forwarded.extend((flag, value))
    forwarded.extend(("--sample-size", "18"))
    return run_swebench.main(forwarded)


if __name__ == "__main__":
    raise SystemExit(main())
