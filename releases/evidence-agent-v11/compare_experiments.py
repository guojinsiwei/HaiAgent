"""Paired statistics from two official evaluation results; no LLM calls or judging."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import random
import statistics
import sys

from benchmark_runtime import atomic_write_json, canonical_sha256
sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from bestfgs.experiment_metrics import METRIC_VERSION, METRIC_REPORT_VERSION
from bestfgs.redundancy import REDUNDANCY_VERSION, aggregate_redundancy, aggregate_mechanical


def official_outcome(task):
    if task.get('search_status') != 'completed':
        return None
    if task.get('verdict') == 'empty_patch':
        return 0
    if task.get('official_report_available') and isinstance(task.get('resolved'), bool):
        return int(task['resolved'])
    return None


def metric_ready(task):
    m = task.get('comparison_metrics') or {}
    counts = [m.get(k) for k in ('interaction_rounds', 'tool_calls', 'redundant_tool_calls')]
    valid_counts = all(type(v) is int and v >= 0 for v in counts)
    return (m.get('metric_version') == METRIC_VERSION and m.get('trace_complete') is True
            and valid_counts and counts[2] <= counts[1]
            and task.get('attempt_count', 1) == 1 and official_outcome(task) is not None)


def reduction(agent, baseline):
    return 1 - agent / baseline if baseline and agent is not None else None


def rates(tasks):
    metrics = [t['comparison_metrics'] for t in tasks]
    calls = sum(m['tool_calls'] for m in metrics)
    repeats = sum(m['redundant_tool_calls'] for m in metrics)
    per_task = [m['redundant_tool_calls'] / m['tool_calls'] for m in metrics if m['tool_calls']]
    phase = {}
    for name in ('action', 'functional_verification', 'final_verification'):
        n = sum(m.get('redundancy_by_phase', {}).get(name, {}).get('tool_calls', 0) for m in metrics)
        r = sum(m.get('redundancy_by_phase', {}).get(name, {}).get('redundant_tool_calls', 0) for m in metrics)
        phase[name] = {'tool_calls': n, 'repeated_calls': r, 'repeat_rate': r / n if n else None}
    result = {'n': len(tasks), 'mean_interaction_rounds': statistics.mean(m['interaction_rounds'] for m in metrics) if tasks else None,
            'tool_calls': calls, 'repeated_calls': repeats, 'repeat_rate_micro': repeats / calls if calls else None,
            'repeat_rate_macro': statistics.mean(per_task) if per_task else None,
            'zero_tool_tasks': sum(m['tool_calls'] == 0 for m in metrics), 'by_phase': phase,
            'recorded_model_usage': {k: sum(t.get('model_usage', {}).get(k, 0) for t in tasks)
                                     for k in ('model_calls', 'api_requests', 'api_responses', 'prompt_tokens', 'completion_tokens')},
            'recorded_wall_seconds': sum(t.get('last_attempt_seconds') or 0 for t in tasks)}
    measured_phases = None
    if metrics and all(isinstance(m.get('redundancy_by_phase'), dict) for m in metrics):
        measured_phases = {}
        for name in sorted({p for m in metrics for p in m['redundancy_by_phase']}):
            values = [m['redundancy_by_phase'].get(name, {}) for m in metrics]
            if all(all(type(v.get(k, 0)) is int and v.get(k, 0) >= 0
                       for k in ('tool_calls', 'redundant_tool_calls')) for v in values):
                measured_phases[name] = {'tool_calls': sum(v.get('tool_calls', 0) for v in values),
                                        'redundant_tool_calls': sum(v.get('redundant_tool_calls', 0) for v in values)}
            else:
                measured_phases[name] = {'tool_calls': None, 'redundant_tool_calls': None}
    result.update(aggregate_mechanical(metrics))
    result.update(aggregate_redundancy(metrics))
    result['tool_call_redundancy_rate_micro'] = result['tool_call_redundancy_rate']
    result['tool_call_redundancy_rate_macro'] = result['repeat_rate_macro'] if result['avoidable_repeat_status'] != 'unavailable' else None
    result['metric_report_version'] = METRIC_REPORT_VERSION
    return result


def paired_effect(pairs, kind):
    if not pairs:
        return None
    if kind == 'success_difference':
        return statistics.mean(official_outcome(a) - official_outcome(b) for a, b in pairs)
    if kind == 'round_reduction':
        return reduction(sum(a['comparison_metrics']['interaction_rounds'] for a, _ in pairs),
                         sum(b['comparison_metrics']['interaction_rounds'] for _, b in pairs))
    def rate(index):
        metrics = [p[index]['comparison_metrics'] for p in pairs]
        if kind == 'mechanical_repeat_rate_reduction':
            return aggregate_mechanical(metrics)['mechanical_repeat_rate']
        return aggregate_redundancy(metrics)['tool_call_redundancy_rate']
    return reduction(rate(0), rate(1))


def bootstrap(pairs, kind, repeats=2000, seed=20260918):
    if not pairs:
        return {'estimate': None, 'ci95': None, 'n_pairs': 0, 'valid_resamples': 0}
    rng = random.Random(seed)
    values = []
    for _ in range(repeats):
        value = paired_effect([pairs[rng.randrange(len(pairs))] for _ in pairs], kind)
        if value is not None:
            values.append(value)
    values.sort()
    # Require at least 95% defined replicates; ratios with near-zero denominators
    # must not get falsely reassuring conditional intervals.
    interval = [values[int(.025 * (len(values) - 1))], values[int(.975 * (len(values) - 1))]] if len(pairs) >= 2 and len(values) >= .95 * repeats else None
    return {'estimate': paired_effect(pairs, kind), 'ci95': interval, 'n_pairs': len(pairs),
            'valid_resamples': len(values), 'requested_resamples': repeats,
            'method': 'paired task-level percentile bootstrap; assumes tasks are sampling units'}


def compare(agent, baseline, *, repeats=2000):
    a_lock, b_lock = agent.get('comparison'), baseline.get('comparison')
    if not a_lock or not b_lock:
        raise ValueError('Legacy results lack a common protocol; do not compare legacy interaction/redundancy fields')
    if a_lock.get('method') != 'bestfgs' or b_lock.get('method') != 'raw':
        raise ValueError('Expected --agent bestfgs and --baseline raw')
    for lock in (a_lock, b_lock):
        if canonical_sha256(lock['protocol']) != lock['protocol_sha256']:
            raise ValueError('Protocol checksum mismatch')
    if a_lock['protocol'] != b_lock['protocol'] or a_lock['protocol'].get('metric_version') != METRIC_VERSION:
        raise ValueError('Tasks, environment, API settings, implementation or metric definition differ')
    if not agent.get('evaluation_parameters') or agent['evaluation_parameters'] != baseline.get('evaluation_parameters'):
        raise ValueError('Official grading runtime, dataset, split or timeout differs/missing')
    expected = a_lock['protocol']['expected_ids']
    if not expected or len(set(expected)) != len(expected):
        raise ValueError('Invalid fixed task denominator')
    if any([t['instance_id'] for t in data['tasks']] != expected for data in (agent, baseline)):
        raise ValueError('Both arms must contain exactly the fixed task IDs in order')
    pairs = list(zip(agent['tasks'], baseline['tasks']))
    for a, b in pairs:
        if a.get('official_report_available') and b.get('official_report_available'):
            if not a.get('grading_script_sha256') or a['grading_script_sha256'] != b.get('grading_script_sha256'):
                raise ValueError(f"Official test script differs/missing: {a['instance_id']}")
    observed_models = [sorted({model for task in data['tasks'] for model in task.get('model_usage', {}).get('response_models', [])}) for data in (agent, baseline)]
    if all(observed_models) and observed_models[0] != observed_models[1]:
        raise ValueError('API-reported model identifiers differ between arms')
    success = {}
    for name, data in (('bestfgs', agent), ('raw', baseline)):
        outcomes = [official_outcome(t) for t in data['tasks']]
        solved = sum(v == 1 for v in outcomes)
        unknown = sum(v is None for v in outcomes)
        success[name] = {'N': len(expected), 'resolved': solved, 'unknown_infrastructure_or_evaluation': unknown,
                         'rate': solved / len(expected) if not unknown else None,
                         'rate_bounds': [solved / len(expected), (solved + unknown) / len(expected)]}
    all_known = all(official_outcome(a) is not None and official_outcome(b) is not None for a, b in pairs)
    all_single = all(t.get('attempt_count', 1) == 1 for p in pairs for t in p)
    success_effect = bootstrap(pairs, 'success_difference', repeats) if all_known else None
    a_rate, b_rate = success['bestfgs']['rate'], success['raw']['rate']
    success['difference_percentage_points'] = 100 * (a_rate - b_rate) if all_known else None
    success['relative_improvement'] = (a_rate - b_rate) / b_rate if all_known and b_rate else None
    success['paired_difference'] = success_effect
    if all_known:
        wins = sum(official_outcome(a) > official_outcome(b) for a, b in pairs)
        losses = sum(official_outcome(a) < official_outcome(b) for a, b in pairs)
        discordant = wins + losses
        success['discordant_pairs'] = {'bestfgs_only': wins, 'raw_only': losses}
        success['mcnemar_exact_two_sided_p'] = min(1., 2 * sum(math.comb(discordant, k) for k in range(min(wins, losses) + 1)) / 2 ** discordant) if discordant else 1.
    eligible = [(a, b) for a, b in pairs if metric_ready(a) and metric_ready(b)]
    joint = [(a, b) for a, b in eligible if official_outcome(a) == official_outcome(b) == 1]
    cohorts = {}
    for name, cohort in (('all_complete_single_attempt_pairs', eligible), ('both_officially_resolved_pairs', joint)):
        cohorts[name] = {'ids': [a['instance_id'] for a, _ in cohort],
                         'bestfgs': rates([a for a, _ in cohort]), 'raw': rates([b for _, b in cohort]),
                         'round_reduction': bootstrap(cohort, 'round_reduction', repeats),
                         'repeat_rate_reduction': bootstrap(cohort, 'repeat_rate_reduction', repeats)}
        cohorts[name]['tool_call_redundancy_rate_reduction'] = cohorts[name]['repeat_rate_reduction']
        cohorts[name]['mechanical_repeat_rate_reduction'] = bootstrap(cohort, 'mechanical_repeat_rate_reduction', repeats)
    def threshold(result, target):
        estimate, interval = result.get('estimate'), result.get('ci95')
        return {'point_estimate_meets_target': estimate >= target if estimate is not None else None,
                'ci95_lower_meets_target': interval[0] >= target if interval else None}
    targets = {'valid_complete_protocol': all_known and all_single and len(eligible) == len(expected),
               'success_plus_10_percentage_points': threshold(success_effect or {}, .10),
               'success_plus_10_percent_relative_point': success['relative_improvement'] >= .10 if success['relative_improvement'] is not None else None,
               'rounds_minus_30_percent_on_joint_success': threshold(cohorts['both_officially_resolved_pairs']['round_reduction'], .30),
               'repeat_rate_minus_50_percent_on_joint_success': {
                   **threshold(cohorts['both_officially_resolved_pairs']['tool_call_redundancy_rate_reduction'], .50),
                   'status': 'automatic_reusable_evidence_metric',
                   'reason': 'Compare the preregistered detected redundancy rate, not all possible semantic waste; inspect unknown coverage in both arms.'}}
    targets['tool_call_redundancy_minus_50_percent_on_joint_success'] = targets['repeat_rate_minus_50_percent_on_joint_success']
    return {'metric_version': METRIC_VERSION, 'metric_report_version': METRIC_REPORT_VERSION,
            'protocol_sha256': a_lock['protocol_sha256'], 'success': success,
            'api_reported_models': {'bestfgs': observed_models[0], 'raw': observed_models[1]},
            'efficiency_cohorts': cohorts, 'targets': targets,
            'excluded_efficiency_ids': [a['instance_id'] for a, b in pairs if not (metric_ready(a) and metric_ready(b))],
            'notes': [
                'Official resolved/N, not internal succeeded. Unknown infrastructure results are not algorithm failures.',
                '10% success improvement is ambiguous: report both percentage points and relative improvement.',
                'CLI feedback batches are not LLM calls; inspect model_calls, tokens and wall time alongside them.',
                'Primary redundancy = automatically confirmed reusable-evidence calls / ALL actual tool calls; unknowns stay in the denominator and have separate coverage and sensitivity bounds.',
                'One final check per operation/condition is allowed. Unsupported shell, external state, truncation and uncertain retries are not declared redundant. Mechanical repetition remains diagnostic only.',
                'Both-success efficiency is conditional and can suffer selection bias. Report its IDs/N and the all-pair cohort together.',
                'One paired run on 100 tasks is not multi-seed evidence; task bootstrap does not model repository clustering or model stochasticity.',
                'Point targets are descriptive, not a certification of the stated improvement; fix the primary endpoint before running.',
                'Failed/retried attempts remain in official results previous_attempts; efficiency excludes them rather than silently erasing their costs.',
            ]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--bootstrap', type=int, default=2000)
    args = parser.parse_args(argv)
    if args.bootstrap < 200:
        parser.error('At least 200 bootstrap replicates required')
    result = compare(json.loads(args.agent.read_text(encoding='utf-8')), json.loads(args.baseline.read_text(encoding='utf-8')), repeats=args.bootstrap)
    atomic_write_json(args.output, result)
    print(json.dumps({'success': result['success'], 'targets': result['targets'], 'report': str(args.output.resolve())}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as exc:
        print(f'[comparison report error] {exc}', file=sys.stderr)
        raise SystemExit(2)
