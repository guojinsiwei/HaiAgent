"""Two isolated contrastive exploration policies; no branches, tree or rollback.

evidence: select a changed lever or a discriminating observation.
orthogonal: user's three declared dimensions + command TF-IDF hard threshold.
Neither self-reported explanation nor textual distance proves causal novelty.
"""
from collections import Counter
import json
import math
import re
import shlex

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

ORTHOGONAL_INSTRUCTION = '''When fixed_context.contrastive_exploration.active is
true, attach contrastive to EVERY run action, AFTER the ordinary memory_review,
strategy_adjustment, action prefix. The latest up to THREE failed strategies are
negative anchors. Propose a new strategy differing significantly in ALL THREE
dimensions: dependency module/environment, modification target, command type.
"contrastive":{
 "negative_anchors_summary":"brief shared failure",
 "proposed_strategy":"new strategy",
 "orthogonality_proof":{
  "dependency_dimension":"brief claimed difference",
  "target_dimension":"brief claimed difference",
  "command_dimension":"brief claimed difference"},
 "final_command":"exact shell script for bash/sh -c/-lc, or POSIX shlex.join(argv)"}
Give concise comparisons, not extended reasoning. Proof fields are model claims,
not verified facts. Command TF-IDF cosine similarity above the configured
threshold is rejected BEFORE execution. No changed-condition exemption applies
in this policy, including a repaired-source rerun of an old failed check.
Regeneration uses the existing model-request budget, not free computation.
Final_command must represent exactly the actual action; do not hide a different
command in the proof. Still use the ordinary run action and bounded task CLI.
For bash/sh -c/-lc, final_command may be the EXACT argv[2] script or a full
POSIX shlex.join(argv) wrapper. Do not change script whitespace, quoting or
redirects. The compared TF-IDF command remains the executed script in either form.
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
    return audit, ('command_similarity_above_threshold' if scores['max_similarity'] > threshold else None)


def _safe_paths(values):
    if not isinstance(values, list) or len(values) > 4:
        raise ValueError('changed_paths must contain at most four task paths')
    return list(dict.fromkeys(normalize_workspace_path(path) for path in values))


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


class ContrastiveExploration:
    def _init_contrastive(self):
        self.contrastive_failures = []
        self.contrastive_episode = None
        self.contrastive_pending = None
        self.contrastive_external_retries = set()
        self.contrastive_last_end = -100
        self.contrastive_visible_anchors = []

    def _contrastive_instruction(self):
        return {'off': '', 'evidence': EVIDENCE_INSTRUCTION,
                'orthogonal': ORTHOGONAL_INSTRUCTION}[self.config.contrastive_mode]

    def _contrastive_context(self, scope, dependencies):
        if self.config.contrastive_mode == 'off':
            return None
        selected = self.contrastive_failures[-3:]
        if self.config.contrastive_mode == 'evidence':
            query = tokens(self.task.goal + ' ' + str(self.last_feedback)[:1500])
            def rank(row):
                changed = any(dependencies.get(p, 'unknown') != state for p, state in row['dependencies'].items())
                return (len(query & tokens(row['command']+' '+row['observation'])), not changed, row['index'])
            selected = sorted(self.contrastive_failures, key=rank, reverse=True)[:3]
        self.contrastive_visible_anchors = selected
        current = self.contrastive_episode
        return dict(active=current is not None, mode=self.config.contrastive_mode,
            phase=current['phase'] if current else 'inactive',
            episode_id=current['id'] if current else None, threshold=self.config.contrastive_threshold,
            negative_anchors=[dict(id=a['id'], command=a['command'][:1300],
                observation=a['observation'][:350], evidence_id=a['evidence_id'],
                scope_matches=scope == a['scope'], targets=list(a['dependencies']),
                condition_status='historical_external_state_unverified',
                memory_ids=a['memory_ids'], hypothesis=a['hypothesis'], status=a['status']) for a in selected],
            model_claims_are_not_proof=True, regeneration_counts_as_model_request=True)

    def _contrastive_before(self, action):
        if not self.contrastive_episode or action['action'] != 'run':
            return None
        e = self.contrastive_episode
        try:
            if self.config.contrastive_mode == 'orthogonal':
                audit, reason = validate_orthogonal(action, self.contrastive_visible_anchors,
                                                    self.config.contrastive_threshold)
            else:
                audit, reason = validate_evidence(action, self.contrastive_visible_anchors,
                    self.last_panel_scope, self.last_panel_dependencies, self.visible_evidence,
                    e['phase'], self.contrastive_external_retries)
        except ValueError as error:
            audit, reason = dict(policy=self.config.contrastive_mode), str(error)
        self.counts['contrastive_proposals'] += 1
        self._emit('contrastive_validation', episode_id=e['id'], accepted=reason is None,
                   action=self._action_core(action), audit=audit, reason=reason)
        if reason:
            self.counts['contrastive_rejections'] += 1
            # These are bounded by the EXISTING consecutive-error/request budgets.
            raise ValueError('contrastive rejection: '+reason)
        self.counts['contrastive_accepted'] += 1
        self.contrastive_pending = dict(episode_id=e['id'], action_key=action_key(action), audit=audit)
        # Advance only after actual execution, not after admission/reminder.
        return audit

    def _contrastive_outcome(self, action, row, assessment):
        if self.config.contrastive_mode == 'off':
            return
        pending = self.contrastive_pending
        self.contrastive_pending = None
        if pending and pending['action_key'] == action_key(action):
            audit = pending['audit']
            prediction = 'unknown'
            if self.config.contrastive_mode == 'evidence':
                self.contrastive_external_retries.update(audit['retry_signatures'])
                chosen = audit['selected']
                output = row['stdout']+'\n'+row['stderr']
                supports, refutes = chosen['supports'] in output, chosen['refutes'] in output
                if not (row['capture_incomplete'] or row['terminal_projection_incomplete']
                        or row['timed_out'] or row['blocked']) and supports != refutes:
                    prediction = 'supported_observation' if supports else 'refuted_observation'
            self._emit('contrastive_outcome', episode_id=pending['episode_id'], evidence_id=row['id'],
                command_key=action_key(action), prediction=prediction,
                workspace_changed=row['before'] != row['after'],
                execution_clean=assessment['execution_clean'], check_status=assessment['check_status'],
                task_success=None, causal_hypothesis_verified=False)
            self.counts['contrastive_observations'] += 1
            self.counts['contrastive_informative_predictions'] += int(prediction != 'unknown')
            self.contrastive_episode['phase'] = 'followup'
        failed = (row['return_code'] != 0 or row['timed_out'] or row['blocked']
                  or assessment.get('check_status') == 'public_check_failed')
        no_match = row['category'] == 'search' and row['return_code'] == 1 and not row['stderr']
        if failed and not no_match and not row['capture_incomplete'] and not row['terminal_projection_incomplete']:
            self.counts['contrastive_failure_records'] += 1
            index = self.counts['contrastive_failure_records']
            chosen = (pending or {}).get('audit', {}).get('selected', {})
            memory_ids = [m['id'] for m in self.memory.items.values() if row['id'] in m['evidence_ids']]
            declared = getattr(self.environment, 'contrastive_dependencies', None)
            relevant = declared(action) if callable(declared) else dependency_paths(action)
            self.contrastive_failures.append(dict(id='F'+str(index), index=index,
                command=command_text(action), command_key=action_key(action), scope=row['after'],
                dependencies={p: row.get('dependency_after', {}).get(p, 'unknown') for p in relevant}, evidence_id=row['id'],
                observation=(row['stderr'] or row['stdout'])[:600], memory_ids=memory_ids,
                hypothesis=chosen.get('hypothesis', 'unknown'), status='observed_failure_not_causal_exclusion'))
            self.contrastive_failures = self.contrastive_failures[-self.config.max_memories:]
            self.log.save('exploration-memory.json', self.contrastive_failures)
        episode = self.contrastive_episode
        if episode:
            verified = (action_key(action) in episode['baseline_keys'] and not failed
                        and not row['capture_incomplete'] and not row['terminal_projection_incomplete']
                        and row['before'] == row['after'] and assessment['execution_clean'])
            if verified or self.counts['tool_calls']-episode['start_tool'] >= self.config.contrastive_episode_tools:
                self._emit('contrastive_episode_end', episode_id=episode['id'],
                    reason='original_check_completed_cleanly' if verified else 'episode_tool_cap', task_success=None)
                self.contrastive_episode = None
                self.contrastive_last_end = self.counts['tool_calls']
        elif (self.failure_streak >= self.config.contrastive_trigger_failures
                and self.counts['tool_calls']-self.contrastive_last_end >= 4
                and self.contrastive_failures):
            self.counts['contrastive_episodes'] += 1
            self.contrastive_episode = dict(id='X'+str(self.counts['contrastive_episodes']), phase='plan',
                start_tool=self.counts['tool_calls'], baseline_keys={self.contrastive_failures[-1]['command_key']})
            self._emit('contrastive_episode_start', episode_id=self.contrastive_episode['id'],
                trigger='repeated_observed_failure', policy=self.config.contrastive_mode,
                baseline_keys=sorted(self.contrastive_episode['baseline_keys']))
