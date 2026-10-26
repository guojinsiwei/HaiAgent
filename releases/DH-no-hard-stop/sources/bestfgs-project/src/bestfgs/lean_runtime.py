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
import traceback

from .lean_audit import Recorder, digest
from .lean_memory import Memories
from .lean_conversation import Conversation
from .lean_progress import DeliveryProgress
from .lean_protocol import LeanConfig, ACTION_SYSTEM, ADVISOR_SYSTEM, parse_action, text, validate_evidence_ids
from .models import ModelCallError
from .response_repair import REPAIRABLE_OUTPUT, repair_feedback
from .lean_monitor import SemanticHooks, MONITOR_SYSTEM
from .memory_events import MemoryEvents, dependency_paths
from .lean_memory import action_key
from .prompt_views import classify, diagnostic_category, compress_stream, clip
from .stagnation_control import StagnationControl, CONTROL_INSTRUCTION
from .tool_outcomes import assess
from .route_selection import RouteSelection, ROUTE_INSTRUCTION
from .memory_injection import MEMORY_INSTRUCTION, reserved_view, remove_goal_duplicates, tail_order, validate_review, review_repair_feedback
from .terminal_text import project_terminal
from .advisor_handover import build_handover
from .contrastive_exploration import ContrastiveExploration
from .action_loop import ActionLoopGuard
from .recovery_clock import recovery_steps
from .rejection_recovery import RejectionRecovery
from .targeted_diagnostics import diagnostic_plan
from .lean_progress import normalize_workspace_path
from .subgoals import SubgoalHooks, SUBGOAL_INSTRUCTION
from .context_budget import ContextBudgetError


class LeanTaskRunner(SubgoalHooks, SemanticHooks, MemoryEvents, StagnationControl, RouteSelection, ContrastiveExploration):
    def __init__(self, environment, action_client, advisor_client, config=None,
                 output=None, submission_feedback=None, secrets=(), *, monitor_client=None):
        action_transport = getattr(action_client, 'inner', action_client)
        advisor_transport = getattr(advisor_client, 'inner', advisor_client)
        if action_transport is advisor_transport:
            raise ValueError('action and advisor must have independent client instances')
        self.environment = environment
        self.clients = {'action': action_client, 'advisor': advisor_client}
        if monitor_client is not None:
            monitor_transport = getattr(monitor_client, 'inner', monitor_client)
            if any(monitor_transport is getattr(c, 'inner', c) for c in self.clients.values()):
                raise ValueError('monitor must have an independent client instance')
            self.clients['monitor'] = monitor_client
        self.config = config or LeanConfig()
        self.environment.outcome_reliability = self.config.outcome_reliability
        if (self.config.semantic_monitor or self.config.auto_memory) and monitor_client is None:
            raise ValueError('enabled semantic features require a monitor client')
        self.output = Path(output) if output else None
        if self.output is None:
            raise ValueError('audit output directory is required')
        self.feedback = submission_feedback
        keys = tuple(getattr(getattr(c, 'config', None), 'api_key', '') for c in self.clients.values())
        self.secrets = tuple(secrets) + keys
        self._used = False

    def _emit(self, event, **fields):
        return self.log.emit(event, **fields)

    def _panel(self, question='', context_budget=None):
        scope = self.environment.scope()
        recent = [self.evidence[key] for key in list(self.evidence)[-6:]]
        query = question or (recent[-1]['purpose'] if recent else self.task.goal)
        if self.config.memory_reliability:
            query = self._memory_query(question, recent)
        tracked = sorted(set(self.memory.dependency_targets()).union(self.progress.paths))
        if self.subgoals is not None:
            tracked = sorted(set(tracked).union(self.subgoals.targets()))
        dependencies = self.environment.dependency_state(tracked)
        memories = self.memory.recall(query, scope, dependencies)
        if self.config.memory_injection and self.pending_memory_intervention:
            # A reconsideration must not lose the particular memory that caused
            # it merely because the generic query ranks other records higher.
            urgent = [dict(m, applicability=(self.memory.applicability(m, scope, dependencies)
                if 'evidence_scopes' in m else 'historical_recheck_required'))
                for m in self.pending_memory_intervention.get('matched_memories', [])]
            urgent_ids = {m['id'] for m in urgent}
            memories = list(urgent) + [m for m in memories if m['id'] not in urgent_ids]
        retrieved_ids = [m['id'] for m in memories]
        memory_omitted = []
        if self.config.memory_injection and self.config.memory_enabled:
            memories, memory_omitted = reserved_view(memories, self.config.memory_reserve_chars,
                byte_budget=getattr(self,'final_context_projection',False))
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
            memory_mode=dict(storage=self.config.memory_enabled,
                             decision_intervention=self.config.memory_decision and self.config.memory_enabled,
                             instruction='Do not propose memory fields when storage is disabled.'),
            checkpoints=[dict(id=k, label=v['label'], hypothesis=v['hypothesis'],
                              fingerprint=v['record']['fingerprint']) for k,v in self.checkpoints.items()],
            budgets=dict(model_requests=self.config.max_turns-self.counts['model_requests'],
                         tools=self.config.max_tools-self.counts['tool_calls'],
                         advisor_calls=self.config.max_advisor_calls-self.counts['advisor_calls'],
                         wall_seconds=max(0, round(self.deadline-time.monotonic(), 2))),
            feedback=self.last_feedback)
        if self.subgoals is not None:
            self.subgoals.sync(scope, dependencies)
            panel['subgoals'] = self.subgoals.view()
        if self.config.memory_reliability:
            panel['memory_reliability'] = dict(enabled=True, notices=self.memory_notices,
                instruction='Observed outcomes are historical facts, not causal rules. Recheck changed dependencies.')
        if self.config.semantic_monitor and self.monitor_review:
            panel['semantic_review'] = dict(self.monitor_review, applicability=(
                'same_workspace_external_state_unverified' if scope == self.monitor_review['reviewed_workspace']
                else 'historical_workspace_changed_recheck_required'))
        if self.config.stagnation_control:
            panel['recovery'] = self.control_view()
        if self.config.route_search:
            panel['route_search'] = self.route_view()
            panel['route_memory'] = self.route_memory_view()
        contrastive = self._contrastive_context(scope, dependencies)
        if contrastive is not None:
            panel['contrastive_exploration'] = contrastive
            panel['rejection_recovery'] = self.rejection_recovery.view()
        payload = dict(task=asdict(self.task), fixed_context=panel, recent_decisions=self.history[-6:])
        if self.config.memory_injection:
            remove_goal_duplicates(payload)
            if panel['memory_intervention']:
                intervention = dict(panel['memory_intervention'])
                intervention['matched_memory_ids'] = [m['id'] for m in intervention.pop('matched_memories', [])]
                intervention['memory_records_ref'] = 'fixed_context.memories at the end of this request'
                panel['memory_intervention'] = intervention
            panel['memory_budget'] = dict(reserved_chars=self.config.memory_reserve_chars,
                retrieved_ids=retrieved_ids, omitted_ids=memory_omitted,
                policy='protected whole memory views; trim observations, never silently remove memories')
            if getattr(self,'final_context_projection',False):
                panel['memory_budget']['reserved_bytes']=panel['memory_budget'].pop('reserved_chars')
            tail_order(payload, self.config.memory_decision and self.config.memory_enabled)
        if question:
            payload['question'] = question
        # Shrink the oldest observations/decisions first. Never truncate task
        # instructions, JSON structure, or the latest feedback silently.
        while (not getattr(self,'final_context_projection',False) and
               len(json.dumps(payload, ensure_ascii=False)) > (context_budget or self.config.context_chars)):
            if payload['recent_decisions']:
                payload['recent_decisions'].pop(0)
            elif len(panel['evidence']) > 1:
                panel['evidence'].pop(0)
            elif panel['memories'] and not self.config.memory_injection:
                panel['memories'].pop()
            elif self.config.memory_injection and panel['evidence'] and any(
                    len(panel['evidence'][0].get(k, '')) > 300 for k in ('stdout', 'stderr')):
                row = dict(panel['evidence'][0])
                row['prompt_view_partial'] = True
                for key in ('stdout', 'stderr'):
                    if len(row.get(key, '')) > 300:
                        row[key] = clip(row[key], 300)
                panel['evidence'][0] = row
            else:
                if getattr(self,'final_context_projection',False):break
                if len(json.dumps(payload, ensure_ascii=False)) > self.config.context_chars - len(ACTION_SYSTEM) - 2000:
                    raise ValueError('task and protected context exceed configured context budget')
                break
        self.visible_evidence = {e['id'] for e in panel['evidence']}
        self.visible_memories = {m['id'] for m in panel['memories']}
        self.visible_memory_records = {m['id']:m for m in panel['memories']}
        if self.config.memory_reliability:
            self._emit('memory_retrieval', query=query, selected_ids=sorted(self.visible_memories),
                retrieved_ids=retrieved_ids, reserve_omitted_ids=memory_omitted,
                available=len(self.memory.items), applicability={m['id']:m['applicability'] for m in panel['memories']})
        return payload

    @staticmethod
    def _action_core(action):
        return {key:value for key,value in action.items() if key not in {
            'memory','uses_memory','memory_reason','memory_review','strategy_adjustment','contrastive',
            'subgoal_plan','subgoal_id','subgoal_phase','subgoal_update'}}

    def _memory_push(self, action):
        if not self.config.memory_enabled or not self.config.memory_decision:
            return None
        if (action.get('action') != 'run' or
                self.counts['memory_interventions'] >= self.config.max_memory_interventions):
            return None
        scope = self.last_panel_scope
        dependencies = self.last_panel_dependencies
        matches = self.memory.match_action(action, scope, dependencies)
        acknowledged = {m for m in action.get('uses_memory', []) if isinstance(m,str)} if isinstance(action.get('uses_memory'), list) else set()
        if self.config.memory_reliability:
            reason=action.get('memory_reason','')
            if not isinstance(reason,str) or not 1<=len(reason.strip())<=400:
                acknowledged=set()
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

    def _role_system(self, role):
        return {'action': ACTION_SYSTEM, 'advisor': ADVISOR_SYSTEM, 'monitor': MONITOR_SYSTEM}[role]

    def _before_submit(self, action):
        return None

    def _protocol_feedback(self, raw, error):
        return None

    def _prepare_context(self, role, system, payload):
        return payload

    def _ask(self, role, question='', payload_override=None):
        if self.counts['model_requests'] >= self.config.max_turns or time.monotonic() >= self.deadline:
            raise TimeoutError('model budget exhausted')
        system = self._role_system(role)
        if role == 'action' and self.subgoals is not None:
            system += '\n' + SUBGOAL_INSTRUCTION
        if role == 'action' and self.config.memory_injection and self.config.memory_enabled and self.config.memory_decision:
            system += '\n' + MEMORY_INSTRUCTION
        if role=='action' and self.config.stagnation_control:
            system += '\n'+(ROUTE_INSTRUCTION if self.config.route_search else CONTROL_INSTRUCTION)
        if role == 'action' and self.config.contrastive_mode != 'off':
            system += '\n' + self._contrastive_instruction()
            system += ('\nThe rejection_recovery panel counts unresolved rejections across gates. '
                f'After {self.config.rejection_recovery_limit} rejections the advisor is consulted once; '
                'further rejections do not terminate the task or grant additional advisor calls. '
                'The original request, tool and wall-clock budgets still apply. '
                'Rephrasing, listings, checkpoints and '
                'consultations do not reset it. A related file/dependency/configuration change '
                'or new targeted evidence can reset it. Role and total budgets still apply.')
        payload = (payload_override if payload_override is not None else
            self._panel(question, self.config.context_chars//2 if role == 'action' and self.conversation.turns else None))
        history_messages, conversation_view = [], None
        client_config = getattr(self.clients[role], 'config', None)
        output_limit = getattr(client_config, 'max_tokens', None)
        if role != 'monitor' and type(output_limit) is int and output_limit > 0:
            payload['response_limits'] = dict(max_output_tokens=output_limit,
                instruction='One compact complete JSON object; split long edits across actions.')
        if role == 'action':
            payload['conversation'] = dict(total_turns=len(self.conversation.turns),
                policy='budgeted full dialogue plus explicit older excerpts; use recall_history for originals')
            self.action_context = (dict(advice=self.advice) if self.advice and
                self.advice.get('id') != self.last_archived_advice_id else {})
        payload = self.log.clean(payload)
        if role != 'monitor' and self.config.memory_injection:
            tail_order(payload, role == 'action' and self.config.memory_enabled and self.config.memory_decision)
        payload = self._prepare_context(role, system, payload)
        if role == 'action':
            history_messages, conversation_view = self.conversation.build(system, payload, self.config.context_chars-1024)
            conversation_view['wire_retry_reserved_chars'] = 1024
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
        exposed = self.visible_memories if role != 'monitor' else set()
        self.counts['memory_exposures'] += len(exposed)
        if exposed:
            self.counts['requests_with_memory'] += 1
        self._emit('model_request', role=role, payload=payload,
                   memory_ids=sorted(exposed), history_messages=history_messages,
                   conversation_view=conversation_view)
        started = time.monotonic()
        # Transport hook records EVERY wire attempt, including format-repair retries.
        # Never records Authorization headers, endpoints, or the API credential.
        old_audit = getattr(transport, 'request_audit', None)
        if hasattr(transport, 'request_audit'):
            transport.request_audit = lambda body, attempt: self._emit(
                'wire_prompt', role=role, logical_request=self.counts['model_requests'],
                attempt=attempt, request_body=body)
        try:
            options = dict(history_messages=history_messages) if role == 'action' else {}
            self._emit('final_prompt', role=role, transport_attempts_logged=hasattr(transport, 'request_audit'),
                messages=[dict(role='system', content=system), *history_messages,
                          dict(role='user', content=json.dumps(payload, ensure_ascii=False))],
                memory_ids=sorted(exposed))
            response = client.complete_json(system_prompt=system,
                user_prompt=json.dumps(payload, ensure_ascii=False), **options)
            self._emit('model_response', role=role, response=response,
                       response_key_order=list(response) if isinstance(response, dict) else [])
            return response
        except ModelCallError:
            self._emit('model_error', role=role,
                error_code=getattr(client, 'last_failure_detail', None),
                failure_kind=getattr(client, 'last_failure_kind', None))
            raise
        finally:
            if hasattr(transport, 'request_audit'):
                transport.request_audit = old_audit
            self.timings[role] += time.monotonic()-started
            if old is not None:
                transport.config = old

    def _fatal_provider_error(self, client):
        return getattr(client, 'last_failure_detail', '') in {
            'http_401', 'http_402', 'http_403', 'provider_401', 'provider_402', 'provider_403'}

    def _record_turn(self, action, feedback):
        self.subgoal_attempt = None
        if self.config.contrastive_mode != 'off':
            sources = [key for key in ('action_loop', 'contrastive_rejection',
                'memory_blocker_ids', 'memory_intervention') if feedback.get(key)]
            if sources and self.rejection_recovery.generation == self.recovery_generation_at_action:
                self.rejection_recovery.reject(self.rejection_dependencies)
                self.counts['recovery_rejected_turns'] += 1
                self._emit('recovery_rejection', sources=sources, **self.rejection_recovery.view())
        turn = self.conversation.append(self.log.clean(action), self.log.clean(feedback),
                                        self.log.clean(self.action_context))
        if self.action_context.get('advice'):
            self.last_archived_advice_id = self.action_context['advice']['id']
        self.action_context = {}
        self._emit('conversation_turn', **turn)

    def _consult(self, question, trigger, *, recovery=False):
        report = self.log.clean(build_handover(self,question,trigger))
        report['id'] = 'H' + str(self.log.sequence+1)
        self._emit('advisor_handover',report=report)
        self.log.save('handover-'+report['id']+'.json',report)
        self.log.save('latest-handover.json',report)
        advisor_limit = self.config.max_advisor_calls
        if (self.config.contrastive_mode != 'off' and not recovery
                and not self.counts['recovery_advisor_attempts']):
            advisor_limit = max(0, advisor_limit - 1)  # Keep one existing slot for the first seven-rejection rescue.
        if (self.counts['advisor_calls'] >= advisor_limit or
                (not recovery and recovery_steps(self)-self.last_advisor_recovery_step < self.config.advisor_cooldown_tools)):
            self._emit('advisor_skipped', reason='capacity_or_cooldown', trigger=trigger)
            return dict(advisor='unavailable_this_turn', instruction='Continue or submit using available evidence.')
        self.last_advisor_tool = self.counts['tool_calls']
        self.last_advisor_recovery_step = recovery_steps(self)
        self._emit('advisor_trigger', trigger=trigger, question=question)
        try:
            reserve = len(json.dumps(report,ensure_ascii=False)) + len(ADVISOR_SYSTEM) + 1280
            payload = self._panel(question,self.config.context_chars-reserve)
            payload['handover_report'] = report
            if (not getattr(self,'final_context_projection',False) and
                len(json.dumps(payload,ensure_ascii=False)) + len(ADVISOR_SYSTEM) + 1024 > self.config.context_chars):
                raise ValueError('protected advisor context plus handover exceeds configured budget')
            self.visible_evidence.update(report['advertised_evidence_ids'])
            response = self._ask('advisor', question, payload_override=payload)
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
        if not self.config.memory_enabled:
            if 'memory' in action:
                self._emit('memory_disabled', origin='actor')
            return
        if 'memory' in action:
            self._emit('memory_candidate', candidate=action['memory'], origin='actor')
            try:
                item, added = self.memory.admit(action['memory'], self.evidence, self.visible_evidence,
                                                self.environment.dependency_state, current_scope=self.last_panel_scope)
                self._memory_audit_admission(item,added,'actor')
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
                if self.config.memory_reliability and self.pending_memory_outcome is None:
                    self.pending_memory_outcome=dict(intervention_id=None,memory_ids=accepted,
                        proposed_action=self._action_core(action),revised_action=self._action_core(action),changed=False)
                    self._emit('memory_use_reason',memory_ids=accepted,
                        reason=clip(str(action.get('memory_reason','')),400),verified=False)
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
            if self.config.memory_reliability:
                repeated=[mid for mid in memory_chain['memory_ids'] if mid in self.memory.items
                    and self.memory.items[mid].get('outcome_key')==outcome.get('outcome_key')
                    and self.memory.items[mid].get('command_key')==outcome.get('command_key')]
                if repeated and not outcome.get('succeeded') and not outcome.get('workspace_changed'):
                    self.monitor_event='memory_retry_same_observed_failure'
                    self._emit('memory_retry_no_new_outcome',memory_ids=repeated,
                        causal_benefit_proven=False,requires_semantic_review=True)
        self._emit('memory_followup_outcome', **memory_chain, action_kind=action_kind,
                   causal_benefit_proven=False, **outcome)

    def _related_paths(self, action):
        paths = dependency_paths(action)
        declared = getattr(self.environment, 'contrastive_dependencies', None)
        if callable(declared):
            paths += declared(action)
        for anchor in self.contrastive_failures:
            if anchor['command_key'] == action_key(action):
                paths += list(anchor['dependencies'])
        for memory in self.memory.items.values():
            if memory.get('command_key') == action_key(action):
                paths += memory['targets']
        paths += self.action_loop.tracked_paths(action)
        return list(dict.fromkeys(paths))[:32]

    def _run_command(self, action, *, diagnostic=False):
        if self.counts['tool_calls'] >= self.config.max_tools:
            raise TimeoutError('tool budget exhausted')
        if time.monotonic() >= self.deadline:
            raise TimeoutError('work budget exhausted')
        action = dict(action, timeout_seconds=min(action.get('timeout_seconds', 60), self.config.command_seconds))
        related_paths = self._related_paths(action) if self.config.contrastive_mode != 'off' else []
        if diagnostic:
            related_paths = list(dict.fromkeys(related_paths + list(self.rejection_recovery.targets)))
        tracked=list(self.memory.dependency_targets())
        if self.config.contrastive_mode != 'off':
            tracked += list(self.rejection_recovery.targets)
        if self.config.route_search:
            tracked=self._route_targets()+tracked
        if self.config.stagnation_control and self.recovery and self.recovery['plan']:
            tracked=self.recovery['plan']['targets']+tracked
        paths=dependency_paths(action,tracked) if self.config.memory_reliability or self.config.stagnation_control else []
        # Optional public executor dependency manifest, not an inferred oracle.
        # This is file inspection, not an uncounted task command.
        if self.config.contrastive_mode != 'off' and callable(getattr(self.environment, 'contrastive_dependencies', None)):
            paths = list(dict.fromkeys(paths + self.environment.contrastive_dependencies(action)))[:16]
        paths = list(dict.fromkeys(paths + related_paths + list(self.rejection_recovery.targets)))[:64]
        if self.subgoals is not None:
            paths = list(dict.fromkeys(paths + self.subgoals.targets()))
        def observe():
            if paths and callable(getattr(self.environment,'observe_state',None)):
                return self.environment.observe_state(paths)
            return self.environment.scope(), self.environment.dependency_state(paths) if paths else {}
        before,dependency_before=observe()
        # Run this after all memory/contrastive/controller decisions, directly
        # before dispatch. Rejections consume a model request, never a tool.
        if self.config.contrastive_mode != 'off':
            blocked = self.action_loop.check(action, before, dependency_before)
            if blocked:
                self.contrastive_pending = None
                self.counts['action_loop_blocks'] += 1
                self._emit('action_loop_block', command=self._action_core(action), **blocked)
                # A cached harness diagnostic must not recursively start another
                # exploration episode and regenerate the identical diagnostic.
                if not diagnostic:
                    self._contrastive_activate('unchanged_action_loop')
                return dict(not_executed=True, action_loop=blocked)
        started = time.monotonic()
        self.counts['tool_calls'] += 1
        self._emit('tool_attempt', call_id=self.counts['tool_calls'], command=action, before=before)
        result = self.environment.execute(action, self.deadline)
        readable_stdout, stdout_view = project_terminal(result.stdout)
        readable_stderr, stderr_view = project_terminal(result.stderr)
        assessment = assess(result)
        clean = assessment['execution_clean'] if self.config.outcome_reliability else result.succeeded
        self.timings['tools'] += time.monotonic()-started
        after,dependency_after=observe()
        if self.config.contrastive_mode != 'off' and not clean:
            # A traceback often identifies imported source absent from argv.
            # Observe those files so editing that source permits the old test.
            error_targets = diagnostic_plan([dict(dependencies={},
                observation=(readable_stderr+'\n'+readable_stdout)[:6000])])['files']
            discovered = []
            for target in error_targets:
                try:
                    if Path(target).is_absolute() and not target.startswith('/app/'):
                        workspace = getattr(self.environment, 'workspace', None)
                        if workspace is None:
                            continue
                        target = Path(target).resolve().relative_to(Path(workspace).resolve()).as_posix()
                    path = normalize_workspace_path(target)
                except ValueError:
                    continue
                if path not in related_paths:
                    discovered.append(path)
            discovered = list(dict.fromkeys(discovered))[:8]
            if discovered:
                dependency_after.update(self.environment.dependency_state(discovered))
                for path in discovered:
                    dependency_before.setdefault(path, dependency_after[path] if before == after else 'unknown')
                paths += [p for p in discovered if p not in paths]
                related_paths += discovered
        stable={p:dependency_after[p] if dependency_before.get(p)==dependency_after.get(p)
                and not dependency_after[p].startswith('link:') else 'unknown' for p in paths}
        raw_outcome_key=digest([result.return_code,result.stdout,result.stderr,result.timed_out,result.blocked])
        outcome_key=digest([result.return_code,readable_stdout,readable_stderr,result.timed_out,result.blocked])
        self._consume_memory_followup('run', outcome_observed=True, succeeded=clean,
            process_succeeded=result.succeeded,check_status=assessment['check_status'],
            workspace_changed=before != after, timed_out=result.timed_out, blocked=result.blocked,
            outcome_key=outcome_key,command_key=action_key(action))
        eid = 'E' + str(self.counts['tool_calls'])
        category = classify(action['argv'])
        if action.get('_native_tool',{}).get('tool')=='inspect_code':
            category = 'search' if action['_native_tool']['mode']=='search' else 'read'
        view = dict(id=eid, argv=clip(json.dumps(action['argv'], ensure_ascii=False), 1800),
            purpose=clip(str(action.get('purpose', '')), 400), before=before, after=after,
            return_code=result.return_code, timed_out=result.timed_out, blocked=result.blocked,
            stdout=compress_stream(result.stdout, category, 2200),
            stderr=compress_stream(result.stderr, category, 1600),
            capture_incomplete=result.output_truncated, category=category,cwd=action.get('cwd','.'),
            terminal_projection=dict(stdout=stdout_view,stderr=stderr_view),
            terminal_projection_incomplete=stdout_view['incomplete'] or stderr_view['incomplete'],
            raw_outcome_key=raw_outcome_key,outcome_identity='readable-terminal-v1')
        self._emit('terminal_projection',evidence_id=eid,stdout=stdout_view,stderr=stderr_view,
            raw_stdout_sha256=hashlib.sha256(result.stdout.encode()).hexdigest(),
            raw_stderr_sha256=hashlib.sha256(result.stderr.encode()).hexdigest())
        if self.config.memory_reliability or self.config.stagnation_control:
            view.update(stable_dependencies=stable,dependency_before=dependency_before,dependency_after=dependency_after,
                dependency_coverage='selected_paths_only_external_and_dynamic_dependencies_unknown',
                command_key=action_key(action),outcome_key=outcome_key)
        if self.config.outcome_reliability:
            view['execution_assessment']=assessment
            self._emit('execution_assessment',evidence_id=eid,**assessment)
        view['relevant_dependencies'] = {p: dependency_after.get(p, 'unknown') for p in related_paths}
        self.evidence[eid] = view
        self._subgoal_outcome(action, dict(view, stdout=readable_stdout,
            dependency_before=dependency_before, dependency_after=dependency_after), assessment,
            diagnostic=diagnostic)
        if self.config.contrastive_mode != 'off':
            self.action_loop.observe(action, view)
            informative = (diagnostic_category(action['argv']) in {'read', 'search', 'diff'}
                           or category in {'test', 'build'}
                           or action.get('_native_tool',{}).get('tool')=='inspect_code')
            if diagnostic:
                try:
                    information = json.loads(readable_stdout)
                    informative = information.get('kind') == 'targeted_diagnostic' and bool(information.get('excerpts'))
                except (ValueError, AttributeError):
                    informative = False
            progress = self.rejection_recovery.observe(view, informative=informative)
            if progress:
                self.counts['recovery_progress_resets'] += 1
                self._emit('recovery_progress', **progress)
        self._observe_memory_event(action,view)
        self._monitor_tool_outcome(view)
        self._control_outcome(action, view, assessment)
        self.last_tool_observation = dict(evidence=dict(view, stdout=readable_stdout, stderr=readable_stderr,
            view='Readable captured output, not a terminal emulation. Originals: tool_call.result; capture_incomplete remains authoritative.'))
        # Raw observations remain in the audit, not all in the hot prompt/store.
        while len(self.evidence) > 48:
            self.evidence.popitem(last=False)
        signature = digest(dict(command_key=action_key(action),
                                before=before, after=after, stdout=readable_stdout, stderr=readable_stderr,
                                exit=result.return_code, timeout=result.timed_out, blocked=result.blocked))
        repeated = not clean and not result.output_truncated and not view['terminal_projection_incomplete'] and before == after
        self.failure_streak = self.failure_streak + 1 if repeated and signature == self.failure_signature else int(repeated)
        self.failure_signature = signature
        diagnostic_kind = diagnostic_category(action['argv'])
        if action.get('_native_tool',{}).get('tool')=='inspect_code':diagnostic_kind=category
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
        self._contrastive_outcome(action, dict(view, stdout=readable_stdout, stderr=readable_stderr), assessment)
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
            'memory_followup_workspace_changed','post_advice_actions',
            'monitor_calls','monitor_reviews_accepted','monitor_deferred','semantic_stalls',
            'auto_memory_candidates','auto_memories_admitted','auto_memories_rejected','observed_memories_admitted',
            'recovery_started','recovery_plans','recovery_verified_repairs','recovery_checked_hypotheses','recovery_failed')})
        self.memory = Memories(self.config.max_memories,reliable=self.config.memory_reliability)
        self.progress = DeliveryProgress(task, self.environment)
        self._init_subgoals()
        self.evidence, self.checkpoints = OrderedDict(), OrderedDict()
        self.graph, self.edges, self.history = [], [], []
        self.conversation = Conversation()
        self.action_context, self.last_archived_advice_id = {}, None
        self.anchor = None
        self.advice, self.last_feedback = {}, {}
        self.advice_pending = False
        self.failure_streak, self.failure_signature = 0, None
        self.diagnostic_streak = 0
        self.last_advisor_tool = -self.config.advisor_cooldown_tools
        self.last_advisor_recovery_step = -self.config.advisor_cooldown_tools
        self.pending_question = None
        self.pending_question_trigger = None
        self.pending_memory_intervention = None
        self.pending_memory_proposal = None
        self.memory_intervention_signatures = set()
        self.last_intervention_memory_ids = set()
        self.pending_memory_outcome = None
        self.visible_evidence, self.visible_memories = set(), set()
        self._init_monitor()
        self._init_memory_events()
        self._init_control()
        self._init_routes()
        self._init_contrastive()
        self.action_loop = ActionLoopGuard()
        self.rejection_recovery = RejectionRecovery(self.config.rejection_recovery_limit)
        self.recovery_generation_at_action = 0
        self.rejection_dependencies = {}
        started = time.monotonic()
        self.started_at = started
        self.deadline = started + self.config.wall_seconds
        version = 'DH-v9-recovery-repair' if self.config.contrastive_mode != 'off' else 'bestfgs-memory-injection-v8-engineering-v2' if self.config.memory_injection else (
            'bestfgs-route-selection-v7' if self.config.route_search else 'bestfgs-monitor-control-v6')
        if self.subgoals is not None:
            version = 'DH-subgoal-v1'
        self._emit('header', version=version, task=asdict(task), config=asdict(self.config),
                   success_semantics='requires_external_evaluation',
                   source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(Path(__file__).parent.glob('*.py'))},
                   models={role:{key:getattr(getattr(getattr(c,'inner',c),'config',None),key,None)
                                 for key in ('provider','model_name','temperature','thinking_enabled','max_tokens')}
                           for role,c in self.clients.items()},
                   metric_definitions=dict(interaction_rounds='all actor, advisor and monitor logical requests, including failures; wire attempts audited separately',
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
                if self.rejection_recovery.advisor_due:
                    state = self.rejection_recovery.view()
                    self.rejection_recovery.advisor_started()
                    self.counts['recovery_advisor_attempts'] += 1
                    self.last_feedback = self._consult(
                        'Seven proposals at the same unresolved blockage were rejected. '
                        'Give one concrete next action and the observation that would distinguish it. '
                        'Use cached evidence; do not repeat the same diagnostic. State: '+json.dumps(state),
                        'seven_rejections', recovery=True)
                    self._emit('recovery_advisor_result', feedback=self.last_feedback)
                    self.pending_question = self.pending_question_trigger = None
                    if self.counts['model_requests'] >= self.config.max_turns:
                        break
                self._maybe_monitor()
                if self._route_tick():
                    continue
                if self.pending_question:
                    question, trigger = self.pending_question, self.pending_question_trigger or 'runtime'
                    self.pending_question, self.pending_question_trigger = None, None
                    self.last_feedback = self._consult(question, trigger)
                    if self.counts['model_requests'] >= self.config.max_turns:
                        break
                raw = None
                try:
                    self.recovery_generation_at_action = self.rejection_recovery.generation
                    self.rejection_dependencies = {}
                    raw = self._ask('action')
                    if time.monotonic() >= self.deadline:
                        stop = 'wall_budget'; break
                    action = parse_action(raw)
                    self._subgoal_begin(action)
                    if self.config.contrastive_mode != 'off' and action['action'] == 'run':
                        targets = self._related_paths(action)
                        # Gate changes do not change the unresolved failure's target.
                        targets += [p for a in self.contrastive_visible_anchors for p in a['dependencies']]
                        self.rejection_dependencies = self.environment.dependency_state(list(dict.fromkeys(targets))[:64])
                    review = validate_review(action, self.visible_memories,
                        self.config.memory_injection and self.config.memory_enabled and self.config.memory_decision)
                    gate = self._contrastive_before(action)
                    if gate and gate.get('not_executed'):
                        self.last_feedback = gate
                        self._record_turn(raw, gate)
                        consecutive_errors = 0
                        continue
                    if gate and gate.get('fallback_action'):
                        # Two rejected proposals yield one deterministic, bounded
                        # diagnostic, then return control to the actor.
                        self.last_feedback = self._run_command(gate['fallback_action'], diagnostic=True)
                        self._record_turn(raw, dict(contrastive_rejection=gate['reason'],
                                                   diagnostic=self.last_feedback))
                        consecutive_errors = 0
                        continue
                    if review:
                        # A textual claim of changing route cannot disguise the
                        # exact executable already linked to an applicable blocker.
                        matching = self.memory.match_action(action, self.last_panel_scope,
                            self.last_panel_dependencies)
                        repeated = [m['id'] for m in matching
                            if m.get('command_key') == action_key(action)]
                        if repeated and review['decision'] != 'justified_retry':
                            if self.config.contrastive_mode == 'off':
                                raise ValueError('same executable matches an applicable prior blocker; '
                                    'change the action or supply justified_retry with new_evidence')
                            self.contrastive_pending = None
                            self.last_feedback = dict(not_executed=True, memory_blocker_ids=repeated,
                                instruction='Same executable matches an applicable prior blocker; '
                                    'change the action or supply justified_retry with new_evidence.')
                            self._emit('memory_action_rejected', **self.last_feedback)
                            self._record_turn(raw, self.last_feedback)
                            consecutive_errors = 0
                            continue
                        self._emit('memory_decision_review', review=review,
                                   strategy_adjustment=action['strategy_adjustment'], verified=False,
                                   causal_benefit_proven=False)
                    recovery_feedback = self._control_before(action)
                    if recovery_feedback:
                        self.last_feedback=recovery_feedback
                        self._record_turn(raw,recovery_feedback)
                        consecutive_errors=0
                        continue
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
                        self._record_turn(raw, dict(not_executed=True, memory_intervention=intervention))
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
                        self.monitor_event = 'checkpoint_created'
                    elif kind == 'recall_history':
                        self.last_feedback = self.conversation.retrieve(action)
                        self._emit('history_retrieval', request=action, result=self.last_feedback)
                    elif kind == 'restore':
                        target = self.checkpoints.get(action['checkpoint_id'])
                        if target is None:
                            raise ValueError('unknown or retired checkpoint')
                        # Preserve the current attempt before switching. Capacity
                        # failure refuses the switch rather than losing work.
                        source = self._checkpoint('before restore', action['reason'], pin=target['id'])
                        self.environment.restore(target['record'])
                        if self.subgoals is not None:
                            self.subgoals.sync(self.environment.scope(), {}, restored=True)
                        self.anchor = target['id']
                        edge = dict(source=source, target=self.anchor, reason=action['reason'])
                        self.edges.append(edge)
                        self.counts['branch_restores'] += 1
                        self.failure_streak, self.failure_signature = 0, None
                        self.diagnostic_streak = 0
                        self.monitor_event = 'branch_restored'
                        self.monitor_review = {}
                        self.last_feedback = dict(restored=self.anchor,
                            instruction='Files restored. Old observations are historical; check applicability.')
                        self._emit('restore', **edge)
                        self.log.save('graph.json', dict(nodes=self.graph, edges=self.edges, current=self.anchor))
                    else:
                        review_feedback = self._before_submit(action)
                        if review_feedback is not None:
                            self.last_feedback = review_feedback
                            self._record_turn(raw, review_feedback)
                            consecutive_errors = 0
                            continue
                        artifact = self.environment.delivery()
                        self.counts['submissions'] += 1
                        self._emit('submission', artifact=artifact, summary=action['summary'])
                        feedback = self.feedback(artifact) if self.feedback else None
                        if feedback is None:
                            submitted, stop = True, 'model_submit'
                            accepted_artifact = artifact
                            self._record_turn(raw, dict(submission='delivered', artifact=artifact,
                                                       official_success=None))
                            break
                        self.last_feedback = dict(submission_feedback=clip(str(feedback), 2400))
                        self._emit('submission_feedback', **self.last_feedback)
                    consecutive_errors = 0
                    self.history.append(dict(action=kind, detail=clip(json.dumps(action, ensure_ascii=False), 1400),
                                             response=self.last_feedback if kind != 'run' else dict(evidence_id='E'+str(self.counts['tool_calls']))))
                    self.history = self.history[-6:]
                    self._record_turn(raw, self.last_tool_observation
                        if kind == 'run' and not self.last_feedback.get('not_executed') else self.last_feedback)
                except ValueError as error:
                    consecutive_errors += 1
                    self.counts['protocol_errors'] += 1
                    self.last_feedback = dict(protocol_error=str(error), instruction='Correct the action; previous files remain available.')
                    self._protocol_feedback(raw, error)
                    format_feedback = review_repair_feedback(error)
                    if format_feedback:
                        self.last_feedback.update(format_feedback)
                    self._emit('protocol_error', **self.last_feedback)
                    if raw is not None:
                        self._record_turn(raw, dict(not_executed=True, **self.last_feedback))
                except ModelCallError:
                    consecutive_errors += 1
                    if any(self._fatal_provider_error(self.clients[r]) for r in ('action', 'advisor')):
                        stop = 'credential_or_balance_error'; break
                    client = self.clients['action']
                    detail = getattr(client, 'last_failure_detail', None)
                    self.last_feedback = dict(model_error='Previous model call failed; no command executed.')
                    if detail in REPAIRABLE_OUTPUT:
                        self.last_feedback.update(error_code=detail, instruction=repair_feedback(
                            detail, getattr(getattr(client, 'config', None), 'max_tokens', None)))
                if consecutive_errors >= self.config.max_consecutive_errors:
                    stop = 'model_or_protocol_error_limit'; break
        except ContextBudgetError as error:
            stop, error_type = 'context_budget_error', type(error).__name__
            self.counts['context_budget_errors'] = self.counts.get('context_budget_errors',0)+1
            self._emit('context_budget_failure',error_type=error_type,reason=str(error),
                       model_protocol_error=False,recovery_rejection=False)
        except TimeoutError:
            stop = 'wall_budget' if time.monotonic() >= self.deadline else 'request_or_tool_budget'
        except ModelCallError:
            stop = ('credential_or_balance_error' if any(self._fatal_provider_error(self.clients[r])
                    for r in ('action', 'advisor')) else 'model_error')
        except Exception as error:
            stop, error_type = 'infrastructure_error', type(error).__name__
            self._emit('infrastructure_error', error_type=error_type,
                       error_frames=[dict(file=Path(f.filename).name,line=f.lineno,function=f.name)
                                     for f in traceback.extract_tb(error.__traceback__)[-12:]])
        try:
            self._route_close_on_exit()
        except Exception as error:
            self.counts['route_restore_failures'] += 1
            stop, error_type = 'infrastructure_error', type(error).__name__
            self._emit('route_restore_failed', error_type=error_type,
                       warning='Unable to restore experiment checkpoint; current files are not a selected winner.')
        artifact = accepted_artifact
        try:
            if artifact is None:
                artifact = self.environment.delivery()
        except Exception as error:
            stop, error_type = 'delivery_error', type(error).__name__
            self._emit('delivery_error', error_type=error_type,
                       error_frames=[dict(file=Path(f.filename).name,line=f.lineno,function=f.name)
                                     for f in traceback.extract_tb(error.__traceback__)[-12:]])
        utilization = dict(self.counts)
        if self.subgoals is not None:
            utilization.update({'subgoal_'+k:v for k,v in self.subgoals.stats.items()})
            self.log.save('subgoals.json', self.subgoals.snapshot())
        utilization.update(memory_exposure_is_not_benefit=True, memory_use_is_self_report=True)
        usage = {role: c.usage_summary() for role,c in self.clients.items() if callable(getattr(c, 'usage_summary', None))}
        result = dict(version=version, task_id=task.task_id, submitted=submitted,
            stop_reason=stop, artifact=artifact, official_success=None, error_type=error_type,
            interaction_rounds=self.counts['model_requests'], action_rounds=self.counts['action_calls'],
            advisor_rounds=self.counts['advisor_calls'], monitor_rounds=self.counts['monitor_calls'], tool_calls=self.counts['tool_calls'],
            wall_seconds=time.monotonic()-started, model_usage=usage,
            mechanism_utilization=utilization, time_by_role=dict(self.timings),
            contextual_tool_redundancy={'status':'requires_independent_audit','rate':None,
                                       'denominator':self.counts['tool_calls']})
        if self.subgoals is not None:
            result['subgoal_summary'] = self.subgoals.snapshot()
        self._emit('method_end', result=result)
        self.log.save('result.json', result)
        self.log.save('memories.json', list(self.memory.items.values()))
        return result
