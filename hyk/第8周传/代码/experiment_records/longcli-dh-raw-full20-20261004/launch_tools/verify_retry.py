"""Bounded public health evidence; no environment or credential contents."""
from collections import Counter
import json
from pathlib import Path
import socket
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from common import save,sha,validate

def events(path):
    counts=Counter();latest=None;failures=[]
    if path.exists():
        with path.open() as stream:
            for line in stream:
                try:row=json.loads(line)
                except json.JSONDecodeError:continue  # Active last line may be incomplete.
                counts[row.get('event','unknown')]+=1;latest=row.get('time',latest)
                if row.get('event')=='transport_diagnostic' and row.get('error_type'):
                    failures.append({k:row.get(k) for k in ('phase','error_type','errno','dns_error_errno')})
    return dict(events=dict(counts),latest=latest,age_seconds=None if latest is None else time.time()-latest,
                transport_failures=failures[-3:])

def alive(marker,script):
    value=json.loads(marker.read_text())
    command=Path('/proc')/str(value['pid'])/'cmdline'
    return command.exists() and str(script) in command.read_bytes().decode().split('\x00')

validate()
job='roundtrip--cs61_fa24_scheme'
original=ROOT/'runs/raw--cs61_fa24_scheme/summary.json'
original_summary=json.loads(original.read_text())
report=dict(updated=time.time(),sealed_inputs_unchanged=True,method='raw',attempt=2,
    job=job,original_retained=original_summary['tool_calls']==0 and original_summary['stop_reason']=='api_error',
    original_artifact_sha256=original_summary['artifact']['sha256'],
    original_artifact_integrity=sha(ROOT/'runs/raw--cs61_fa24_scheme/source.tar.gz')==original_summary['artifact']['sha256'],
    retry_controller_alive=alive(ROOT/'launch_tools/raw-scheme-retry.json',ROOT/'launch_tools/run_raw_retry.py'),
    continuation_alive=alive(ROOT/'launch_tools/continuation-1.json',ROOT/'launch_tools/continue_unclaimed.py'),
    current_provider_addresses=sorted({a[4][0] for a in socket.getaddrinfo('api.deepseek.com',443,type=socket.SOCK_STREAM)}),
    retry_api=events(ROOT/'runs'/job/'model-audit.jsonl'),
    retry_tools=events(ROOT/'runs'/job/'trace/events.jsonl'))
save(ROOT/'launch_tools/raw-scheme-retry-verification.json',report)
print(json.dumps(report),flush=True)
