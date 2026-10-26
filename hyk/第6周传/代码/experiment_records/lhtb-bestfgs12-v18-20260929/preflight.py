"""Freeze only verified inputs. No credentials and no model calls."""
import hashlib
import json
import os
import subprocess
import time
from control import HERE, METHODS, source_hashes, plan
from prepare import reserve, write, COMMIT
from audit import verify


def main():
    if (HERE / 'health.json').exists():
        raise RuntimeError('Already started: cannot reseal an experiment')
    reserve()
    if subprocess.check_output(['git', '-C', str(HERE / 'upstream'), 'rev-parse', 'HEAD'], text=True).strip() != COMMIT:
        raise RuntimeError('Benchmark commit mismatch')
    preparation = json.loads((HERE / 'preparation.json').read_text())
    if preparation['state'] != 'images_ready' or preparation['ready_images'] != 12:
        raise RuntimeError('Images not ready')
    images = json.loads((HERE / 'images.json').read_text())
    manifest = json.loads((HERE / 'manifest.json').read_text())
    if {r['task'] for r in images} != {r['task'] for r in manifest['tasks']}:
        raise RuntimeError('Image/task set mismatch')
    for row in images:
        info = json.loads(subprocess.check_output(['docker', 'image', 'inspect', row['image']]))[0]
        if info['Id'] != row['id'] or not any(d.endswith('@' + row['digest']) for d in info.get('RepoDigests', [])):
            raise RuntimeError('Image identity mismatch')
        if info['Config'].get('Volumes') or info['Config'].get('User') not in (None, '', 'root', '0'):
            raise RuntimeError('Unsupported image volume or default user: ' + row['task'])
    fixtures = {}
    for method in METHODS:
        reports = list((HERE / 'fixtures' / ('fixture5-' + method + '-fixture')).glob('*/result.json'))
        if len(reports) != 1:
            raise RuntimeError('Missing continuation fixture')
        report = json.loads(reports[0].read_text())
        reward = (report.get('verifier_result') or {}).get('rewards') or {}
        metadata = (report.get('agent_result') or {}).get('metadata') or {}
        if report.get('exception_info') or not reward or min(reward.values()) < 1 or metadata.get('continue_until_timeout_phases', 0) < 1:
            raise RuntimeError('Failed continuation fixture')
        audit_path = reports[0].parent / 'agent/audit.jsonl'
        fixtures[method] = verify(audit_path)
        events = [json.loads(line) for line in audit_path.read_text().splitlines()]
        if not any(e.get('event') == 'method_end' and e.get('stop_reason') == 'wall_budget_exhausted' for e in events):
            raise RuntimeError('Budget-delivery fixture did not exercise the repaired path')
    python = str(__import__('sys').executable)
    subprocess.run([python, '-m', 'unittest', 'test_supervisor', 'test_audit'],
                   cwd=HERE, check=True)
    subprocess.run([python, '-m', 'unittest', 'test_adaptation', 'test_control',
                    'test_durable', 'test_outcomes'], cwd=HERE, check=True)
    # Verify the exact v18 package that will be sealed and deployed. This is
    # entirely offline and performs no paid model request.
    subprocess.run([python, '-B', 'verify_lean.py'], cwd=HERE / 'bestfgs-project', check=True)
    plan()
    hashes = source_hashes()
    value = {'ready': True, 'source_hashes': hashes, 'fixture_audits': fixtures,
             'protocol_sha256': hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
             'sealed_at': time.time(), 'model_calls': 0}
    write(HERE / 'ready.json', value)
    print(json.dumps({'ready': True, 'protocol_sha256': value['protocol_sha256']}))


if __name__ == '__main__':
    main()
