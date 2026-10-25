"""Harbor adapter for frozen HAIAgent/Raw, isolated live task state, no snapshots."""
import json
import os
from pathlib import Path
import tempfile

import certifi
from harbor.agents.base import BaseAgent

HERE = Path(__file__).resolve().parent
SHARED = Path('/mnt/sdb/home/lizh639/terminalbench-v14-setup')
PYTHON = SHARED / 'python/cpython-3.12.12-linux-x86_64-gnu'


class HAIAgent(BaseAgent):
    def __init__(self, *args, method='hai', task_id=None, wall_seconds=900, fixture=False, **kwargs):
        super().__init__(*args, **kwargs)
        if method not in ('hai', 'raw') or not task_id:
            raise ValueError('Explicit paired method/task identity required')
        self.method, self.task_id = method, task_id
        self.wall_seconds, self.fixture = float(wall_seconds), fixture

    @staticmethod
    def name():
        return 'hai-paired-terminal'

    def version(self):
        return '0.3.0-college-pilot-2'

    async def setup(self, environment):
        await environment.upload_dir(PYTHON, '/installed-agent/python')
        await environment.upload_dir(HERE / 'project/src', '/installed-agent/src')
        await environment.upload_file(HERE / 'runner.py', '/installed-agent/runner.py')
        await environment.upload_file(Path(certifi.where()), '/installed-agent/ca-bundle.crt')
        result = await environment.exec('mkdir -p /app /logs/agent && /installed-agent/python/bin/python3.12 -c "import ssl,sys;assert sys.version_info[:2]==(3,12)"', user='root', timeout_sec=60)
        if result.return_code:
            raise RuntimeError('Shared interpreter setup failed')

    async def run(self, instruction, environment, context):
        key = os.environ.get('DEEPSEEK_API_KEY', '')
        if not self.fixture and not key:
            raise RuntimeError('Missing API credential')
        payload = {'instruction': instruction, 'task_id': self.task_id, 'method': self.method,
                   'wall_seconds': self.wall_seconds, 'fixture': self.fixture, 'model': self.model_name}
        with tempfile.TemporaryDirectory(prefix='hai-payload-') as directory:
            path = Path(directory) / 'input.json'
            path.write_text(json.dumps(payload), encoding='utf-8')
            await environment.upload_file(path, '/installed-agent/input.json')
        result = await environment.exec(
            '/installed-agent/python/bin/python3.12 /installed-agent/runner.py',
            cwd='/app', user='root', timeout_sec=self.wall_seconds + 60,
            env={'PYTHONPATH': '/installed-agent/src', 'PYTHONUNBUFFERED': '1',
                 'SSL_CERT_FILE': '/installed-agent/ca-bundle.crt', 'DEEPSEEK_API_KEY': key})
        if result.return_code not in (0, 3):
            # Do not dump subprocess output or credential-bearing environment.
            raise RuntimeError(f'HAI runtime failed, exit={result.return_code}; inspect sanitized logs')
        # Budget exhaustion still delivers final live state for official verification.
        # No internal score is written to context/rewards.
