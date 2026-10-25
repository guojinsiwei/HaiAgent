/** Instrument official DSH extension points; enforce only experiment budgets. */
import { appendFileSync, existsSync, mkdirSync, readFileSync, readdirSync, lstatSync } from 'node:fs';
import { createHash } from 'node:crypto';
import path from 'node:path';

export const name = 'longcli-experiment-budget';

function fingerprint(root) {
  const hash = createHash('sha256');
  let files = 0;
  let bytes = 0;
  function walk(dir) {
    for (const filename of readdirSync(dir).sort()) {
      if (['.git', 'node_modules', '__pycache__', '.pytest_cache', 'test_output'].includes(filename)) continue;
      const full = path.join(dir, filename);
      const stat = lstatSync(full);
      if (stat.isSymbolicLink()) continue;
      if (stat.isDirectory()) walk(full);
      else if (stat.isFile()) {
        files += 1;
        bytes += stat.size;
        if (files > 50000 || bytes > 256 * 1024 * 1024) throw new Error('snapshot bound');
        hash.update(path.relative(root, full));
        hash.update('\0');
        hash.update(readFileSync(full));
      }
    }
  }
  try { walk(root); return hash.digest('hex'); } catch { return null; }
}

export function apply(ctx) {
  const root = process.env.LONGCLI_WORKSPACE ?? '/app';
  const auditDir = process.env.LONGCLI_AUDIT ?? '/audit';
  mkdirSync(auditDir, { recursive: true });
  const log = path.join(auditDir, 'events.jsonl');
  let requests = 0;
  let modelStreams = 0;
  let tools = 0;
  let sequence = 0;
  const decisions = new Set();
  const attempts = new Map();
  const currentBySession = new Map();
  let verifiedConfiguration = false;
  const record = (data) => appendFileSync(log, JSON.stringify({ time: new Date().toISOString(), ...data }) + '\n');
  record({ event: 'boot', workspace: root, fresh_home: !existsSync('/dsh-home/sessions'), keyless_instrumentation: true });
  ctx.on('session/event', (_session, event) => {
    if (event.type.startsWith('compaction/')) record({ event: 'native_compaction', type: event.type });
  });
  ctx.on('agent/request', async (payload, next) => {
    if (!verifiedConfiguration) {
      const compaction = ctx.get('compaction')?.config;
      const pruner = ctx.get('toolResultPruner')?.config;
      if (compaction?.thresholdRatio !== 0.008 || compaction?.retainTokens !== 0 || compaction?.maxTokens !== 4096
          || pruner?.thresholdChars !== 6000 || pruner?.headChars !== 2000 || pruner?.tailChars !== 1000) {
        record({ event: 'configuration_failure', compaction, pruner });
        throw new Error('LONGCLI_NATIVE_BUDGET_CONFIGURATION_NOT_APPLIED');
      }
      record({ event: 'configuration_verified', threshold_ratio: compaction.thresholdRatio,
        retain_tokens: compaction.retainTokens, summary_max_tokens: compaction.maxTokens,
        prune_threshold_chars: pruner.thresholdChars, prune_head_chars: pruner.headChars, prune_tail_chars: pruner.tailChars });
      verifiedConfiguration = true;
    }
    const decision = JSON.stringify([payload.agent?.id, payload.turn, payload.step]);
    if (!decisions.has(decision) && requests >= 800 || tools >= 600) {
      record({ event: 'budget_stop', reason: tools >= 600 ? 'tool_budget' : 'model_budget' });
      throw new Error('LONGCLI_DECISION_BUDGET');
    }
    currentBySession.set(payload.agent?.id, decision);
    if (!decisions.has(decision)) {
      decisions.add(decision);
      requests += 1;
    }
    record({ event: 'request', requests, agent: payload.agent?.id, turn: payload.turn, step: payload.step });
    return { ...(await next()), temperature: 0, maxTokens: 4096, reasoningEffort: 'off' };
  });
  // Includes native title/compaction calls and subagents. A failed stream retry
  // also consumes this hard API ceiling, rather than silently adding spend.
  ctx.on('llm/stream', async function* (options, next) {
    // Root retry chains share one logical request; auxiliary native calls are
    // separate logical requests and consume the same global 800 allowance.
    if (options.purpose && requests >= 800 || modelStreams >= 1600) {
      record({ event: 'budget_stop', reason: 'model_budget' });
      throw new Error('LONGCLI_MODEL_BUDGET');
    }
    modelStreams += 1;
    if (options.purpose) requests += 1;
    else {
      const decision = currentBySession.get(options.sessionId);
      if (!decision) throw new Error('LONGCLI_MISSING_REQUEST_ID');
      attempts.set(decision, (attempts.get(decision) ?? 0) + 1);
      if (attempts.get(decision) > 2) throw new Error('LONGCLI_WIRE_ATTEMPT_BUDGET');
    }
    // Options are immutable in official DSH. Actor config above and the relay
    // enforce the cap; native auxiliary config already requests smaller outputs.
    record({ event: 'model_stream', model_streams: modelStreams, logical_requests: requests, purpose: options.purpose, model: options.model,
      requested_max_tokens: options.maxTokens });
    yield* next();
  });
  ctx.on('tools/execute', async (exec, next) => {
    // Nested calls are recorded separately, but consume their owning root admission.
    const nested = Boolean(exec.parent);
    if (!nested && tools >= 600) {
      record({ event: 'budget_stop', reason: 'tool_budget' });
      throw new Error('LONGCLI_TOOL_BUDGET');
    }
    if (!nested) tools += 1;
    const seq = ++sequence;
    const before = fingerprint(root);
    record({ event: 'tool_start', seq, tools, nested, name: exec.name, arguments: exec.arguments, workspace_before: before });
    const upstream = exec.signal;
    exec.signal = AbortSignal.any([upstream, AbortSignal.timeout(300000)]);
    try {
      const result = await next();
      record({ event: 'tool_result', seq, tools, nested, name: exec.name, arguments: exec.arguments,
        result, workspace_before: before, workspace_after: fingerprint(root) });
      return result;
    } catch (error) {
      record({ event: 'tool_exception', seq, name: exec.name, error_type: error?.name, message: String(error?.message ?? error).slice(0, 500) });
      throw error;
    } finally { exec.signal = upstream; }
  });
}
