"""Bounded, evidence-first monitor views and whole-run scheduling."""
import hashlib
import json
import math
from collections import Counter
from .prompt_views import clip


def size(value):
    return len(json.dumps(value, ensure_ascii=False))


def build_context(runner, reason, limit):
    all_rows = list(runner.evidence.values())
    pending = list(runner.memory_pending.values())[-4:] if hasattr(runner, 'memory_pending') else []
    # Latest observations plus older representative pending failures; bounded
    # individually, rather than dropping all useful evidence for task repetition.
    selected = all_rows[-8:]
    selected += [r for r in pending if r['id'] not in {v['id'] for v in selected}][-2:]
    goal = runner.task.goal
    progress = runner.progress.view()
    task_digest = hashlib.sha256(goal.encode()).hexdigest()
    candidates = selected
    # If fixed per-record metadata alone exhausts a very small budget, retain
    # two recent observations rather than abandoning the review entirely.
    for scale, count in ((1,len(candidates)),(.65,len(candidates)),
                         (.4,len(candidates)),(.2,len(candidates)),(.2,4),(.2,2)):
        selected = candidates if count >= len(candidates) else all_rows[-count:]
        def excerpt(text, maximum):
            return clip(str(text), max(60, int(maximum*scale)))
        evidence = []
        for row in selected:
            evidence.append(dict(id=row['id'], argv=excerpt(row.get('argv',''),360),
                purpose=excerpt(row.get('purpose',''),140),
                stdout=excerpt(row.get('stdout',''),500), stderr=excerpt(row.get('stderr',''),350),
                before=row.get('before'), after=row.get('after'), return_code=row.get('return_code'),
                timed_out=row.get('timed_out',False), blocked=row.get('blocked',False),
                category=row.get('category'), capture_incomplete=row.get('capture_incomplete',False),
                outcome={k:row.get('execution_assessment',{}).get(k) for k in
                         ('execution_clean','suspected_failure','check_status')},
                monitor_view_partial=True, historical=row['id'] not in {e['id'] for e in all_rows[-8:]}))
        memories=[dict(id=m['id'],conclusion=excerpt(m['conclusion'],220),
                       condition=excerpt(m['condition'],150),status=m.get('status'))
                  for m in list(runner.memory.items.values())[-4:]]
        prior=runner.monitor_review
        recovery=runner.control_view() if hasattr(runner,'control_view') else {}
        recovery_view={k:recovery.get(k) for k in ('id','status','action_seen','target_changed','verification_seen')}
        if recovery:
            recovery_view.update(reason=excerpt(recovery.get('reason',''),250),
                                 plan_excerpt=excerpt(json.dumps(recovery.get('plan'),ensure_ascii=False),500),
                                 partial=True)
        signatures=Counter((r.get('command_key',r.get('argv')),r.get('outcome_key',r.get('stdout')),r.get('after'))
                           for r in all_rows)
        payload=dict(task=dict(goal=excerpt(goal,2200),goal_sha256=task_digest,goal_chars=len(goal),
                              partial=len(goal)>int(2200*scale),
                              constraints=excerpt(json.dumps(list(runner.task.constraints),ensure_ascii=False),800)),
            trigger=reason,loop_detection=runner.config.semantic_monitor,memory_generation=runner.config.auto_memory,
            current_workspace=runner.environment.scope(),external_state='unverified',evidence=evidence,
            delivery=dict(missing_artifacts=[excerpt(p,120) for p in progress.get('missing_artifacts',[])[:16]],
                          extracted_paths=len(progress.get('requested_artifacts',[])),
                          task_correctness='unverified',note='No extracted paths is NOT completion.'),
            prior_review={k:excerpt(prior.get(k,''),350) for k in ('id','verdict','reason','next_check')},
            recent_memories=memories,
            comparison=dict(window_steps=len(all_rows),omitted_evidence_count=max(0,len(candidates)-len(selected)),
                            exact_observation_repeats=sum(n-1 for n in signatures.values()),
                            repeats_are_not_automatically_useless=True,
                            intervention=recovery_view),
            scope='Partial excerpts, not full task/trajectory. Use uncertain when omitted context is needed. Exact quotes support observations, not causal conclusions.')
        if size(payload)<=limit:
            return payload,dict(mode='compact' if scale==1 else 'minimal',chars=size(payload),limit=limit,
                                evidence_count=len(evidence),task_partial=payload['task']['partial'])
    raise ValueError('monitor_minimum_evidence_budget_unavailable')


def schedule(runner):
    """Reserve periodic calls across the full tool/time horizon; anomalies cannot spend them."""
    tools=runner.counts['tool_calls']
    progress=max(tools/runner.config.max_tools,
                 (__import__('time').monotonic()-runner.started_at)/runner.config.wall_seconds)
    quota=runner.config.max_monitor_calls
    periodic=max(1,math.ceil(quota/2))
    due=sum(progress >= (i+.5)/periodic for i in range(periodic))
    used=runner.monitor_lanes['periodic']
    if used<due:
        return 'periodic', 'periodic_review'
    emergency=quota-periodic
    allowance=min(emergency,1+int(progress*emergency))
    if runner.monitor_lanes['anomaly']>=allowance:
        return None
    recent=list(runner.evidence.values())[-runner.config.monitor_cooldown_tools:]
    fails=sum(r.get('return_code')!=0 or r.get('execution_assessment',{}).get('suspected_failure',False) for r in recent)
    keys=[(r.get('command_key',r.get('argv')),r.get('outcome_key',r.get('stdout')),r.get('after')) for r in recent]
    repeated=max(Counter(keys).values(),default=0)>=3
    reason=runner.monitor_event or ('failure_cluster' if fails>=3 else 'repeated_observation' if repeated else None)
    return ('anomaly',reason) if reason else None
