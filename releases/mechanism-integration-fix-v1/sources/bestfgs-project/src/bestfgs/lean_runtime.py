"""BestFGS v18: continuous action loop with bounded, event-driven advice.

This intentionally does not run the legacy semantic-coverage frontier scheduler.
The attempt graph records explicit checkpoints and restores, not every command.
"""
from collections import Counter, OrderedDict
from dataclasses import asdict, replace
import json
import hashlib
from pathlib import Path
import time

from .lean_audit import Recorder, digest
from .lean_memory import Memories
from .lean_progress import DeliveryProgress
from .lean_protocol import LeanConfig, ACTION_SYSTEM, ADVISOR_SYSTEM, parse_action, text, validate_evidence_ids
from .models import ModelCallError
from .prompt_views import classify, diagnostic_category, compress_stream, clip


class LeanTaskRunner:
    def __init__(self, environment, action_client, advisor_client, config=None,
                 output=None, submission_feedback=None, secrets=()):
        action_transport = getattr(action_client, 'inner', action_client)
        advisor_transport = getattr(advisor_client, 'inner', advisor_client)
        if action_transport is advisor_transport:
            raise ValueError('action and advisor must have independent client instances')
        self.environment = environment
        self.clients = {'action': action_client, 'advisor': advisor_client}
        self.config = config or LeanConfig()
        self.output = Path(output) if output else None
        if self.output is None:
            raise ValueError('audit output directory is required')
        self.feedback = submission_feedback
        keys = tuple(getattr(getattr(c, 'config', None), 'api_key', '') for c in self.clients.values())
        self.secrets = tuple(secrets) + keys
        self._used = False

    def _emit(self, event, **fields):
        return self.log.emit(event, **fields)

    def _panel(self, question=''):
        scope = self.environment.scope()
        recent = [self.evidence[key] for key in list(self.evidence)[-6:]]
        query = question or (recent[-1]['purpose'] if recent else self.task.goal)
        tracked = sorted(set(self.memory.dependency_targets()).union(self.progress.paths))
        dependencies = self.environment.dependency_state(tracked)
        memories = self.memory.recall(query, scope, dependencies)
        progress = self.progress.view(dependencies)
        # The model call cannot mutate the task workspace. Reuse this exact
        # pre-action state when deciding whether its proposed action matches a
        # visible memory, avoiding another controller inspection process.
        self.last_panel_scope, self.last_panel_dependencies = scope, dependencies
        elapsed_ratio = min(1, max(0, (time.monotonic()-self.started_at) / self.config.wall_seconds))
        pressure_ratio = max(elapsed_ratio,
            self.counts['model_requests']/self.config.max_turns,
            self.counts['tool_calls']/self.config.max_tools)
        if pressure_ratio >= .85:
            pressure = {'stage':'preserve_and_deliver', 'used_ratio':round(pressure_ratio, 3),
                'instruction':('Preserve the best viable state, close explicit missing-artifact gaps, '
                               'and submit when the current artifact is the best defensible result.')}
        elif pressure_ratio >= .60:
            pressure = {'stage':'converge', 'used_ratio':round(pressure_ratio, 3),
                'instruction':('Converge exploration into an implementation or one discriminating check; '
                               'avoid opening unrelated directions without evidence.')}
        else:
            pressure = {'stage':'normal', 'used_ratio':round(pressure_ratio, 3)}
        if self.diagnostic_streak >= self.config.diagnostic_nudge_threshold:
            pressure['diagnostic_nudge'] = (
                'Extended read-only diagnosis detected. Identify the one fact blocking an implementation, '
                'then run a discriminating check or attempt a minimal deliverable. Continued diagnosis is '
                'allowed when it can produce new evidence.')
        panel = dict(current_workspace=scope, external_state='unverified',
            evidence=recent, memories=memories, advice=self.advice,
            delivery_progress=progress, budget_pressure=pressure,
            memory_intervention=self.pending_memory_intervention,
            checkpoints=[dict(id=k, label=v['label'], hypothesis=v['hypothesis'],
                              fingerprint=v['record']['fingerprint']) for k,v in self.checkpoints.items()],
            budgets=dict(model_requests=self.config.max_turns-self.counts['model_requests'],
                         tools=self.config.max_tools-self.counts['tool_calls'],
                         advisor_calls=self.config.max_advisor_calls-self.counts['advisor_calls'],
                         wall_seconds=max(0, round(self.deadline-time.monotonic(), 2))),
            feedback=self.last_feedback)
        payload = dict(task=asdict(self.task), fixed_context=panel, recent_decisions=self.history[-6:])
        if question:
            payload['question'] = question
        # Shrink the oldest observations/decisions first. Never truncate task
        # instructions, JSON structure, or the latest feedback silently.
        while len(json.dumps(payload, ensure_ascii=False)) > self.config.context_chars:
            if payload['recent_decisions']:
                payload['recent_decisions'].pop(0)
            elif len(panel['evidence']) > 1:
                panel['evidence'].pop(0)
            elif panel['memories']:
                panel['memories'].pop()
            else:
                raise ValueError('task and protected context exceed configured context budget')
        self.visible_evidence = {e['id'] for e in panel['evidence']}
        self.visible_memories = {m['id'] for m in panel['memories']}
        self.visible_memory_records = {m['id']:m for m in panel['memories']}
        return payload

    @staticmethod
    def _action_core(action):
        return {key:value for key,value in action.items() if key not in {'memory','uses_memory'}}

    def _memory_push(self, action):
        if (action.get('action') != 'run' or
                self.counts['memory_interventions'] >= self.config.max_memory_interventions):
            return None
        scope = self.last_panel_scope
        dependencies = self.last_panel_dependencies
        matches = self.memory.match_action(action, scope, dependencies)
        acknowledged = set(action.get('uses_memory', [])) if isinstance(action.get('uses_memory'), list) else set()
        matches = [item for item in matches if item['id'] not in acknowledged]
        # A memory may match several syntactically different commands. Remind
        # once per memory and observable workspace state, rather than nagging
        # again after every reformulation of the same direction.
        matches = [item for item in matches if digest({'scope':scope, 'memory_id':item['id']})
                   not in self.memory_intervention_signatures]
        if not matches:
            return None
        for item in matches:
            self.memory_intervention_signatures.add(digest({'scope':scope, 'memory_id':item['id']}))
        self.counts['memory_interventions'] += 1
        return {'id':'MI'+str(self.counts['memory_interventions']),
            'proposed_action':self._action_core(action), 'matched_memories':matches,
            'instruction':('Reconsider this proposed action against the matched evidence. You may change it, '
                           'check applicability, or deliberately repeat it with uses_memory listing the IDs. '
                           'No command has run and the reminder is not a prohibition.'),
            'causal_benefit_proven':False}

    def _record_memory_reconsideration(self, action):
        if self.pending_memory_proposal is None:
            return
        previous = self.pending_memory_proposal
        self.last_intervention_memory_ids = {m['id'] for m in previous['matched_memories']}
        changed = self._action_core(action) != previous['proposed_action']
        key = 'memory_action_changed' if changed else 'memory_action_unchanged'
        self.counts[key] += 1
        self._emit('memory_reconsideration', intervention_id=previous['id'],
                   previous_action=previous['proposed_action'], revised_action=self._action_core(action),
                   changed=changed, causal_benefit_proven=False)
        self.pending_memory_outcome = {'intervention_id':previous['id'], 'memory_ids':sorted(
            self.last_intervention_memory_ids), 'proposed_action':previous['proposed_action'],
            'revised_action':self._action_core(action), 'changed':changed}
        self.pending_memory_proposal = None
        self.pending_memory_intervention = None

    def _ask(self, role, question=''):
        if self.counts['model_requests'] >= self.config.max_turns or time.monotonic() >= self.deadline:
            raise TimeoutError('model budget exhausted')
        payload = self._panel(question)
        remaining = self.deadline-time.monotonic()
        if remaining < 1:
            raise TimeoutError('model budget exhausted')
        client = self.clients[role]
        transport = getattr(client, 'inner', client)
        old = getattr(transport, 'config', None)
        if old is not None:
            wall = max(1, min(old.max_wall_time_seconds, int(remaining)))
            # Keep one logical decision round while allowing one bounded wire
            # repair for malformed JSON/transient transport failures.  The
            # underlying client still audits every API request separately, so
            # this cannot hide cost or reset the task/model budgets.
            transport.config = replace(old, request_attempts=max(1, min(2, old.request_attempts)), parse_attempts=1,
                timeout_seconds=min(old.timeout_seconds, wall), max_wall_time_seconds=wall)
        self.counts['model_requests'] += 1
        self.counts[role + '_calls'] += 1
        self.counts['memory_exposures'] += len(self.visible_memories)
        if self.visible_memories:
            self.counts['requests_with_memory'] += 1
        self._emit('model_request', role=role, payload=payload,
                   memory_ids=sorted(self.visible_memories))
        started = time.monotonic()
        try:
            response = client.complete_json(system_prompt=ACTION_SYSTEM if role == 'action' else ADVISOR_SYSTEM,
                user_prompt=json.dumps(payload, ensure_ascii=False))
            self._emit('model_response', role=role, response=response)
            return response
        except ModelCallError:
            self._emit('model_error', role=role,
                error_code=getattr(client, 'last_failure_detail', None),
                failure_kind=getattr(client, 'last_failure_kind', None))
            raise
        finally:
            self.timings[role] += time.monotonic()-started
            if old is not None:
                transport.config = old

    def _fatal_provider_error(self, client):
        return getattr(client, 'last_failure_detail', '') in {
            'http_401', 'http_402', 'http_403', 'provider_401', 'provider_402', 'provider_403'}

    def _consult(self, question, trigger):
        if (self.counts['advisor_calls'] >= self.config.max_advisor_calls or
                self.counts['tool_calls']-self.last_advisor_tool < self.config.advisor_cooldown_tools):
            self._emit('advisor_skipped', reason='capacity_or_cooldown', trigger=trigger)
            return dict(advisor='unavailable_this_turn', instruction='Continue or submit using available evidence.')
        self.last_advisor_tool = self.counts['tool_calls']
        self._emit('advisor_trigger', trigger=trigger, question=question)
        try:
            response = self._ask('advisor', question)
            alternatives = response.get('alternatives') if isinstance(response, dict) else None
            if not isinstance(alternatives, list) or len(alternatives) > 2:
                raise ValueError('advisor must return at most two alternatives')
            parsed = []
            for item in alternatives:
                if not isinstance(item, dict):
                    raise ValueError('invalid alternative')
                row = {key: text(item.get(key), key, 700) for key in ('hypothesis', 'check', 'difference')}
                ids = validate_evidence_ids(item.get('evidence_ids', []), self.visible_evidence)
                row['evidence_ids'] = ids
                parsed.append(row)
            self.advice = dict(id='A' + str(self.counts['advisor_calls']), question=question,
                               alternatives=parsed, status='hypotheses_not_verified')
            self.advice_pending = True
            self.counts['advisor_responses_accepted'] += 1
            self._emit('advice', **self.advice)
            return self.advice
        except ValueError as error:
            self.counts['advisor_deferred'] += 1
            self._emit('advisor_deferred', reason=str(error))
        except ModelCallError:
            if self._fatal_provider_error(self.clients['advisor']):
                raise
            self.counts['advisor_deferred'] += 1
            self._emit('advisor_deferred', reason='model_error')
        return dict(advisor='deferred', instruction='Continue with existing evidence; no action was executed.')

    def _checkpoint(self, label, hypothesis, pin=None):
        if self.counts['checkpoints_created'] >= self.config.max_checkpoints:
            raise ValueError('checkpoint budget exhausted')
        record = self.environment.checkpoint(label)
        self.counts['checkpoints_created'] += 1
        key = 'C' + str(self.counts['checkpoints_created'])
        node = dict(id=key, parent=self.anchor, label=label, hypothesis=hypothesis, record=record,
                    evidence_ids=list(self.evidence)[-3:], active=True)
        self.checkpoints[key] = node
        self.graph.append(node)
        self.anchor = key
        while len(self.checkpoints) > self.config.max_active_checkpoints:
            victim = next(k for k in self.checkpoints if k != pin and k != key)
            self.checkpoints.pop(victim)['active'] = False
            self._emit('checkpoint_retired', checkpoint_id=victim, files_retained=True)
        self._emit('checkpoint', node=node)
        self.log.save('graph.json', dict(nodes=self.graph, edges=self.edges, current=self.anchor))
        return key

    def _optional_memory(self, action):
        if 'memory' in action:
            try:
                item, added = self.memory.admit(action['memory'], self.evidence, self.visible_evidence,
                                                self.environment.dependency_state)
                self.counts['memories_admitted'] += int(added)
                self._emit('memory_admitted', memory=item, new=added)
            except ValueError as error:
                self.counts['memories_rejected'] += 1
                self._emit('memory_rejected', reason=str(error))
        claims = action.get('uses_memory', [])
        if isinstance(claims, list):
            intervention_ids = ({m['id'] for m in (self.pending_memory_intervention or {}).get('matched_memories', [])}
                                | self.last_intervention_memory_ids)
            accepted = sorted({m for m in claims if isinstance(m, str)
                               and m in self.visible_memories.union(intervention_ids)})
            self.counts['memory_use_self_reports'] += len(accepted)
            if accepted:
                self._emit('memory_use_self_report', memory_ids=accepted, causal_benefit_proven=False)
        self.last_intervention_memory_ids = set()

    def _consume_memory_followup(self, action_kind, **outcome):
        memory_chain = self.pending_memory_outcome
        self.pending_memory_outcome = None
        if not memory_chain:
            return
        self.counts['memory_followup_actions'] += 1
        if action_kind == 'run':
            self.counts['memory_followup_runs'] += 1
            self.counts['memory_followup_succeeded'] += int(outcome.get('succeeded', False))
            self.counts['memory_followup_workspace_changed'] += int(
                outcome.get('workspace_changed', False))
        self._emit('memory_followup_outcome', **memory_chain, action_kind=action_kind,
                   causal_benefit_proven=False, **outcome)

    def _run_command(self, action):
        if self.counts['tool_calls'] >= self.config.max_tools:
            raise TimeoutError('tool budget exhausted')
        if time.monotonic() >= self.deadline:
            raise TimeoutError('work budget exhausted')
        action = dict(action, timeout_seconds=min(action.get('timeout_seconds', 60), self.config.command_seconds))
        before = self.environment.scope()
        started = time.monotonic()
        self.counts['tool_calls'] += 1
        self._emit('tool_attempt', call_id=self.counts['tool_calls'], command=action, before=before)
        result = self.environment.execute(action, self.deadline)
        self.timings['tools'] += time.monotonic()-started
        after = self.environment.scope()
        self._consume_memory_followup('run', outcome_observed=True, succeeded=result.succeeded,
            workspace_changed=before != after, timed_out=result.timed_out, blocked=result.blocked)
        eid = 'E' + str(self.counts['tool_calls'])
        category = classify(action['argv'])
        view = dict(id=eid, argv=clip(json.dumps(action['argv'], ensure_ascii=False), 1800),
            purpose=clip(str(action.get('purpose', '')), 400), before=before, after=after,
            return_code=result.return_code, timed_out=result.timed_out, blocked=result.blocked,
            stdout=compress_stream(result.stdout, category, 2200),
            stderr=compress_stream(result.stderr, category, 1600),
            capture_incomplete=result.output_truncated, category=category)
        self.evidence[eid] = view
        # Raw observations remain in the audit, not all in the hot prompt/store.
        while len(self.evidence) > 48:
            self.evidence.popitem(last=False)
        signature = digest(dict(argv=action['argv'], cwd=action.get('cwd', '.'), stdin=action.get('stdin'),
                                before=before, after=after, stdout=result.stdout, stderr=result.stderr,
                                exit=result.return_code, timeout=result.timed_out, blocked=result.blocked))
        repeated = not result.succeeded and not result.output_truncated and before == after
        self.failure_streak = self.failure_streak + 1 if repeated and signature == self.failure_signature else int(repeated)
        self.failure_signature = signature
        diagnostic_kind = diagnostic_category(action['argv'])
        diagnostic = result.succeeded and before == after and diagnostic_kind in {'read','listing','search','diff'}
        self.diagnostic_streak = self.diagnostic_streak + 1 if diagnostic else 0
        advice_id = self.advice.get('id') if self.advice_pending else None
        self._emit('tool_call', evidence_id=eid, command=action, result=asdict(result),
                   before=before, after=after, redundancy_label='unreviewed',
                   repeated_failure_streak=self.failure_streak, diagnostic_streak=self.diagnostic_streak,
                   diagnostic_category=diagnostic_kind,
                   advice_visible_id=advice_id, causal_benefit_proven=False)
        if advice_id:
            self.counts['post_advice_actions'] += 1
            self.advice_pending = False
        if self.failure_streak >= self.config.repeated_failure_threshold:
            self.pending_question = 'The same command failed repeatedly with identical captured output. What different explanation or information source should be checked?'
            self.pending_question_trigger = 'repeated_failure'
        elif self.diagnostic_streak >= self.config.diagnostic_advisor_threshold:
            self.pending_question = (
                'Read-only diagnosis has continued without a workspace change. Which single unknown currently '
                'blocks implementation, and what cheap check or minimal implementation would distinguish it?')
            self.pending_question_trigger = 'extended_diagnosis'
            self.diagnostic_streak = 0
        return dict(evidence=view)

    def run(self, task):
        if self._used:
            raise RuntimeError('Runner is single-use; create a new isolated run')
        self._used = True
        self.task = task
        self.log = Recorder(self.output, self.secrets)
        self.counts, self.timings = Counter(), Counter()
        self.counts.update({name:0 for name in ('model_requests','action_calls','advisor_calls','tool_calls',
            'memory_exposures','requests_with_memory','memories_admitted','memories_rejected',
            'memory_use_self_reports','advisor_responses_accepted','advisor_deferred',
            'checkpoints_created','branch_restores','submissions','protocol_errors',
            'memory_interventions','memory_action_changed','memory_action_unchanged',
            'memory_followup_actions','memory_followup_runs','memory_followup_succeeded',
            'memory_followup_workspace_changed','post_advice_actions')})
        self.memory = Memories(self.config.max_memories)
        self.progress = DeliveryProgress(task, self.environment)
        self.evidence, self.checkpoints = OrderedDict(), OrderedDict()
        self.graph, self.edges, self.history = [], [], []
        self.anchor = None
        self.advice, self.last_feedback = {}, {}
        self.advice_pending = False
        self.failure_streak, self.failure_signature = 0, None
        self.diagnostic_streak = 0
        self.last_advisor_tool = -self.config.advisor_cooldown_tools
        self.pending_question = None
        self.pending_question_trigger = None
        self.pending_memory_intervention = None
        self.pending_memory_proposal = None
        self.memory_intervention_signatures = set()
        self.last_intervention_memory_ids = set()
        self.pending_memory_outcome = None
        self.visible_evidence, self.visible_memories = set(), set()
        started = time.monotonic()
        self.started_at = started
        self.deadline = started + self.config.wall_seconds
        self._emit('header', version='bestfgs-lean-v18.1', task=asdict(task), config=asdict(self.config),
                   success_semantics='requires_external_evaluation',
                   source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(Path(__file__).parent.glob('*.py'))},
                   models={role:{key:getattr(getattr(getattr(c,'inner',c),'config',None),key,None)
                                 for key in ('provider','model_name','temperature','thinking_enabled','max_tokens')}
                           for role,c in self.clients.items()},
                   metric_definitions=dict(interaction_rounds='all main and advisor model requests, including failed attempts',
                       tool_calls='all calls issued to the task executor, including refused/timed-out calls',
                       redundancy='independent context-aware labels; unreviewed is not zero',
                       memory_behavior_chain=('intervention -> reconsidered action -> next executed tool outcome; '
                           'association only, never a causal benefit claim'),
                       delivery_progress=('public requested-path existence plus unverified criteria; '
                           'existence never means task success')))
        submitted, stop, consecutive_errors = False, 'model_budget', 0
        accepted_artifact = None
        error_type = None
        try:
            self._checkpoint('initial state', 'Root before any attempted solution')
            while self.counts['model_requests'] < self.config.max_turns:
                if time.monotonic() >= self.deadline:
                    stop = 'wall_budget'; break
                if self.pending_question:
                    question, trigger = self.pending_question, self.pending_question_trigger or 'runtime'
                    self.pending_question, self.pending_question_trigger = None, None
                    self.last_feedback = self._consult(question, trigger)
                    if self.counts['model_requests'] >= self.config.max_turns:
                        break
                try:
                    raw = self._ask('action')
                    if time.monotonic() >= self.deadline:
                        stop = 'wall_budget'; break
                    action = parse_action(raw)
                    self._record_memory_reconsideration(action)
                    intervention = self._memory_push(action)
                    if intervention:
                        self.pending_memory_intervention = intervention
                        self.pending_memory_proposal = intervention
                        self.last_feedback = {'memory_intervention_id':intervention['id'],
                            'instruction':intervention['instruction']}
                        self._emit('memory_intervention', **intervention)
                        self.history.append({'action':'memory_intervention',
                            'detail':clip(json.dumps(intervention,ensure_ascii=False),1800),
                            'response':self.last_feedback})
                        self.history = self.history[-6:]
                        consecutive_errors = 0
                        continue
                    self._optional_memory(action)
                    kind = action['action']
                    if kind != 'run':
                        # The revised decision itself is observable, but a
                        # consult/checkpoint/restore/submit is not a tool result.
                        # Consume the chain now so it cannot leak onto a later run.
                        self._consume_memory_followup(kind, outcome_observed=False)
                    if kind == 'run':
                        self.last_feedback = self._run_command(action)
                    elif kind == 'consult':
                        self.last_feedback = self._consult(action['question'], 'main_requested')
                    elif kind == 'checkpoint':
                        cid = self._checkpoint(action['label'], action['hypothesis'])
                        self.last_feedback = dict(checkpoint_id=cid)
                    elif kind == 'restore':
                        target = self.checkpoints.get(action['checkpoint_id'])
                        if target is None:
                            raise ValueError('unknown or retired checkpoint')
                        # Preserve the current attempt before switching. Capacity
                        # failure refuses the switch rather than losing work.
                        source = self._checkpoint('before restore', action['reason'], pin=target['id'])
                        self.environment.restore(target['record'])
                        self.anchor = target['id']
                        edge = dict(source=source, target=self.anchor, reason=action['reason'])
                        self.edges.append(edge)
                        self.counts['branch_restores'] += 1
                        self.failure_streak, self.failure_signature = 0, None
                        self.diagnostic_streak = 0
                        self.last_feedback = dict(restored=self.anchor,
                            instruction='Files restored. Old observations are historical; check applicability.')
                        self._emit('restore', **edge)
                        self.log.save('graph.json', dict(nodes=self.graph, edges=self.edges, current=self.anchor))
                    else:
                        artifact = self.environment.delivery()
                        self.counts['submissions'] += 1
                        self._emit('submission', artifact=artifact, summary=action['summary'])
                        feedback = self.feedback(artifact) if self.feedback else None
                        if feedback is None:
                            submitted, stop = True, 'model_submit'
                            accepted_artifact = artifact
                            break
                        self.last_feedback = dict(submission_feedback=clip(str(feedback), 2400))
                        self._emit('submission_feedback', **self.last_feedback)
                    consecutive_errors = 0
                    self.history.append(dict(action=kind, detail=clip(json.dumps(action, ensure_ascii=False), 1400),
                                             response=self.last_feedback if kind != 'run' else dict(evidence_id='E'+str(self.counts['tool_calls']))))
                    self.history = self.history[-6:]
                except ValueError as error:
                    consecutive_errors += 1
                    self.counts['protocol_errors'] += 1
                    self.last_feedback = dict(protocol_error=str(error), instruction='Correct the action; previous files remain available.')
                    self._emit('protocol_error', **self.last_feedback)
                except ModelCallError:
                    consecutive_errors += 1
                    if any(self._fatal_provider_error(c) for c in self.clients.values()):
                        stop = 'credential_or_balance_error'; break
                    self.last_feedback = dict(model_error='Previous model call failed; no command executed.')
                if consecutive_errors >= self.config.max_consecutive_errors:
                    stop = 'model_or_protocol_error_limit'; break
        except TimeoutError:
            stop = 'wall_budget' if time.monotonic() >= self.deadline else 'request_or_tool_budget'
        except ModelCallError:
            stop = ('credential_or_balance_error' if any(self._fatal_provider_error(c)
                    for c in self.clients.values()) else 'model_error')
        except Exception as error:
            stop, error_type = 'infrastructure_error', type(error).__name__
            self._emit('infrastructure_error', error_type=error_type)
        artifact = accepted_artifact
        try:
            if artifact is None:
                artifact = self.environment.delivery()
        except Exception as error:
            stop, error_type = 'delivery_error', type(error).__name__
            self._emit('delivery_error', error_type=error_type)
        utilization = dict(self.counts)
        utilization.update(memory_exposure_is_not_benefit=True, memory_use_is_self_report=True)
        usage = {role: c.usage_summary() for role,c in self.clients.items() if callable(getattr(c, 'usage_summary', None))}
        result = dict(version='bestfgs-lean-v18.1', task_id=task.task_id, submitted=submitted,
            stop_reason=stop, artifact=artifact, official_success=None, error_type=error_type,
            interaction_rounds=self.counts['model_requests'], action_rounds=self.counts['action_calls'],
            advisor_rounds=self.counts['advisor_calls'], tool_calls=self.counts['tool_calls'],
            wall_seconds=time.monotonic()-started, model_usage=usage,
            mechanism_utilization=utilization, time_by_role=dict(self.timings),
            contextual_tool_redundancy={'status':'requires_independent_audit','rate':None,
                                       'denominator':self.counts['tool_calls']})
        self._emit('method_end', result=result)
        self.log.save('result.json', result)
        self.log.save('memories.json', list(self.memory.items.values()))
        return result
