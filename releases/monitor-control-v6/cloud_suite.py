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
        integration_manifest = ROOT / 'integration-source-manifest.json'
        if integration_manifest.exists():
            assert json.loads(integration_manifest.read_text()) == {
                str(p.relative_to(ROOT/'integration')): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (ROOT/'integration').glob('*.py')}, 'integration source mismatch'
        baseline = json.loads((ROOT / 'baseline-manifest.json').read_text())
        for row in baseline:
            assert hashlib.sha256(Path(row['origin']).read_bytes()).hexdigest() == row['sha256'], row['origin']
        save(RUN / 'source-manifest.json', expected)
        shutil.copy2(__file__, RUN / 'cloud_suite.py')
        sys.path[:0] = [str(SOURCES), str(ROOT / 'integration'), str(SOURCES / 'bestfgs-project/src'),
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
    docker('cp', str(SOURCES / 'bestfgs-project/src/bestfgs/shell_probe.py'), original + ':/opt/lhtb-agent-tools/shell_probe.py')
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


def output_recovery_case():
    """Reject two truncated writes, recover with small edits in real Docker."""
    from audit import Audit, JSONClientAudit
    from bestfgs.lean_docker import ContinuousDockerEnvironment
    from bestfgs.lean_protocol import LeanConfig
    from bestfgs.lean_runtime import LeanTaskRunner
    from bestfgs.retrac_adapter import OpenAICompatibleJSONClient, RetracModelConfig
    from bestfgs.models import TaskSpec
    from bestfgs.lean_conversation import message_chars
    from outcomes import classify
    name, wire = 'best-output-recovery', []
    actions = iter([action('bash', '-lc', "printf 'part1\\n' > recovered.txt"),
                    action('bash', '-lc', "printf 'part2\\n' >> recovered.txt"),
                    action('cat', 'recovered.txt'), SUBMIT])
    def fake_http(client, **kwargs):
        body = json.loads(kwargs['encoded'])
        wire.append(body)
        if len(wire) <= 2:
            value, reason = action('touch', 'REJECTED_SHOULD_NOT_EXIST'), 'length'
        else:
            if len(wire) == 3:
                assert 'output_length' in body['messages'][-1]['content']
                assert 'file chunk' in body['messages'][-1]['content']
            value, reason = next(actions), 'stop'
        return json.dumps(dict(choices=[dict(message=dict(content=json.dumps(value)), finish_reason=reason)],
            usage=dict(prompt_tokens=10, completion_tokens=10))).encode()
    with state_for(name) as state:
        env = ContinuousDockerEnvironment(state)
        client = OpenAICompatibleJSONClient(RetracModelConfig('fixture', 'https://example.invalid', 'offline',
            provider='deepseek', max_tokens=4096, request_attempts=2, parse_attempts=1, retry_interval_seconds=0),
            diagnostics_path=RUN/name/'wire-failures.jsonl')
        outer_path = RUN/name/'outer-audit.jsonl'
        audited = JSONClientAudit(client, Audit(outer_path, ['offline']), 'action', state.deadline)
        try:
            with patch.object(OpenAICompatibleJSONClient, '_request_bytes', fake_http):
                result = LeanTaskRunner(env, audited, Policy([]),
                    LeanConfig(max_turns=12, max_tools=6, wall_seconds=500), RUN/name/'method').run(
                        TaskSpec(name, 'Write recovered.txt with part1 and part2; submit'))
            save(RUN/name/'wire-requests.json', wire)
            content = docker('exec', env.container, 'cat', '/app/recovered.txt')
            absent = subprocess.run(['docker', 'exec', env.container, 'test', '!', '-e',
                '/app/REJECTED_SHOULD_NOT_EXIST'], capture_output=True).returncode == 0
            check('best_truncated_response_recovery', result['submitted'] and result['tool_calls'] == 3
                and content == 'part1\npart2' and absent and len(wire) == 6
                and all(body['max_tokens'] == 4096 and message_chars(body['messages']) <= 48000 for body in wire),
                dict(requests=len(wire), tool_calls=result['tool_calls'], rejected_action_absent=absent,
                     artifact=content, failure_counts=client.failure_counts, external_http_requests=0))
            events = [json.loads(line) for line in outer_path.read_text().splitlines()]
            events.append(dict(event='method_end', result=result))
            classified = classify(dict(method='bestfgs', process_exit_code=0, verifier_result={}), events)
            check('best_recovered_output_error_classification', classified['method_issues'] == []
                and classified['recovered_model_errors'] == 1
                and [e['error_code'] for e in events if e['event'] == 'model_error'] == ['output_length'], classified)
        finally:
            env.close()


def semantic_memory_case():
    from bestfgs.lean_docker import ContinuousDockerEnvironment
    from bestfgs.lean_runtime import LeanTaskRunner
    from bestfgs.lean_protocol import LeanConfig
    from bestfgs.models import TaskSpec
    from bestfgs.retrac_adapter import OpenAICompatibleJSONClient, RetracModelConfig
    from bestfgs.monitor_config import monitor_config
    name, wire = 'best-semantic-memory', []
    monitor_reply = dict(verdict='stalled', reason='Different arguments repeated the same unchanged parser failure.',
        evidence_ids=['E1','E2'], next_check='Check the input format before retrying.', memories=[
            dict(kind='blocker', conclusion='These two attempts both failed with PARSER_PROBE.',
                 condition='Only for this unchanged fixture input; external state unverified.',
                 targets=[], operation='bash', next_step='Inspect the input format', evidence_ids=['E1','E2'],
                 support=[dict(evidence_id=e, field='stderr', quote='PARSER_PROBE') for e in ['E1','E2']])])
    def fake_http(client, **kwargs):
        body = json.loads(kwargs['encoded']); wire.append(body)
        return json.dumps(dict(choices=[dict(message=dict(content=json.dumps(monitor_reply)),finish_reason='stop')],
            usage=dict(prompt_tokens=20, completion_tokens=20))).encode()
    with state_for(name) as state:
        env = ContinuousDockerEnvironment(state)
        actor = Policy([action('bash','-lc','echo PARSER_PROBE >&2; exit 2','attempt-A'),
                        action('bash','-lc','echo PARSER_PROBE >&2; exit 2','attempt-B'),
                        action('bash','-lc',"printf 'recovered' > result.txt", uses_memory=['M1']), SUBMIT])
        advisor = Policy([dict(alternatives=[])])
        monitor = OpenAICompatibleJSONClient(monitor_config(RetracModelConfig('fixture',
            'https://example.invalid','offline',provider='deepseek')))
        try:
            with patch.object(OpenAICompatibleJSONClient,'_request_bytes',fake_http):
                result = LeanTaskRunner(env, actor, advisor,
                    LeanConfig(semantic_monitor=True,auto_memory=True,max_monitor_calls=1,
                        monitor_cooldown_tools=2,monitor_interval_tools=3,max_turns=12,max_tools=8,wall_seconds=500),
                    RUN/name/'method',monitor_client=monitor).run(TaskSpec(name,'Write result.txt after diagnosing the failure'))
            trace = events(RUN/name/'method/events.jsonl')
            save(RUN/name/'policy-prompts.json',dict(actor=actor.prompts,advisor=advisor.prompts,monitor_wire=wire))
            check('semantic_different_command_loop', result['mechanism_utilization']['semantic_stalls']==1
                and result['advisor_rounds']==1 and len(advisor.prompts)==1,
                dict(stalls=result['mechanism_utilization']['semantic_stalls'],advisor_rounds=result['advisor_rounds']))
            memories = actor.prompts[2]['fixed_context']['memories']
            check('automatic_quoted_memory_on_next_action', len(memories)==1
                and memories[0]['origin']=='semantic_monitor' and len(memories[0]['support'])==2,
                dict(memories=memories,admitted=result['mechanism_utilization']['auto_memories_admitted']))
            artifact = docker('exec',env.container,'cat','/app/result.txt')
            check('semantic_loop_to_real_artifact',result['submitted'] and artifact=='recovered'
                and result['tool_calls']==3 and any(e['event']=='monitor_followup' for e in trace),
                dict(artifact=artifact,tool_calls=result['tool_calls'],submitted=result['submitted']))
            check('monitor_wire_budget_and_isolation',len(wire)==1 and len(wire[0]['messages'])==2
                and wire[0]['max_tokens']==1536 and len(json.dumps(wire[0]['messages'],ensure_ascii=False))<20000
                and result['interaction_rounds']==6,
                dict(monitor_requests=len(wire),model_rounds=result['interaction_rounds'],external_model_calls=0))
        finally:
            env.close()


def memory_reliability_case():
    from bestfgs.lean_docker import ContinuousDockerEnvironment
    from bestfgs.lean_runtime import LeanTaskRunner
    from bestfgs.lean_protocol import LeanConfig
    from bestfgs.models import TaskSpec
    name='best-memory-reliability'
    fail=action('bash','-lc','cat config.txt >&2; exit 2')
    repair_memory=dict(kind='finding',conclusion='The command read invalid-data from config.txt.',
        condition='At the observed config.txt version.',operation='x'*143,targets=['config.txt'],
        evidence_ids=['E2','E3'],next_step='Repair the input then verify it.')
    actor=Policy([action('bash','-lc',"printf 'invalid-data' > config.txt"),fail,fail,
        action('bash','-lc',"printf 'unrelated' > note.txt"),
        dict(fail,uses_memory=['M1']),
        action('bash','-lc',"printf 'valid-data' > config.txt",memory=repair_memory),SUBMIT])
    monitor=Policy([])
    with state_for(name) as state:
        env=ContinuousDockerEnvironment(state)
        try:
            runner=LeanTaskRunner(env,actor,Policy([]),
                LeanConfig(memory_reliability=True,auto_memory=True,max_advisor_calls=0,
                    monitor_cooldown_tools=20,monitor_interval_tools=24,max_turns=30,max_tools=30,wall_seconds=500),
                RUN/name/'method',monitor_client=monitor)
            result=runner.run(TaskSpec(name,'Fix config.txt and preserve the parser failure evidence.'))
            trace=events(RUN/name/'method/events.jsonl')
            save(RUN/name/'policy-prompts.json',actor.prompts)
            check('observed_memory_without_llm',runner.counts['observed_memories_admitted']==1
                  and result['monitor_rounds']==0,dict(observed=runner.counts['observed_memories_admitted'],monitor_calls=result['monitor_rounds']))
            memories=actor.prompts[4]['fixed_context']['memories']
            current=next((m for m in memories if m['id']=='M1'),{})
            check('unrelated_edit_preserves_dependency_applicability','unchanged' in current.get('applicability',''),
                  dict(memory=current,unrelated_file=docker('exec',env.container,'cat','/app/note.txt')))
            check('acknowledgment_needs_reason_not_hard_ban',runner.counts['memory_interventions']==1
                  and result['tool_calls']==5 and result['submitted'],
                  dict(interventions=runner.counts['memory_interventions'],tool_calls=result['tool_calls'],submitted=result['submitted']))
            final=actor.prompts[-1]['fixed_context']['memories']
            check('related_edit_requires_recheck',any(m['id']=='M1' and 'recheck_required' in m['applicability'] for m in final),
                  dict(memories=final,artifact=docker('exec',env.container,'cat','/app/config.txt')))
            check('overlong_operation_retains_real_evidence',any(e['event']=='memory_field_repaired' for e in trace)
                  and any(m['id']=='M2' for m in runner.memory.items.values()),
                  dict(repairs=[e for e in trace if e['event']=='memory_field_repaired']))
        finally:
            env.close()


def monitor_control_v6_case():
    from bestfgs.lean_docker import ContinuousDockerEnvironment
    from bestfgs.lean_runtime import LeanTaskRunner
    from bestfgs.lean_protocol import LeanConfig
    from bestfgs.models import TaskSpec
    from bestfgs.tool_outcomes import assess
    name='monitor-control-v6'
    with state_for(name) as state:
        env=ContinuousDockerEnvironment(state)
        try:
            env.outcome_reliability=True
            result=env.execute(action('bash','-lc',"/opt/lhtb-agent-tools/python/bin/python3.12 -c 'raise RuntimeError(\"broken\")' 2>&1 | tail -5"),state.deadline)
            check('v6_docker_pipeline_exit_observation',result.return_code==0
                  and [1,0] in result.execution_observation['pipelines'] and not assess(result)['execution_clean'],
                  dict(process_exit=result.return_code,assessment=assess(result)))
            read=action('bash','-lc','cat file.txt')
            fix=['bash','-lc',"printf repaired > result.txt"]
            verify=['bash','-lc','test "$(cat result.txt)" = repaired && echo RECOVERY_CHECK_PASSED']
            plan=dict(hypothesis='Required result.txt is missing',mode='repair',targets=['result.txt'],
                      action_argv=fix,verification_argv=verify,success_contains='RECOVERY_CHECK_PASSED')
            actor=Policy([read,read,read,dict(action(*fix),recovery_plan=plan),action(*verify),SUBMIT])
            runner=LeanTaskRunner(env,actor,Policy([]),LeanConfig(max_turns=30,max_tools=20,wall_seconds=500,
                max_advisor_calls=0,memory_reliability=True,outcome_reliability=True,stagnation_control=True),RUN/name/'method')
            report=runner.run(TaskSpec(name,'Create result.txt and verify its content'))
            trace=events(RUN/name/'method/events.jsonl')
            check('v6_docker_intervention_edit_verify',report['submitted'] and runner.counts['recovery_verified_repairs']==1,
                  dict(counts=report['mechanism_utilization'],recovery=runner.control_view()))
            check('v6_docker_real_artifact_delivery',docker('exec',env.container,'cat','/app/result.txt')=='repaired'
                  and any(e['event']=='recovery_plan' for e in trace),dict(artifact=report['artifact']))
        finally:env.close()


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
                         output_recovery_case=output_recovery_case,
                         semantic_memory_case=semantic_memory_case,
                         memory_reliability_case=memory_reliability_case,
                         monitor_control_v6_case=monitor_control_v6_case,
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
