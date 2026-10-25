"""Carry terminal records and relocate only future trials to the roomy filesystem."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

OLD = Path('/mnt/sdb/home/lizh639/lhtb-triple12-v161-20260927-r3')
NEW = Path('/var/tmp/lizh639-lhtb-r4')


def main():
    from supervisor import identity, read, write
    if NEW.exists(): raise RuntimeError('Target already exists; inspect before reuse')
    if shutil.disk_usage('/var/tmp').free < 100*2**30:
        raise RuntimeError('Insufficient target disk space')
    rows = read(OLD/'prior-results.json')
    quarantined = []
    for folder in sorted((OLD/'ledger').iterdir()):
        start = read(folder/'started.json')
        if start and identity(start['pid']) == start['identity']:
            raise RuntimeError('Old trial still active')
        value = read(folder/'result.json')
        if value is None:
            spec = read(folder/'intent.json')
            reports = list((OLD/'runs'/folder.name).glob('*/result.json'))
            audits = list((OLD/'runs'/folder.name).glob('*/agent/audit.jsonl'))
            if len(audits) != 1: raise RuntimeError('Missing failed trial evidence')
            evidence = [json.loads(line) for line in audits[0].read_text().splitlines()]
            if not any(e.get('event') == 'adapter_error' and 'Disk reserve under 60 GiB' in e.get('traceback', '') for e in evidence):
                raise RuntimeError('Cannot identify the interrupted trial failure')
            report = read(reports[0], {}) if len(reports) == 1 else {}
            value = dict(task=spec['task']['task'], method=spec['method'],
                verifier_result=report.get('verifier_result'), exception_info=report.get('exception_info'),
                process_exit_code=None, infrastructure_error='disk_reserve_exhausted_and_worker_interrupted',
                audit_path=str(audits[0]), audit_sha256=hashlib.sha256(audits[0].read_bytes()).hexdigest(),
                classification={'infrastructure_ok': False, 'reasons': ['disk_reserve_exhausted', 'worker_interrupted']},
                recovery_action='quarantined_without_replay')
            if reports: value['report'] = str(reports[0])
            quarantined.append(folder.name)
        value = dict(value, carried_forward=True, origin_protocol_sha256=read(OLD/'ready.json')['protocol_sha256'])
        rows.append(value)
    if len({(r['task'],r['method']) for r in rows}) != len(rows):
        raise RuntimeError('Duplicate prior outcome')
    NEW.mkdir(mode=0o700)
    for name in ('bestfgs-project','hai-project','upstream','fixture'):
        shutil.copytree(OLD/name, NEW/name, ignore=shutil.ignore_patterns('__pycache__'))
    for source in OLD.glob('*.py'): shutil.copy2(source, NEW/source.name)
    for name in ('manifest.json','images.json','verified-digests.json','PROTOCOL.md'):
        shutil.copy2(OLD/name, NEW/name)
    write(NEW/'prior-results.json', rows)
    sys.path[:0] = [str(NEW), str(NEW/'upstream/harbor/src'), str(NEW/'hai-project/src'), str(NEW/'bestfgs-project/src')]
    import control
    control.plan()
    control.reserve()
    hashes = control.source_hashes()
    ready = dict(ready=True, source_hashes=hashes,
        protocol_sha256=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest(),
        sealed_at=time.time(), carried=len(rows), new_attempts=36-len(rows), model_calls=0,
        previous_protocol_sha256=read(OLD/'ready.json')['protocol_sha256'])
    write(NEW/'ready.json', ready)
    assert control.validate()['ready']
    for name in ('bestfgs-project/src','hai-project/src','upstream/harbor/src'):
        for source in (OLD/name).rglob('*.py'):
            assert source.read_bytes() == (NEW/source.relative_to(OLD)).read_bytes()
    write(NEW/'migration.json', dict(old=str(OLD), new=str(NEW), terminal_records=len(rows),
        official_reports=sum(r.get('verifier_result') is not None for r in rows), quarantined=quarantined,
        pending=36-len(rows), unchanged_method_sources=True, model_calls=0,
        note='Old artifacts retained; no failed trial replay; only unstarted trials move to root filesystem.'))
    print((NEW/'migration.json').read_text())


if __name__ == '__main__': main()
