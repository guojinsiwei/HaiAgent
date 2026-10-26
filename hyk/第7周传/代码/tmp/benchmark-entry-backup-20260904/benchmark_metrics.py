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
    """Aggregate recorded MCTS transition counts without affecting the policy."""

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
