"""Real cloud Docker integration acceptance, scripted policies, no model API.

Run using the existing Harbor virtualenv. Never modifies frozen experiment sources.
Exit 0: acceptance green; 1: product acceptance failures; 2: test/setup errors.
"""
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import traceback
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
BEST = Path('/var/tmp/lizh639-lhtb-bestfgs-v181-only-r1')
HAI = Path('/var/tmp/lizh639-lhtb-hai082-only-r1')
PYDIST = Path('/mnt/sdb/home/lizh639/terminalbench-v14-setup/python/cpython-3.12.12-linux-x86_64-gnu')
LABEL = 'org.bestfgs.integration.owner'
OWNER = 'integration-' + uuid.uuid4().hex
START = time.time()
RESULTS = []
BASE_IMAGE = None
ORIGINALS = set()
SOURCES = ROOT / 'sources'
RUN = ROOT / ('run-' + time.strftime('%Y%m%d-%H%M%S') + '-' + OWNER[-8:])
RUN.mkdir(exist_ok=False)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def docker(*args, timeout=180, input=None):
    result = subprocess.run(['docker', *map(str, args)], input=input, text=True,
                            capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'docker {args[0]} failed: {result.stderr[-1500:]}')
    return result.stdout.strip()


def inspect(kind, ident):
    return json.loads(docker(kind, 'inspect', ident))[0]


def remove_original(ident):
    assert ident in ORIGINALS
    assert inspect('container', ident)['Config']['Labels'].get(LABEL) == OWNER
    docker('rm', '-f', ident)
    ORIGINALS.remove(ident)


def prepare_sources():
    manifest_path = ROOT / 'fixed-source-manifest.json'
    if manifest_path.exists():
        expected = json.loads(manifest_path.read_text())
        actual = {str(p.relative_to(SOURCES)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in SOURCES.rglob('*.py')}
        assert actual == expected, 'repair source manifest mismatch'
        baseline = json.loads((ROOT / 'baseline-manifest.json').read_text())
        for row in baseline:
            assert hashlib.sha256(Path(row['origin']).read_bytes()).hexdigest() == row['sha256'], row['origin']
        save(RUN / 'source-manifest.json', expected)
        shutil.copy2(__file__, RUN / 'cloud_suite.py')
        sys.path[:0] = [str(SOURCES), str(SOURCES / 'bestfgs-project/src'),
                       str(SOURCES / 'hai-project/src')]
        return
    if not SOURCES.exists():
        SOURCES.mkdir()
        shutil.copytree(BEST / 'bestfgs-project/src', SOURCES / 'bestfgs-project/src',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copytree(HAI / 'hai-project/src', SOURCES / 'hai-project/src',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for name in ('docker_state.py', 'container_command.py', 'audit.py'):
            shutil.copy2(HAI / name, SOURCES / name)
        shutil.copy2(HAI / 'transport.py', SOURCES / 'hai_transport.py')
        shutil.copy2(HAI / 'outcomes.py', SOURCES / 'hai_outcomes.py')
    hashes = []
    for p in sorted(SOURCES.rglob('*.py')):
        rel = p.relative_to(SOURCES)
        if rel.parts[0] == 'bestfgs-project':
            origin = BEST / rel
        elif rel.parts[0] == 'hai-project':
            origin = HAI / rel
        else:
            origin = HAI / {'hai_transport.py': 'transport.py',
                            'hai_outcomes.py': 'outcomes.py'}.get(p.name, p.name)
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        assert digest == hashlib.sha256(origin.read_bytes()).hexdigest(), str(rel)
        hashes.append(dict(path=str(rel), origin=str(origin), sha256=digest))
    assert (BEST / 'docker_state.py').read_bytes() == (HAI / 'docker_state.py').read_bytes()
    save(RUN / 'source-manifest.json', hashes)
    sys.path[:0] = [str(SOURCES), str(SOURCES / 'bestfgs-project/src'),
                   str(SOURCES / 'hai-project/src')]


def prepare_image():
    global BASE_IMAGE
    source = os.environ.get('INTEGRATION_IMAGE', 'ubuntu:24.04')
    info = inspect('image', source)  # Never pull or replace a shared image.
    save(RUN / 'environment.json', dict(host=socket.gethostname(), owner=OWNER,
        source_image=source, source_image_id=info['Id'], docker=docker('version', '--format', '{{.Server.Version}}'),
        network='none', cpus=1, memory_mb=1024, model_api_calls=0,
        scope='Real adapters and runtimes; scripted policy, not Harbor grading or real-model evaluation'))
    original = docker('run', '-d', '--label', LABEL + '=' + OWNER, '--network', 'none',
        '--cpus', '1', '--memory', '1024m', '--memory-swap', '1024m', '--pids-limit', '128',
        '--entrypoint', '/bin/sh', source, '-c', 'sleep 7200')
    ORIGINALS.add(original)
    docker('exec', original, 'mkdir', '-p', '/opt/lhtb-agent-tools', '/app', '/usr/local/bin')
    docker('cp', str(PYDIST), original + ':/opt/lhtb-agent-tools/python', timeout=300)
    docker('cp', str(SOURCES / 'hai-project/src'), original + ':/opt/lhtb-agent-tools/src')
    docker('cp', str(SOURCES / 'container_command.py'), original + ':/opt/lhtb-agent-tools/container_command.py')
    docker('exec', original, '/bin/sh', '-c',
           'test -e /usr/local/bin/python || ln -s /opt/lhtb-agent-tools/python/bin/python3.12 /usr/local/bin/python')
    fixture = """from pathlib import Path
Path('/app/file.txt').write_text('stable fixture observation\\n')
for i in range(200,206):
 Path(f'/tmp/opt{i}.py').write_text("print('no viable candidate')\\n")
for i in range(400,406):
 Path(f'/tmp/opt{i}.py').write_text("print(" + repr('no viable candidate; ' + 'detail ' * 270) + ")\\n")
"""
    docker('exec', original, '/opt/lhtb-agent-tools/python/bin/python3.12', '-c', fixture)
    BASE_IMAGE = docker('commit', '--change', 'LABEL ' + LABEL + '=' + OWNER,
                        original, 'mechanism-integration:' + OWNER)
    remove_original(original)


@contextlib.contextmanager
def state_for(name):
    from docker_state import DockerState, LABEL as STATE_LABEL
    original = docker('run', '-d', '--label', LABEL + '=' + OWNER, '--network', 'none',
        '--cpus', '1', '--memory', '1024m', '--memory-swap', '1024m', '--pids-limit', '128',
        '--entrypoint', '/bin/sh', BASE_IMAGE, '-c', 'sleep 3600')
    ORIGINALS.add(original)
    state = None
    try:
        state = DockerState(original, RUN / name / 'state', 1, 1024, time.monotonic() + 600)
        yield state
    finally:
        if state:
            for ident in list(state.containers):
                state.remove(ident)
            for ident in list(state.images):
                assert inspect('image', ident)['Config']['Labels'].get(STATE_LABEL) == state.owner
                docker('image', 'rm', ident)
                state.images.remove(ident)
            state.journal()
        remove_original(original)


class Policy:
    model = 'scripted-no-network'
    def __init__(self, values):
        self.values = iter(values)
        self.prompts = []

    def complete_json(self, **kwargs):
        self.prompts.append(json.loads(kwargs['user_prompt']))
        return next(self.values)

    def complete(self, messages, deadline, recorder):
        self.prompts.append(messages)
        return dict(content=json.dumps(next(self.values)), complete=True)


SUBMIT = dict(action='submit', summary='Deliver integration fixture only')


def action(*argv, **extra):
    return dict(action='run', argv=list(argv), cwd='/app', purpose='integration test',
                timeout_seconds=60, stdin=None) | extra


def events(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def best_run(name, actions, advice=()):
    from bestfgs.lean_docker import ContinuousDockerEnvironment
    from bestfgs.lean_protocol import LeanConfig
    from bestfgs.lean_runtime import LeanTaskRunner
    from bestfgs.models import TaskSpec
    with state_for(name) as state:
        env = ContinuousDockerEnvironment(state)
        actor, advisor = Policy(actions), Policy(advice)
        try:
            result = LeanTaskRunner(env, actor, advisor,
                LeanConfig(max_turns=40, max_tools=30, wall_seconds=500),
                RUN / name / 'method').run(TaskSpec(name, 'Inspect file.txt and deliver result.txt when requested'))
            save(RUN / name / 'policy-prompts.json', dict(actor=actor.prompts, advisor=advisor.prompts))
            if not result['submitted']:
                raise RuntimeError('scripted run did not submit: ' + json.dumps(result))
            return result, events(RUN / name / 'method/events.jsonl'), actor, advisor
        finally:
            env.close()


def check(name, good, evidence, expected_issue=None):
    status = 'PASS' if good else 'FAIL'
    RESULTS.append(dict(name=name, status=status, evidence=evidence, expected_issue=expected_issue))
    print(json.dumps(RESULTS[-1]), flush=True)
    save(RUN / 'results.json', dict(status='running', checks=RESULTS))


def docker_lifecycle():
    from bestfgs.lean_docker import ContinuousDockerEnvironment
    from docker_state import PYTHON
    with state_for('docker-lifecycle') as state:
        env = ContinuousDockerEnvironment(state)
        try:
            ident = env.container
            first = env.scope()
            r = env.execute(action(PYTHON, '-c', "from pathlib import Path; Path('result.txt').write_text('A'); Path('/tmp/external.txt').write_text('A')"), state.deadline)
            saved = env.checkpoint('A')
            env.execute(action(PYTHON, '-c', "from pathlib import Path; Path('result.txt').write_text('B'); Path('/tmp/external.txt').write_text('B')"), state.deadline)
            same_live = ident == env.container
            env.restore(saved)
            r = env.execute(action(PYTHON, '-c', "from pathlib import Path; assert Path('result.txt').read_text()=='A'; assert Path('/tmp/external.txt').read_text()=='A'; print('restored')"), state.deadline)
            env.delivery()
            delivered = docker('exec', state.original, 'cat', '/app/result.txt')
            info = inspect('container', env.container)
            check('docker_snapshot_restore_delivery', r.succeeded and delivered == 'A' and same_live and first != env.scope(),
                  dict(restore_output=r.stdout, delivered=delivered, live_container_reused=same_live,
                       mounts=info['Mounts'], network=info['HostConfig']['NetworkMode']))
            denied = env.execute(action('cat', '/etc/passwd') | {'cwd': '/etc'}, state.deadline)
            check('workspace_escape_refused', denied.blocked or not denied.succeeded,
                  dict(blocked=denied.blocked, exit=denied.return_code))
            timed = env.execute(action(PYTHON, '-c', 'import time; time.sleep(3)', timeout_seconds=1), state.deadline)
            follow = env.execute(action('cat', 'file.txt'), state.deadline)
            check('command_timeout_and_recovery', timed.timed_out and follow.succeeded,
                  dict(timed_out=timed.timed_out, next_call_succeeded=follow.succeeded))
        finally:
            env.close()


def best_cases():
    from bestfgs.lean_protocol import ADVISOR_SYSTEM
    plain = best_run('best-plain', [action('cat', 'file.txt')] * 14 + [SUBMIT], [dict(alternatives=[])])
    wrapped = best_run('best-wrapped', [action('bash', '-lc', 'cd /app && cat file.txt')] * 14 + [SUBMIT], [dict(alternatives=[])])
    check('best_plain_read_advisor', len(plain[3].prompts) == 1, dict(advisor_calls=len(plain[3].prompts)))
    check('best_shell_wrapped_read_advisor', len(wrapped[3].prompts) == 1,
          dict(advisor_calls=len(wrapped[3].prompts), expected=1), 'shell compound classified generic')
    for count in (3, 4):
        advice = dict(alternatives=[dict(hypothesis='Inspect fixture encoding', check='Read bytes',
            difference='Use raw bytes', evidence_ids=['E'+str(i) for i in range(1, count+1)])])
        result, trace, actor, advisor = best_run('best-evidence-' + str(count),
            [action('cat', 'file.txt')] * 4 + [dict(action='consult', question='Inspect the evidence'), SUBMIT], [advice])
        accepted = result['mechanism_utilization']['advisor_responses_accepted']
        deferred = [e.get('reason') for e in trace if e['event']=='advisor_deferred']
        contract_ok = (accepted == 1 if count == 3 else
                       accepted == 0 and 'at most 3 IDs' in ADVISOR_SYSTEM
                       and any('at most 3 IDs' in reason for reason in deferred))
        check('best_visible_evidence_' + str(count), contract_ok,
              dict(accepted=accepted, visible=[e['id'] for e in advisor.prompts[0]['fixed_context']['evidence']],
                   deferred=deferred, declared_maximum=3,
                   expected_behavior='accept valid 3; explicitly reject over-limit 4'),
              'undocumented three-evidence limit' if count == 4 else None)


def hai_case(name, cwd, long=False, intervention=False):
    from hai_transport import LinearExecutor
    from haiagent.protocol import Config, Task
    import haiagent.runtime as runtime
    from terminal_context.core import TaskContext, size
    contexts = []
    def capture_context(*args, **kwargs):
        instance = TaskContext(*args, **kwargs)
        contexts.append(instance)
        return instance
    with state_for(name) as state:
        executor = LinearExecutor(state)
        base = 400 if long else 200
        actions = [action('bash', '-lc', f'python /tmp/opt{i}.py --mode search',
                          strategy='search candidate configuration', subgoal='find a viable candidate')
                   | {'cwd': cwd} for i in range(base, base + (4 if intervention else 3))]
        if intervention:
            actions.append(action('cat', 'file.txt', strategy='inspect different evidence',
                                  subgoal='find a viable candidate') | {'cwd': cwd})
        actor = Policy(actions + [SUBMIT])
        with patch.object(runtime, 'TaskContext', capture_context):
            result = runtime.run(Task(name, 'Find a viable candidate and create result.txt', executor.workspace,
                delivery='terminal'), Config(response_protocol='json', max_turns=8, max_tools=6, wall_seconds=500),
                actor, RUN / name / 'method', executor=executor)
        state.deliver(executor.current)
        save(RUN / name / 'policy-prompts.json', actor.prompts)
        snapshot = contexts[0].snapshot()
        save(RUN / name / 'context-snapshot.json', snapshot)
        trace = events(RUN / name / 'method/events.jsonl')
        requests = [e for e in trace if e['event']=='request_context']
        memories = snapshot['memories']
        if not result['submitted'] or not memories:
            raise RuntimeError('HAI fixture failed to produce memory/submission: ' + json.dumps(result))
        evidence = dict(cwd=cwd, memory_count=len(memories), validity=[m['validity'] for m in memories],
            memory_bytes=[size([m]) for m in memories], selected_ids=requests[-1]['selected_memory_ids'],
            tools=result['tool_calls'], workspace_scope=snapshot['scope'])
        if intervention:
            reminders = [e for e in trace if e['event']=='memory_intervention']
            reconsiderations = [e for e in trace if e['event']=='memory_reconsideration']
            followups = [e for e in trace if e['event']=='memory_followup_outcome']
            check('hai_container_cwd_intervention', len(reminders) == 1 and result['tool_calls'] == 4
                  and any(e.get('changed_direction') for e in reconsiderations)
                  and any(e.get('outcome_observed') for e in followups),
                  dict(reminders=len(reminders), tools=result['tool_calls'],
                       reconsiderations=reconsiderations, followups=followups))
        elif long:
            check('hai_large_memory_reaches_next_prompt', bool(requests[-1]['selected_memory_ids']), evidence,
                  'whole memory dropped above 3000-byte slice')
        else:
            check(name, all(m['validity'] != 'stale' for m in memories) and bool(requests[-1]['selected_memory_ids']),
                  evidence, 'container /app versus host mirror alias' if cwd=='/app' else None)


def classifier_cases():
    import hai_outcomes
    official = dict(process_exit_code=0, verifier_result=dict(rewards=dict(reward=0)), exception_info=None)
    budget = hai_outcomes.classify(official, [dict(event='model_error'), dict(event='mechanism_utilization'),
        dict(event='method_end', result=dict(stop_reason='wall_budget'))])
    infra = hai_outcomes.classify(official, [dict(event='method_end', result=dict(stop_reason='infrastructure_error'))])
    check('classifier_budget_with_metrics', budget['infrastructure_ok'], budget, 'metrics changes adjacency')
    check('classifier_infrastructure_stop', not infra['infrastructure_ok'], infra, 'stop reason ignored')


def conversation_wire_case():
    """Actual Docker/runtime/JSON transport; replace HTTP response bytes only."""
    from bestfgs.lean_docker import ContinuousDockerEnvironment
    from bestfgs.lean_protocol import LeanConfig
    from bestfgs.lean_runtime import LeanTaskRunner
    from bestfgs.retrac_adapter import OpenAICompatibleJSONClient, RetracModelConfig
    from bestfgs.models import TaskSpec
    from bestfgs.lean_conversation import message_chars
    actions = iter([action('printf', 'EARLY_WIRE_OBSERVATION')]
        + [action('cat', 'file.txt')]*9
        + [dict(action='recall_history', turn_ids=[1]), SUBMIT])
    wire = []
    def fake_http(client, **kwargs):
        wire.append(json.loads(kwargs['encoded']))
        return json.dumps(dict(choices=[dict(message=dict(content=json.dumps(next(actions))),
            finish_reason='stop')],usage=dict(prompt_tokens=1,completion_tokens=1))).encode()
    name = 'best-conversation-wire'
    with state_for(name) as state:
        env = ContinuousDockerEnvironment(state)
        client = OpenAICompatibleJSONClient(RetracModelConfig('fixture','https://example.invalid','offline',
            provider='deepseek',request_attempts=1,parse_attempts=1))
        config = LeanConfig(max_turns=30,max_tools=20,wall_seconds=500)
        try:
            with patch.object(OpenAICompatibleJSONClient, '_request_bytes', fake_http):
                result = LeanTaskRunner(env,client,Policy([]),config,RUN/name/'method').run(
                    TaskSpec(name,'Remember early observations; inspect fixture and submit'))
            save(RUN/name/'wire-requests.json',wire)
            final = wire[-1]['messages']
            recall_request = wire[-2]['messages']
            check('best_conversation_beyond_six_on_wire', result['submitted']
                  and sum(m['role']=='assistant' for m in recall_request)>6
                  and 'EARLY_WIRE_OBSERVATION' in json.dumps(recall_request[:-1])
                  and 'EARLY_WIRE_OBSERVATION' not in recall_request[-1]['content']
                  and all(message_chars(w['messages']) <= config.context_chars for w in wire),
                  dict(requests=len(wire),assistant_turns=sum(m['role']=='assistant' for m in recall_request),
                       max_message_chars=max(message_chars(w['messages']) for w in wire),
                       context_chars=config.context_chars,external_http_requests=0))
            check('best_history_retrieval_on_wire', result['submitted']
                  and 'history_records' in final[-1]['content']
                  and 'EARLY_WIRE_OBSERVATION' in final[-1]['content']
                  and result['tool_calls']==10,
                  dict(tool_calls=result['tool_calls'],retrieval_visible='history_records' in final[-1]['content']))
        finally:
            env.close()


def main():
    fatal = None
    cleanup_errors = []
    try:
        prepare_sources()
        prepare_image()
        # Scripted clients bypass HTTP entirely; deny accidental Python socket use too.
        with patch.object(socket.socket, 'connect', side_effect=RuntimeError('Network disabled for integration tests')):
            tests = dict(docker_lifecycle=docker_lifecycle, best_cases=best_cases,
                         conversation_wire_case=conversation_wire_case,
                         hai_relative_cwd_memory=lambda: hai_case('hai_relative_cwd_memory', '.'),
                         hai_container_cwd_memory=lambda: hai_case('hai_container_cwd_memory', '/app'),
                         hai_large_memory=lambda: hai_case('hai_large_memory', '.', long=True),
                         hai_container_cwd_intervention=lambda: hai_case('hai_container_cwd_intervention', '/app', intervention=True),
                         classifier_cases=classifier_cases)
            selected = os.environ.get('INTEGRATION_CASES', ','.join(tests)).split(',')
            if any(name not in tests for name in selected):
                raise ValueError('unknown integration test selection')
            for name in selected:
                try:
                    tests[name]()
                except Exception:
                    detail = traceback.format_exc()
                    RESULTS.append(dict(name=name, status='ERROR', traceback=detail))
                    print(detail, flush=True)
    except Exception:
        fatal = traceback.format_exc()
        print(fatal, flush=True)
    finally:
        for ident in list(ORIGINALS):
            try:
                remove_original(ident)
            except Exception:
                cleanup_errors.append(traceback.format_exc())
        if BASE_IMAGE:
            try:
                assert inspect('image', BASE_IMAGE)['Config']['Labels'].get(LABEL) == OWNER
                docker('image', 'rm', BASE_IMAGE)
            except Exception:
                cleanup_errors.append(traceback.format_exc())
    counts = {key: sum(r['status'] == key for r in RESULTS) for key in ('PASS', 'FAIL', 'ERROR')}
    code = 2 if fatal or cleanup_errors or counts['ERROR'] else (1 if counts['FAIL'] else 0)
    result = dict(status='completed', acceptance_passed=code == 0, exit_code=code, counts=counts,
        model_api_calls=0, checks=RESULTS, fatal=fatal, cleanup_errors=cleanup_errors,
        remaining_originals=sorted(ORIGINALS), elapsed_seconds=round(time.time()-START, 3),
        run_dir=str(RUN), source_dir=str(SOURCES))
    save(RUN / 'results.json', result)
    save(ROOT / 'latest.json', result)
    print(json.dumps(result), flush=True)
    return code


if __name__ == '__main__':
    sys.exit(main())
