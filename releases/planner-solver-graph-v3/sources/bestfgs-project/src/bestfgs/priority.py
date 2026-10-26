from __future__ import annotations

from dataclasses import asdict, dataclass
import math

from .models import MacroAction, StructuredContext


@dataclass(frozen=True, slots=True)
class PhaseWeights:
    progress: float
    recommend: float
    novelty: float
    information_gain: float
    candidate_maturity: float


@dataclass(frozen=True, slots=True)
class NodePriorityEvidence:
    """Only evidence produced by real transitions may raise these values."""

    real_progress: float = 0.0
    candidate_maturity: float = 0.0
    last_direction_status: str = "exploring"


@dataclass(frozen=True, slots=True)
class PriorityBreakdown:
    band: int
    score: float
    solve_pressure: float
    progress: float
    recommend: float
    avoid_compliance: float
    novelty: float
    information_gain: float
    candidate_maturity: float
    cost_penalty: float
    repeat_penalty: float
    failure_penalty: float
    aging_bonus: float

    def as_dict(self) -> dict[str, int | float]:
        return asdict(self)


def clamp01(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return max(0.0, min(1.0, value))


def phase_weights(solve_pressure: float) -> PhaseWeights:
    """Interpolate smoothly from semantic exploration to verified solving."""

    x = clamp01(solve_pressure)
    return PhaseWeights(
        progress=0.20 + 0.15 * x,
        recommend=0.10 + 0.15 * x,
        novelty=0.30 - 0.25 * x,
        information_gain=0.30 - 0.20 * x,
        candidate_maturity=0.10 + 0.15 * x,
    )


def compute_solve_pressure(
    *,
    previous: float,
    semantic_coverage: float,
    coverage_threshold: float,
    iteration: int,
    max_iterations: int,
    used_tool_calls: int,
    action_tool_budget: int,
    candidate_maturity: float = 0.0,
) -> float:
    """Return a monotonic phase value in [0, 1].

    Budget consumption, semantic coverage and real candidate evidence are
    blended instead of allowing any single early threshold to saturate the
    signal.  The value reaches one only at the ordinary budget boundary (or
    when all three evidence sources are jointly very strong).
    """

    iteration_progress = clamp01(max(0, iteration) / max(1, max_iterations))
    tool_progress = clamp01(max(0, used_tool_calls) / max(1, action_tool_budget))
    budget_progress = max(iteration_progress, tool_progress)
    coverage_progress = clamp01(
        semantic_coverage / max(coverage_threshold, 1e-9)
    )
    maturity_progress = clamp01(candidate_maturity)
    blended = (
        0.55 * budget_progress
        + 0.25 * coverage_progress
        + 0.20 * maturity_progress
    )
    if budget_progress >= 1.0:
        blended = 1.0
    return max(clamp01(previous), clamp01(blended))


def semantic_novelty(context: StructuredContext, action: MacroAction) -> float:
    for direction in context.semantic_directions:
        if direction.direction_id != action.semantic_direction_id:
            continue
        if direction.status == "unexplored":
            return 1.0
        if direction.status == "exploring":
            return 0.5
        return 0.0
    # A newly proposed direction is useful, but receives less credit than a
    # direction from the task's established semantic map.
    return 0.65


def information_gain(context: StructuredContext, action: MacroAction, novelty: float) -> float:
    unresolved = {item.strip().casefold() for item in context.unresolved_issues if item.strip()}
    targets = {item.strip().casefold() for item in action.target_issue_ids if item.strip()}
    exact_matches = len(unresolved.intersection(targets))
    if unresolved and exact_matches:
        targeted = min(1.0, exact_matches / min(2, len(unresolved)))
    else:
        targeted = 0.0
    declared_evidence = 1.0 if action.expected_evidence.strip() else 0.0
    diagnostic = 1.0 if action.intent == "explore" else 0.35
    return clamp01(
        0.55 * targeted
        + 0.25 * novelty * diagnostic
        + 0.20 * declared_evidence
    )


def calculate_priority(
    *,
    context: StructuredContext,
    action: MacroAction,
    evidence: NodePriorityEvidence,
    solve_pressure: float,
    direction_failures: int,
    action_repeat_count: int,
    consecutive_direction_count: int,
    estimated_tool_calls: int,
    max_commands_per_action: int,
    waiting_rounds: int,
    experience_id_bonus: bool = False,
) -> PriorityBreakdown:
    """Score one state-action frontier item without another model request."""

    weights = phase_weights(solve_pressure)
    progress = clamp01(evidence.real_progress)
    recommend = (
        1.0 / (1.0 + max(0, direction_failures))
        if experience_id_bonus and action.applied_rule_ids
        else 0.0
    )
    avoid_compliance = min(1.0, len(action.avoided_rule_ids) / 2) if experience_id_bonus else 0.0
    novelty = semantic_novelty(context, action)
    info_gain = information_gain(context, action, novelty)
    candidate_maturity = clamp01(
        evidence.candidate_maturity
        + (0.25 if action.intent == "candidate" else 0.0)
        + (0.20 if action.verification_commands else 0.0)
    )
    verification_gaps = {
        item.strip().casefold()
        for item in context.unresolved_issues
        if item.strip().casefold().startswith("independent verification gap:")
    }
    refinement_targeted = bool(
        verification_gaps
        and (
            {item.strip().casefold() for item in action.target_issue_ids}
            & verification_gaps
            or any(
                gap.removeprefix("independent verification gap:").strip()
                in (
                    action.semantic_direction_label
                    + " "
                    + action.expected_evidence
                    + " "
                    + action.rationale
                ).casefold()
                for gap in verification_gaps
            )
        )
    )

    cost_penalty = 0.15 * clamp01(
        max(1, estimated_tool_calls) / max(1, max_commands_per_action)
    )
    repeat_signal = max(
        clamp01(action_repeat_count / 2),
        clamp01(max(0, consecutive_direction_count - 1) / 2),
    )
    repeat_penalty = 0.20 * repeat_signal
    failure_penalty = 0.20 * clamp01(direction_failures / 3)
    aging_bonus = min(0.10, max(0, waiting_rounds) * 0.02)

    score = (
        weights.progress * progress
        + weights.recommend * recommend
        + 0.12 * avoid_compliance
        + weights.novelty * novelty
        + weights.information_gain * info_gain
        + weights.candidate_maturity * candidate_maturity
        - cost_penalty
        - repeat_penalty
        - failure_penalty
        + aging_bonus
    )

    # A concrete independent-audit gap on a mature candidate is the most
    # specific available next step.  It outranks broad exploration until that
    # refinement frontier has been exhausted.
    if refinement_targeted and candidate_maturity >= 0.60:
        band = 4
    elif progress >= 0.75 or candidate_maturity >= 0.75:
        band = 3
    # A recommendation is only promoted above information-seeking actions
    # once solve pressure is substantial.  Before that it remains a weighted
    # hint inside the exploration band, so the phase weights can genuinely
    # prefer a targeted novel diagnosis.
    elif progress >= 0.40 or (
        (recommend > 0 or avoid_compliance > 0) and solve_pressure >= 0.50
    ):
        band = 2
    elif novelty > 0 or info_gain > 0.20:
        band = 1
    else:
        band = 0

    return PriorityBreakdown(
        band=band,
        score=round(score, 6),
        solve_pressure=round(clamp01(solve_pressure), 6),
        progress=round(progress, 6),
        recommend=round(recommend, 6),
        avoid_compliance=round(avoid_compliance, 6),
        novelty=round(novelty, 6),
        information_gain=round(info_gain, 6),
        candidate_maturity=round(candidate_maturity, 6),
        cost_penalty=round(cost_penalty, 6),
        repeat_penalty=round(repeat_penalty, 6),
        failure_penalty=round(failure_penalty, 6),
        aging_bonus=round(aging_bonus, 6),
    )
