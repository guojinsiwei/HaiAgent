"""Interpret existing evidence without discarding scores or changing raw history."""
import json
from pathlib import Path

def read(p):
    try:return json.loads(Path(p).read_text())
    except (FileNotFoundError,ValueError):return {}

def classify(summary, directory):
    s=dict(summary);d=Path(directory)
    err=(d/'audit/dsh.stderr.log').read_text(errors='replace') if (d/'audit/dsh.stderr.log').exists() else ''
    if 'KZ per-task monetary ceiling; next request not sent' in err:
        s['stop_reason']='per_task_budget_exhausted'
        if s.get('engineering_fault')=='solver_process_error':s.pop('engineering_fault')
        # Only releases recorded as repair-v1 have corrected cache pricing.
        if not (d/'repair-version.json').exists():
            s['repair_cause']='legacy_cache_price_overcount'
            s['budget_accounting_affected']=True
    if s.get('budget_reason')=='budget_service_unavailable':
        s['engineering_fault']='budget_service_unavailable'
        s['stop_reason']='budget_service_unavailable'
        s['repair_cause']='budget_rpc_timeout'
    if s.get('grading')=='complete':s['state']='needs_attention' if s.get('engineering_fault') else 'graded'
    return s

def retry_eligible(s):
    return bool(s.get('repair_cause')) and s.get('official_success') is not True and not s.get('actual_budget_exhausted',False)
