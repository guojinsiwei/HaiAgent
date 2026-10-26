"""Quiescent recovery only. Ambiguous admissions never become free retries."""
import copy
import os
from pathlib import Path
from receipts import read_receipt
from queue_policy import TERMINAL, finish


def process_identity(pid, proc=Path('/proc')):
    try:
        fields=(proc/str(int(pid))/'stat').read_text().rsplit(')',1)[1].split()
        if fields[0]=='Z':return None
        return {'pid':int(pid),'start':fields[19],
                'boot':(proc/'sys/kernel/random/boot_id').read_text().strip()}
    except FileNotFoundError:
        return None


def owned_alive(identity):
    return bool(identity and process_identity(identity['pid'])==identity)


def completed_attempt(root,row,offline,alive=owned_alive):
    attempt=row.get('preflight_attempt_id' if offline else 'attempt_id')
    receipt,status=read_receipt(Path(root)/'attempts'/f'{attempt}.json')
    if (status!='present' or not attempt or receipt.get('schema_version')!=1 or receipt.get('attempt_id')!=attempt or
        receipt.get('state') not in ('completed','launch_failed') or
        type(receipt.get('harbor_exit')) is not int or
        alive(receipt.get('runner')) or alive(receipt.get('harbor'))):
        return None
    return receipt


def reconcile(root, state, collect, alive=owned_alive):
    out=copy.deepcopy(state);problems=[]
    if alive(out.get('supervisor_identity')):
        return None,['supervisor_still_running']
    for row in out['rows']:
        if row['state'] in TERMINAL or row['state']=='pending':continue
        offline=row.get('admission_offline',row['state'] in ('preflight_admitted','preflighting'))
        receipt=completed_attempt(root,row,offline,alive)
        if receipt is None:
            problems.append(row['job']+': ambiguous or active admission');continue
        result=collect(row,offline)
        result['harbor_exit']=receipt['harbor_exit']
        if receipt['harbor_exit']!=0:result['engineering_clean']=False
        if offline and result.get('engineering_clean'):
            row.update(state='pending',preflight_ok=True,preflight=result)
        else:
            if offline:result.update(reason='preflight_failed',paid_calls=0)
            finish(row,result)
    if problems:return None,problems
    out['active']=[]
    out['state']='reconciled'
    return out,[]
