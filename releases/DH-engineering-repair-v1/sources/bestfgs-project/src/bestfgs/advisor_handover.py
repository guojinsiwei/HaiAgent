"""Bounded evidence-derived handover, without another model/summarization call."""
import hashlib
import json
from .lean_audit import digest
from .prompt_views import clip


def build_handover(runner, question, trigger, limit=6000):
    scope = runner.environment.scope()
    dependencies = runner.environment.dependency_state(runner.memory.dependency_targets())
    problems = [row for row in runner.evidence.values() if row.get('return_code',0) != 0
        or row.get('timed_out') or row.get('blocked')
        or row.get('execution_assessment',{}).get('suspected_failure')]
    grouped = {}
    for row in problems:
        key = digest([row.get('command_key',row.get('argv')),row.get('cwd','.'),row['after']])
        if key not in grouped: grouped[key] = []
        grouped[key].append(row)
    groups = list(grouped.values())
    groups.sort(key=lambda rows: list(runner.evidence).index(rows[-1]['id']))
    selected = groups[-3:][::-1]
    query = question + ' ' + runner.task.goal[:500]
    if problems: query += ' ' + problems[-1].get('stderr','')[:500]
    memories = runner.memory.recall(query,scope,dependencies,limit=3)
    for scale in (1,.65,.4,.2):
        def excerpt(value, maximum):
            return clip(str(value),max(40,int(maximum*scale)))
        attempts = []
        for rows in selected:
            row = rows[-1]
            attempts.append(dict(command=excerpt(row.get('argv',''),360),cwd=row.get('cwd','.'),
                purpose=excerpt(row.get('purpose',''),180),evidence_ids=[r['id'] for r in rows[-3:]],
                observed_repetitions=len(rows),return_code=row.get('return_code'),
                timed_out=row.get('timed_out',False),blocked=row.get('blocked',False),
                diagnostic_excerpt=excerpt(row.get('stderr') or row.get('stdout',''),400),
                capture_incomplete=row.get('capture_incomplete',False),
                workspace_changed=row['before'] != row['after'],observed_after=row['after'],
                historical=True, current_failure_confirmed=False,
                observation_type='captured_command_failure' if row.get('return_code',0) != 0
                    else 'warning_not_verified_failure'))
        report = dict(version='advisor-handover-v1',trigger=trigger,
            original_goal=dict(excerpt=excerpt(runner.task.goal,900),chars=len(runner.task.goal),
                sha256=hashlib.sha256(runner.task.goal.encode()).hexdigest(),
                full_goal_ref='task.goal in this request'),
            question=excerpt(question,700),current_workspace=scope,external_state='unverified',
            latest_problem=attempts[0] if attempts else None,
            failed_attempts=attempts,distinct_failed_attempts_observed=len(groups),
            omitted_attempt_groups=max(0,len(groups)-len(attempts)),
            relevant_memories=[dict(id=m['id'],conclusion=excerpt(m['conclusion'],300),
                condition=excerpt(m['condition'],240),applicability=m['applicability'],
                status=m.get('status','unverified_claim'),evidence_ids=m['evidence_ids']) for m in memories],
            advertised_evidence_ids=sorted({eid for a in attempts for eid in a['evidence_ids']}),
            limitations=['Command failures are NOT proof that a whole algorithm or route is impossible.',
                'Historical problems may already be resolved; current cause and external state are unknown.',
                'Fewer than three attempts is valid. No invented failed strategies or causal diagnosis.'])
        if len(json.dumps(report,ensure_ascii=False)) <= limit:
            return report
    raise ValueError('handover evidence cannot fit configured budget')
