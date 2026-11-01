"""Return available official reports only; never launches/replays grading."""
import json
from pathlib import Path
import shlex
import time

from common import ROOT,save
from relay import college,COLLEGE,GRADER_PY

def pull():
    protocol=json.loads((ROOT/'protocol.json').read_text())
    expected={m+'--'+r['task'] for r in protocol['tasks'] for m in protocol['methods']}
    retry='roundtrip--cs61_fa24_scheme'
    grading_retry='roundtrip--61810_pgtbl'
    clock_retry='roundtrip--outer-clock-fix--61810_pgtbl'
    reader=('import json; from pathlib import Path; '
        'root=Path('+repr(COLLEGE+'/grades')+'); '
        'rows=[json.loads(p.read_text()) for p in sorted(root.glob("*/result.json"))]; '
        'print(json.dumps(rows))')
    reports=json.loads(college(GRADER_PY+' -c '+shlex.quote(reader),stage='Official score report return'))
    summaries={}
    for worker in (0,1):
        status=json.loads((ROOT/'paired-status.json').read_text())
        for health in status.get('workers',[]):
            if health.get('worker')==worker:
                summaries.update({r['job']:r for r in health.get('results',[])})
    supplementary_path=ROOT/'raw-scheme-retry-status.json'
    if supplementary_path.exists():
        supplementary=json.loads(supplementary_path.read_text())
        if supplementary.get('generation'):summaries[retry]=supplementary['generation']
    # This alias is only regrading of the SAME original DH source, not a new
    # generation attempt. Keep both official reports and their provenance.
    summaries[grading_retry]=summaries['dh--61810_pgtbl']
    summaries[clock_retry]=summaries['dh--61810_pgtbl']
    grades={}
    target=ROOT/'official-score-return'
    for report in reports:
        job=report['job']
        assert job in expected or job in (retry,grading_retry,clock_retry),'Unknown official report'
        assert job in summaries,'Generation provenance missing'
        assert report['artifact_sha256']==summaries[job]['artifact']['sha256'],'Artifact mismatch'
        assert report['fixture'] is False,'Offline fixture must not count as paid experiment'
        save(target/job/'official-report.json',report)
        grades[job]=report
    rows=[]
    for task in protocol['tasks']:
        name=task['task'];row=dict(task=name)
        for method in protocol['methods']:
            job=method+'--'+name
            report=grades.get(job)
            row[method]=None if report is None else dict(job=job,
                grading_state=report['grading_state'],f2p=report.get('f2p',{}).get('step_score'),
                p2p=report.get('p2p_step_score'),official_success=report.get('official_success'))
        if name=='cs61_fa24_scheme' and retry in grades:
            report=grades[retry]
            row['raw_network_retry']=dict(job=retry,attempt=2,grading_state=report['grading_state'],
                f2p=report.get('f2p',{}).get('step_score'),p2p=report.get('p2p_step_score'),
                official_success=report.get('official_success'),original_retained=True)
        if name=='61810_pgtbl' and grading_retry in grades:
            chosen=clock_retry if clock_retry in grades else grading_retry
            report=grades[chosen]
            row['dh_grading_retry']=dict(job=chosen,grading_attempt=3 if chosen==clock_retry else 2,
                grading_state=report['grading_state'],f2p=report.get('f2p',{}).get('step_score'),
                p2p=report.get('p2p_step_score'),official_success=report.get('official_success'),original_retained=True)
        rows.append(row)
    counts={method:dict(returned=sum(j.startswith(method+'--') for j in grades),
        official_successes=sum(j.startswith(method+'--') and r.get('official_success') is True for j,r in grades.items()))
        for method in protocol['methods']}
    result=dict(updated=time.time(),expected_original=40,returned_original=len(expected & grades.keys()),
        returned_supplementary=int(retry in grades),returned_grading_retry=sum(j in grades for j in (grading_retry,clock_retry)),arms=counts,rows=rows,
        pending=sorted(expected-grades.keys()),original_and_retry_separately_reported=True,
        no_model_calls=True,no_grading_replayed=True)
    save(target/'scores.json',result)
    def score(value):
        if value is None:return '待评分'
        if value['grading_state']!='complete':return '评分故障'
        return f"{value['f2p']*100:.2f}%"
    lines=['DH vs RAW：官方 F2P 分数（不是完整任务成功率）',
        '已回传原始报告 '+str(result['returned_original'])+'/40；补跑报告 '+str(result['returned_supplementary'])+'/1。',
        '未知/未评分不计作零分；RAW–scheme 初次 DNS 失败与授权补跑独立保留。',
        'DH–pgtbl 补评报告 '+str(result['returned_grading_retry'])+'/2（同限时复测及外层时限修正）；原失败不覆盖。',
        '', '任务\tDH 首次\tRAW 首次\tRAW DNS 补跑\tDH 补评']
    for row in rows:
        lines.append('\t'.join([row['task'],score(row['dh']),score(row['raw']),
            score(row['raw_network_retry']) if 'raw_network_retry' in row else '—',
            score(row['dh_grading_retry']) if 'dh_grading_retry' in row else '—']))
    (target/'scores.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(dict(returned_original=result['returned_original'],returned_supplementary=result['returned_supplementary'],
        arms=counts,pending=len(result['pending']),output=str(target)),ensure_ascii=False))

if __name__=='__main__':pull()
