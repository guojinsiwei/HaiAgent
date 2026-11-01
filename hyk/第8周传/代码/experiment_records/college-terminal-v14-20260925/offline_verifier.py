"""Provide frozen dependency files only after the agent stops, then use Harbor's verifier.

Official task files, images, tests and grading code are unchanged. Cache contents
are infrastructure inputs, recorded separately from the original experiment.
"""
import hashlib
import json
from pathlib import Path
import shlex
import time

from harbor.verifier.verifier import Verifier

CACHE = Path('/mnt/sdb/home/lizh639/terminalbench-v14-setup/offline-cache')
TARGET = '/opt/tb-verifier-cache'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verifier_env():
    return {
        'BASH_ENV': TARGET + '/offline-shell.sh',
        'UV_DOWNLOAD_URL': 'file://' + TARGET + '/assets',
        'UV_PYTHON_INSTALL_DIR': TARGET + '/python',
        'UV_PYTHON_DOWNLOADS': 'never',
        'UV_PYTHON_PREFERENCE': 'only-managed',
        'UV_CACHE_DIR': TARGET + '/uv-cache',
        'UV_OFFLINE': 'true',
        'UV_NO_INDEX': 'true',
        'UV_FIND_LINKS': TARGET + '/wheels',
        'PIP_NO_INDEX': '1',
        'PIP_FIND_LINKS': TARGET + '/wheels',
        'PIP_DISABLE_PIP_VERSION_CHECK': '1',
    }


class OfflineVerifier(Verifier):
    async def prepare_dependencies(self):
        manifest_path = Path(__file__).with_name('offline-cache-manifest.json')
        manifest = json.loads(manifest_path.read_text())
        name = self.task.paths.tests_dir.parent.name
        task = manifest['tasks'][name]
        # Refuse unnoticed test changes, or an incomplete cache, before executing tests.
        test_path = self.task.paths.tests_dir / 'test.sh'
        if sha(test_path) != task['test_script_sha256']:
            raise RuntimeError('Offline verifier: original test script hash changed')
        payloads = ['base'] + ([task['group']] if task['group'] != 'base' else [])
        for group in payloads:
            item = manifest['payloads'][group]
            if sha(CACHE / item['file']) != item['sha256']:
                raise RuntimeError('Offline verifier: dependency payload hash changed')
        self.trial_paths.verifier_dir.mkdir(parents=True, exist_ok=True)
        record_path = self.trial_paths.verifier_dir / 'offline-dependencies.json'
        record = {'manifest_sha256': sha(manifest_path), 'task': name,
                  'phase': 'verifier_only_after_agent', 'payloads': payloads,
                  'payload_sha256': {g: manifest['payloads'][g]['sha256'] for g in payloads},
                  'started_at': time.time(), 'original_test_script_sha256': sha(test_path),
                  'status': 'preparing'}
        record_path.write_text(json.dumps(record, indent=2) + '\n')
        result = await self.environment.exec(
            command='mkdir -p ' + shlex.quote(TARGET), user='root')
        if result.return_code != 0:
            raise RuntimeError('Offline verifier: cannot create dependency directory')
        for group in payloads:
            item = manifest['payloads'][group]
            remote = TARGET + '/' + group + '.tar.gz'
            await self.environment.upload_file(source_path=CACHE / item['file'], target_path=remote)
            result = await self.environment.exec(
                command='tar -xzf ' + shlex.quote(remote) + ' -C ' + shlex.quote(TARGET),
                user='root', timeout_sec=300)
            if result.return_code != 0:
                raise RuntimeError('Offline verifier: cannot unpack dependency payload')
            await self.environment.exec(command='rm -f ' + shlex.quote(remote), user='root')
        self.override_env.update(verifier_env())
        record.update(status='ready', ready_at=time.time())
        record_path.write_text(json.dumps(record, indent=2) + '\n')

    async def verify(self):
        await self.prepare_dependencies()
        # Harbor uploads and executes the original tests and parses their reward.
        return await super().verify()
