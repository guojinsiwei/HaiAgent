"""Only run plore_ploit on the same two development tasks used by the originals."""

from __future__ import annotations

import sys
from datetime import datetime

import run_swebench


INSTANCE_IDS = ("sympy__sympy-16450", "matplotlib__matplotlib-20826")


def main(argv: list[str] | None = None) -> int:
    forwarded = list(sys.argv[1:] if argv is None else argv)
    forbidden = {"--instance-id", "--sample-fraction", "--sample-size", "--sample-seed"}
    if any(item.split("=", 1)[0] in forbidden for item in forwarded):
        print("This entry uses two fixed development tasks; use run_swebench.py for other tasks.", file=sys.stderr)
        return 2
    if not any(item.split("=", 1)[0] == "--run-id" for item in forwarded):
        forwarded.extend(("--run-id", datetime.now().strftime("plore-ploit-two-%Y%m%d-%H%M%S-%f")))
    for instance_id in INSTANCE_IDS:
        forwarded.extend(("--instance-id", instance_id))
    return run_swebench.main(forwarded)


if __name__ == "__main__":
    raise SystemExit(main())
