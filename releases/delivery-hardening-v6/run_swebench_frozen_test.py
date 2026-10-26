"""运行冻结的SWE-bench Verified v1最终测试集。"""

from __future__ import annotations

import sys
from datetime import datetime

from benchmark_splits import frozen_swebench_ids
import run_swebench


def main(argv: list[str] | None = None) -> int:
    forwarded = list(sys.argv[1:] if argv is None else argv)
    forbidden = {"--instance-id", "--sample-fraction", "--sample-size", "--sample-seed", "--selection-file"}
    if any(item.split("=", 1)[0] in forbidden for item in forwarded):
        print("冻结测试集入口不允许修改题目清单或抽样参数。", file=sys.stderr)
        return 2
    if not any(item == "--run-id" or item.startswith("--run-id=") for item in forwarded):
        forwarded.extend(
            (
                "--run-id",
                datetime.now().strftime("best-fgs-swe-frozen-v1-%Y%m%d-%H%M%S-%f"),
            )
        )
    forwarded.append("--allow-frozen-test-set")
    for instance_id in frozen_swebench_ids():
        forwarded.extend(("--instance-id", instance_id))
    return run_swebench.main(forwarded)


if __name__ == "__main__":
    raise SystemExit(main())
