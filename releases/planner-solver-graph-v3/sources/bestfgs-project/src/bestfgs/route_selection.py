"""Budgeted two-route experiments; conditional evidence, never a task oracle.

The actor registers commands and predictions once. The controller spends the
existing tool/checkpoint/time budgets, compares the same check from the same
file checkpoint, and restores the selected candidate (or the starting state).
"""
import json
import time
from .lean_audit import digest
from .lean_protocol import parse_action, text
from .lean_progress import normalize_workspace_path
from .stagnation_control import executable


ROUTE_INSTRUCTION = '''When fixed_context.route_search.status is needs_plan,
attach route_experiment to your next run action. The accompanying run is NOT
executed on admission. Instead the controller executes your registered experiment
under the SAME total tool/time/checkpoint budget. Supply this compact schema:
{"probe":{"argv":["program","arg"],"cwd":"."},
 "check":{"argv":["program","arg"],"cwd":"."},
 "pass_contains":"specific public-check success marker",
 "fail_contains":"specific public-check failure marker",
 "routes":[
 {"hypothesis":"first falsifiable explanation", "supports":"probe marker A",
  "refutes":"probe marker B", "targets":["relative/file"],
  "steps":[{"argv":["program","arg"],"cwd":"."}]},
 {"hypothesis":"competing explanation", "supports":"probe marker B",
  "refutes":"probe marker A", "targets":["relative/file"],
  "steps":[{"argv":["program","different arg"],"cwd":"."}]}]}.
Use exactly two substantively different routes, each with 1-3 small executable
steps. The probe must distinguish the hypotheses, not merely ask for more context.
The SAME side-effect-free public check runs on baseline and all tried routes;
derive it from original task requirements, never from hidden grading information.
Both probe and check must leave workspace files unchanged. Use commands that
actually inspect/test, not unconditional success printing. Predictions/markers
are pre-registered and immutable during this episode; exit zero alone is not a
passing check. Ambiguous, truncated or conflicting outputs remain unknown.
A hypothesis refuted by its registered prediction is set aside conditionally.
Otherwise both routes may be tried independently from the same file checkpoint.
Each command has at most 15 seconds; propose cheap focused experiments, not long
builds. Trial steps may modify only task-authorized resources. File restoration
does NOT undo network effects or process state; avoid external/irreversible work.
If neither route improves the check over baseline, original files are restored.
Read route_memory: don't resubmit an identical failed experiment in the same
observable workspace. This is conditional evidence, not a global action ban.
Do not claim a passed model-proposed check proves task success.
'''


def command(value):
    if not isinstance(value, dict):
        raise ValueError('experiment command must be an object')
    parsed = parse_action(dict(value, action='run'))
    if len(json.dumps(parsed, ensure_ascii=False)) > 2000:
        raise ValueError('experiment command too large')
    result = executable(parsed)
    result['cwd'] = normalize_workspace_path(result['cwd']) if result['cwd'] != '.' else '.'
    result.update(action='run', timeout_seconds=min(value.get('timeout_seconds', 15), 15))
    return result


def parse_experiment(value):
    if not isinstance(value, dict):
        raise ValueError('route_experiment must be an object')
    probe, check = command(value.get('probe')), command(value.get('check'))
    if executable(probe) == executable(check):
        raise ValueError('probe and public check must differ')
    if check['argv'][0].rsplit('/', 1)[-1] in ('echo', 'printf', 'true'):
        raise ValueError('unconditional printing is not a public check')
    passed = text(value.get('pass_contains'), 'pass marker', 160)
    failed = text(value.get('fail_contains'), 'fail marker', 160)
    if passed in failed or failed in passed:
        raise ValueError('overlapping check markers')
    routes = value.get('routes')
    if not isinstance(routes, list) or len(routes) != 2:
        raise ValueError('exactly two competing routes required')
    normalized = []
    for i, route in enumerate(routes):
        if not isinstance(route, dict):
            raise ValueError('invalid route')
        hypothesis = text(route.get('hypothesis'), 'hypothesis', 360)
        supports = text(route.get('supports'), 'support marker', 160)
        refutes = text(route.get('refutes'), 'refutation marker', 160)
        if supports in refutes or refutes in supports:
            raise ValueError('overlapping prediction markers')
        targets = route.get('targets')
        if not isinstance(targets, list) or not 1 <= len(targets) <= 4:
            raise ValueError('one to four explicit targets required')
        targets = sorted(set(normalize_workspace_path(p) for p in targets))
        steps = route.get('steps')
        if not isinstance(steps, list) or not 1 <= len(steps) <= 3:
            raise ValueError('one to three bounded steps required')
        steps = [command(step) for step in steps]
        if any(executable(s) in (executable(probe), executable(check)) for s in steps):
            raise ValueError('trial steps must differ from probe and check')
        key = digest([targets, [executable(s) for s in steps], executable(probe),
                      executable(check), supports, refutes, passed, failed])
        normalized.append(dict(id='A' if i == 0 else 'B', hypothesis=hypothesis,
            supports=supports, refutes=refutes, targets=targets, steps=steps, key=key))
    if (normalized[0]['hypothesis'].casefold() == normalized[1]['hypothesis'].casefold()
            or [executable(s) for s in normalized[0]['steps']] ==
               [executable(s) for s in normalized[1]['steps']]):
        raise ValueError('routes must differ in hypothesis and executable actions')
    if (normalized[0]['supports'], normalized[0]['refutes']) == (normalized[1]['supports'], normalized[1]['refutes']):
        raise ValueError('probe predictions must distinguish routes')
    return dict(probe=probe, check=check, pass_contains=passed, fail_contains=failed, routes=normalized)


def check_result(row, plan):
    """Raw captured observation, not a model self-report or compressed excerpt."""
    if row['capture_incomplete'] or row['timed_out'] or row['blocked'] or row['before'] != row['after']:
        return 'unknown'
    output = row['stdout'] + '\n' + row['stderr']
    good, bad = plan['pass_contains'] in output, plan['fail_contains'] in output
    if good and not bad and row['execution_assessment']['execution_clean']:
        return 'pass'
    if bad and not good:
        return 'fail'
    return 'unknown'


class RouteSelection:
    def _init_routes(self):
        self.route_episode = None
        self.route_memory = []
        self.last_route_end = -12
        for name in ('route_episodes', 'route_plans', 'route_tools', 'route_trials',
                     'route_pruned', 'route_selected', 'route_no_gain', 'route_rejected',
                     'route_restore_failures'):
            self.counts[name] = 0

    def route_view(self):
        episode = self.route_episode
        if not episode:
            return {}
        view = {k: episode.get(k) for k in ('id', 'status', 'reason', 'phase', 'used_tools', 'baseline',
                                            'probe_evidence', 'predictions', 'results', 'selected', 'finish_reason')}
        view['budget'] = dict(tool_cap=self.config.route_tool_cap, max_total_episodes=self.config.max_route_episodes)
        # Full pre-registered commands remain in route_plan audit, not hot context.
        view['hypotheses'] = [dict(id=r['id'], hypothesis=r['hypothesis']) for r in
                              (episode.get('plan') or {}).get('routes', [])]
        return view

    def route_memory_view(self):
        scope = self.environment.scope()
        return [dict(m, applicability='same_workspace_external_state_unverified'
                     if m['condition_scope'] == scope else 'historical_recheck_required')
                for m in self.route_memory[-4:]]

    def _route_start(self, reason):
        e = self.route_episode
        if e and e['status'] != 'closed':
            return
        if (self.counts['route_episodes'] >= self.config.max_route_episodes or
                self.counts['tool_calls'] - self.last_route_end < 12):
            return
        if (self.config.max_tools - self.counts['tool_calls'] < self.config.route_tool_cap + 1 or
                self.config.max_checkpoints - self.counts['checkpoints_created'] < 3 or
                self.deadline - time.monotonic() < 120):
            self._emit('route_unavailable', reason='insufficient_existing_budget')
            return
        self.counts['route_episodes'] += 1
        self.route_episode = dict(id='S'+str(self.counts['route_episodes']), status='needs_plan',
            reason=reason[:600], phase='proposal', used_tools=0, gates=0, plan=None,
            base=None, results=[], predictions={}, selected=None, finish_reason=None)
        self._emit('route_started', experiment=self.route_view())

    def _route_before(self, action):
        e = self.route_episode
        if not e or e['status'] != 'needs_plan' or action['action'] != 'run':
            return None
        if action.get('route_experiment') is not None:
            try:
                plan = parse_experiment(action['route_experiment'])
                required = 2 + sum(len(r['steps'])+1 for r in plan['routes'])
                if required > self.config.route_tool_cap:
                    raise ValueError('experiment exceeds episode tool budget')
                if (self.config.max_tools-self.counts['tool_calls'] < required+1 or
                        self.config.max_checkpoints-self.counts['checkpoints_created'] < 3 or
                        self.deadline-time.monotonic() < 120):
                    raise ValueError('insufficient remaining experiment budget')
                e['condition_scope'] = self.environment.scope()
                e['plan'] = plan
                e['base_dependencies'] = self.environment.dependency_state(self._route_targets())
                e['base'] = self._checkpoint('route experiment base', e['reason'])
                e.update(status='running', phase='baseline', expires=min(self.deadline-30, time.monotonic()+180))
                self.counts['route_plans'] += 1
                self._emit('route_plan', experiment_id=e['id'], condition_scope=e['condition_scope'],
                           base=e['base'], plan=plan, required_tools=required, task_success=None)
                return dict(not_executed=True, route_experiment=e['id'],
                            instruction='Plan registered; controller will run baseline, probe and bounded candidate trials.')
            except ValueError as error:
                self.counts['route_rejected'] += 1
                self._emit('route_plan_rejected', experiment_id=e['id'], reason=str(error))
                feedback = str(error)
        else:
            feedback = 'Provide two competing hypotheses, a discriminating probe, two bounded routes and one shared public check.'
        if e['gates'] < 2:
            e['gates'] += 1
            return dict(not_executed=True, route_experiment=e['id'], instruction=feedback)
        self._route_finish('no_valid_experiment_proposed')
        return None

    def _route_targets(self):
        return sorted({p for r in ((self.route_episode or {}).get('plan') or {}).get('routes', []) for p in r['targets']})

    def _route_observe_repeat(self, action, row):
        if self.route_episode and self.route_episode['status'] == 'running':
            return
        key = digest([executable(action), row['before'], row['after'], row.get('outcome_key')])
        self.control_seen[key] = self.control_seen.get(key, 0) + 1
        self.control_seen.move_to_end(key)
        while len(self.control_seen) > 96:
            self.control_seen.popitem(last=False)
        if self.control_seen[key] >= 3:
            self._route_start('Same command, observable state and captured output repeated; discriminate competing explanations.')

    def _route_execute(self, command_value, role):
        e = self.route_episode
        action = dict(command_value, purpose='Route experiment '+e['id']+': '+role)
        e['used_tools'] += 1
        self.counts['route_tools'] += 1
        self._emit('route_tool_dispatch', experiment_id=e['id'], role=role, command=action)
        self._run_command(action)
        row = self.last_tool_observation['evidence']
        self._record_turn(dict(action, decision_source='registered_route_controller'), self.last_tool_observation)
        self._emit('route_observation', experiment_id=e['id'], role=role, evidence_id=row['id'],
                   outcome=row['execution_assessment'], before=row['before'], after=row['after'])
        return row

    def _route_restore(self, checkpoint, reason):
        target = self.checkpoints[checkpoint]
        self.environment.restore(target['record'])
        edge = dict(source=self.anchor, target=checkpoint, reason=reason, controller='route_search')
        self.edges.append(edge)
        self.anchor = checkpoint
        self.counts['branch_restores'] += 1
        self.failure_streak, self.failure_signature, self.diagnostic_streak = 0, None, 0
        self.monitor_review = {}
        self.pending_question = self.pending_question_trigger = None
        self._emit('restore', **edge)
        self.log.save('graph.json', dict(nodes=self.graph, edges=self.edges, current=self.anchor))

    def _route_next(self):
        e = self.route_episode
        if not e['queue']:
            winners = [r for r in e['results'] if r['improved_public_check']]
            winner = min(winners, key=lambda r:r['tools']) if winners else None
            self._route_finish('shared_check_improved' if winner else 'no_candidate_improved', winner)
            return
        e['current'] = e['queue'].pop(0)
        self._route_restore(e['base'], 'Independent trial from common base: '+e['current']['id'])
        e.update(phase='trial', step=0, trial_evidence=[])
        self.counts['route_trials'] += 1
        self._emit('route_trial_started', experiment_id=e['id'], route=e['current']['id'],
                   base=e['base'], scope=self.environment.scope())

    def _route_tick(self):
        if not self.config.route_search:
            return False
        e = self.route_episode
        if not e or e['status'] == 'closed':
            return False
        # Existing monitor/adviser flags cannot displace a registered experiment.
        self.pending_question = self.pending_question_trigger = None
        if e['status'] == 'needs_plan':
            return False
        if (time.monotonic() >= e['expires'] or e['used_tools'] >= self.config.route_tool_cap or
                self.counts['tool_calls'] >= self.config.max_tools-1):
            self._route_finish('experiment_budget_exhausted')
            return True
        p = e['plan']
        if e['phase'] == 'baseline':
            row = self._route_execute(p['check'], 'baseline_check')
            e['baseline'] = dict(evidence_id=row['id'], verdict=check_result(row, p), outcome_key=row['outcome_key'])
            if e['baseline']['verdict'] != 'fail':
                self._route_finish('baseline_already_passes' if e['baseline']['verdict'] == 'pass' else 'baseline_inconclusive')
            else:
                e['phase'] = 'probe'
        elif e['phase'] == 'probe':
            row = self._route_execute(p['probe'], 'discriminating_probe')
            e['probe_evidence'] = row['id']
            e['probe_outcome_key'] = row['outcome_key']
            if row['before'] != row['after']:
                self._route_finish('probe_mutated_workspace')
                return True
            output = row['stdout']+'\n'+row['stderr']
            usable = row['execution_assessment']['execution_clean'] and not row['capture_incomplete']
            queue = []
            for r in p['routes']:
                supports, refutes = r['supports'] in output, r['refutes'] in output
                prediction = ('supported' if supports else 'refuted') if usable and supports != refutes else 'unknown'
                previous = any(m['condition_scope'] == e['condition_scope'] and m['route_key'] == r['key']
                               and m.get('probe_outcome_key') == row['outcome_key']
                               and m.get('baseline',{}).get('outcome_key') == e['baseline']['outcome_key']
                               and m['status'] in ('failed_public_check','prediction_refuted') for m in self.route_memory)
                e['predictions'][r['id']] = 'previous_failure_same_condition' if previous else prediction
                if previous or prediction == 'refuted':
                    self.counts['route_pruned'] += 1
                    self._emit('route_pruned', experiment_id=e['id'], route=r['id'],
                               reason=e['predictions'][r['id']], evidence_id=row['id'], causal_claim=False)
                else:
                    queue.append(r)
            e['queue'] = sorted(queue, key=lambda r:e['predictions'][r['id']] != 'supported')
            self._emit('route_predictions', experiment_id=e['id'], predictions=e['predictions'],
                       evidence_id=row['id'], ground_truth=False)
            self._route_next()
        elif e['phase'] == 'trial':
            row = self._route_execute(e['current']['steps'][e['step']], 'trial_'+e['current']['id'])
            e['trial_evidence'].append(row['id'])
            e['step'] += 1
            if e['step'] == len(e['current']['steps']):
                e['phase'] = 'verify'
        elif e['phase'] == 'verify':
            row = self._route_execute(p['check'], 'shared_check_'+e['current']['id'])
            r = e['current']
            dependencies = row['dependency_after']
            changed = [t for t in r['targets'] if dependencies.get(t) not in (None, 'unknown')
                       and not dependencies[t].startswith('link:')
                       and dependencies[t] != e['base_dependencies'].get(t)]
            verdict = check_result(row, p)
            improved = verdict == 'pass' and bool(changed)
            saved = self._checkpoint('route candidate '+r['id'], r['hypothesis'], pin=e['base']) if improved else None
            result = dict(route=r['id'], verdict=verdict, changed_targets=changed,
                improved_public_check=improved, checkpoint=saved, tools=len(e['trial_evidence'])+1,
                action_evidence_ids=list(e['trial_evidence']), check_evidence_id=row['id'])
            e['results'].append(result)
            self._emit('route_trial_result', experiment_id=e['id'], **result, task_success=None)
            self._route_next()
        return True

    def _route_finish(self, reason, winner=None):
        e = self.route_episode
        if not e or e['status'] == 'closed':
            return
        if winner is None and reason in ('experiment_budget_exhausted','run_ended_before_experiment_completed'):
            completed = [r for r in e['results'] if r['improved_public_check']]
            winner = min(completed,key=lambda r:r['tools']) if completed else None
        if e['base']:
            self._route_restore(winner['checkpoint'] if winner else e['base'], 'Route selection: '+reason)
        e.update(status='closed', selected=winner['route'] if winner else None, finish_reason=reason)
        self.last_route_end = self.counts['tool_calls']
        self.counts['route_selected' if winner else 'route_no_gain'] += 1
        for r in (e.get('plan') or {}).get('routes', []):
            observed = next((v for v in e['results'] if v['route'] == r['id']), None)
            prediction = e['predictions'].get(r['id'])
            if not observed and prediction != 'refuted':
                continue
            status = ('verified_public_check' if observed['improved_public_check'] else
                      'failed_public_check' if observed['verdict'] == 'fail' else 'inconclusive') if observed else 'prediction_refuted'
            memory = dict(experiment_id=e['id'], route=r['id'], route_key=r['key'],
                condition_scope=e['condition_scope'], hypothesis=r['hypothesis'],
                status=status, probe_evidence=e.get('probe_evidence'), baseline=e.get('baseline'),
                probe_outcome_key=e.get('probe_outcome_key'),
                trial=observed, selected=e['selected'] == r['id'], external_state='unverified', task_success=None)
            self.route_memory.append(memory)
            self._emit('route_memory_recorded', memory=memory)
        self.route_memory = self.route_memory[-12:]
        self.log.save('route-memory.json', self.route_memory)
        self.last_feedback = dict(route_selection=self.route_view(),
            instruction='Continue from selected files. These public-check observations do not prove whole-task success.')
        self._emit('route_finished', experiment=self.route_view(), task_success=None)

    def _route_close_on_exit(self):
        if self.config.route_search and self.route_episode and self.route_episode['status'] != 'closed':
            self._route_finish('run_ended_before_experiment_completed')
