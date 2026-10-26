"""Linux Harbor transport for frozen v12. Algorithm sources are not modified."""
import json
import os
from pathlib import Path
import shlex
import tempfile
import certifi

from harbor.agents.base import BaseAgent

PROJECT = Path('/home/ecs-user/BestFGS-blocking-memory-v12')
PYTHON = Path('/home/ecs-user/terminalbench-runtime/python/cpython-3.12.14-linux-x86_64-gnu')
HERE = Path(__file__).resolve().parent
CA_BUNDLE = Path(certifi.where())
TLS_ENV = {'SSL_CERT_FILE':'/installed-agent/ca-bundle.crt',
           'REQUESTS_CA_BUNDLE':'/installed-agent/ca-bundle.crt'}


def common_args(model, method):
    if method not in ('bestfgs', 'raw') or not model:
        raise ValueError('Explicit method and model required')
    args = ['--engine', 'evidence', '--provider', 'deepseek', '--model', model,
            '--base-url', 'https://api.deepseek.com', '--api-key-env', 'DEEPSEEK_API_KEY',
            '--temperature', '0.2', '--reasoning-effort', 'high', '--solve-reasoning-effort', 'high',
            '--max-iterations', '48', '--max-tool-calls', '160', '--max-commands-per-action', '12',
            '--budget-multiplier', '1', '--no-adaptive-budget', '--success-judge-mode', 'off',
            '--comparison-metrics', '--model-timeout', '90', '--model-max-wall-time', '1200',
            '--model-request-attempts', '8', '--model-parse-attempts', '5',
            '--experience-mode', 'conditioned' if method == 'bestfgs' else 'off',
            '--blocking-memory', 'control' if method == 'bestfgs' else 'off']
    if method == 'raw':
        args += ['--disable-evidence-branching']
    return args


class CloudAgent(BaseAgent):
    def __init__(self, *args, method='bestfgs', agent_timeout_sec=None, **kwargs):
        super().__init__(*args, **kwargs)
        if method not in ('bestfgs', 'raw'):
            raise ValueError('Unknown method')
        self.method = method
        self.task_timeout = float(agent_timeout_sec or 900)

    @staticmethod
    def name():
        return 'bestfgs-v12-paired-transport'

    def version(self):
        return 'ecs-paired36-extended-v2'

    async def setup(self, environment):
        # Same isolated interpreter for both methods; no task package installation.
        await environment.upload_dir(PYTHON, '/installed-agent/python')
        await environment.upload_dir(PROJECT / 'src', '/installed-agent/src')
        await environment.upload_file(HERE / 'container_runner.py', '/installed-agent/container_runner.py')
        # Minimal official task images may contain no CA store. Supply the host
        # runtime's Mozilla CA bundle to our agent only; never disable TLS checks.
        await environment.upload_file(CA_BUNDLE, '/installed-agent/ca-bundle.crt')
        check = await environment.exec('mkdir -p /app /logs/agent && /installed-agent/python/bin/python3.12 -c "import ssl, sys; assert sys.version_info[:2] == (3, 12)"', user='root', timeout_sec=60)
        if check.return_code:
            raise RuntimeError('Shared isolated Python runtime failed')

    async def run(self, instruction, environment, context):
        key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
        if not key:
            raise RuntimeError('Missing DEEPSEEK_API_KEY')
        model = self.model_name
        if not model:
            raise RuntimeError('Model must be explicitly frozen')
        payload = {'method': self.method, 'args': common_args(model, self.method),
                   'instruction': instruction, 'timeout': max(30, self.task_timeout - 40)}
        with tempfile.TemporaryDirectory(prefix='paired-input-') as directory:
            path = Path(directory) / 'input.json'
            path.write_text(json.dumps(payload), encoding='utf-8')
            await environment.upload_file(path, '/installed-agent/input.json')
        result = await environment.exec(
            '/installed-agent/python/bin/python3.12 /installed-agent/container_runner.py',
            cwd='/app', user='root', env={**TLS_ENV, 'DEEPSEEK_API_KEY': key},
            timeout_sec=max(60, self.task_timeout - 5))
        if result.return_code:
            # Do not echo raw subprocess streams, which could contain credentials.
            raise RuntimeError(f'Paired transport failed with exit {result.return_code}; inspect redacted agent status')
