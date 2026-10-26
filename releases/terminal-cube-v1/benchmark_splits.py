"""读取并保护冻结的Benchmark测试集。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal


PROJECT_ROOT = Path(__file__).resolve().parent
FROZEN_MANIFEST = PROJECT_ROOT / "benchmark_splits" / "frozen_test_set_v1.json"
FROZEN_CHECKSUM = PROJECT_ROOT / "benchmark_splits" / "frozen_test_set_v1.sha256"


class FrozenTestSetError(RuntimeError):
    """冻结测试集缺失、被修改或被开发流程误用。"""


def _load_manifest() -> dict[str, object]:
    try:
        raw = FROZEN_MANIFEST.read_bytes()
        expected = FROZEN_CHECKSUM.read_text(encoding="ascii").strip().lower()
    except OSError as exc:
        raise FrozenTestSetError(f"无法读取冻结测试集：{exc}") from exc
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise FrozenTestSetError(
            "冻结测试集校验失败：frozen_test_set_v1.json 已被修改。"
            "不要覆盖v1；需要新划分时请另建v2。"
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FrozenTestSetError(f"冻结测试集JSON无效：{exc}") from exc
    if payload.get("split_version") != "v1" or payload.get("frozen") is not True:
        raise FrozenTestSetError("冻结测试集版本或frozen标记无效")
    return payload


def frozen_swebench_ids() -> tuple[str, ...]:
    """返回冻结的SWE-bench Verified测试实例。"""
    payload = _load_manifest()
    section = payload.get("swebench_verified")
    values = section.get("instance_ids") if isinstance(section, dict) else None
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise FrozenTestSetError("冻结SWE-bench实例清单无效")
    if len(values) != 50 or len(values) != len(set(values)):
        raise FrozenTestSetError("冻结SWE-bench实例数量或唯一性校验失败")
    return tuple(values)


def frozen_terminal_task_names(*, bare: bool = False) -> tuple[str, ...]:
    """返回冻结的Terminal-Bench任务名；bare=True时去掉数据集前缀。"""
    payload = _load_manifest()
    section = payload.get("terminal_bench_2")
    values = section.get("task_names") if isinstance(section, dict) else None
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise FrozenTestSetError("冻结Terminal-Bench任务清单无效")
    if len(values) != 9 or len(values) != len(set(values)):
        raise FrozenTestSetError("冻结Terminal-Bench任务数量或唯一性校验失败")
    if not bare:
        return tuple(values)
    prefix = "terminal-bench/"
    if any(not item.startswith(prefix) for item in values):
        raise FrozenTestSetError("冻结Terminal-Bench任务前缀无效")
    return tuple(item[len(prefix) :] for item in values)


def reject_frozen_overlap(
    values: list[str] | tuple[str, ...],
    *,
    benchmark: Literal["swebench", "terminal-bench"],
    allow_frozen_test_set: bool,
) -> None:
    """阻止开发或调试运行误用冻结测试题。"""
    protected = (
        set(frozen_swebench_ids())
        if benchmark == "swebench"
        else set(frozen_terminal_task_names(bare=True))
    )
    overlap = sorted(set(values) & protected)
    if overlap and not allow_frozen_test_set:
        rendered = ", ".join(overlap)
        raise FrozenTestSetError(
            f"本次选择包含冻结测试题：{rendered}。"
            "开发阶段禁止运行；最终测试请使用专用frozen_test入口。"
        )
