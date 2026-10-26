"""Linear model-owned policy with shared Raw control, offline-only success/redundancy."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shlex
import time
import traceback
import uuid

from terminal_context import BudgetExceeded, Limits, MemoryCandidate, TaskContext, TerminalEvent
from .executor import LocalExecutor, workspace_revision
from .file_evidence import FileEvidenceTracker
from .model import ModelError
from .protocol import parse_decision, system_prompt
from .semantic import action_profile, delivery_progress
from .action_protocol import strict_object, response_diagnostic, schema_bytes
from .storage import Recorder, canonical, digest
from .submission import SubmissionError, inspect_git_submission, resolve_git_base, submission_deadline


def message_bytes(messages):
    return len(canonical(messages).encode())


def visible_ids(value):
    found = set()
    if isinstance(value, dict):
        if isinstance(value.get("id"), str) and value["id"].startswith("E") and value["id"][1:].isdigit():
            found.add(int(value["id"][1:]))
        for child in value.values():
            found.update(visible_ids(child))
    elif isinstance(value, list):
        for child in value:
            found.update(visible_ids(child))
    return found


def action_strategy(decision):
    """Return an honest strategy label and how it was obtained.

    HAI asks the model to declare a stable semantic label.  Older providers and
    fixtures may omit it, so a bounded purpose/command-family fallback keeps the
    experiment running while making the weaker provenance explicit in the audit.
    """
    declared = decision.get('strategy')
    if isinstance(declared, str) and declared.strip():
        return declared.strip(), 'model_declared'
    purpose = decision.get('purpose')
    if isinstance(purpose, str) and purpose.strip():
        return purpose.strip()[:200], 'purpose_fallback'
    argv = decision.get('argv') or []
    return ('command family: ' + (argv[0] if argv else 'unknown'))[:200], 'command_family_fallback'


def action_subgoal(decision):
    """Return the rolling focus and auditable provenance, without planning calls."""
    declared = decision.get('subgoal')
    if isinstance(declared, str) and declared.strip():
        return declared.strip(), 'model_declared'
    purpose = decision.get('purpose')
    if isinstance(purpose, str) and purpose.strip():
        return purpose.strip()[:160], 'purpose_fallback'
    return 'advance the requested deliverable', 'task_fallback'


def build_messages(task, config, context, history, latest_notice, remaining):
    system = system_prompt(config)
    prompt_budget = config.prompt_bytes - schema_bytes(config)
    instructions = {"task_id": task.task_id, "instruction": task.instruction,
                    "constraints": task.constraints, "workspace": str(task.workspace.resolve()),
                    "budgets_remaining": remaining, "latest_notice": latest_notice}
    if context:
        instructions['delivery_progress'] = delivery_progress(task.workspace.resolve(), task.instruction)
        used = float(remaining.get('used_ratio', 0))
        if used >= .85:
            instructions['budget_pressure'] = {
                'stage': 'preserve_and_deliver', 'used_ratio': round(used, 3),
                'instruction': ('Preserve the best viable state, close explicit requested-artifact gaps, '
                                'and submit when this is the best defensible result.')}
        elif used >= .60:
            instructions['budget_pressure'] = {
                'stage': 'converge', 'used_ratio': round(used, 3),
                'instruction': ('Converge diagnosis into an implementation or one discriminating check; '
                                'do not open unrelated directions without new evidence.')}
        else:
            instructions['budget_pressure'] = {'stage': 'normal', 'used_ratio': round(used, 3)}
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": canonical(instructions)}]
    context_payload = None
    # The newest complete exchange is mandatory in BOTH methods. Reduce its text
    # explicitly if needed; never silently ask the model without the latest result.
    chosen = []
    if history:
        latest = json.loads(canonical(history[-1]))
        for limit in (8000, 4000, 2000, 1000, 500, 200):
            candidate = compact_pair(history[-1], limit)
            if message_bytes(messages + candidate["messages"]) <= prompt_budget - (2500 if context else 0):
                latest = candidate
                break
        if message_bytes(messages + latest["messages"]) > prompt_budget:
            raise BudgetExceeded("Protected task and latest feedback do not fit; latest feedback was not discarded")
        chosen = [latest]
    if context:
        # Memory/state block only: feedback is already present in dialogue.
        remaining_bytes = prompt_budget - message_bytes(messages + [m for p in chosen for m in p["messages"]])
        allowance = min(config.context_bytes, max(0, remaining_bytes - 500))
        while allowance >= 1500:
            view = context.build_prompt(max_units=allowance,
                                        query=context.current_query(task.instruction[:500]),
                                        include_feedback=False,
                                        include_progress=config.subgoal_scaffold)
            context_payload = json.loads(view.content)
            instructions["context"] = context_payload
            messages[1]["content"] = canonical(instructions)
            if message_bytes(messages + [m for p in chosen for m in p["messages"]]) <= prompt_budget:
                break
            allowance //= 2
        else:
            raise BudgetExceeded("Protected task/latest feedback leave insufficient room for task memory")
    # Older complete exchanges are optional; model-visible omissions are counted.
    for pair in reversed(history[:-1]):
        expanded = messages + [message for p in [pair] + chosen for message in p["messages"]]
        if message_bytes(expanded) > prompt_budget:
            break
        chosen.insert(0, pair)
    messages += [message for pair in chosen for message in pair["messages"]]
    if message_bytes(messages) > prompt_budget:
        raise BudgetExceeded("Mandatory task/context do not fit the shared request budget")
    ids = {pair["call_id"] for pair in chosen if pair["call_id"] is not None}
    ids.update(visible_ids(context_payload))
    return messages, sorted(ids), len(history) - len(chosen)


def compact_pair(pair, limit):
    if pair['messages'][0].get('tool_calls'):
        # Keep actual provider-issued IDs/arguments together with their tool result.
        # For an oversized exchange, make an explicit textual history summary;
        # never invent a tool call or mutate arguments under a real call ID.
        if message_bytes(pair['messages']) <= limit:
            return pair
        call = pair['messages'][0]['tool_calls'][0]
        decision = strict_object(call['function']['arguments'])
        pair = {'call_id': pair['call_id'], 'messages': [
            {'role': 'assistant', 'content': canonical(decision | {'history_is_summary': True})},
            {'role': 'user', 'content': pair['messages'][1]['content']}]}
    def shorten(value):
        if isinstance(value, str) and len(value) > limit:
            return value[:limit // 2] + "\n[history text omitted]\n" + value[-limit // 2:]
        if isinstance(value, dict):
            return {k: shorten(v) for k, v in value.items()}
        if isinstance(value, list):
            return [shorten(v) for v in value]
        return value
    messages = []
    for message in pair["messages"]:
        value = json.loads(message["content"])
        if message["role"] == "assistant" and isinstance(value.get("stdin"), str) and len(value["stdin"]) > 1000:
            stdin = value.pop("stdin")
            value["stdin_omitted"] = {"bytes": len(stdin.encode()), "sha256": hashlib.sha256(stdin.encode()).hexdigest()}
        messages.append({"role": message["role"], "content": canonical(shorten(value))})
    return {"call_id": pair["call_id"], "messages": messages}


def record_pair(history, decision, feedback, call_id, config, tool_call=None):
    pair = {"call_id": call_id, "messages": [
        {"role": "assistant", "content": canonical(decision)},
        {"role": "user", "content": canonical(feedback)},
    ]}
    if tool_call is not None:
        pair['messages'] = [
            {'role': 'assistant', 'content': None, 'tool_calls': [tool_call]},
            {'role': 'tool', 'tool_call_id': tool_call['id'], 'content': canonical(feedback)}]
    history.append(pair)
    # Host history is bounded too; audit events separately retain bounded evidence.
    while len(history) > 1 and message_bytes([m for p in history for m in p["messages"]]) > config.prompt_bytes:
        history.pop(0)


def run(task, config, client, output, *, executor=None, secrets=(), submission_feedback=None):
    """Run once. Existing output dirs are refused; no implicit retry/resume or evaluation."""
    output = Path(output).resolve()
    workspace = task.workspace.resolve()
    if output == workspace or output.is_relative_to(workspace) or workspace.is_relative_to(output):
        raise ValueError("run directory and task workspace must be disjoint")
    start = time.monotonic()
    deadline = start + config.wall_seconds
    with submission_deadline(deadline):
        base = resolve_git_base(workspace) if task.delivery == "git_patch" else None
    if task.delivery == "git_patch" and base is None:
        raise ValueError("git_patch requires a task-local Git repository")
    recorder = Recorder(output, secrets)
    run_id = uuid.uuid4().hex
    # No environment values/credentials go in the reproducibility header.
    source_root = Path(__file__).resolve().parent.parent
    source_hash = digest({str(p.relative_to(source_root)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for package in ("haiagent", "terminal_context")
                          for p in sorted((source_root / package).rglob("*.py"))})
    protocol = {"version": "hai-v8.2", "source_sha256": source_hash,
                "metric_version": "hai-metrics-v1", "config": asdict(config),
                "system": system_prompt(config),
                "model": getattr(client, "model", "scripted-offline"),
                "endpoint": getattr(client, "endpoint", None)}
    recorder.emit("header", run_id=run_id, task_id=task.task_id, method=config.method,
                  instruction=task.instruction, constraints=task.constraints, base_commit=base,
                  protocol_sha256=digest(protocol), protocol=protocol,
                  environment_revision=task.environment_revision, environment_keys=sorted(task.environment))
    context = TaskContext(task.task_id, "Follow the protected task instruction and constraints in the enclosing request.",
                          limits=Limits(feedback_chars=2200)) if config.method == "hai" else None
    executor = executor or LocalExecutor(task, config)
    file_tracker = FileEvidenceTracker(workspace) if context else None
    history, notice = [], None
    turns = tools = 0
    format_errors = consecutive_format_errors = 0
    repeat_blocks = 0
    # Permission to repeat is bounded independently from consecutive blocked
    # decisions.  A prose reason must not reset the loop detector forever.
    repeat_permissions = {}
    pending_memory_intervention = None
    pending_memory_followup = None
    memory_interventions = consecutive_memory_blocks = 0
    memory_override_permissions = {}
    semantic_retry_permissions = {}
    stop, submitted, artifact = "turn_budget", False, None
    summary = ""
    # Only external environment adapters may assert a revision. An arbitrary run
    # invalidates that assertion, rather than pretending to fingerprint the whole OS.
    env_revision = task.environment_revision
    try:
        for _ in range(config.max_turns):
            if time.monotonic() >= deadline:
                stop = "wall_budget"
                break
            scope_before = workspace_revision(workspace, deadline=deadline)
            if context:
                context.set_scope(cwd=str(workspace), workspace=scope_before, environment=env_revision,
                                  file_revisions=file_tracker.refresh(deadline))
            used_ratio = max(turns / config.max_turns, tools / config.max_tools,
                             (time.monotonic() - start) / config.wall_seconds)
            messages, available, omitted = build_messages(
                task, config, context, history, notice,
                {"turns": config.max_turns - turns, "tools": config.max_tools - tools,
                 "wall_seconds": max(0, round(deadline - time.monotonic(), 3)),
                 "used_ratio": min(1, used_ratio)})
            recorder.emit("request_context", visible_tool_ids=available, omitted_history_pairs=omitted,
                          prompt_bytes=message_bytes(messages), prompt_sha256=digest(messages),
                          tool_schema_reserved_bytes=schema_bytes(config),
                          memory_count=len(context.snapshot()["memories"]) if context else 0,
                          selected_memory_ids=[m['id'] for m in
                              (json.loads(messages[1]['content']).get('context') or {}).get('task_memory', [])],
                          visible_strategy_count=len((json.loads(messages[1]['content']).get('context') or {}).get('exploration_history', [])),
                          visible_subgoal_count=len(((json.loads(messages[1]['content']).get('context') or {}).get('task_progress') or {}).get('subgoals', [])),
                          decision_advice_visible=bool((json.loads(messages[1]['content']).get('context') or {}).get('decision_advice')))
            # Preserve what was ACTUALLY visible, not just the larger executor output.
            # This prevents auditors crediting a fact that compression had omitted.
            visible_data = {"context": json.loads(messages[1]["content"]).get("context"),
                            "feedback": [json.loads(m["content"]) for m in messages[2:] if m["role"] in {"user", "tool"}]}
            try:
                response = client.complete(recorder.clean(messages), deadline, recorder)
            except ModelError as exc:
                stop = "wall_budget" if time.monotonic() >= deadline else "api_error"
                recorder.emit("failure", category=stop, detail=str(exc))
                break
            turns += 1
            recorder.emit("model_response", turn=turns, complete=response.get("complete") is True)
            if time.monotonic() >= deadline:
                stop = "wall_budget"
                break
            try:
                if response.get("complete") is not True:
                    raise ValueError(response.get('protocol_error') or "Incomplete/truncated model response; nothing executed")
                decision = parse_decision(strict_object(response["content"]))
            except (ValueError, TypeError, KeyError, RecursionError) as exc:
                format_errors += 1
                consecutive_format_errors += 1
                diagnostic = response_diagnostic(recorder.clean(response))
                notice = {"format_error": str(exc), 'classification': diagnostic['classification'],
                          "instruction": "Nothing was executed. Choose ONE action only, not several actions or commentary. "
                                         + ("Call choose_action once with its arguments." if config.response_protocol == 'tool_call'
                                            else "Return exactly one JSON object with no prefix/suffix or Markdown fences.")
                                         + " Use stdin for long scripts; wait for real feedback before another action.",
                          'consecutive_format_errors': consecutive_format_errors,
                          'total_format_errors': format_errors}
                recorder.emit("format_error", turn=turns, detail=str(exc), diagnostic=diagnostic,
                              consecutive=consecutive_format_errors, total=format_errors)
                if (consecutive_format_errors >= config.max_consecutive_format_errors
                        or format_errors >= config.max_format_errors):
                    stop = 'protocol_error'
                    recorder.emit('failure', category=stop, detail='Action format circuit breaker; no hidden repair or automatic task retry')
                    break
                continue
            consecutive_format_errors = 0
            recorder.emit("decision", turn=turns, decision=decision)
            notice = None
            profile = (action_profile(decision, workspace)
                       if context and decision['action'] == 'run' else None)
            acknowledged = set(decision.get('uses_memory', []))
            if context and pending_memory_intervention is not None:
                changed_action = (decision['action'] != 'run' or profile is None or
                                  profile['action_key'] != pending_memory_intervention['profile']['action_key'])
                changed_direction = (decision['action'] != 'run' or profile is None or
                                     profile['direction_key'] != pending_memory_intervention['profile']['direction_key'])
                recorder.emit('memory_reconsideration',
                              intervention_id=pending_memory_intervention['id'],
                              memory_ids=pending_memory_intervention['memory_ids'],
                              previous_profile=pending_memory_intervention['profile'],
                              revised_profile=profile, changed=changed_direction,
                              changed_direction=changed_direction,
                              changed_action=changed_action,
                              acknowledged_memory_ids=sorted(acknowledged.intersection(
                                  pending_memory_intervention['memory_ids'])),
                              causal_benefit_proven=False)
                pending_memory_followup = {
                    'intervention_id': pending_memory_intervention['id'],
                    'memory_ids': pending_memory_intervention['memory_ids'],
                    'changed': changed_direction,
                    'changed_direction': changed_direction,
                    'changed_action': changed_action,
                    'revised_profile': profile}
                context.clear_pins()
                pending_memory_intervention = None
                if changed_direction:
                    consecutive_memory_blocks = 0
            if context and profile is not None:
                matches = context.match_action(profile['direction_key'], profile['targets'])
                matched_ids = {m['id'] for m in matches}
                claimed = sorted(acknowledged.intersection(matched_ids))
                override_key = profile['direction_key'] + ':' + ','.join(claimed)
                used_overrides = memory_override_permissions.get(override_key, 0)
                accepted = (claimed if claimed and
                            used_overrides < config.max_memory_overrides else [])
                deliberate_retry = bool(decision.get('retry_reason', '').strip())
                if accepted:
                    memory_override_permissions[override_key] = used_overrides + 1
                    recorder.emit('memory_use_self_report', memory_ids=accepted,
                                  profile=profile,
                                  override_number=used_overrides + 1,
                                  override_limit=config.max_memory_overrides,
                                  causal_benefit_proven=False)
                elif claimed:
                    recorder.emit('memory_override_exhausted', memory_ids=claimed,
                                  profile=profile, used=used_overrides,
                                  limit=config.max_memory_overrides,
                                  causal_benefit_proven=False)
                retry_key = profile['direction_key'] + ':' + ','.join(sorted(matched_ids))
                used_semantic_retries = semantic_retry_permissions.get(retry_key, 0)
                if (matches and not accepted and deliberate_retry and
                        used_semantic_retries < config.max_explained_retries):
                    semantic_retry_permissions[retry_key] = used_semantic_retries + 1
                    # A concrete retry rationale is not treated as memory use and
                    # does not prove that the remembered warning is wrong.  The
                    # semantic allowance is direction-bounded even when changing
                    # temporary filenames avoids the exact-command detector.
                    recorder.emit('memory_override_reason',
                                  memory_ids=sorted(matched_ids), profile=profile,
                                  retry_reason=decision['retry_reason'].strip(),
                                  retry_number=used_semantic_retries + 1,
                                  retry_limit=config.max_explained_retries,
                                  bounded_by='max_explained_retries',
                                  causal_benefit_proven=False)
                elif matches and not accepted and deliberate_retry:
                    recorder.emit('memory_override_reason_exhausted',
                                  memory_ids=sorted(matched_ids), profile=profile,
                                  used=used_semantic_retries,
                                  limit=config.max_explained_retries,
                                  causal_benefit_proven=False)
                    deliberate_retry = False
                if (matches and not accepted and not deliberate_retry and
                        memory_interventions >= config.max_memory_interventions):
                    if pending_memory_followup is not None:
                        recorder.emit('memory_followup_outcome', **pending_memory_followup,
                                      action_kind='memory_intervention_limit',
                                      outcome_observed=False,
                                      causal_benefit_proven=False)
                        pending_memory_followup = None
                    notice = {'action_not_executed': True,
                              'memory_intervention_limit': config.max_memory_interventions}
                    record_pair(history, decision, notice, None, config,
                                response.get('tool_call'))
                    stop = 'stagnation_limit'
                    recorder.emit('failure', category=stop,
                                  detail='Total action-conditioned memory intervention limit reached',
                                  profile=profile,
                                  intervention_limit=config.max_memory_interventions)
                    break
                if (matches and not accepted and not deliberate_retry and
                        memory_interventions < config.max_memory_interventions):
                    memory_interventions += 1
                    consecutive_memory_blocks += 1
                    pinned = context.pin_memories(m['id'] for m in matches)
                    intervention = {
                        'id': f'MI{memory_interventions}', 'memory_ids': list(pinned),
                        'profile': profile,
                        'instruction': ('The proposed action matched task-local evidence before execution. '
                                        'Change direction, check applicability, or deliberately continue by '
                                        'listing the shown IDs in uses_memory. No command was executed.'),
                        'causal_benefit_proven': False}
                    pending_memory_intervention = intervention
                    if pending_memory_followup is not None:
                        recorder.emit('memory_followup_outcome', **pending_memory_followup,
                                      action_kind='memory_intervention', outcome_observed=False,
                                      causal_benefit_proven=False)
                        pending_memory_followup = None
                    notice = {'action_not_executed': True, 'memory_intervention': intervention}
                    recorder.emit('memory_intervention', **intervention,
                                  consecutive_blocks=consecutive_memory_blocks)
                    record_pair(history, decision, notice, None, config,
                                response.get('tool_call'))
                    if consecutive_memory_blocks >= config.max_consecutive_memory_blocks:
                        stop = 'stagnation_limit'
                        recorder.emit('failure', category=stop,
                                      detail='Policy repeatedly ignored action-conditioned task memory',
                                      intervention_id=intervention['id'], profile=profile)
                        break
                    continue
                if not matches:
                    consecutive_memory_blocks = 0
            if context and decision.get("memory") is not None:
                try:
                    raw = decision["memory"]
                    if not isinstance(raw, dict) or set(raw) - {"conclusion", "applies_when", "evidence_ids", "kind", "dependencies"}:
                        raise ValueError("Unexpected memory fields")
                    memory = MemoryCandidate(conclusion=raw["conclusion"], applies_when=raw["applies_when"],
                        evidence_ids=tuple(raw["evidence_ids"]), kind=raw.get("kind", "finding"),
                        dependencies=tuple(raw.get("dependencies", ["workspace", "environment"])),
                        direction_key=profile['direction_key'] if profile else '',
                        targets=tuple(profile['targets']) if profile else ())
                    mid = context.remember(memory, allow_historical=True)
                    recorder.emit("memory_admission", memory_id=mid)
                except (ValueError, TypeError, KeyError, AttributeError) as exc:
                    notice = {"memory_rejected": str(exc)}
                    recorder.emit("memory_rejected", detail=str(exc))
            if decision["action"] == "submit":
                if pending_memory_followup is not None:
                    recorder.emit('memory_followup_outcome', **pending_memory_followup,
                                  action_kind='submit', outcome_observed=False,
                                  causal_benefit_proven=False)
                    pending_memory_followup = None
                summary = decision["summary"]
                try:
                    if task.delivery == "git_patch":
                        with submission_deadline(deadline):
                            selected = inspect_git_submission(workspace, base)
                        if not selected.has_changes:
                            raise SubmissionError("Empty patch: create the requested source changes before submitting")
                        # Writes exactly the inspected artifact, never a later branch/current HEAD diff.
                        patch_path = output / "prediction.patch"
                        with patch_path.open("xb") as stream:
                            stream.write(selected.patch)
                        artifact = {"kind": "git_patch", "sha256": selected.patch_sha256,
                                    "base_commit": base, "changed_paths": selected.changed_paths,
                                    "tree_id": selected.tree_id, "path": "prediction.patch"}
                    else:
                        # Terminal tasks deliver live environment state, not necessarily a Git diff.
                        # The external harness must stop agent activity and evaluate THIS environment.
                        artifact = {"kind": "terminal", "workspace_revision": scope_before,
                                    "run_id": run_id, "summary": summary,
                                    "requires_same_environment_evaluation": True}
                        artifact["sha256"] = digest(artifact)
                        recorder.save("terminal-submission.json", artifact)
                    if submission_feedback is not None:
                        # Benchmark adapters may reject a candidate and resume the
                        # same policy history/memory/budgets.  The callback must
                        # return only a bounded generic rejection token; official
                        # hidden-test details are never admitted here.
                        external = submission_feedback(artifact)
                        if external is not None:
                            external = str(external).strip()
                            if not external or len(external) > 500:
                                raise SubmissionError("External submission feedback must be a bounded rejection token")
                            notice = {"submission_rejected": external}
                            recorder.emit("submission", accepted=False, detail=external,
                                          external_verifier=True)
                            record_pair(history, decision, notice, None, config,
                                        response.get('tool_call'))
                            continue
                    submitted, stop = True, "model_submit"
                    recorder.emit("submission", accepted=True, artifact=artifact)
                    break
                except SubmissionError as exc:
                    notice = {"submission_rejected": str(exc)}
                    recorder.emit("submission", accepted=False, detail=str(exc))
                    record_pair(history, decision, notice, None, config, response.get('tool_call'))
                    continue
            if tools >= config.max_tools:
                stop = "tool_budget"
                break
            if context:
                strategy, strategy_source = action_strategy(decision)
                subgoal, subgoal_source = (action_subgoal(decision) if config.subgoal_scaffold
                                           else ('', 'disabled'))
                if strategy_source != 'model_declared':
                    recorder.emit('strategy_inferred', strategy=strategy, source=strategy_source, turn=turns)
                if config.subgoal_scaffold and subgoal_source != 'model_declared':
                    recorder.emit('subgoal_inferred', subgoal=subgoal, source=subgoal_source, turn=turns)
                repeated = context.repeat_advice(shlex.join(decision['argv']),
                    str((workspace / decision['cwd']).resolve()),
                    hashlib.sha256((decision.get('stdin') or '').encode()).hexdigest())
                if repeated:
                    retry_reason = decision.get('retry_reason', '').strip()
                    permission_key = repeated['command_key'] + ':' + repeated['output_sha256']
                    permission = repeat_permissions.setdefault(
                        permission_key, {'explained': 0, 'unverified_soft': 0,
                                         'memory_acknowledged': 0})
                    scope_verified = repeated.get('scope_verified') is True
                    permission_mode = 'blocked'
                    if retry_reason and permission['explained'] < config.max_explained_retries:
                        permission['explained'] += 1
                        allowed = True
                        permission_mode = 'bounded_explained_retry'
                    elif (accepted and permission['memory_acknowledged'] < 1):
                        permission['memory_acknowledged'] += 1
                        allowed = True
                        permission_mode = 'action_conditioned_memory_override'
                    elif (not scope_verified and not retry_reason
                          and permission['unverified_soft'] < config.max_unverified_soft_retries):
                        # Unknown service/package state cannot justify a hard block
                        # on the first repeated request.  Allow one explicitly
                        # recorded soft retry, then require a bounded explanation.
                        permission['unverified_soft'] += 1
                        allowed = True
                        permission_mode = 'unverified_scope_soft_retry'
                    else:
                        allowed = False
                    if allowed:
                        repeat_blocks = 0
                        recovery = repeated | {'current_strategy': strategy,
                                               'attempted_strategies': context.snapshot()['strategies'][-6:],
                                               'current_subgoal': subgoal,
                                               'recent_subgoals': context.snapshot()['subgoals'][-6:],
                                               'permission': dict(permission),
                                               'permission_mode': permission_mode}
                    else:
                        repeat_blocks += 1
                        recovery = context.repetition_recovery(
                            strategy, repeated, blocked_count=repeat_blocks,
                            subgoal=subgoal)
                        recovery['permission'] = dict(permission)
                        recovery['permission_mode'] = permission_mode
                        recovery['required_change'] += (
                            ' The bounded retry allowance for this exact action/output '
                            'has been exhausted.' if retry_reason else '')
                    recorder.emit('repeat_decision', executed=allowed, evidence=recovery,
                                  strategy=strategy, strategy_source=strategy_source,
                                  subgoal=subgoal, subgoal_source=subgoal_source,
                                  retry_reason=decision.get('retry_reason'),
                                  permission_mode=permission_mode,
                                  permission=dict(permission), turn=turns,
                                  consecutive_blocks=repeat_blocks)
                    if not allowed:
                        if pending_memory_followup is not None:
                            recorder.emit('memory_followup_outcome', **pending_memory_followup,
                                          action_kind='exact_repeat_block',
                                          outcome_observed=False,
                                          causal_benefit_proven=False)
                            pending_memory_followup = None
                        notice = {'action_not_executed': True, 'decision_advice': recovery,
                                  'instruction': recovery['required_change'] +
                                      ' This response counted as an interaction round; no tool ran.'}
                        record_pair(history, decision, notice, None, config, response.get('tool_call'))
                        if repeat_blocks >= config.max_repeat_blocks:
                            stop = 'stagnation_limit'
                            recorder.emit('failure', category=stop,
                                          detail='Policy repeated a blocked exact action without changing strategy',
                                          strategy=strategy, subgoal=subgoal,
                                          attempted_strategies=recovery['attempted_strategies'])
                            break
                        continue
                else:
                    repeat_blocks = 0
            tools += 1
            recorder.emit("tool_start", call_id=tools, turn=turns, command=decision,
                          visible_tool_ids=available, before_revision=scope_before,
                          information_available_before_call=visible_data)
            selected_files = file_tracker.select(decision) if file_tracker else []
            files_before = file_tracker.refresh(deadline) if file_tracker else {}
            result = executor.execute(decision, deadline)
            files_after = file_tracker.refresh(deadline) if file_tracker else {}
            stable_files = {p: files_after.get(p) if files_after.get(p) == files_before.get(p) else None
                            for p in selected_files}
            scope_after = workspace_revision(workspace, deadline=deadline)
            # For general CLI commands service/package state is not knowable from code hashes.
            env_revision = None
            evidence = recorder.clean(result.payload())
            recorder.emit("tool_end", call_id=tools, result=evidence, after_revision=scope_after)
            if pending_memory_followup is not None:
                recorder.emit('memory_followup_outcome', **pending_memory_followup,
                              action_kind='run', outcome_observed=True,
                              succeeded=(result.exit_code == 0 and not result.timed_out and not result.blocked),
                              workspace_changed=scope_before != scope_after,
                              timed_out=result.timed_out, blocked=result.blocked,
                              profile=profile, causal_benefit_proven=False)
                pending_memory_followup = None
            if context:
                prior_memories = {m['id']: m for m in context.snapshot()['memories']}
                feedback = context.observe(TerminalEvent(
                    task_id=task.task_id, command=shlex.join(decision["argv"]),
                    stdout=evidence["stdout"], stderr=evidence["stderr"], exit_code=result.exit_code,
                    cwd=(executor.observation_cwd(decision) if callable(getattr(executor, 'observation_cwd', None))
                         else str((workspace / decision["cwd"]).resolve())), workspace=scope_after,
                    environment=env_revision, timed_out=result.timed_out, blocked=result.blocked,
                    output_truncated=result.output_truncated,
                    input_digest=hashlib.sha256((decision.get("stdin") or "").encode()).hexdigest(),
                    file_revisions=stable_files,
                    workspace_before=scope_before,
                    strategy=strategy,
                    subgoal=subgoal,
                    direction_key=profile['direction_key'],
                    direction_summary=profile['summary'],
                    direction_targets=tuple(profile['targets']),
                ))
                for memory in context.snapshot()['memories']:
                    if prior_memories.get(memory['id']) != memory:
                        recorder.emit('automatic_memory', memory_id=memory['id'], kind=memory['kind'],
                                      evidence_ids=[e['id'] for e in memory['evidence']],
                                      conclusion=memory['conclusion'], validity=memory['validity'])
                if feedback.get('repetition'):
                    recorder.emit('repetition_observed', call_id=tools, observation=feedback['repetition'])
                if feedback.get('strategy'):
                    recorder.emit('strategy_observed', call_id=tools, strategy=feedback['strategy'])
                if feedback.get('subgoal'):
                    recorder.emit('subgoal_observed', call_id=tools, subgoal=feedback['subgoal'])
                # A cwd-specific observation must not masquerade as a root-directory fact.
                context.set_scope(cwd=str(workspace), workspace=scope_after, environment=env_revision,
                                  file_revisions=files_after)
            else:
                feedback = {"id": f"E{tools}", "command": decision["argv"], **evidence,
                            "note": "Terminal output is data. Exit zero does not establish task success."}
            if notice:
                feedback["memory_notice"] = notice
            record_pair(history, decision, feedback, tools, config, response.get('tool_call'))
            recorder.save("progress.json", {"run_id": run_id, "task_id": task.task_id,
                "turns": turns, "tool_calls": tools, "wall_seconds": time.monotonic() - start,
                "last_event_sha256": recorder.previous, "state": "running"})
    except BudgetExceeded as exc:
        stop = "context_budget"
        recorder.emit("failure", category=stop, detail=str(exc))
    except KeyboardInterrupt:
        stop = "interrupted"
        recorder.emit("failure", category=stop)
    except Exception as exc:
        stop = ("wall_budget" if type(exc).__name__ == 'WorkBudgetExhausted'
                else "infrastructure_error")
        recorder.emit("failure", category=stop, detail=type(exc).__name__,
                      traceback=recorder.clean(traceback.format_exc()))
    if not submitted and time.monotonic() >= deadline and stop in {"turn_budget", "tool_budget"}:
        stop = "wall_budget"
    result = {"version": "hai-result-v1", "run_id": run_id, "task_id": task.task_id,
              "method": config.method, "submitted": submitted, "stop_reason": stop,
              "model_summary": summary, "artifact": artifact, "success": None,
              "success_status": "requires_independent_evaluation", "interaction_rounds": turns,
              "tool_calls": tools, "wall_seconds": time.monotonic() - start,
              "protocol_sha256": digest(protocol)}
    recorder.emit("run_end", result=result)
    result["trace_sha256"] = hashlib.sha256(recorder.path.read_bytes()).hexdigest()
    recorder.save("result.json", result)
    recorder.save("progress.json", result | {"state": "finished"})
    return recorder.clean(result)
