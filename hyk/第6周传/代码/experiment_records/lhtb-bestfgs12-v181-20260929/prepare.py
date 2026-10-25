"""Preparation only: deterministic selection, independent source, bounded image pulls."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

HERE = Path(__file__).resolve().parent
COMMIT = 'd78f5eb52ad754c5ee9154741af73130a85a65b8'
SEED = 'lhtb-file-artifacts-triple25-20260926'  # Preserve pre-outcome ordering after user reduced N.
TASK_COUNT = 12
EXCLUSIONS = {
    'genetic-convergence-testing': 'non-/app artifacts; outside this file workspace adapter',
    'generals-bot-arena': 'live arena/service behavior outside this preparation scope',
    'vector-db-iterative-build': 'persistent database service outside this preparation scope',
}

def write(path, value):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)

def select(inventory):
    eligible = [r for r in inventory['tasks'] if r['agent'].get('continue_until_timeout')
                and r['task'] not in EXCLUSIONS]
    ordered = sorted(eligible, key=lambda r: hashlib.sha256((SEED + '/' + r['task']).encode()).hexdigest())
    if len(ordered) < TASK_COUNT:
        raise ValueError('Insufficient eligible tasks; never silently shrink the sample')
    tasks = ordered[:TASK_COUNT]
    for row in tasks:
        for item in row['artifacts']:
            value = item['source'] if isinstance(item, dict) else item
            if value.startswith('/') and not value.startswith('/app/'):
                raise ValueError('Artifact outside approved workspace')
    return {'benchmark_commit': COMMIT, 'selection_seed': SEED,
            'selection_rule': 'File-artifact continue-until-timeout tasks; exclude documented live-service/non-app tasks. SHA256 seeded rank, first 12 (user reduced 25 to 12 before runs). No outcome filtering.',
            'excluded': EXCLUSIONS, 'eligible_count': len(eligible), 'tasks': tasks,
            'methods': ['bestfgs'], 'total_trials': 12,
            'status': 'preparation_only_not_authorized_by_readiness_gate'}

def reserve():
    paths = ['/var/lib/docker', str(HERE)]
    if any(shutil.disk_usage(p).free < 60 * 2**30 for p in paths):
        raise RuntimeError('Disk reserve under 60 GiB; no data deleted')

def pull(image):
    reserve()
    # Reuse only the same verified official reference. Pin actual local image ID.
    try:
        existing = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image], stderr=subprocess.DEVNULL))[0]
    except subprocess.CalledProcessError:
        existing = None
    cache_path = HERE / 'verified-digests.json'
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    expected = cache.get(image)
    # Official amd64 manifest successfully resolved and verified during the
    # first preparation pass (before Harbor removed its official local tag).
    if image == 'zli12321/lhtb-matpower-opf-regression:20260615' and expected is None:
        expected = 'sha256:a92798c18dc53ca6605cbed609a7a20131287abaeb2a45d6ff854c0ff82f0cff'
        cache[image] = expected
        write(cache_path, cache)
    if expected is None:
        # Official Hub metadata is independent of registry anonymous-token
        # routing. Accept only a unique linux/amd64 platform digest.
        repository, tag = image.rsplit(':', 1)
        try:
            metadata = json.loads(subprocess.check_output([
                'curl', '-4', '--fail', '--silent', '--show-error',
                '--connect-timeout', '10', '--max-time', '30',
                '--retry', '2', '--retry-delay', '3',
                f'https://hub.docker.com/v2/repositories/{repository}/tags/{tag}'
            ], timeout=110))
            matches = {row['digest'] for row in metadata.get('images', [])
                       if row.get('architecture') == 'amd64' and row.get('os') == 'linux'}
            if len(matches) == 1:
                candidate = matches.pop()
                if candidate.startswith('sha256:') and len(candidate) == 71:
                    int(candidate[7:], 16)
                    expected = candidate
                    cache[image] = expected
                    write(cache_path, cache)
                    print(json.dumps({'image': image, 'digest_source': 'official_hub_api',
                                      'digest': expected}), flush=True)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, KeyError):
            pass  # Fall back to the official registry; never trust a mirror tag.
    if expected is None:
        for attempt in range(3):
            try:
                # .Manifest preserves the registry's content digest, including
                # single-platform images; hashing pretty-printed JSON is wrong.
                descriptor = json.loads(subprocess.check_output(['docker', 'buildx', 'imagetools',
                    'inspect', '--format', '{{json .Manifest}}', image], timeout=90))
                media = descriptor.get('mediaType', '')
                if 'index' in media or 'manifest.list' in media:
                    manifest = json.loads(subprocess.check_output(['docker', 'buildx', 'imagetools',
                        'inspect', '--raw', image + '@' + descriptor['digest']], timeout=90))
                    matches = [m['digest'] for m in manifest['manifests']
                               if m.get('platform', {}).get('architecture') == 'amd64'
                               and m.get('platform', {}).get('os') == 'linux']
                    if len(matches) != 1:
                        raise RuntimeError('Nonunique amd64 digest')
                    expected = matches[0]
                else:
                    expected = descriptor['digest']
                if not expected.startswith('sha256:') or len(expected) != 71:
                    raise RuntimeError('Invalid official digest')
                cache[image] = expected
                write(cache_path, cache)
                break
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                if attempt == 2:
                    raise
                time.sleep(10)
    if existing and any(d.endswith('@' + expected) for d in existing.get('RepoDigests', [])):
        return {'image': image, 'id': existing['Id'], 'digest': expected, 'size': existing['Size'], 'reused': True}
    source = 'dockerproxy.net/' + image.rsplit(':', 1)[0] + '@' + expected
    for attempt in range(1, 4):
        reserve()
        print(json.dumps({'image': image, 'attempt': attempt}), flush=True)
        try:
            subprocess.run(['docker', 'pull', source], check=True, timeout=3600)
            break
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            if attempt == 3:
                raise
            time.sleep(20)
    info = json.loads(subprocess.check_output(['docker', 'image', 'inspect', source]))[0]
    if info.get('Architecture') != 'amd64' or info.get('Os') != 'linux':
        raise RuntimeError('Unexpected image platform')
    if not any(d.endswith('@' + expected) for d in info.get('RepoDigests', [])):
        raise RuntimeError('Digest mismatch')
    subprocess.run(['docker', 'tag', source, image], check=True)
    return {'image': image, 'id': info['Id'], 'digest': expected, 'size': info['Size'], 'reused': False}

def main():
    import fcntl
    with (HERE / 'prepare.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest = json.loads((HERE / 'manifest.json').read_text())
        upstream = HERE / 'upstream'
        actual = subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != COMMIT:
            raise RuntimeError('Benchmark commit mismatch')
        subprocess.run(['git', '-C', str(upstream), 'sparse-checkout', 'set', 'harbor',
                        *['tasks/' + t['task'] for t in manifest['tasks']]], check=True)
        rows, failures = [], []
        for task in manifest['tasks']:
            try:
                record = pull(task['environment']['docker_image'])
                rows.append({'task': task['task'], **record})
            except Exception as error:
                failures.append({'task': task['task'], 'error_type': type(error).__name__})
                # Low disk is global: do not keep downloading other images.
                try:
                    reserve()
                except RuntimeError:
                    break
            write(HERE / 'images.json', rows)
            write(HERE / 'preparation.json', {'state': 'preparing', 'ready_images': len(rows),
                                             'failed': failures, 'updated': time.time(), 'model_calls': 0})
        write(HERE / 'preparation.json', {'state': 'images_ready' if len(rows) == len(manifest['tasks']) else 'needs_attention',
            'ready_images': len(rows), 'failed': failures, 'updated': time.time(),
            'launch_ready': False, 'model_calls': 0})

if __name__ == '__main__':
    main()
