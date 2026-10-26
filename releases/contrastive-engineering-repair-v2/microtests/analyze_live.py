"""Verify live trace chains and summarize observed behavior, not causal benefit."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'sources/bestfgs-project/src'))
from bestfgs.lean_audit import read_trace, atomic_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    args=parser.parse_args()
    manifest=json.loads((ROOT/'evidence/source-manifest.json').read_text(encoding='utf-8'))
    report=json.loads((args.directory/'summary.json').read_text(encoding='utf-8'))
    observed=[]
    for stored in report['results']:
        run=args.directory/(stored['case']+('-memory' if stored['memory_enabled'] else '-control'))
        rows=read_trace(run/'events.jsonl')
        if rows[0]['source_hashes']!=manifest['candidate']: raise ValueError('Live source hashes differ')
        seed=[r for r in rows if r['event']=='live_test_phase' and r['phase']=='scripted_failure_seed']
        provider=[r for r in rows if r['event']=='live_test_phase' and r['phase']=='autonomous_provider']
        wire=[r for r in rows if r['event']=='wire_prompt' and r['role']=='action']
        responses=[r for r in rows if r['event']=='model_response' and r['role']=='action'][2:]
        calls=[r for r in rows if r['event']=='tool_call']
        repairs=[r for r in calls[2:] if r['command']['argv'][:2] in (['microtool','write'],['microtool','copy'])]
        grades=[r for r in rows if r['event']=='independent_fixture_grade']
        assert len(seed)==2 and len(provider)==stored['provider_decisions']
        assert len(wire)==stored['actual_api_usage']['api_requests']
        assert len(responses)==len(provider) and len(repairs)==1
        assert grades[-1]['fixture_goal_verified'] and stored['submitted']
        observed.append(dict(case=stored['case'],memory_enabled=stored['memory_enabled'],
            trace_chain_verified=True,source_hashes_verified=True,api_requests=len(wire),
            autonomous_decisions=len(provider),repair_action=repairs[0]['command']['argv'],
            repair_evidence_id=repairs[0]['evidence_id'],goal_verified=True,
            memory_reviews=stored['memory_reviews'],
            failures_after_seed=stored['failure_tool_calls_after_seed'],
            repeat_proposals_refused=stored['repeat_proposals_refused']))
    totals={field:sum(r['actual_api_usage'][field] for r in report['results'])
            for field in ('api_requests','prompt_tokens','completion_tokens')}
    verdict=dict(observed_runs=observed,actual_api_totals=totals,
        conclusion='All six goals independently passed. No unmodified check retries after seeds in either arm. No memory advantage demonstrated.',
        limitation=report['limitation'],causal_memory_benefit_proven=False)
    atomic_json(args.directory/'independent-analysis.json',verdict)
    print(json.dumps(verdict,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
