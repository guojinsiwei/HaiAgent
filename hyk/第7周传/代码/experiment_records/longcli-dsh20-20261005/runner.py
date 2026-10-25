"""Fresh-container DSH trials and isolated API relay; never replay an existing job."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import subprocess
import threading
import time
import urllib.error
import urllib.request

from common import ROOT, export_tree, import_tree, save, sha

BASE = Path('/var/tmp/lizh639-longcli-dh-raw-full20-20261004')
RUNTIME = ROOT / 'runtime'
LOCK = threading.Lock()


def docker(*args, check=True, timeout=120):
    p = subprocess.run(['docker', *map(str, args)], capture_output=True, text=True,
                       timeout=timeout, encoding='utf-8', errors='replace')
    if check and p.returncode:
        raise RuntimeError('Docker operation failed: ' + p.stderr[-700:])
    return p


class Relay:
    """Only a per-job token is visible in the task container, never the API key."""
    def __init__(self, key, gateway, directory, mock=False):
        self.key = key
        self.token = secrets.token_hex(32)
        self.directory = directory
        self.mock = mock
        self.calls = 0
        self.mock_actor_calls = 0
        self.usage = {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}
        self.lock = threading.Lock()
        self.accepting = True
        relay = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                self.connection.settimeout(90)
                if self.path not in ('/v1/chat/completions', '/chat/completions') or self.headers.get('Authorization') != 'Bearer ' + relay.token:
                    self.send_error(403)
                    return
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 32 * 1024 * 1024:
                    self.send_error(413)
                    return
                try:
                    body = json.loads(self.rfile.read(size))
                    with relay.lock:
                        if not relay.accepting or relay.calls >= 800:
                            self.send_error(429, 'Experiment request budget exhausted')
                            return
                        relay.calls += 1
                        seq = relay.calls
                    assert body.get('model') == 'deepseek-flash'
                    cap = min(4096, int(body.get('max_tokens', body.get('max_completion_tokens', 4096))))
                    assert cap > 0
                    body.pop('max_completion_tokens', None)
                    body.update(temperature=0, thinking={'type': 'disabled'}, max_tokens=cap)
                    # The comparison uses only Chat Completions; no dynamic destination.
                    raw = json.dumps(body).encode()
                    (directory / f'request-{seq:04d}.json').write_bytes(raw)
                    if relay.mock:
                        relay.respond_mock(self, body, seq)
                        return
                    request = urllib.request.Request('https://api.deepseek.com/chat/completions', data=raw,
                        headers={'Authorization': 'Bearer ' + relay.key, 'Content-Type': 'application/json'})
                    started = time.time()
                    with urllib.request.urlopen(request, timeout=90) as upstream:
                        self.send_response(upstream.status)
                        self.send_header('Content-Type', upstream.headers.get('Content-Type', 'text/event-stream'))
                        self.send_header('Connection', 'close')
                        self.end_headers()
                        self.close_connection = True
                        usage = {}
                        with (directory / f'response-{seq:04d}.sse').open('wb') as log:
                            for line in upstream:
                                log.write(line)
                                self.wfile.write(line)
                                self.wfile.flush()
                                if line.startswith(b'data: ') and line[6:].strip() != b'[DONE]':
                                    try:
                                        frame = json.loads(line[6:])
                                        if frame.get('usage'):
                                            usage = frame['usage']
                                    except (ValueError, TypeError):
                                        pass
                        with relay.lock:
                            for metric in relay.usage:
                                relay.usage[metric] += int(usage.get(metric, 0))
                        save(directory / f'call-{seq:04d}.json', {'seq': seq, 'status': upstream.status,
                            'seconds': time.time() - started, 'usage': usage, 'request_sha256': hashlib.sha256(raw).hexdigest()})
                except urllib.error.HTTPError as error:
                    # Do not persist remote authentication diagnostics or any credential-bearing headers.
                    save(directory / f'call-{seq:04d}.json', {'seq': seq, 'status': error.code, 'error': 'provider_http'})
                    payload = json.dumps({'error': {'message': 'Provider HTTP failure', 'type': 'provider_http', 'code': str(error.code)}}).encode()
                    self.send_response(error.code)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except Exception as error:
                    save(directory / 'relay-error.json', {'error_type': type(error).__name__, 'paid': not relay.mock})
                    try:
                        self.send_error(502, 'Provider transport failure')
                    except (BrokenPipeError, ConnectionResetError):
                        pass

        self.server = ThreadingHTTPServer((gateway, 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://{gateway}:{self.server.server_port}/v1'

    def respond_mock(self, handler, body, seq):
        tools = {r['function']['name']: r['function'] for r in body.get('tools', [])}
        if 'bash' not in tools:
            delta = {'role': 'assistant', 'content': 'Keyless integration'}
            reason = 'stop'
        else:
            with self.lock:
                self.mock_actor_calls += 1
                actor_step = self.mock_actor_calls
            if actor_step == 1:
                arguments = {'command': 'printf "fresh-task-proof\\n" > isolation-proof.txt; printf "KEYLESS_OK\\n"; test ! -e /tests/run-tests.sh',
                             'description': 'Check a fresh workspace and hidden-test isolation'}
                delta = {'role': 'assistant', 'tool_calls': [{'index': 0, 'id': 'call_keyless_1', 'type': 'function',
                    'function': {'name': 'bash', 'arguments': json.dumps(arguments)}}]}
                reason = 'tool_calls'
            elif actor_step == 2:
                delta = {'role': 'assistant', 'tool_calls': [{'index': 0, 'id': 'call_keyless_2', 'type': 'function',
                    'function': {'name': 'bash', 'arguments': json.dumps({'command': 'cat isolation-proof.txt; false | true; printf "CHECK_COMPLETE\\n"',
                                                                       'description': 'Read the task-local proof file'})}}]}
                reason = 'tool_calls'
            else:
                delta = {'role': 'assistant', 'content': 'Keyless harness integration completed.'}
                reason = 'stop'
        handler.send_response(200)
        handler.send_header('Content-Type', 'text/event-stream')
        handler.send_header('Connection', 'close')
        handler.end_headers()
        handler.close_connection = True
        for value in [
            {'id': f'mock-{seq}', 'object': 'chat.completion.chunk', 'model': 'deepseek-flash', 'created': 1,
             'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]},
            {'id': f'mock-{seq}', 'object': 'chat.completion.chunk', 'model': 'deepseek-flash', 'created': 1,
             'choices': [{'index': 0, 'delta': {}, 'finish_reason': reason}],
             'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}}]:
            handler.wfile.write(b'data: ' + json.dumps(value).encode() + b'\n\n')
        handler.wfile.write(b'data: [DONE]\n\n')
        handler.wfile.flush()

    def close(self):
        with self.lock:
            self.accepting = False
        self.server.shutdown()
        self.server.server_close()


def network():
    # No peer task containers share this network, even when solving concurrently.
    name = 'longcli-dsh-net-' + secrets.token_hex(8)
    result = docker('network', 'inspect', name, check=False)
    if result.returncode:
        docker('network', 'create', '--internal', '--label', 'experiment=' + ROOT.name, name)
        result = docker('network', 'inspect', name)
    info = json.loads(result.stdout)[0]
    assert info['Internal'] and info['Labels']['experiment'] == ROOT.name
    return name, info['IPAM']['Config'][0]['Gateway']


def run_trial(row, key=None, mock=False, suffix=''):
    job = ('keyless' if mock else 'dsh') + '--' + row['task'] + suffix
    directory = ROOT / ('acceptance-jobs' if mock else 'jobs') / job
    directory.mkdir(parents=True, exist_ok=False)
    workspace = directory / 'workspace'
    import_tree(BASE / ('starter-' + row['task'] + '.tar.gz'), workspace)
    assert (workspace / row['project']).is_dir()
    assert not (workspace / 'isolation-proof.txt').exists()
    (directory / 'home').mkdir()
    (directory / 'audit').mkdir()
    api = directory / 'api'
    api.mkdir()
    net, gateway = network()
    relay = Relay(key, gateway, api, mock)
    name = 'longcli-dsh-' + secrets.token_hex(8)
    summary = {'job': job, 'task': row['task'], 'container': name, 'mock': mock,
               'state': 'preparing', 'started': time.time(), 'fresh_container': True, 'fresh_home': True,
               'runtime_version': '0.2.0-rc.2', 'api_key_visible_in_container': False}
    save(directory / 'health.json', summary)
    try:
        assert docker('image', 'inspect', row['image_id'], '--format', '{{.Id}}').stdout.strip() == row['image_id']
        docker('create', '--name', name, '--label', 'experiment=' + ROOT.name,
            '--user', f'{os.getuid()}:{os.getgid()}',
            '--network', net, '--cpus', '2', '--memory', '8g', '--pids-limit', '256',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--mount', f'type=bind,src={workspace},dst=/app',
            '--mount', f'type=bind,src={directory / "home"},dst=/dsh-home',
            '--mount', f'type=bind,src={directory / "audit"},dst=/audit',
            '--mount', f'type=bind,src={RUNTIME},dst=/opt/dsh,readonly',
            '--mount', f'type=bind,src={ROOT / "budget.mjs"},dst=/opt/experiment/budget.mjs,readonly',
            '--mount', f'type=bind,src={ROOT / "experiment.patch.yml"},dst=/opt/experiment/experiment.patch.yml,readonly',
            '--mount', f'type=bind,src={ROOT / "empty-tests"},dst=/tests,readonly',
            '-e', 'DSH_HOME=/dsh-home', '-e', 'DSH_TELEMETRY_DISABLED=1',
            '-e', 'DSH_PERMISSION_MODE=danger-full-access', '-e', 'DSH_APPROVAL_POLICY=never',
            '-e', 'LONGCLI_PROXY_URL=' + relay.url, '-e', 'LONGCLI_PROXY_TOKEN=' + relay.token,
            '-e', 'PATH=/opt/dsh/node/package/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
            '-w', '/app', row['image_id'],
            '/opt/dsh/node/package/bin/node', '/opt/dsh/dsh/node_modules/@deepseek-ai/dsh/lib/bin.js',
            '--profile', 'headless', '--patch', '/opt/experiment/experiment.patch.yml', '--json',
            'Run the keyless integration check.' if mock else row['instruction'])
        # Assert only public files are mounted at the official hidden-test location.
        mounts = json.loads(docker('inspect', name, '--format', '{{json .Mounts}}').stdout)
        assert next(m for m in mounts if m['Destination'] == '/tests')['RW'] is False
        for item in mounts:
            if item['RW']:
                assert Path(item['Source']).is_relative_to(directory), 'Cross-task writable mount'
        save(directory / 'isolation.json', {'container_id': docker('inspect', name, '--format', '{{.Id}}').stdout.strip(),
            'mounts': mounts, 'hidden_tests_masked': True, 'network_internal': True})
        summary['state'] = 'running'
        with (directory / 'console.jsonl').open('x') as stdout, (directory / 'stderr.log').open('x') as stderr:
            p = subprocess.Popen(['docker', 'start', '-a', name], stdout=stdout, stderr=stderr)
            wall = 120 if mock else 7200
            while p.poll() is None:
                if time.time() - summary['started'] >= wall:
                    summary['stop_reason'] = 'wall_budget'
                    docker('stop', '-t', '3', name, check=False)
                    p.wait(timeout=20)
                    break
                summary.update(updated=time.time(), api_attempts=relay.calls, usage=dict(relay.usage))
                save(directory / 'health.json', summary)
                time.sleep(1 if mock else 10)
        summary.update(exit_code=p.returncode, state='generation_complete', api_attempts=relay.calls, usage=relay.usage)
        # Ensure background tool processes cannot mutate the delivered source after freezing.
        docker('stop', '-t', '3', name, check=False)
        assert docker('inspect', name, '--format', '{{.State.Running}}').stdout.strip() == 'false', 'Container did not quiesce'
        if mock:
            assert p.returncode == 0 and relay.mock_actor_calls == 3, 'Keyless native DSH run failed'
            assert (workspace / 'isolation-proof.txt').read_text() == 'fresh-task-proof\n'
            events = [json.loads(line) for line in (directory / 'audit/events.jsonl').read_text().splitlines()]
            assert sum(e['event'] == 'tool_result' for e in events) == 2
            results = [e for e in events if e['event'] == 'tool_result']
            assert all(not e['result']['isError'] for e in results)
            assert any('KEYLESS_OK' in json.dumps(e) for e in results)
            assert '/dev/null: Permission denied' not in json.dumps(results)
            summary['state'] = 'keyless_pass'
        else:
            archive = directory / 'final-source.tar.gz'
            summary['artifact'] = export_tree(workspace, archive, source_only=True)
            summary['state'] = 'awaiting_grade'
            events = [json.loads(line) for line in (directory / 'audit/events.jsonl').read_text().splitlines()]
            summary['model_decisions'] = sum(e['event'] == 'request' for e in events)
            summary['all_model_streams'] = sum(e['event'] == 'model_stream' for e in events)
            summary['root_tool_dispatches'] = sum(e['event'] == 'tool_start' and not e.get('nested') for e in events)
            summary['native_tool_results'] = sum(e['event'] == 'tool_result' for e in events)
            summary['shell_tool_results'] = sum(e['event'] == 'tool_result' and e['name'] in ('bash', 'bash_persistent') for e in events)
            stops = [e['reason'] for e in events if e['event'] == 'budget_stop']
            if stops:
                summary['stop_reason'] = stops[-1]
            else:
                summary.setdefault('stop_reason', 'native_completed' if p.returncode == 0 else 'native_error')
    except Exception as error:
        summary.update(state='engineering_failure', error_type=type(error).__name__, error=str(error)[:700])
    finally:
        relay.close()
        # Only the exact container created above is removed. Workspace/logs remain recoverable.
        docker('rm', '-f', name, check=False)
        inventory = docker('ps', '-a', '--filter', 'name=' + name, '--format', '{{.Names}}', check=False)
        destroyed = inventory.returncode == 0 and name not in inventory.stdout.splitlines()
        network_removed = docker('network', 'rm', net, check=False).returncode == 0
        summary.update(ended=time.time(), seconds=time.time() - summary['started'], container_destroyed=destroyed)
        summary['network_destroyed'] = network_removed
        if not destroyed or not network_removed:
            summary.update(state='engineering_failure', error_type='CleanupUnconfirmed',
                           error='Container/network teardown could not be confirmed')
        save(directory / 'summary.json', summary)
        save(directory / 'health.json', summary)
    return summary


def validate_ready():
    manifest = json.loads((ROOT / 'deployment-manifest.json').read_text())
    for name, expected in manifest['files'].items():
        assert sha(ROOT / name) == expected, 'Deployment changed: ' + name
    acceptance = json.loads((ROOT / 'keyless-acceptance.json').read_text())
    assert acceptance['state'] == 'passed' and acceptance['paid_api_requests'] == 0
    assert acceptance['different_containers']
    assert all(r['container_destroyed'] and r['network_destroyed'] for r in acceptance['trials'])
    assert json.loads((ROOT / 'grading-acceptance.json').read_text())['state'] == 'passed'
    assert not list((ROOT / 'jobs').iterdir()), 'Existing trials: never restart automatically'
    return True


def paid_campaign(credential_file):
    # The real key exists only in this controller's RAM after this read.
    assert credential_file.parent == Path('/dev/shm')
    assert credential_file.name.startswith('longcli-dsh20-')
    assert credential_file.stat().st_mode & 0o077 == 0
    key = credential_file.read_text().strip()
    credential_file.unlink()
    assert key and not any(c.isspace() for c in key)
    validate_ready()
    rows = json.loads((ROOT / 'protocol.json').read_text())['tasks']
    health = {'state': 'running', 'pid': os.getpid(), 'updated': time.time(), 'active': [],
              'pending': [r['task'] for r in rows], 'generation_done': [], 'grading_done': [], 'errors': []}
    active = {}
    grading = {}
    pending = list(rows)
    pilot_done = False
    paused = False
    from college_grader import grade

    def evaluate(result):
        directory = ROOT / 'jobs' / result['job']
        artifact = directory / 'final-source.tar.gz'
        report = grade(result['job'], artifact, result['artifact']['sha256'])
        name = report['container']
        owner = docker('inspect', name, '--format', '{{index .Config.Labels "experiment"}}').stdout.strip()
        assert owner == json.loads((ROOT / 'protocol.json').read_text())['experiment'], 'Refusing to remove a foreign grading container'
        assert docker('inspect', name, '--format', '{{.State.Running}}').stdout.strip() == 'false'
        docker('rm', name)
        report['grading_container_destroyed'] = True
        save(ROOT / 'grades' / result['job'] / 'result.json', report)
        return report

    with ThreadPoolExecutor(max_workers=4) as solvers, ThreadPoolExecutor(max_workers=1) as graders:
        while pending or active or grading:
            limit = 4 if pilot_done else 1
            while pending and not paused and len(active) < limit:
                row = pending.pop(0)
                active[solvers.submit(run_trial, row, key)] = row
            for future in list(active):
                if not future.done():
                    continue
                row = active.pop(future)
                try:
                    result = future.result()
                except Exception as error:
                    result = {'task': row['task'], 'state': 'engineering_failure', 'error_type': type(error).__name__}
                health['generation_done'].append(result)
                failed = result['state'] == 'engineering_failure' or not result.get('container_destroyed') or not result.get('network_destroyed')
                jobdir = ROOT / 'jobs' / result.get('job', 'dsh--' + row['task'])
                calls = [json.loads(p.read_text()) for p in sorted((jobdir / 'api').glob('call-*.json'))]
                critical = any(c.get('status') in (400, 401, 403, 429) for c in calls)
                transport_failed = (jobdir / 'api/relay-error.json').exists()
                if failed or critical or (transport_failed and result.get('native_tool_results', 0) == 0):
                    paused = True
                    health['errors'].append({'task': row['task'], 'reason': 'engineering_or_provider_failure',
                                             'stop_reason': result.get('stop_reason'), 'no_auto_retry': True})
                if result.get('artifact'):
                    grading[graders.submit(evaluate, result)] = row['task']
                pilot_done = True
            for future in list(grading):
                if not future.done():
                    continue
                task = grading.pop(future)
                try:
                    result = future.result()
                except Exception as error:
                    result = {'task': task, 'grading_state': 'failed', 'error_type': type(error).__name__}
                health['grading_done'].append(result)
                if result.get('grading_state') != 'complete':
                    paused = True
                    health['errors'].append({'task': task, 'reason': 'grading_failure', 'no_auto_retry': True})
            health.update(updated=time.time(), state='admission_paused' if paused else 'running',
                          active=[r['task'] for r in active.values()], pending=[r['task'] for r in pending],
                          grading_active=list(grading.values()))
            save(ROOT / 'health.json', health)
            if paused and not active and not grading:
                break
            if not active and not grading and not pending:
                break
            time.sleep(5)
    health.update(updated=time.time(), ended=time.time(), state='needs_attention' if paused else 'complete')
    save(ROOT / 'health.json', health)
    save(ROOT / 'summary.json', health)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--keyless', action='store_true')
    parser.add_argument('--credential-file', type=Path)
    args = parser.parse_args()
    protocol = json.loads((ROOT / 'protocol.json').read_text())
    if args.keyless:
        attempt = secrets.token_hex(3)
        first = run_trial(protocol['tasks'][0], mock=True, suffix='--' + attempt + '--a')
        second = run_trial(protocol['tasks'][0], mock=True, suffix='--' + attempt + '--b')
        result = {'state': 'passed' if all(r['state'] == 'keyless_pass' for r in (first, second)) else 'failed',
                  'paid_api_requests': 0, 'trials': [first, second], 'different_containers': first['container'] != second['container']}
        save(ROOT / 'keyless-acceptance.json', result)
        print(json.dumps(result))
        raise SystemExit(0 if result['state'] == 'passed' else 1)
    if not args.credential_file:
        raise RuntimeError('Supply a new campaign credential through the hidden local entry')
    paid_campaign(args.credential_file)


if __name__ == '__main__':
    main()
