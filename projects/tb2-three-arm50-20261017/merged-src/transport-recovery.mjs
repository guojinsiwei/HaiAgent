// Shared harness compatibility layer, not a KZ exploration policy.
// DSH rc.2 settles failed streams BEFORE executing their tool calls. Recover
// only its exact malformed-tool-JSON error at the native request-error hook.
import { createUserMessage } from '@deepseek-ai/dsh-llm';
import { z } from 'zod';
import { randomUUID } from 'node:crypto';
import { appendFileSync } from 'node:fs';
import path from 'node:path';

export const name = 'tool-json-recovery';
export const inject = ['agents', 'sessionProjections'];
export const INVALID_TOOL_JSON = 'DeepSeek Messages stream: tool input is invalid JSON';
export const NOTICE = 'The last model response contained invalid JSON in tool arguments. No tool from that failed response was executed. Earlier completed actions and their results remain valid: do not repeat them. Regenerate the intended next action with complete valid JSON (escape quotes/newlines in string values). This is a response-format correction, not evidence that the task strategy failed.';

export function isToolJsonFailure(failure) {
  return failure?.code === 'MALFORMED_RESPONSE' && failure.message === INVALID_TOOL_JSON;
}

function wait(ms, signal) {
  if (signal.aborted) return Promise.resolve(false);
  return new Promise(resolve => {
    const finish = ok => { clearTimeout(timer); signal.removeEventListener('abort', abort); resolve(ok); };
    const abort = () => finish(false);
    const timer = setTimeout(() => finish(true), ms);
    signal.addEventListener('abort', abort, { once: true });
  });
}

export function apply(ctx, config = {}) {
  if (config.auditFile && !path.isAbsolute(config.auditFile)) throw Error('tool-json-recovery auditFile must be absolute');
  function audit(event, data) {
    if (config.auditFile) appendFileSync(config.auditFile,
      JSON.stringify({ time: new Date().toISOString(), event, ...data }) + '\n', { mode: 0o600 });
  }
  const key = 'toolJsonRecovery';
  ctx.sessionProjections.register({
    key, stateVersion: 1,
    stateSchema: z.object({ retries: z.number().int().nonnegative(), notified: z.boolean() }),
    init: () => ({ retries: 0, notified: false }),
    apply(state, event) {
      if (event.type === 'step/start' || event.type === 'turn/end') return { retries: 0, notified: false };
      // Share the retry allowance with native transport retries in this step;
      // do not add five MORE attempts after five native retries.
      if (event.type === 'llm/retry') return { ...state, retries: state.retries + 1 };
      if (event.type === 'protocol/retry') return { ...state, notified: true };
      return state;
    },
  });
  const lifetime = new AbortController();
  ctx.effect(() => () => lifetime.abort());
  ctx.on('agent/request-error', async (payload, next) => {
    const { agent, failure, retryPolicy: policy, signal, turn, step, provider } = payload;
    if (!isToolJsonFailure(failure)) return next();
    if (signal.aborted || lifetime.signal.aborted) return;
    // Respect explicitly disabled retries and avoid inventing an unbounded
    // policy when the host did not supply a bounded native one.
    if (policy?.mode !== 'normal') return next();
    const state = ctx.sessionProjections.stateOf(agent.session, key);
    const detail = { turn, step, provider, code: failure.code, kind: 'invalid_tool_json',
      retries: state.retries, retryLimit: policy.maxRetries, toolsExecutedFromFailedResponse: 0 };
    if (state.retries >= policy.maxRetries) {
      agent.session.append('protocol/retry-exhausted', detail);
      audit('protocol/retry-exhausted', detail);
      // Stable, non-secret marker for batch scheduling. The exception and
      // task artifacts remain intact; never pretend this was completion.
      ctx.logger.warn('TOOL_JSON_RECOVERY_EXHAUSTED: native request retry allowance exhausted; preserve this task and continue unrelated tasks only if no repeated infrastructure failure.');
      return;
    }
    if (!state.notified) agent.session.append('user/message', createUserMessage({
      content: [{ type: 'text', text: NOTICE }],
      source: { kind: 'tool-json-recovery', form: 'notice', summary: 'Regenerate malformed tool parameters; retain prior results' },
    }), { surfaceOp: 'append' });
    const delayMs = Math.min(policy.initialDelayMs * 2 ** Math.min(state.retries, 30), policy.maxDelayMs);
    agent.session.append('protocol/retry', { ...detail, retries: state.retries + 1, delayMs });
    audit('protocol/retry', { ...detail, retries: state.retries + 1, delayMs });
    // Use the native event/key contract so a later TIMEOUT cannot reset and
    // stack another retry allowance on top of JSON recovery.
    const policyKey = JSON.stringify([policy.mode, policy.maxRetries, [...policy.retryableCodes].sort(),
      policy.initialDelayMs, policy.maxDelayMs, policy.jitterRatio]);
    const retryId = randomUUID();
    agent.session.append('llm/retry', { turn, step, provider, mode: policy.mode, policyKey,
      retryId, retry: state.retries + 1, delayMs, failure: { code: failure.code, message: INVALID_TOOL_JSON } });
    const fused = AbortSignal.any([signal, lifetime.signal]);
    if (!await wait(delayMs, fused)) return;
    agent.session.append('llm/retry-started', { turn, step, retryId, retry: state.retries + 1 });
    return { kind: 'retry' };
  }, { prepend: true });
}
