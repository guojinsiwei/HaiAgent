"""Two isolated contrastive exploration policies; no branches, tree or rollback.

evidence: select a changed lever or a discriminating observation.
orthogonal: measured exploration with lexical similarity telemetry.
Neither self-reported explanation nor textual distance proves causal novelty.
"""
from collections import Counter
import json
import math
import re
import shlex
from .exploration_learning import validate_comparison, validate_experiment, select_anchors, result_memory, recall_results, result_views

from .lean_audit import digest
from .lean_memory import action_key, tokens
from .lean_protocol import parse_action, text
from .lean_progress import normalize_workspace_path
from .memory_events import dependency_paths


EVIDENCE_INSTRUCTION = '''When fixed_context.contrastive_exploration.active is true,
attach contrastive to every run action, AFTER the ordinary memory_review,
strategy_adjustment, action prefix. Use short factual decision summaries, not
extended reasoning. Failure anchors are conditional observations, never proof
that an entire algorithm is impossible. Do not seek novelty for its own sake.
On phase=plan, propose exactly TWO candidates and select one in the SAME reply:
"contrastive":{"selected":"A","candidates":[
 {"id":"A","anchor_ids":["F1"],"hypothesis":"specific explanation",
  "difference":"new assumption, changed relevant parameter or new observation",
  "kind":"probe|repair|retry","action":{"action":"run","argv":["..."],"cwd":"."},
  "supports":"literal expected result marker","refutes":"different literal marker",
  "changed_paths":[],"evidence_ids":[]},
 {"id":"B",...}]}
On phase=followup, use the SAME selected/candidates schema with ONE candidate.
The selected candidate action must match the actual top-level argv/cwd/stdin.
References must name supplied anchors/evidence. Supports/refutes are preregistered
predictions, NOT invented observations. Prefer a direct low-risk repair if the
cause is established; otherwise choose a cheap check distinguishing explanations.
Repeating the same failed executable requires a relevant changed file path
anchored in that failure. changed_paths is checked against observed file hashes;
changing an unrelated file or merely declaring a new strategy is insufficient.
Changing a meaningful parameter is allowed even with the same file/module/type.
Absence of a file change is not itself failure. An external-state recheck is
allowed once per unchanged anchored attempt with kind=retry and
external_recheck=true; state your testable observation in difference. It is
audited as external_state_unverified, not a verified condition change.
Execute ONLY the chosen action. No alternate execution, checkpoint or rollback.
'''

ORTHOGONAL_INSTRUCTION = '''Active exploration uses contrastive with negative_anchors_summary, proposed_strategy,
orthogonality_proof (dependency_dimension, target_dimension, command_dimension),
changed_dimensions (at least one), and final_command matching the exact action.
State what stays unchanged. Use exploration:{"hypothesis":"...","alternative":"...",
"measurement":"how the task-derived scalar is computed",
"supports":{"field":"stdout","metric":"mismatch_count","op":"gt","value":0},
"refutes":{"field":"stdout","metric":"mismatch_count","op":"lte","value":0}}.
The command must output a JSON line with the measured scalar; never manufacture it.
Missing, conflicting, mistyped or incomplete observations remain unknown. Literal
markers are retained as observations only. Measurements do not prove causality or
whole-task success. Refer to the latest same-episode result on each next probe:
result_decision:{"result_id":"XE3","action":"repair|verify|revise|retest|defer",
"reason":"how this observation changes the action"}, inside contrastive.
Routine reads, native file edits, local correction and changed-input verification
need no exploration form. Lexical similarity is telemetry; the exact unchanged
failed-action guard remains active. Eight probes OR sixteen actual actions OR two
format rejections close the gate, followed by four recovery steps of cooldown.
No diagnostic command is automatically injected. Continue ordinary task work.
All requests and commands share the original budget. Keep comparisons concise.
'''

PREDICTION_EXTENSION = '''On phase=plan add selected and exactly TWO candidates inside contrastive.
On phase=followup supply ONE candidate. Candidate schema:
{"id":"A","hypothesis":"short testable explanation",
 "action":{"action":"run","argv":["..."],"cwd":"."},
 "supports":"literal output marker","refutes":"distinct literal marker"}.
The selected candidate must match the actual argv/cwd/stdin. Execute only that
candidate. These are brief predictions, not observations or success claims.
'''


def command_text(action):
    """Exact displayed command; execution remains original argv, never a reparse."""
    argv = action.get('argv', [])
    if len(argv) == 3 and argv[0].rsplit('/', 1)[-1] in {'sh', 'bash'} and argv[1] in {'-c', '-lc'}:
        return argv[2]
    return shlex.join(argv)


def tfidf_similarity(new_command, memory_commands):
    """sklearn default word TF-IDF (lowercase, >=2 word chars, smooth IDF, L2).

    Stdlib implementation avoids silently adding sklearn to experiment workers.
    Refit on the same [new]+anchors corpus as the user's supplied pseudocode.
    All-empty vocabulary yields 0 and an explicit uncertainty flag, not a
    format error. Numeric single-character parameters can disappear; intentional
    reproduction of this word tokenizer, tested and reported as a limitation.
    """
    if not memory_commands:
        return dict(max_similarity=0.0, per_anchor=[], empty_vocabulary=False)
    counts = [Counter(re.findall(r'(?u)\b\w\w+\b', value.lower()))
              for value in [new_command, *memory_commands]]
    df = Counter(word for count in counts for word in count)
    if not df:
        return dict(max_similarity=0.0, per_anchor=[0.0]*len(memory_commands), empty_vocabulary=True)
    idf = {word: math.log((1 + len(counts))/(1 + frequency)) + 1 for word, frequency in df.items()}
    vectors = [{word: frequency*idf[word] for word, frequency in count.items()} for count in counts]
    norms = [math.sqrt(sum(v*v for v in vector.values())) for vector in vectors]
    similarities = [sum(value*vectors[i].get(word, 0) for word, value in vectors[0].items()) /
        (norms[0]*norms[i]) if norms[0] and norms[i] else 0.0 for i in range(1, len(vectors))]
    return dict(max_similarity=max(similarities), per_anchor=similarities, empty_vocabulary=False)


def validate_orthogonal(action, anchors, threshold):
    value = action.get('contrastive')
    if not isinstance(value, dict):
        raise ValueError('orthogonal policy requires contrastive comparison')
    for name in ('negative_anchors_summary', 'proposed_strategy'):
        text(value.get(name), name, 500)
    proof = value.get('orthogonality_proof')
    if not isinstance(proof, dict):
        raise ValueError('orthogonality_proof must contain three dimensions')
    for name in ('dependency_dimension', 'target_dimension', 'command_dimension'):
        text(proof.get(name), name, 350)
    validate_comparison(proof,value.get('changed_dimensions'))
    validate_experiment(value.get('exploration'))
    actual = command_text(action)
    proposed = value.get('final_command')
    argv = action.get('argv', [])
    shell = len(argv) == 3 and argv[0].rsplit('/', 1)[-1] in {'sh', 'bash'} and argv[1] in {'-c', '-lc'}
    try:
        consistent = isinstance(proposed, str) and (
            (shell and proposed == actual) or shlex.split(proposed) == argv)
    except ValueError:
        consistent = False
    if not consistent:
        raise ValueError('final_command must exactly render the executed argv; no proof/action mismatch')
    scores = tfidf_similarity(actual, [row['command'] for row in anchors])
    audit = dict(policy='orthogonal', threshold=threshold, **scores,
                 dimension_claims_verified=False, causal_novelty_verified=False)
    measured=validate_experiment(value.get('exploration'))['mode']=='metric'
    audit['similarity_is_telemetry'] = measured
    return audit, ('command_similarity_above_threshold' if not measured and scores['max_similarity']>threshold else None)


def _safe_paths(values):
    if not isinstance(values, list) or len(values) > 4:
        raise ValueError('changed_paths must contain at most four task paths')
    return list(dict.fromkeys(normalize_workspace_path(path) for path in values))


def validate_predictions(action, phase):
    value = action['contrastive']
    rows = value.get('candidates')
    n = 2 if phase == 'plan' else 1
    if not isinstance(rows, list) or len(rows) != n:
        raise ValueError('predict '+str(n)+' candidate(s) before selecting an action')
    by_id, keys = {}, []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('invalid prediction candidate')
        ident = text(row.get('id'), 'candidate id', 8)
        if ident in by_id:
            raise ValueError('duplicate prediction candidate id')
        for field in ('hypothesis', 'supports', 'refutes'):
            text(row.get(field), field, 350)
        if row['supports'] in row['refutes'] or row['refutes'] in row['supports']:
            raise ValueError('prediction markers must distinguish outcomes')
        candidate = parse_action(row.get('action'))
        if candidate['action'] != 'run':
            raise ValueError('predictions require executable candidates')
        keys.append(action_key(candidate))
        by_id[ident] = row
    if len(set(keys)) != n:
        raise ValueError('prediction candidates must have different executable actions')
    chosen = by_id.get(value.get('selected'))
    if chosen is None or action_key(chosen['action']) != action_key(action):
        raise ValueError('selected prediction must match the executed action')
    return chosen


def validate_evidence(action, anchors, scope, dependencies, visible_evidence, phase, external_retries):
    value = action.get('contrastive')
    if not isinstance(value, dict):
        raise ValueError('evidence policy requires contrastive candidates')
    rows = value.get('candidates')
    required = 2 if phase == 'plan' else 1
    if not isinstance(rows, list) or len(rows) != required:
        raise ValueError('evidence policy needs '+str(required)+' candidates in phase '+phase)
    by_id, available = {}, {a['id']: a for a in anchors}
    candidate_keys = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('invalid candidate')
        identifier = text(row.get('id'), 'candidate id', 8)
        if identifier in by_id:
            raise ValueError('duplicate candidate id')
        references = row.get('anchor_ids')
        if not isinstance(references, list) or not 1 <= len(references) <= 3 or any(
                not isinstance(ref, str) or ref not in available for ref in references):
            raise ValueError('candidate must reference supplied negative anchors')
        for name in ('hypothesis', 'difference', 'supports', 'refutes'):
            text(row.get(name), name, 350)
        if row['supports'] in row['refutes'] or row['refutes'] in row['supports']:
            raise ValueError('support/refutation markers must be distinguishable')
        if row.get('kind') not in {'probe', 'repair', 'retry'}:
            raise ValueError('candidate kind must be probe, repair or retry')
        candidate = parse_action(row.get('action'))
        if candidate['action'] != 'run':
            raise ValueError('candidate action must be run')
        changed = _safe_paths(row.get('changed_paths', []))
        ids = row.get('evidence_ids', [])
        if not isinstance(ids, list) or len(ids) > 3 or any(not isinstance(i, str) or i not in visible_evidence for i in ids):
            raise ValueError('candidate cites unavailable evidence')
        if 'external_recheck' in row and type(row['external_recheck']) is not bool:
            raise ValueError('external_recheck must be boolean')
        # Only selected candidate will be executed. Claims are not semantic proof.
        by_id[identifier] = dict(row, changed_paths=changed)
        candidate_keys.append(action_key(candidate))
    if len(set(candidate_keys)) != required:
        raise ValueError('plan candidates must propose different executable actions')
    selected = value.get('selected')
    if not isinstance(selected, str) or selected not in by_id:
        raise ValueError('selected candidate is unavailable')
    chosen = by_id[selected]
    if action_key(chosen['action']) != action_key(action):
        raise ValueError('selected candidate and actual executable differ')
    conflicts, exemptions, retry_signatures = [], [], []
    for anchor in anchors:
        if anchor['command_key'] != action_key(action):
            continue
        known = {p: state for p, state in anchor['dependencies'].items()
                 if state != 'unknown' and not str(state).startswith('link:')}
        changed = [p for p, state in known.items() if dependencies.get(p, 'unknown') not in
                   ('unknown', state) and not str(dependencies.get(p)).startswith('link:')]
        # A related file change is inspectable even if the old scope differs.
        if changed:
            if chosen['kind'] == 'retry' and set(changed).intersection(chosen['changed_paths']):
                exemptions.append(dict(anchor_id=anchor['id'], reason='observed_relevant_file_change', paths=changed))
                continue
            conflicts.append(anchor['id'])
            continue
        retry_key = digest([anchor['command_key'], anchor['scope'], scope, anchor['dependencies'], dependencies])
        if (chosen['kind'] == 'retry' and chosen.get('external_recheck') is True
                and retry_key not in external_retries):
            retry_signatures.append(retry_key)
            exemptions.append(dict(anchor_id=anchor['id'], reason='one_external_recheck_unverified'))
        else:
            conflicts.append(anchor['id'])
    return dict(policy='evidence', selected=chosen, alternatives=rows,
                exemptions=exemptions, retry_signatures=list(set(retry_signatures)),
                conflicts=conflicts, semantic_claims_verified=False), (
                    'unchanged_failed_executable_without_relevant_change' if conflicts else None)


from .recovery_clock import recovery_steps
from .rejection_recovery import changed_paths
from .targeted_diagnostics import diagnostic_action
from .exploration_trigger import ExplorationTrigger, check_identity, issue_identity


class ContrastiveExploration:
    def _contrastive_activate(self, trigger):
        if (self.config.contrastive_mode == 'off' or self.contrastive_episode
                or recovery_steps(self)-self.contrastive_last_end < 4):
            return
        if self.contrastive_last_end >= 0 and not self.contrastive_rearm:return
        candidate = self.exploration_trigger.pending(self.config.contrastive_trigger_failures)
        if candidate is None:
            return
        decision = self.exploration_trigger.consume(candidate)
        self.counts['contrastive_episodes'] += 1
        baselines = {f['command_key'] for f in self.contrastive_failures if decision['key'] in (f.get('check_key'),f.get('issue_key')) or f['evidence_id'] in decision['evidence']}
        self.contrastive_episode = dict(id='X'+str(self.counts['contrastive_episodes']), phase='plan',
            start_tool=self.counts['tool_calls'], probes=0,auxiliary_tools=0,trigger_key=decision['key'],
            baseline_keys=baselines)
        self._emit('contrastive_episode_start', episode_id=self.contrastive_episode['id'],
            trigger=trigger, trigger_evidence=decision, policy=self.config.contrastive_mode,
            baseline_keys=sorted(self.contrastive_episode['baseline_keys']))

    def _init_contrastive(self):
        self.exploration_trigger = ExplorationTrigger(capacity=self.config.max_memories)
        self.contrastive_failures = []
        self.contrastive_episode = None
        self.contrastive_pending = None
        self.contrastive_external_retries = set()
        self.contrastive_last_end = -100  # Recovery steps, not actual tool calls.
        self.contrastive_visible_anchors = []
        self.contrastive_reject_streak = 0
        self.contrastive_seen_outcomes = set()
        self.contrastive_check_status = {}
        self.exploration_results=[]
        self.exploration_seen=set()
        self.contrastive_rearm=True
        self.contrastive_condition=None
        self.monitor_trigger_signatures=[]

    def _learning_plan(self,action,kind):
        value=action.get('contrastive',{}).get('exploration')
        if value is None:return None
        episode=self.contrastive_episode or {}
        return dict(experiment=validate_experiment(value),kind=kind,episode=episode.get('id'),
            anchor_ids=[i for a in self.contrastive_visible_anchors for i in a.get('evidence_ids',[a['evidence_id']])],
            check_key=episode.get('trigger_key'),goal=action.get('subgoal_id'),command=command_text(action),
            result_decision=action.get('contrastive',{}).get('result_decision'))

    def _finish_learning(self,action,row,assessment,local_defect=False):
        if row['id'] in self.exploration_seen:return
        self.exploration_seen.add(row['id'])
        pending=self.contrastive_pending
        plan=(pending or {}).get('audit',{}).get('learning') if pending and pending['action_key']==action_key(action) else None
        episode=self.contrastive_episode
        if episode:
            field='probes' if plan and plan['kind']=='probe' else 'auxiliary_tools'
            episode[field]=episode.get(field,0)+1
        decision=(pending or {}).get('audit',{}).get('result_decision') if pending and pending['action_key']==action_key(action) else None
        follow=getattr(self,'exploration_followup',None)
        if follow and follow['key']==action_key(action):
            decision=follow['decision'];self.exploration_followup=None
        if decision:self._emit('exploration_result_used',decision=decision,evidence_id=row['id'],
            execution_complete=not any(row.get(k) for k in ('timed_out','blocked','capture_incomplete','terminal_projection_incomplete','aborted','native_tool_error')),
            workspace_changed=row['before']!=row['after'],check_status=assessment.get('check_status'),task_success=None)
        if not plan:return
        record=result_memory(plan,row,assessment,local_defect)
        self.exploration_results=(self.exploration_results+[record])[-self.config.max_memories:]
        self.log.save('exploration-results.json',self.exploration_results)
        self._emit('exploration_learning',record=record)
        self.counts['exploration_'+record['status']]+=1

    def _end_learning_cap(self):
        episode=self.contrastive_episode
        if episode and (episode.get('probes',0)>=self.config.contrastive_episode_tools or episode.get('probes',0)+episode.get('auxiliary_tools',0)>=getattr(self.config,'contrastive_total_actions',16)):
            self._emit('contrastive_episode_end',episode_id=episode['id'],reason='episode_probe_cap' if episode.get('probes',0)>=self.config.contrastive_episode_tools else 'episode_total_action_cap',
                       probes=episode['probes'],auxiliary_tools=episode.get('auxiliary_tools',0),task_success=None)
            self.contrastive_episode=None;self.contrastive_rearm=False;self.exploration_trigger.retire_pending()
            self.contrastive_last_end=recovery_steps(self)

    def _contrastive_instruction(self):
        value = {'off': '', 'evidence': EVIDENCE_INSTRUCTION,
                 'orthogonal': ORTHOGONAL_INSTRUCTION}[self.config.contrastive_mode]
        if self.config.contrastive_mode == 'orthogonal' and self.config.contrastive_predictions:
            value += '\n' + PREDICTION_EXTENSION
        return value

    def _contrastive_context(self, scope, dependencies):
        if self.config.contrastive_mode == 'off':
            return None
        current=self.contrastive_episode
        goal=getattr(getattr(self,'subgoals',None),'active',None)
        goals=getattr(getattr(self,'subgoals',None),'items',{})
        targets=goals.get(goal,{}).get('definition',{}).get('targets',[])
        query=str(getattr(self,'last_feedback',''))[:1500]
        selected = select_anchors(self.contrastive_failures,trigger_key=(current or {}).get('trigger_key'),
                                  query=query,targets=targets,goal=goal)
        if self.config.contrastive_mode == 'evidence':
            query = tokens(self.task.goal + ' ' + str(self.last_feedback)[:1500])
            def rank(row):
                changed = any(dependencies.get(p, 'unknown') != state for p, state in row['dependencies'].items())
                return (len(query & tokens(row['command']+' '+row['observation'])), not changed, row['index'])
            selected = sorted(self.contrastive_failures, key=rank, reverse=True)[:3]
        self.contrastive_visible_anchors = selected
        current = self.contrastive_episode
        return dict(active=current is not None, mode=self.config.contrastive_mode,
            prediction_extension=self.config.contrastive_predictions,
            phase=current['phase'] if current else 'inactive',
            episode_id=current['id'] if current else None, threshold=self.config.contrastive_threshold,
            negative_anchors=[dict(id=a['id'], command=a['command'][:1300],
                observation=a['observation'][:350], evidence_id=a['evidence_id'],
                scope_matches=scope == a['scope'], targets=list(a['dependencies']),
                condition_status='historical_external_state_unverified',
                attempts=a.get('attempts',1),evidence_ids=a.get('evidence_ids',[a['evidence_id']]),conditions_changed=a.get('conditions_changed',False),
                memory_ids=a['memory_ids'], hypothesis=a['hypothesis'], status=a['status']) for a in selected],
            exploration_results=result_views(recall_results(self.exploration_results,query=query,
                check_key=(current or {}).get('trigger_key') or (self.exploration_trigger.state.get('lastDecision') or {}).get('key'),
                goal=goal,scope=scope,dependencies=dependencies)),
            exploration_budget=dict(probes=(current or {}).get('probes',0),auxiliary_tools=(current or {}).get('auxiliary_tools',0),limit=self.config.contrastive_episode_tools),
            model_claims_are_not_proof=True, regeneration_counts_as_model_request=True)

    def _contrastive_before(self, action, exempt=False):
        self.contrastive_pending=None
        if not self.contrastive_episode or action['action'] != 'run':
            return None
        e = self.contrastive_episode
        matches = [a for a in self.contrastive_visible_anchors if a['command_key'] == action_key(action)]
        paths = list(dict.fromkeys(p for a in matches for p in a['dependencies']))
        current = self.environment.dependency_state(paths) if paths else {}
        changed = [a['id'] for a in matches if changed_paths(a['dependencies'], current)]
        if matches and len(changed) == len(matches):
            # A real repair makes the old test necessary again. Do not demand a
            # different command or a textual orthogonality proof for that retry.
            audit = dict(policy=self.config.contrastive_mode, condition_change_exemptions=changed,
                         retry_signatures=[], semantic_claims_verified=False)
            try:audit['learning']=self._learning_plan(action,'verify')
            except ValueError:audit['learning']=None
            if self.config.contrastive_predictions:
                try:
                    audit['selected'] = validate_predictions(action, e['phase'])
                except ValueError:
                    audit['prediction_unavailable'] = True
            self.counts['contrastive_proposals'] += 1
            self.counts['contrastive_accepted'] += 1
            self.contrastive_reject_streak = 0
            self.contrastive_pending = dict(episode_id=e['id'], action_key=action_key(action), audit=audit)
            self._emit('contrastive_validation', episode_id=e['id'], accepted=True,
                       action=self._action_core(action), audit=audit, reason=None)
            return audit
        try:
            if exempt:
                audit,reason=dict(policy=self.config.contrastive_mode),None
            elif self.config.contrastive_mode == 'orthogonal':
                audit, reason = validate_orthogonal(action, self.contrastive_visible_anchors,
                                                    self.config.contrastive_threshold)
                # Similarity is conditional on observed task files. The same
                # check after a relevant repair is necessary, not stagnation.
                matches = [a for a in self.contrastive_visible_anchors
                           if a['command_key'] == action_key(action)]
                paths = list(dict.fromkeys(p for a in matches for p in a['dependencies']))
                current = self.environment.dependency_state(paths) if paths else {}
                changed = [a['id'] for a in matches if any(
                    old != 'unknown' and not str(old).startswith('link:') and
                    current.get(p, 'unknown') not in ('unknown', old) and
                    not str(current.get(p)).startswith('link:')
                    for p, old in a['dependencies'].items())]
                if reason and matches and len(changed) == len(matches):
                    reason = None
                    audit['condition_change_exemptions'] = changed
                if self.config.contrastive_predictions:
                    audit['selected'] = validate_predictions(action, e['phase'])
            else:
                audit, reason = validate_evidence(action, self.contrastive_visible_anchors,
                    self.last_panel_scope, self.last_panel_dependencies, self.visible_evidence,
                    e['phase'], self.contrastive_external_retries)
            decision=action.get('contrastive',{}).get('result_decision')
            latest=next((r for r in reversed(self.exploration_results) if r['episode']==e['id']),None)
            if decision is not None:
                if (not isinstance(decision,dict) or not any(r['id']==decision.get('result_id') for r in self.exploration_results)
                    or decision.get('action') not in ('repair','verify','revise','retest','defer')
                    or not isinstance(decision.get('reason'),str) or not decision['reason'].strip()):
                    raise ValueError('Follow-up requires a real result_id, action and reason.')
            if not exempt and latest and (decision or {}).get('result_id')!=latest['id']:
                raise ValueError('Next probe must reference latest result '+latest['id']+' in contrastive.result_decision.')
            audit['result_decision']=decision
            audit['learning']=self._learning_plan(action,'probe')
        except ValueError as error:
            audit, reason = dict(policy=self.config.contrastive_mode), str(error)
        self.counts['contrastive_proposals'] += 1
        self._emit('contrastive_validation', episode_id=e['id'], accepted=reason is None,
                   action=self._action_core(action), audit=audit, reason=reason)
        if reason:
            self.counts['contrastive_rejections'] += 1
            self.contrastive_pending = None
            self.contrastive_reject_streak += 1
            if self.contrastive_reject_streak < 2:
                return dict(not_executed=True, contrastive_rejection=reason,
                    instruction='Revise the proposal; no task command executed. '
                                'Next rejection closes the gate; ordinary work continues.')
            self._emit('contrastive_episode_end',episode_id=e['id'],reason='two_rejections',task_success=None)
            self.contrastive_episode=None;self.contrastive_rearm=False
            self.exploration_trigger.retire_pending();self.contrastive_last_end=recovery_steps(self)
            self.contrastive_reject_streak=0
            return dict(not_executed=True,contrastive_rejection=reason,
                        instruction='Exploration gate closed. Continue ordinary work; choose a useful read if needed.')
        self.contrastive_reject_streak = 0
        self.counts['contrastive_accepted'] += 1
        self.contrastive_pending = dict(episode_id=e['id'], action_key=action_key(action), audit=audit)
        # Advance only after actual execution, not after admission/reminder.
        return audit

    def _contrastive_outcome(self, action, row, assessment):
        if self.config.contrastive_mode == 'off':
            return
        self._finish_learning(action,row,assessment)
        pending = self.contrastive_pending
        self.contrastive_pending = None
        complete = not (row['capture_incomplete'] or row['terminal_projection_incomplete']
                        or row['timed_out'] or row['blocked'] or row.get('aborted') or row.get('native_tool_error'))
        observed = digest([row['return_code'], row['stdout'], row['stderr']])
        new_evidence = complete and observed not in self.contrastive_seen_outcomes
        condition=digest([row['after'],row.get('dependency_after',{})])
        if complete and (new_evidence or condition!=self.contrastive_condition):self.contrastive_rearm=True
        self.contrastive_condition=condition
        self.contrastive_seen_outcomes.add(observed)
        key = action_key(action)
        previous_check = self.contrastive_check_status.get(key)
        improved = (complete and previous_check == 'public_check_failed'
                    and assessment['check_status'] == 'public_check_passed')
        if assessment['check_status'] != 'unknown':
            self.contrastive_check_status[key] = assessment['check_status']
        if pending and pending['action_key'] == action_key(action):
            audit = pending['audit']
            prediction = 'unknown'
            if self.config.contrastive_mode == 'evidence':
                self.contrastive_external_retries.update(audit['retry_signatures'])
            chosen = audit.get('selected', {})
            output = row['stdout']+'\n'+row['stderr']
            if chosen:
                supports, refutes = chosen['supports'] in output, chosen['refutes'] in output
                if complete and supports != refutes:
                    prediction = 'supported_observation' if supports else 'refuted_observation'
            if audit.get('learning'):
                learned=next((r for r in reversed(self.exploration_results) if r['evidence_id']==row['id']),None)
                prediction={'supported':'supported_observation','refuted':'refuted_observation'}.get((learned or {}).get('status'),'unknown')
            self._emit('contrastive_outcome', episode_id=pending['episode_id'], evidence_id=row['id'],
                command_key=action_key(action), prediction=prediction,
                workspace_changed=row['before'] != row['after'],
                new_evidence=new_evidence, public_check_improved=improved,
                execution_clean=assessment['execution_clean'], check_status=assessment['check_status'],
                prediction_extension=self.config.contrastive_predictions,
                task_success=None, causal_hypothesis_verified=False)
            self.counts['contrastive_observations'] += 1
            self.counts['contrastive_informative_predictions'] += int(prediction != 'unknown')
            self.counts['contrastive_new_evidence'] += int(new_evidence)
            self.counts['contrastive_workspace_changes'] += int(row['before'] != row['after'])
            self.counts['contrastive_public_check_improvements'] += int(improved)
            if self.contrastive_episode:self.contrastive_episode['phase'] = 'followup'
        failed = (row['return_code'] != 0 or row['timed_out'] or row['blocked']
                  or assessment.get('check_status') == 'public_check_failed')
        no_match = row['category'] == 'search' and row['return_code'] == 1 and not row['stderr']
        check = check_identity(command_text(action), action.get('cwd', '.'))
        if complete and not no_match:
            self.exploration_trigger.observe(check, row['id'], 'failed' if failed else
                                             'passed' if assessment['execution_clean'] else 'unknown')
        goals=getattr(getattr(self,'subgoals',None),'items',{})
        goal=action.get('subgoal_id') or getattr(getattr(self,'subgoals',None),'active',None)
        issue=issue_identity(dict(goal=goal,targets=goals.get(goal,{}).get('definition',{}).get('targets',[])),row,action.get('cwd','.'))
        if complete and not no_match and failed and issue:self.exploration_trigger.observe(issue,row['id'],'failed')
        if failed and not no_match and complete:
            self.counts['contrastive_failure_records'] += 1
            index = self.counts['contrastive_failure_records']
            chosen = (pending or {}).get('audit', {}).get('selected', {})
            memory_ids = [m['id'] for m in self.memory.items.values() if row['id'] in m['evidence_ids']]
            declared = getattr(self.environment, 'contrastive_dependencies', None)
            relevant = list(row.get('relevant_dependencies', {})) or (
                declared(action) if callable(declared) else dependency_paths(action))
            self.contrastive_failures.append(dict(id='F'+str(index), index=index,
                command=command_text(action), command_key=action_key(action), check_key=check, issue_key=issue, scope=row['after'],
                goal=action.get('subgoal_id'),
                dependencies={p: row.get('dependency_after', {}).get(p, 'unknown') for p in relevant}, evidence_id=row['id'],
                observation=(row['stderr'] or row['stdout'])[:600], memory_ids=memory_ids,
                hypothesis=chosen.get('hypothesis', 'unknown'), status='observed_failure_not_causal_exclusion'))
            self.contrastive_failures = self.contrastive_failures[-self.config.max_memories:]
            self.log.save('exploration-memory.json', self.contrastive_failures)
        episode = self.contrastive_episode
        if episode:
            verified = (action_key(action) in episode['baseline_keys'] and not failed
                        and complete
                        and row['before'] == row['after'] and assessment['execution_clean'])
            if verified:
                self._emit('contrastive_episode_end', episode_id=episode['id'],
                    reason='original_check_completed_cleanly' if verified else 'episode_tool_cap', task_success=None)
                self.contrastive_episode = None
                self.contrastive_rearm=False
                self.exploration_trigger.retire_pending()
                self.contrastive_last_end = recovery_steps(self)
            else:self._end_learning_cap()
        elif (self.exploration_trigger.pending(self.config.contrastive_trigger_failures)
                and recovery_steps(self)-self.contrastive_last_end >= 4
                and self.contrastive_failures):
            self._contrastive_activate('same_check_failed_again')
        self.log.save('exploration-trigger.json', self.exploration_trigger.state)

    def _contrastive_monitor(self,review,evidence):
        if self.config.contrastive_mode=='off' or review.get('verdict')!='stalled':return False
        ids=review.get('evidence_ids',[])
        if (len(set(ids))<2 or not review.get('next_check') or any(not re.fullmatch(r'E[0-9]+',i) for i in ids)
            or self.contrastive_episode or recovery_steps(self)-self.contrastive_last_end<4):return False
        rows=[evidence.get(i) for i in ids]
        if any(not r or any(r.get(k) for k in ('capture_incomplete','terminal_projection_incomplete','timed_out','blocked','aborted','native_tool_error'))
               or r.get('execution_assessment',{}).get('check_status')=='public_check_passed' for r in rows):return False
        latest=max([int(i[1:]) for i in evidence if re.fullmatch(r'E[0-9]+',i)]+[0])
        if max(int(i[1:]) for i in ids)<latest-6:return False
        signature=digest(sorted(ids))
        if signature in self.monitor_trigger_signatures:return False
        self.monitor_trigger_signatures=(self.monitor_trigger_signatures+[signature])[-64:]
        self.exploration_trigger.request('monitor:'+signature,ids,'monitor_stalled_with_execution_evidence')
        self.contrastive_rearm=True
        self._contrastive_activate('monitor_stalled_with_execution_evidence')
        return self.contrastive_episode is not None
