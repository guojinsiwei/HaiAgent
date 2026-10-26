"""Inventory historical official scores, keeping unrelated benchmark metrics separate."""
import collections
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
EXCLUDE={'upstream','public','grader','tests','fixture','fixtures','node_modules','site-packages',
         '.git','arms','src','method','evidence','artifacts','.codex-second-notebook-tools','__pycache__'}
FIELDS={'resolved_instances','submitted_instances','completed_instances','total_instances','unresolved_instances',
        'error_instances','infra_failure_instances','official_success','grading_state','f2p','p2p_is_pass',
        'reward','rewards','success_rate','mean_reward','mean_score','mean','score','step_score','is_pass',
        'resolved','infra_failure','completed','total','scored','passed','failed','groups','methods','arms',
        'official_graded_task_count','official_successful_task_count','official_ungraded_task_count','success_basis'}


def metric_tree(data,depth=0):
    if depth>5:return None
    if isinstance(data,dict):
        found={}
        for k,v in data.items():
            if k in FIELDS:
                if isinstance(v,(dict,list)):
                    sub=metric_tree(v,depth+1)
                    if sub is not None:found[k]=sub
                else:found[k]=v
            elif depth<3 and isinstance(v,(dict,list)):
                sub=metric_tree(v,depth+1)
                if sub:found[k]=sub
        return found or None
    if isinstance(data,list):
        values=[metric_tree(v,depth+1) for v in data if isinstance(v,(dict,list))]
        return [v for v in values if v] or None
    return data


def main():
    command=['rg','--files','-uu','-g','*.json']
    for part in EXCLUDE:command.extend(['-g','!**/'+part+'/**'])
    for name in ('tmp',
                 'notebook-nojudge-upload-*','notebook-upload-*','swe-setup-upload-*'):
        command.extend(['-g','!'+name+'/**'])
    listed=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,encoding='utf-8')
    files=[]
    for name in listed.stdout.splitlines():
        p=ROOT/name
        if (any(s in p.name.lower() for s in ('summary','result','report','grade'))
                or 'local-official-results' in p.parts or 'official-results' in p.parts):
            files.append(p)
    records=[]
    conflicts=[]
    swe=collections.defaultdict(dict)
    longcli=collections.defaultdict(list)
    for p in files:
        relative=p.relative_to(ROOT).as_posix()
        try:
            data=json.loads(p.read_text(encoding='utf-8-sig'))
            metrics=metric_tree(data)
            record=dict(path=relative,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                        schema='list' if isinstance(data,list) else 'dict',metrics=metrics)
            if isinstance(data,dict):
                record['keys']=list(data.keys())
                if 'resolved_instances' in data:
                    record['swe_official_aggregate']={k:data.get(k) for k in (
                        'submitted_instances','completed_instances','resolved_instances','error_instances','infra_failure_instances')}
                if p.name=='report.json' and 'run_evaluation' in p.parts:
                    group='/'.join(p.parts[p.parts.index('run_evaluation')+1:-2])
                    for instance,r in data.items():
                        if isinstance(r,dict) and isinstance(r.get('resolved'),bool):
                            if instance in swe[group] and swe[group][instance]['resolved'] != r['resolved']:
                                conflicts.append(dict(group=group,instance=instance,previous=swe[group][instance]['source'],current=relative))
                            swe[group][instance]=dict(resolved=r['resolved'],infra_failure=r.get('infra_failure'),
                                                      source=relative)
                if p.name=='grade.json' and 'f2p' in data and not data.get('fixture'):
                    arm=(data.get('job') or p.parent.name).split('--',1)[0]
                    longcli[arm].append(dict(task=data.get('task'),reward=(data.get('f2p') or {}).get('step_score'),
                        success=data.get('official_success'),source=relative))
            records.append(record)
        except Exception as e:records.append(dict(path=relative,read_error=type(e).__name__))
    inventory=dict(scope='Workspace result inventories including hidden run copies; public official score files only',
        files_considered=len(files),score_files=sum(bool(r.get('metrics')) for r in records),
        discovery_warnings=listed.stderr.splitlines(),records=records,swe_duplicate_conflicts=conflicts,
        swe_report_groups=[dict(group=k,reports=len(v),resolved=sum(r['resolved'] for r in v.values()),
            success_pct=100*sum(r['resolved'] for r in v.values())/len(v),rows=v) for k,v in swe.items()],
        longcli_groups=[dict(arm=k,scored=sum(type(r['reward']) in (int,float) for r in v),
            full=sum(r['success'] is True for r in v),
            mean_pct=100*sum(r['reward'] for r in v if type(r['reward']) in (int,float))/
                     sum(type(r['reward']) in (int,float) for r in v),rows=v) for k,v in longcli.items()])
    (OUT/'local-score-inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in inventory.items() if k not in {'records','swe_report_groups','longcli_groups'}}))
    for key in ('swe_report_groups','longcli_groups'):
        for g in inventory[key]:print(json.dumps(dict(kind=key,**{k:v for k,v in g.items() if k!='rows'})))
    for r in records:
        if r.get('swe_official_aggregate'):print(json.dumps(dict(path=r['path'],**r['swe_official_aggregate'])))


if __name__=='__main__':main()
