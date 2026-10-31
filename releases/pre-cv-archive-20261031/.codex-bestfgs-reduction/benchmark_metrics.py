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
    """Aggregate recorded BestFGS transition counts without affecting the policy."""

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


def swe_official_outcomes(report: dict[str, Any]) -> dict[str, bool | None]:
    outcomes = {key: None for key in report.get("submitted_ids", [])}
    outcomes.update({key: False for key in report.get("unresolved_ids", [])})
    outcomes.update({key: True for key in report.get("resolved_ids", [])})
    return outcomes


def terminal_official_outcomes(report: dict[str, Any]) -> dict[str, bool | None]:
    outcomes: dict[str, bool | None] = {}
    for evaluation in report.get("stats", {}).get("evals", {}).values():
        for reward, trials in evaluation.get("reward_stats", {}).get("reward", {}).items():
            try:
                value = float(reward)
            except (ValueError, TypeError):
                continue
            if math.isfinite(value):
                outcomes.update({trial: value == 1.0 for trial in trials})
    return outcomes


def summarize_official_interactions(
    rows: Iterable[dict[str, Any]], outcomes: dict[str, bool | None], *,
    id_key: str, rounds_key: str = "interaction_rounds", success_key: str = "succeeded",
    selected_count: int | None = None,
) -> dict[str, Any]:
    """Join grader results by task ID; absent grader/round data remains unknown."""
    rows = list(rows)
    summary = summarize_interaction_rounds(rows, rounds_key=rounds_key, success_key=success_key)
    diagnostic = dict(summary)
    graded = [{**row, "official_success": outcomes[row[id_key]]}
              for row in rows if row.get(id_key) in outcomes
              and isinstance(outcomes[row[id_key]], bool)]
    official = summarize_interaction_rounds(graded, rounds_key=rounds_key, success_key="official_success")
    for key in ("successful_recorded_task_count", "failed_recorded_task_count",
                "average_successful_interaction_rounds", "average_failed_interaction_rounds"):
        summary[key] = official[key]
    matrix = {key: 0 for key in ("true_positive", "false_positive", "true_negative", "false_negative")}
    for row in graded:
        predicted = row.get(success_key)
        if not isinstance(predicted, bool):
            continue
        actual = row["official_success"]
        matrix[("true_" if predicted == actual else "false_")
               + ("positive" if predicted else "negative")] += 1
    selected = selected_count if selected_count is not None else max(len(rows), len(outcomes))
    total_predictions = matrix["true_positive"] + matrix["false_positive"]
    matrix["precision"] = matrix["true_positive"] / total_predictions if total_predictions else None
    judged = sum(matrix[key] for key in ("true_positive", "false_positive", "true_negative", "false_negative"))
    matrix["accuracy"] = (matrix["true_positive"] + matrix["true_negative"]) / judged if judged else None
    summary.update({
        "task_count": selected,
        "success_basis": "official",
        "official_graded_task_count": sum(isinstance(value, bool) for value in outcomes.values()),
        "official_successful_task_count": sum(value is True for value in outcomes.values()),
        "official_ungraded_task_count": max(0, selected - sum(isinstance(value, bool) for value in outcomes.values())),
        "official_labeled_recorded_task_count": official["recorded_task_count"],
        "agent_diagnostic": diagnostic,
        "agent_vs_official": matrix,
    })
    return summary


def print_official_interaction_summary(summary: dict[str, Any]) -> None:
    print(f"平均交互轮次（全部有记录任务）：{summary.get('average_interaction_rounds')}")
    print(f"官方成功任务平均交互轮次：{summary.get('average_successful_interaction_rounds')}")
    print(f"官方失败任务平均交互轮次：{summary.get('average_failed_interaction_rounds')}")
    print(f"官方未评分任务：{summary.get('official_ungraded_task_count', 0)}（不混入成功/失败均值）")
    matrix = summary.get("agent_vs_official", {})
    print(f"内部判定误报成功：{matrix.get('false_positive', 0)}；漏判成功：{matrix.get('false_negative', 0)}")


RESEARCH_METRIC_LABELS = {
    "final_semantic_coverage_rate": "最终语义覆盖率（固定核心）",
    "effective_exploration_ratio": "有效探索比例",
    "knowledge_reuse_rate": "知识复用率",
    "tool_call_redundancy_rate": "工具调用冗余率",
}

COVERAGE_DIAGNOSTIC_LABELS = {
    "final_discovered_semantic_coverage_rate": "最终动态发现覆盖率",
}

EXPERIENCE_FUNNEL_COUNT_LABELS = {
    "recommend_rules_created": "生成recommend规则",
    "avoid_rules_created": "生成avoid规则",
    "retrieval_events": "规则召回轮次",
    "recommend_rules_exposed": "recommend提示暴露",
    "avoid_rules_exposed": "avoid提示暴露",
    "semantic_avoid_exposures": "语义avoid提示暴露",
    "model_rule_selected_actions": "模型选择规则的动作",
    "recommend_actions_validated": "通过适用性校验的recommend动作",
    "recommend_actions_enqueued": "进入前沿的recommend动作",
    "recommend_actions_executed": "实际执行的recommend动作",
    "recommend_actions_effective": "产生有效证据/修改的recommend动作",
    "recommend_frontier_priority_wins": "Recommend触发全局前沿利用优先",
    "avoid_actions_blocked": "avoid精确阻止动作",
    "avoid_actions_validated": "通过适用性校验的avoid规避动作",
    "avoid_actions_enqueued": "进入前沿的avoid规避动作",
    "avoid_actions_executed": "实际执行的avoid规避动作",
    "avoid_actions_effective": "产生有效证据/修改的avoid规避动作",
    "all_blocked_fallback_overrides": "全阻止后的安全兜底",
}

EXPERIENCE_FUNNEL_RATE_LABELS = {
    "recommend_enqueue_rate": "recommend校验→入队率",
    "recommend_execution_rate": "recommend入队→执行率",
    "recommend_effectiveness_rate": "recommend执行→有效率",
    "avoid_block_rate": "avoid动作阻止率",
    "avoid_execution_rate": "avoid规避入队→执行率",
    "avoid_effectiveness_rate": "avoid规避执行→有效率",
}


def summarize_research_metrics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Macro-average existing per-task indicators; missing records are not zeros."""
    materialized = list(rows)
    summary: dict[str, Any] = {}
    for key in (*RESEARCH_METRIC_LABELS, *COVERAGE_DIAGNOSTIC_LABELS):
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
    funnel_totals = {key: 0 for key in EXPERIENCE_FUNNEL_COUNT_LABELS}
    funnel_recorded = 0
    actions_evaluated = 0
    for row in materialized:
        indicators = row.get("post_hoc_indicators")
        funnel = indicators.get("experience_funnel") if isinstance(indicators, dict) else None
        if not isinstance(funnel, dict):
            continue
        funnel_recorded += 1
        for key in funnel_totals:
            value = funnel.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                funnel_totals[key] += value
        value = funnel.get("actions_evaluated_against_rules")
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            actions_evaluated += value
    validated = funnel_totals["recommend_actions_validated"]
    enqueued = funnel_totals["recommend_actions_enqueued"]
    executed = funnel_totals["recommend_actions_executed"]
    effective = funnel_totals["recommend_actions_effective"]
    blocked = funnel_totals["avoid_actions_blocked"]
    avoid_enqueued = funnel_totals["avoid_actions_enqueued"]
    avoid_executed = funnel_totals["avoid_actions_executed"]
    avoid_effective = funnel_totals["avoid_actions_effective"]
    summary["experience_funnel"] = {
        "recorded_task_count": funnel_recorded,
        "totals": funnel_totals,
        "actions_evaluated_against_rules": actions_evaluated,
        "rates": {
            "recommend_enqueue_rate": enqueued / validated if validated else None,
            "recommend_execution_rate": executed / enqueued if enqueued else None,
            "recommend_effectiveness_rate": effective / executed if executed else None,
            "avoid_block_rate": blocked / actions_evaluated if actions_evaluated else None,
            "avoid_execution_rate": (
                avoid_executed / avoid_enqueued if avoid_enqueued else None
            ),
            "avoid_effectiveness_rate": (
                avoid_effective / avoid_executed if avoid_executed else None
            ),
        },
    }
    return summary


def print_research_metrics(summary: dict[str, Any]) -> None:
    print("四项研究指标（有记录任务的宏平均；缺失值不按0计）：")
    for key, label in RESEARCH_METRIC_LABELS.items():
        metric = summary.get(key, {})
        value = metric.get("mean")
        rendered = f"{value:.2%}" if value is not None else "N/A"
        print(f"  {label}：{rendered}；有效记录={metric.get('recorded_task_count', 0)}题")
    for key, label in COVERAGE_DIAGNOSTIC_LABELS.items():
        metric = summary.get(key, {})
        value = metric.get("mean")
        rendered = f"{value:.2%}" if value is not None else "N/A"
        print(
            f"  {label}：{rendered}；有效记录={metric.get('recorded_task_count', 0)}题"
            "（诊断地图扩张，不参与奖励）"
        )
    funnel = summary.get("experience_funnel", {})
    totals = funnel.get("totals", {})
    rates = funnel.get("rates", {})
    print(
        "RE-TRAC任务内经验漏斗"
        f"（有效记录={funnel.get('recorded_task_count', 0)}题）："
    )
    for key, label in EXPERIENCE_FUNNEL_COUNT_LABELS.items():
        print(f"  {label}：{totals.get(key, 0)}")
    for key, label in EXPERIENCE_FUNNEL_RATE_LABELS.items():
        value = rates.get(key)
        rendered = f"{value:.2%}" if isinstance(value, (int, float)) else "N/A"
        print(f"  {label}：{rendered}")
