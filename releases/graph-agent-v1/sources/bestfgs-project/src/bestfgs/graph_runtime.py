"""Graph scheduling over the current audited execution/memory/role components."""
from collections import OrderedDict
from copy import deepcopy
from dataclasses import asdict
import time

from .graph_search import (GraphLimits, StateNode, SearchEdge, executable_key,
                          frontier_priority, parse_proposals, GRAPH_ACTION_SYSTEM)
from .lean_audit import digest
from .lean_memory import action_key
from .action_loop import loop_key
from .lean_protocol import LeanConfig
from .lean_runtime import LeanTaskRunner
from .memory_injection import MEMORY_INSTRUCTION, validate_review, review_repair_feedback
from .models import ModelCallError


class SearchLimit(Exception):
    pass


class GraphTaskRunner(LeanTaskRunner):
    runtime_version = 'bestfgs-graph-agent-v1'
    # Budget clocks, task memories and IDs are global. Decision history,
    # failures, advice and unconsumed interventions are branch-local.
    branch_fields = ('conversation', 'history', 'last_feedback',
        'action_context', 'last_archived_advice_id', 'failure_streak',
        'failure_signature', 'diagnostic_streak', 'pending_question',
        'pending_question_trigger', 'monitor_event', 'monitor_review',
        'advice', 'advice_pending', 'pending_memory_intervention',
        'pending_memory_proposal', 'pending_memory_outcome',
        'last_intervention_memory_ids')

    def __init__(self, environment, action_client, advisor_client, config=None,
                 output=None, submission_feedback=None, secrets=(), *,
                 monitor_client=None, graph_limits=None):
        config = config or LeanConfig(memory_reliability=True,
            outcome_reliability=True, semantic_monitor=True, auto_memory=True,
            monitor_reliability=True)
        if config.contrastive_mode != 'off' or config.route_search or config.stagnation_control:
            raise ValueError('graph engine is separate from orthogonal gates and HAI route/control')
        if not config.outcome_reliability or not config.memory_reliability:
            raise ValueError('graph engine requires reliable observations and conditional memory')
        if submission_feedback is not None:
            raise ValueError('graph engine cannot consult an official/hidden grader during solving')
        self.limits = graph_limits or GraphLimits()
        super().__init__(environment, action_client, advisor_client, config, output,
            submission_feedback, secrets, monitor_client=monitor_client)

    def _role_system(self, role):
        return GRAPH_ACTION_SYSTEM if role == 'action' else super()._role_system(role)

    def _memory_instruction(self):
        instruction = MEMORY_INSTRUCTION.replace(
            'FIRST THREE top-level keys in the SAME JSON response',
            'FIRST THREE keys in EACH nested candidate action object').replace(
            'existing top-level string', 'action-object string')
        return instruction + ('\nGraph format clarification: the outer envelope may start with candidates. '
            'The response prefix and examples above apply inside each candidate action object. '
            'A direct consult/recall_history/submit still uses the original top-level review prefix.')

    def _record_turn(self, action, feedback):
        super()._record_turn(action, feedback)
        self._emit('graph_history_link', node=self.current_node,
            branch_turn_id=len(self.conversation.turns), actual_tools=self.counts['tool_calls'])

    def _panel(self, question='', context_budget=None):
        payload = super()._panel(question, context_budget)
        payload['graph_search'] = dict(current_node=self.current_node,
            width=self.limits.width, nodes=len(self.search_nodes),
            pending_edges=sum(e.status=='pending' for e in self.search_edges.values()),
            snapshot_scope='workspace_files_only; processes/network/external state NOT restored',
            proposals_are_siblings=True, controller_selects=True,
            memory_scope='one task, shared conditionally across branches',
            node_evidence_scope='current branch ancestry, not other branches as current facts')
        return payload

    def _capture_runtime(self):
        return {name:deepcopy(getattr(self, name)) for name in self.branch_fields}

    def _save_current(self):
        if self.current_node:
            self.search_nodes[self.current_node].runtime = self._capture_runtime()

    def _activate(self, identifier, *, save_current=True):
        if self.current_node == identifier:
            return
        if save_current:
            self._save_current()
        node = self.search_nodes[identifier]
        source = self.current_node
        before = self.environment.scope()
        if before != node.scope:
            self.environment.restore(node.record)
            if self.environment.scope() != node.scope:
                raise RuntimeError('graph source restoration fingerprint mismatch')
            self.counts['branch_restores'] += 1
        self.current_node = identifier
        for name, value in node.runtime.items():
            setattr(self, name, deepcopy(value))
        self.evidence = OrderedDict((eid,self.all_evidence[eid]) for eid in node.evidence_ids[-48:])
        self.anchor = identifier
        self.counts['graph_source_switches'] += 1
        self._emit('graph_restore', source=source, target=identifier,
            files_restored=before!=node.scope, fingerprint=node.scope,
            restoration='workspace_files_only', budgets_reset=False)

    def _snapshot(self, label):
        if self.counts['graph_snapshots'] >= self.limits.max_snapshots:
            raise SearchLimit('graph_snapshot_budget')
        before = self.environment.scope()
        record = self.environment.checkpoint(label)
        if record.get('fingerprint') != before or self.environment.scope() != before:
            raise RuntimeError('graph snapshot fingerprint mismatch')
        self.counts['graph_snapshots'] += 1
        self.counts['checkpoints_created'] += 1
        return record

    def _persist(self):
        nodes = [dict(id=n.id, scope=n.scope, record=n.record, depth=n.depth,
            evidence_ids=n.evidence_ids, public_checks=n.public_checks,
            latest_failed=n.latest_failed, information_new=n.information_new,
            expansions=n.expansions, incoming=n.incoming, observed_dependencies=n.dependencies,
            knowledge_sha256=digest(sorted(n.observations))) for n in self.search_nodes.values()]
        self.log.save('search-graph.json',dict(version=self.runtime_version,
            nodes=nodes, edges=[asdict(e) for e in self.search_edges.values()],
            current=self.current_node, limits=asdict(self.limits),
            state_equivalence='file fingerprint AND exact observation set AND latest observation AND same-state check map',
            official_success=None))

    def _memory_hint(self, edge):
        if not self.config.memory_enabled:
            return 0.0
        node = self.search_nodes[edge.source]
        paths = self.memory.dependency_targets()
        # No restoration just for ranking. A dependency-specific hint is only
        # available for the physically active state; full-scope lessons can
        # be conservatively considered for other saved states.
        dependencies = (self.environment.dependency_state(paths) if edge.source==self.current_node
                        else node.dependencies)
        hint = 0.0
        for record in self.memory.items.values():
            status = self.memory.applicability(record, node.scope, dependencies)
            applicable = 'unchanged' in status or status.startswith('same_workspace')
            if not applicable:
                continue
            if record.get('command_key') == action_key(edge.action):
                hint -= 1.0 if record['kind']=='blocker' else 0.0
            query = (edge.hypothesis+' '+edge.expected_evidence).casefold()
            if record['kind']=='procedure' and record.get('next_step','').casefold() in query and record.get('next_step'):
                hint += .5
        return max(-1.0, min(1.0, hint))

    def _select(self):
        if self.selections >= self.limits.max_selections:
            raise SearchLimit('graph_selection_budget')
        pressure = max(self.counts['model_requests']/self.config.max_turns,
                       self.counts['tool_calls']/self.config.max_tools)
        entries = []
        for edge in self.search_edges.values():
            if edge.status != 'pending':
                continue
            priority = frontier_priority(self.search_nodes[edge.source], kind=edge.kind,
                waiting=self.selections-edge.born, used_ratio=pressure,
                memory_hint=self._memory_hint(edge))
            edge.priority = priority
            entries.append((priority['score'], 1, -int(edge.id[1:]), 'edge', edge.id, edge.source))
        if self.counts['model_requests'] < self.config.max_turns:
            for node in self.search_nodes.values():
                if node.expansions >= self.limits.max_expansions_per_node:
                    continue
                # Consume this node's already proposed alternatives first;
                # other nodes' expansion entries still compete globally.
                if any(e.source==node.id and e.status=='pending' for e in self.search_edges.values()):
                    continue
                if sum(e.status=='pending' for e in self.search_edges.values())+self.limits.width > self.limits.max_pending_edges:
                    continue
                priority = frontier_priority(node, kind='expand', waiting=self.selections-node.born,
                                             used_ratio=pressure)
                entries.append((priority['score'], 0, -int(node.id[1:]), 'expand', node.id, node.id))
        if not entries:
            raise SearchLimit('graph_frontier_exhausted')
        chosen = max(entries)
        self.selections += 1
        self.counts['graph_frontier_selections'] += 1
        self._emit('graph_frontier_select', kind=chosen[3], id=chosen[4],
            source=chosen[5], priority=chosen[0], frontier_size=len(entries))
        return chosen[3], chosen[4], chosen[5]

    def _expand(self, node):
        node.expansions += 1
        self.counts['graph_expansions'] += 1
        response = self._ask('action')
        rows = parse_proposals(response, self.limits.width)
        # Validate EVERY nested action before it becomes executable; one
        # malformed candidate cannot smuggle an unchecked sibling through.
        for row in rows:
            validate_review(row['action'], self.visible_memories,
                self.config.memory_injection and self.config.memory_enabled and self.config.memory_decision)
        added = 0
        existing = {executable_key(e.action) for e in self.search_edges.values()
                    if e.source==node.id and e.status!='stale_memory_view'}
        for row in rows:
            key = executable_key(row['action'])
            if key in existing:
                self.counts['graph_duplicate_proposals'] += 1
                self._emit('graph_duplicate_proposal', source=node.id, command=row['action'])
                continue
            existing.add(key)
            identifier = 'G'+str(len(self.search_edges)+1)
            self.search_edges[identifier] = SearchEdge(id=identifier, source=node.id,
                born=self.selections, memory_ids=tuple(sorted(self.visible_memories)), **row)
            added += 1
        self._record_turn(response, dict(graph_proposals_registered=added,
            source_node=node.id, commands_executed=False))
        self.last_feedback = dict(graph_proposals_registered=added,
            instruction='No proposed command has executed until an edge is selected.')
        self._save_current()
        self._emit('graph_expansion', source=node.id, added=added, total_proposals=len(rows))

    def _transition(self, edge, row):
        source = self.search_nodes[edge.source]
        assessment = row.get('execution_assessment', {})
        # Use the full captured readable-output hash, NOT the compressed
        # prompt excerpt. A retry declaration is not new terminal evidence.
        signature = digest([loop_key(edge.action), row['outcome_key'], row['after']])
        observations = source.observations | {signature}
        complete = not any(row.get(k, False) for k in
            ('timed_out','blocked','capture_incomplete','terminal_projection_incomplete'))
        # Incomplete observations cannot safely establish equivalent knowledge.
        if not complete:
            observations = observations | {digest(['incomplete',row['id']])}
        scope = self.environment.scope()
        changed = scope != source.scope
        checks = {} if changed else dict(source.public_checks)
        check = assessment.get('check_status', 'unknown')
        if complete and check in {'public_check_passed','public_check_failed'}:
            checks[executable_key(edge.action)] = check
        identity = (scope, digest(sorted(observations)), signature, digest(checks))
        known = self.state_index.get(identity)
        edge.evidence_id = row['id']
        if known:
            edge.target = known
            self.search_nodes[known].incoming.append(edge.id)
            self.counts['graph_state_merges'] += 1
            # The just-executed turn belongs to the transition, NOT to the
            # unchanged parent. Never overwrite its branch history here.
            self._activate(known, save_current=False)
            self._emit('graph_state_merge', edge_id=edge.id, source=edge.source, target=known,
                equivalent_files=True, equivalent_observations=True)
            return
        if len(self.search_nodes) >= self.limits.max_nodes:
            raise SearchLimit('graph_node_budget')
        record = self._snapshot('graph edge '+edge.id) if changed else source.record
        identifier = 'N'+str(len(self.search_nodes))
        node = StateNode(identifier, scope, record, source.depth+1,
            frozenset(observations), list(dict.fromkeys(source.evidence_ids+[row['id']])),
            self._capture_runtime(), checks,
            latest_failed=bool(assessment.get('suspected_failure') or row['return_code']!=0
                               or row.get('timed_out') or row.get('blocked')),
            information_new=complete and signature not in source.observations,
            files_changed=source.files_changed or changed, born=self.selections,
            incoming=[edge.id], dependencies={**({} if changed else source.dependencies),
                                             **row.get('dependency_after',{})})
        self.search_nodes[identifier] = node
        self.state_index[identity] = identifier
        edge.target = identifier
        self.current_node = identifier
        self.anchor = identifier
        self.evidence = OrderedDict((eid,self.all_evidence[eid]) for eid in node.evidence_ids[-48:])
        self.counts['graph_nodes_created'] += 1
        self._emit('graph_transition', edge_id=edge.id, source=edge.source, target=identifier,
            evidence_id=row['id'], files_changed=changed, information_new=node.information_new,
            check_status=check, task_correctness='unverified')

    def _execute(self, edge):
        # Admission is checked again against CURRENT conditional memories;
        # queued actions cannot assume old memory availability indefinitely.
        self._panel()
        action = edge.action
        if (self.config.memory_injection and self.config.memory_enabled and self.config.memory_decision
                and tuple(sorted(self.visible_memories)) != edge.memory_ids):
            # This proposal never saw the new view. Do not falsely blame the
            # model for missing a review of memories it had not received.
            edge.status = 'stale_memory_view'
            self.counts['graph_stale_proposals'] += 1
            self.last_feedback = dict(not_executed=True, stale_graph_proposal=edge.id,
                instruction='Conditional memory view changed since this proposal. Regenerate it using the current view.')
            self._emit('graph_proposal_stale', edge_id=edge.id,
                prior_memory_ids=edge.memory_ids, current_memory_ids=sorted(self.visible_memories))
            self._record_turn(action,self.last_feedback)
            return False
        review = validate_review(action, self.visible_memories,
            self.config.memory_injection and self.config.memory_enabled and self.config.memory_decision)
        if review:
            self._emit('memory_decision_review', review=review,
                strategy_adjustment=action['strategy_adjustment'], verified=False, causal_benefit_proven=False)
        self._record_memory_reconsideration(action)
        intervention = self._memory_push(action)
        if intervention:
            edge.status = 'memory_deferred'
            self.pending_memory_intervention = self.pending_memory_proposal = intervention
            self.last_feedback = dict(not_executed=True, memory_intervention=intervention)
            self._emit('memory_intervention', **intervention)
            self._record_turn(action, self.last_feedback)
            return False
        self._optional_memory(action)
        kind = action['action']
        edge.status = 'selected'
        if kind == 'submit':
            self._consume_memory_followup(kind, outcome_observed=False)
            self.counts['submissions'] += 1
            edge.status = 'submitted'
            self._emit('submission', node=self.current_node, summary=action['summary'],
                artifact=self.environment.delivery(), success=None)
            return True
        if kind != 'run':
            self._consume_memory_followup(kind, outcome_observed=False)
            feedback = (self._consult(action['question'], 'main_requested') if kind=='consult'
                        else self.conversation.retrieve(action))
            edge.status = 'executed'
            self.last_feedback = feedback
            self._record_turn(action, feedback)
            return False
        if len(self.search_nodes) >= self.limits.max_nodes:
            raise SearchLimit('graph_node_budget')
        before = self.environment.scope()
        blocked = self.action_loop.check(action, before)
        if blocked:
            self.counts['action_loop_blocks'] += 1
            self.counts['graph_cached_results'] += 1
            edge.status = 'cached_result'
            row = self.all_evidence[blocked['evidence_id']]
            self._emit('action_loop_block', command=self._action_core(action), **blocked)
            self.last_feedback = dict(not_executed=True, action_loop=blocked)
            self._record_turn(action, self.last_feedback)
            self._transition(edge, row)
            return False
        # Reserve snapshot capacity before a command might modify files.
        if self.counts['graph_snapshots'] >= self.limits.max_snapshots:
            raise SearchLimit('graph_snapshot_budget')
        feedback = self._run_command(action)
        row = feedback['evidence']
        self.all_evidence[row['id']] = row
        self.action_loop.observe(action, row)
        edge.status = 'executed'
        self.last_feedback = feedback
        self._record_turn(action, self.last_tool_observation)
        self._transition(edge, row)
        return False

    def run(self, task):
        version = self._initialize_run(task)
        self.search_nodes, self.search_edges, self.state_index = OrderedDict(), OrderedDict(), {}
        self.all_evidence = OrderedDict()
        self.current_node, self.selections = None, 0
        submitted, stop, error_type, errors = False, 'model_budget', None, 0
        try:
            record = self._snapshot('graph root')
            root = StateNode('N0', self.environment.scope(), record, runtime=self._capture_runtime())
            self.search_nodes['N0'] = root
            self.state_index[(root.scope,digest([]),'',digest({}))] = 'N0'
            self.current_node = self.anchor = 'N0'
            self._emit('graph_header', algorithm='global_best_first_file_state_graph',
                limits=asdict(self.limits), heritage='v13/v14 global frontier; historical phase_weights',
                memory='current conditional task-local memory', automatic_llm_assessment=False)
            while True:
                if time.monotonic() >= self.deadline:
                    stop='wall_budget'; break
                if self.counts['tool_calls'] >= self.config.max_tools:
                    stop='tool_budget'; break
                kind, identifier, source = self._select()
                self._activate(source)
                edge = self.search_edges.get(identifier) if kind=='edge' else None
                try:
                    self._maybe_monitor()
                    if self.pending_question and self.counts['model_requests'] < self.config.max_turns:
                        question, trigger = self.pending_question, self.pending_question_trigger or 'runtime'
                        self.pending_question = self.pending_question_trigger = None
                        self.last_feedback = self._consult(question, trigger)
                    if kind=='expand':
                        if self.counts['model_requests'] >= self.config.max_turns:
                            stop='model_budget'; break
                        self._expand(self.search_nodes[source])
                    else:
                        submitted = self._execute(edge)
                    errors = 0
                except ValueError as error:
                    errors += 1
                    self.counts['protocol_errors'] += 1
                    self.last_feedback = dict(not_executed=True, protocol_error=str(error)[:400])
                    repair = review_repair_feedback(error)
                    if repair:
                        self.last_feedback.update(repair)
                    self._emit('protocol_error', **self.last_feedback)
                    if edge:
                        edge.status='rejected'
                    self._record_turn(edge.action if edge else dict(action='graph_expand'), self.last_feedback)
                except ModelCallError:
                    errors += 1
                    if any(self._fatal_provider_error(c) for c in self.clients.values()):
                        stop='credential_or_balance_error'; break
                    self.last_feedback = dict(model_error='Model request failed; no graph edge executed.')
                self._save_current()
                self._persist()
                if submitted:
                    stop='model_submit'; break
                if errors >= self.config.max_consecutive_errors:
                    stop='model_or_protocol_error_limit'; break
        except SearchLimit as error:
            stop=str(error)
        except TimeoutError:
            stop='wall_budget' if time.monotonic()>=self.deadline else 'request_or_tool_budget'
        except Exception as error:
            stop, error_type = 'infrastructure_error', type(error).__name__
            self._emit('infrastructure_error', error_type=error_type)
        artifact = None
        try:
            # Never silently replace an explicit model submission. Otherwise
            # retain the node with strongest same-state PUBLIC check evidence.
            # With no passed public checks, keep the active branch, not a
            # guessed "best" branch inferred from novelty or model claims.
            if not submitted and error_type is None and self.search_nodes:
                best = max(self.search_nodes.values(), key=lambda n:
                    sum(v=='public_check_passed' for v in n.public_checks.values()))
                active = self.search_nodes[self.current_node]
                count = lambda n:sum(v=='public_check_passed' for v in n.public_checks.values())
                if count(best)>count(active):
                    self._activate(best.id)
                    self._emit('graph_delivery_fallback', node=best.id,
                        semantics='public_check_count_heuristic_not_official_success')
            artifact = self.environment.delivery()
        except Exception as error:
            stop, error_type = 'delivery_error', type(error).__name__
        self._persist()
        usage = {role:c.usage_summary() for role,c in self.clients.items()
                 if callable(getattr(c,'usage_summary',None))}
        result = dict(version=version, task_id=task.task_id, submitted=submitted,
            stop_reason=stop, artifact=artifact, official_success=None, error_type=error_type,
            interaction_rounds=self.counts['model_requests'], action_rounds=self.counts['action_calls'],
            advisor_rounds=self.counts['advisor_calls'], monitor_rounds=self.counts['monitor_calls'],
            tool_calls=self.counts['tool_calls'], wall_seconds=time.monotonic()-self.started_at,
            model_usage=usage, mechanism_utilization=dict(self.counts), time_by_role=dict(self.timings),
            graph_diagnostics=dict(nodes=len(self.search_nodes), edges=len(self.search_edges),
                selected_node=self.current_node, limits=asdict(self.limits)),
            contextual_tool_redundancy=dict(status='requires_independent_audit',rate=None,
                                           denominator=self.counts['tool_calls']))
        self._emit('method_end',result=result)
        self.log.save('result.json',result)
        self.log.save('memories.json',list(self.memory.items.values()))
        return result
