"""Repair only isolated retry processes; never monkeypatch a running campaign."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


async def handoff_verifier_logs(environment, execute):
    # Only trusted verifier output; no recursion through symlinks or task files.
    command = (
        'test ! -L /logs/verifier && '
        'find -P /logs/verifier -xdev -type d '
        f'-exec chown {os.getuid()}:{os.getgid()} {{}} + -exec chmod u+rwx {{}} + && '
        'find -P /logs/verifier -xdev -type f '
        f'-exec chown {os.getuid()}:{os.getgid()} {{}} + -exec chmod u+r {{}} +'
    )
    result = await execute(command=command, user='root', timeout_sec=60)
    if result.return_code:
        raise RuntimeError('Verifier output ownership handoff failed')


def install():
    from harbor.verifier.verifier import Verifier
    from host_agent import PairAgent
    from agents import OfflineHLD
    original_verify = Verifier.verify
    original_install = PairAgent.install
    original_run = PairAgent.run
    original_offline = OfflineHLD.run

    async def verify(self):
        output = self.trial_paths.verifier_dir.resolve()
        if not output.is_relative_to(ROOT):
            raise RuntimeError('Unexpected verifier output directory')
        execute = self.environment.exec

        async def execute_and_handoff(*args, **kwargs):
            result = await execute(*args, **kwargs)
            command = kwargs.get('command', args[0] if args else '')
            if '/tests/test.sh' in command:
                await handoff_verifier_logs(self.environment, execute)
            return result

        self.environment.exec = execute_and_handoff
        try:
            return await original_verify(self)
        finally:
            self.environment.exec = execute

    async def setup(self, env):
        upload = env.upload_file

        async def upload_resolved(source, target, *args, **kwargs):
            return await upload(Path(source).resolve(strict=True), target, *args, **kwargs)

        env.upload_file = upload_resolved
        try:
            await original_install(self, env)
        finally:
            env.upload_file = upload
        await env.upload_file(ROOT / 'resource_entry.py', '/opt/kz/resource_entry.py')

    async def run(self, instruction, environment, context):
        compose = environment._run_docker_compose_command

        async def launch(command, *args, **kwargs):
            tail = ['main', '/opt/node/bin/node', '/opt/kz/container-run.mjs']
            if command[-3:] == tail:
                command = command[:-3] + ['main', '/opt/kz-python/bin/python3',
                    '/opt/kz/resource_entry.py'] + tail[1:]
            return await compose(command, *args, **kwargs)

        environment._run_docker_compose_command = launch
        try:
            return await original_run(self, instruction, environment, context)
        finally:
            environment._run_docker_compose_command = compose

    async def offline(self, instruction, environment, context):
        await original_offline(self, instruction, environment, context)
        result = await self.exec_as_agent(environment,
            '/opt/kz-python/bin/python3 /opt/kz/resource_entry.py '
            '/bin/sh -c \'test "$(nproc)" = 1 && /opt/node/bin/node --version\'',
            cwd=self.cwd, timeout_sec=30)
        if result.return_code:
            raise RuntimeError('CPU quota visibility preflight failed')
        context.metadata['resource_awareness_verified'] = True

    Verifier.verify = verify
    PairAgent.install = setup
    PairAgent.run = run
    OfflineHLD.run = offline
