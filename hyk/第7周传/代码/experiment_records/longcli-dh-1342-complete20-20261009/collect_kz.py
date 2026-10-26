"""Read-only public result export; no environment/credentials/provider calls."""
import json,hashlib,statistics,time
from pathlib import Path

ROOT=Path('/mnt/sdb/home/lizh639/longcli-dh-1342-complete20-20261009')

def collect():
    lock=json.loads((ROOT/'KZ-config-lock.json').read_text());rows=[]
    refs=lock['original_seven']+[dict(task=f.parent.name.split('--',1)[1],report=str(f))
        for f in (ROOT/'grades').glob('1342--*/result.json')]
    for ref in refs:
        file=Path(ref['report']);raw=file.read_bytes();g=json.loads(raw)
        digest=hashlib.sha256(raw).hexdigest()
        if 'sha256' in ref:assert digest==ref['sha256']
        sf=file.parent.parent.parent/'jobs'/file.parent.name/'summary.json'
        s=json.loads(sf.read_text());bf=ROOT/'jobs'/file.parent.name/'cost-bar.json'
        cost=json.loads(bf.read_text()) if bf.exists() else None
        rows.append(dict(task=ref['task'],cohort='original7' if 'sha256' in ref else 'supplement13',
            scored=g.get('grading_state')=='complete',score=g['f2p']['step_score'],
            official_success=g['official_success'],report=str(file),report_sha256=digest,
            summary=str(sf),summary_sha256=hashlib.sha256(sf.read_bytes()).hexdigest(),
            tools=s.get('tool_calls'),api_attempts=s.get('actual_api_attempts',s.get('api_attempts')),
            stop_reason=s.get('stop_reason'),engineering_fault=s.get('engineering_fault'),
            cost_upper_cny=cost.get('cost_upper_cny') if cost else None))
    assert len(rows)==20 and len({r['task'] for r in rows})==20 and all(r['scored'] for r in rows)
    return dict(name='KZ',generated=time.time(),rows=rows,scored=20,
        official_successes=sum(r['official_success'] for r in rows),
        mean_score=statistics.mean(r['score'] for r in rows),
        mean_tools=statistics.mean(r['tools'] for r in rows),
        mean_api=statistics.mean(r['api_attempts'] for r in rows),
        cost_censored=any(r['stop_reason']=='cost_budget_cny' for r in rows),
        comparability={'unchanged_core_files':lock['unchanged_source_files'],
            'same_solver_configuration':lock['consistent_core'],
            'old_seven_no_money_cap':True,'supplement_cap_cny':50,
            'concurrency_old_arm':2,'concurrency_supplement':6,
            'provider_alias_cannot_pin_weights':True},paid_audit_model_calls=0)

if __name__=='__main__':print(json.dumps(collect(),ensure_ascii=False))
