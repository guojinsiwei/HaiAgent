"""Traceable fixed-20 historical comparison; never mix per-task best attempts."""
import hashlib
import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parent
RECORDS=ROOT.parent


def read(path):return json.loads(path.read_text(encoding='utf-8'))


def main():
    historical=RECORDS/'longcli-dh-raw-full20-20261004'
    protocol=read(historical/'protocol.json')
    data=read(historical/'full-report/report-data.json')
    grades=data['original_and_supplementary_grades']
    tasks=[row['task'] for row in protocol['tasks']]
    arms={m:{} for m in ('DH','RAW','DSH','Reflexion')}
    selected={}
    for method in ('dh','raw'):
        for task in tasks:
            job=method+'--'+task
            if method=='raw' and task=='cs61_fa24_scheme':job='roundtrip--cs61_fa24_scheme'
            if method=='dh' and task=='61810_pgtbl':job='roundtrip--outer-clock-fix--61810_pgtbl'
            report=grades[job]
            generation=data['network_retry_generation'] if job=='roundtrip--cs61_fa24_scheme' else data['original_generations'][method+'--'+task]
            assert report['artifact_sha256']==generation['artifact']['sha256']
            arms[method.upper()][task]=report
            selected[method.upper()+'/'+task]={'report_container':str(historical/'full-report/report-data.json'),'report_key':job}
    folders={'DSH':['longcli-dsh20-byte-context-repair-20261006'],
             'Reflexion':['longcli-reflexion20-college-20261006','longcli-reflexion-recovery-20261006']}
    for method,names in folders.items():
        for name in names:
            for path in (ROOT/'repaired-scores'/name).glob('*.json'):
                report=read(path);task=report['task'];assert task not in arms[method]
                arms[method][task]=report
                selected[method+'/'+task]={'source':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    metrics={}
    pinned={row['task']:row['image_id'] for row in protocol['tasks']}
    for method,rows in arms.items():
        assert set(rows)==set(tasks),method+' has missing/extra tasks'
        assert all(r['grading_state']=='complete' for r in rows.values())
        for task,report in rows.items():
            assert report['image_id']==pinned[task],method+'/'+task+' image differs'
            assert report['grading_cpu']==8 and report['grading_memory_gib']==8
        values=[r['f2p']['step_score'] for r in rows.values()]
        metrics[method]={'tasks':len(rows),'mean':statistics.mean(values),'median':statistics.median(values),
            'f2p_full':sum(r['f2p']['is_pass'] for r in rows.values()),
            'strict_success':sum(r['official_success'] for r in rows.values()),
            'zero':sum(v==0 for v in values),
            'os10_mean':statistics.mean(r['f2p']['step_score'] for t,r in rows.items() if t.startswith('61810_')),
            'other10_mean':statistics.mean(r['f2p']['step_score'] for t,r in rows.items() if not t.startswith('61810_'))}
        print(method,json.dumps(metrics[method]))
    pairs={}
    for method in ('DSH','Reflexion'):
        for baseline in ('DH','RAW'):
            differences=[arms[method][t]['f2p']['step_score']-arms[baseline][t]['f2p']['step_score'] for t in tasks]
            pairs[method+'/'+baseline]={'wins':sum(d>0 for d in differences),'ties':sum(d==0 for d in differences),
                'losses':sum(d<0 for d in differences),'mean_delta':statistics.mean(differences)}
    result={'tasks':tasks,'metrics':metrics,'paired':pairs,'source_selection':selected,
        'scores':[{'task':t,**{m:r[t]['f2p']['step_score'] for m,r in arms.items()}} for t in tasks],
        'notes':['Historical DH is v9 repair/recovery-counter-fix, not DHv1 and not graph search.',
                 'RAW scheme uses authorized retry after initial DNS failure; original failure retained.',
                 'DH pgtbl uses same-artifact corrected outer-clock grading; no new solver run.',
                 'All groups use fixed 20 task IDs, pinned official commit, deepseek-flash thinking disabled, temperature zero.',
                 '800 logical requests/600 tools are common ceilings, not identical algorithm-internal turn limits.',
                 'Historical DH48k characters differs from UTF8-byte DSH/Reflexion48k; DSH includes native tool schema.',
                 'Cube versus academy host/process isolation and persistent-shell semantics differ.',
                 'This is a historical matched-task comparison, not a fully controlled four-arm causal ablation.',
                 'Strict success includes raw official P2P checks, including known starter defects.']}
    (ROOT/'four-way-results-20261007.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(pairs))


if __name__=='__main__':main()
