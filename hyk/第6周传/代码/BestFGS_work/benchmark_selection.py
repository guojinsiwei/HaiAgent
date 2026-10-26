"""Freeze/replay development samples; never expose held-out tasks to development."""

from __future__ import annotations

import hashlib
import json
import math
import random
import secrets
from pathlib import Path
from typing import Callable

from benchmark_splits import FROZEN_MANIFEST


def _selection_digest(payload: dict) -> str:
    content = {key: value for key, value in payload.items() if key != "selection_sha256"}
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def development_selection(
    *,
    path: Path,
    benchmark: str,
    dataset: str,
    protected: set[str],
    discover: Callable[[], list[str]],
    seed: int | None,
    sample_size: int | None = None,
    fraction: float | None = None,
    save: bool = True,
) -> dict:
    """Existing files are reused, never overwritten. Call after frozen-set validation.

    A saved sample freezes task IDs/order, not remote dataset contents or model output.
    Discovery is unnecessary when replaying a saved sample.
    """
    if (sample_size is None) == (fraction is None):
        raise ValueError("必须且只能指定抽样题数或抽样比例")
    if sample_size is not None and (type(sample_size) is not int or sample_size < 1):
        raise ValueError("抽样题数必须是正整数")
    if fraction is not None and not 0 < fraction <= 1:
        raise ValueError("抽样比例必须在 (0, 1] 内")
    frozen_hash = hashlib.sha256(FROZEN_MANIFEST.read_bytes()).hexdigest()
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("抽样文件必须是JSON对象")
        if payload.get("selection_sha256") != _selection_digest(payload):
            raise ValueError("抽样文件校验失败：内容已被修改，请恢复原文件，不要重新抽题替代")
        expected = {
            "selection_version": 1,
            "benchmark": benchmark,
            "dataset": dataset,
            "frozen_manifest_sha256": frozen_hash,
            "sample_fraction": fraction,
        }
        if any(payload.get(key) != value for key, value in expected.items()):
            raise ValueError("抽样文件的数据集、划分版本或抽样规则不匹配；请换文件名，不要覆盖")
        ids = payload.get("task_ids")
        if (
            not isinstance(ids, list) or not ids
            or not all(isinstance(item, str) and item for item in ids)
            or len(ids) != len(set(ids)) or set(ids) & protected
        ):
            raise ValueError("抽样文件题目为空、重复、无效或包含冻结测试题")
        pool_size = payload.get("development_pool_size")
        dataset_size = payload.get("dataset_size")
        saved_seed = payload.get("sample_seed")
        if (
            type(pool_size) is not int or pool_size < len(ids)
            or type(dataset_size) is not int or dataset_size != pool_size + len(protected)
            or type(saved_seed) is not int
        ):
            raise ValueError("抽样文件的题库规模或seed无效")
        expected_size = sample_size if sample_size is not None else math.ceil(pool_size * fraction)
        if len(ids) != expected_size or payload.get("sample_size") != expected_size:
            raise ValueError("抽样文件题数不符合当前入口要求")
        if seed is not None and seed != saved_seed:
            raise ValueError("指定seed与已有抽样文件不一致；换题请使用新文件名")
        return payload

    population = discover()
    if (
        not isinstance(population, list) or not population
        or not all(isinstance(item, str) and item for item in population)
        or len(population) != len(set(population))
    ):
        raise ValueError("数据集题目清单为空、重复或无效")
    if not protected.issubset(population):
        raise ValueError("数据集缺少冻结清单中的题目；请检查数据集名称/版本，不自动更改冻结划分")
    development = sorted(set(population) - protected)
    count = sample_size if sample_size is not None else math.ceil(len(development) * fraction)
    if not 1 <= count <= len(development):
        raise ValueError(f"开发池只有{len(development)}题，无法抽取{count}题")
    actual_seed = seed if seed is not None else secrets.randbits(64)
    payload = {
        "selection_version": 1,
        "benchmark": benchmark,
        "dataset": dataset,
        "frozen_manifest_sha256": frozen_hash,
        "dataset_size": len(population),
        "development_pool_size": len(development),
        "development_pool_sha256": hashlib.sha256(
            "\n".join(development).encode("utf-8")
        ).hexdigest(),
        "sample_fraction": fraction,
        "sample_size": count,
        "sample_seed": actual_seed,
        "task_ids": random.Random(actual_seed).sample(development, count),
    }
    payload["selection_sha256"] = _selection_digest(payload)
    if save:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents overwriting another experiment's selection.
        with path.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    return payload
