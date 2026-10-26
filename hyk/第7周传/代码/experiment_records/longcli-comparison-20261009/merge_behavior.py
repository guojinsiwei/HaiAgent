"""Merge recovered native/local receipts; retain unknowns and raw score sources."""
from collections import Counter
from datetime import datetime,timezone
import base64,gzip,hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
INPUTS=['behavior-college-final.json.gz.b64','behavior-cube-final.json.gz.b64',
        'behavior-local-final.json.gz.b64']

def read(file):return json.loads(file.read_text(encoding='utf-8-sig'))
def sha(file):return hashlib.sha256(file.read_bytes()).hexdigest()

def merge():
    snapshot=read(ROOT/'public-snapshot.json')
    canonical={(g['budget'],g['method']):g for g in snapshot['groups']}
    selected={};inputs=[]
    for name in INPUTS:
        file=ROOT/name
        data=json.loads(gzip.decompress(base64.b64decode(file.read_text())))
        inputs.append({'file':name,'sha256':sha(file),'site':data['site']})
        for g in data['groups']:
            identity=(g['budget'],g['method'])
            assert identity in canonical
            for t in g['tasks']:
                if identity in [('large','dh'),('large','dsh')] and t['task']=='61810_lock':continue
                # Native compute-host receipts replace empty grading-host folders.
                slot=selected.setdefault(identity,{})
                slot[t['task']]=dict(t,audit_site=data['site'])
    groups=[]
    for identity,g in canonical.items():
        tasks=list(selected.get(identity,{}).values())
        expected_rows=[r for r in g['rows'] if r['scored'] and not
            (identity in [('large','dh'),('large','dsh')] and r['task']=='61810_lock')]
        assert {t['task'] for t in tasks}=={r['task'] for r in expected_rows},identity
        counts=Counter();reasons=Counter()
        for t in tasks:
            c=t['counts'];assert c['total']==sum(c.get(k,0) for k in
                ['redundant','unknown','not_demonstrated_redundant'])
            assert c['total']==t['expected_tools'],(identity,t['task'],c)
            counts.update(c);reasons.update(t['reasons'])
        total=counts['total'];confirmed=counts.get('redundant',0);unknown=counts.get('unknown',0)
        groups.append(dict(name=g['name'],budget=g['budget'],method=g['method'],tasks=tasks,
            counts=dict(counts),reasons=dict(reasons),scored=len(tasks),
            confirmed_lower_bound=confirmed/total if total else None,
            unresolved_upper_bound=(confirmed+unknown)/total if total else None,
            receipt_coverage=sum(t['captured'] for t in tasks)/total if total else 1,
            classification_coverage=(total-unknown)/total if total else 1))
    return dict(version='recovered-behavior-audit-20261009',generated=datetime.now(timezone.utc).isoformat(),
        inputs=inputs,audit_code_sha256=sha(ROOT/'audit_behavior.py'),paid_model_calls=0,
        experiment_replays=0,groups=groups,
        definition='重复已读信息，或在证据证明输入条件未变时再次执行同一已失败动作。',
        limitations=['不是语义真值标注；已确认比例为保守下界。',
            '未知包含动态进程、外部状态、截断输出及无法证明的分支状态，不能自动称为冗余。',
            '上界仅对应把剩余未知全部视为冗余的假设，不是另一种实测值。',
            '同文件读取的重复信息可跨命令确认；不同文件相同文本不直接算重复。',
            'LATS 使用模型可见分支轨迹及检查点内容恢复状态，不把回溯后的验证一概算冗余。',
            '计数来自真实工具分派；预算拒绝但未执行的动作不计工具调用。'])

if __name__=='__main__':print(json.dumps(merge(),ensure_ascii=False,indent=2))
