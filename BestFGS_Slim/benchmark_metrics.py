"""Shared reporting-only metrics for benchmark runners."""

from __future__ import annotations

import math
from typing import Any, Iterable


def summarize_interaction_rounds(
    rows: Iterable[dict[str, Any]],
    *,
    rounds_key: str = "interaction_rounds",
    success_key: str = "succeeded",
) -> dict[str, int | float | None]:
    """Aggregate recorded search-transition counts without affecting the policy."""

    materialized = list(rows)
    recorded: list[int] = []
    successful: list[int] = []
    failed: list[int] = []
    for row in materialized:
        value = row.get(rounds_key)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or value < 0
            or int(value) != value
        ):
            continue
        rounds = int(value)
        recorded.append(rounds)
        if bool(row.get(success_key)):
            successful.append(rounds)
        else:
            failed.append(rounds)

    return {
        "task_count": len(materialized),
        "recorded_task_count": len(recorded),
        "successful_recorded_task_count": len(successful),
        "failed_recorded_task_count": len(failed),
        "total_interaction_rounds": sum(recorded),
        "average_interaction_rounds": _mean_or_none(recorded),
        "average_successful_interaction_rounds": _mean_or_none(successful),
        "average_failed_interaction_rounds": _mean_or_none(failed),
    }


def _mean_or_none(values: list[int]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


RESEARCH_METRIC_LABELS = {
    "final_semantic_coverage_rate": "最终语义覆盖率",
    "effective_exploration_ratio": "有效探索比例",
    "knowledge_reuse_rate": "知识复用率",
    "tool_call_redundancy_rate": "工具调用冗余率",
}


def summarize_research_metrics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Macro-average existing per-task indicators; missing records are not zeros."""
    materialized = list(rows)
    summary: dict[str, Any] = {}
    for key in RESEARCH_METRIC_LABELS:
        values = []
        for row in materialized:
            indicators = row.get("post_hoc_indicators")
            value = indicators.get(key) if isinstance(indicators, dict) else None
            if (
                not isinstance(value, bool) and isinstance(value, (int, float))
                and math.isfinite(value) and 0 <= value <= 1
            ):
                values.append(value)
        summary[key] = {
            "mean": round(sum(values) / len(values), 6) if values else None,
            "recorded_task_count": len(values),
        }
    return summary


def print_research_metrics(summary: dict[str, Any]) -> None:
    print("四项研究指标（有记录任务的宏平均；缺失值不按0计）：")
    for key, label in RESEARCH_METRIC_LABELS.items():
        metric = summary.get(key, {})
        value = metric.get("mean")
        rendered = f"{value:.2%}" if value is not None else "N/A"
        print(f"  {label}：{rendered}；有效记录={metric.get('recorded_task_count', 0)}题")
