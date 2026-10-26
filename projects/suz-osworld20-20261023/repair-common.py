"""Revision-specific configuration; never resets the existing budget."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'SUZ-repair1'
def source_hash():
    h=hashlib.sha256()
    for p in sorted(SOURCE.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts:
            h.update(str(p.relative_to(SOURCE)).encode());h.update(p.read_bytes())
    return h.hexdigest()
def config(task,mode,bucket=None):
    base=json.loads((ROOT/'model-config.json').read_text())
    return {**base,'task_id':task,'mode':mode,'coordinate_type':'relative',
        'max_output_tokens':32768,'initial_output_tokens':8192,'role_max_tokens':8192,
        'truncation_recovery_tokens':32768,'budget_cny':8,'source_sha256':source_hash(),
        'shared_budget':{'path':str(ROOT/'budget.sqlite'),'bucket':bucket or mode+'/'+task,
                        'total_limit_cny':320,'bucket_limit_cny':8}}
