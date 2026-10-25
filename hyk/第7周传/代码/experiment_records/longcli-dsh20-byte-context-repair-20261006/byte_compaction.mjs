/** DSH budget adaptation only: byte-pressure admission, native durable commits.
 * Never changes solver prompts, dispatches actions, or edits workspace files.
 * The relay's exact 48000-byte guard remains authoritative. Projection below
 * is conservative for this pinned text-only Chat Completions route, not a tokenizer.
 */
export const POLICY = Object.freeze({ triggerBytes: 42000,
  retainBytes: 4096, minimumPrefixBytes: 5000, marginBytes: 1024 });

// Match Python json.dumps(..., ensure_ascii=False) whitespace in the relay guard.
export function wireJson(value) {
  if (Array.isArray(value)) return '[' + value.map(wireJson).join(', ') + ']';
  if (value !== null && typeof value === 'object') return '{' + Object.entries(value)
    .filter(([, v]) => v !== undefined).map(([k, v]) => JSON.stringify(k) + ': ' + wireJson(v)).join(', ') + '}';
  return JSON.stringify(value);
}
export const bytes = value => Buffer.byteLength(wireJson(value), 'utf8');

export function projectMessage(message) {
  const content = message.content ?? [];
  const text = content.filter(b => b.type === 'text').map(b => b.text).join('\n');
  if (message.role === 'tool') return { role: 'tool', tool_call_id: message.toolCallId, content: text || '(no output)' };
  if (message.role === 'assistant') {
    const calls = content.filter(b => b.type === 'tool-call').map(b => ({ id: b.id, type: 'function',
      function: { name: b.name, arguments: b.arguments } }));
    return { role: 'assistant', content: text || null, ...(calls.length ? { tool_calls: calls } : {}) };
  }
  // CLI fixtures are text-only; don't silently underprice an unknown image/block.
  if (content.some(b => b.type !== 'text')) throw new Error('LONGCLI_UNSUPPORTED_PRESSURE_CONTENT');
  return { role: message.role, content: text };
}

export function surfaceView(session) {
  return session.surface.nodes.map(seq => ({ seq, event: session.eventAt(seq),
    message: session.deriveEventMessage(session.eventAt(seq)) })).filter(n => n.message !== null);
}
export function footprint(session, view = surfaceView(session)) {
  const tools = session.requestHeader()?.tools?.map(t => ({ type: 'function', function: {
    name: t.name, description: t.description, parameters: t.parameters, strict: false } })) ?? [];
  return bytes({ messages: view.map(n => projectMessage(n.message)), tools })
    + POLICY.marginBytes + view.length * 64 + tools.length * 64;
}

/** Select an older prefix, preserving a recent raw tail and whole tool groups.
 * Same pairing predicates and native compactRegion transaction as upstream.
 */
export function selectRange(session, view, balancedBefore, balancedAfter, retainBytes = POLICY.retainBytes) {
  if (view.length < 2) return null;
  const first = view[0].event.type === 'system/message' ? 1 : 0;
  let tail = 0, keep = view.length;
  for (let i = view.length - 1; i >= first; i--) {
    tail += bytes(projectMessage(view[i].message)) + 64;
    keep = i;
    if (tail >= retainBytes) break;
  }
  while (keep > first && (!balancedBefore(session, view[keep].seq)
      || !balancedAfter(session, view[keep - 1].seq))) keep--;
  if (keep <= first) return null;
  const selectedBytes = view.slice(first, keep).reduce((s, n) => s + bytes(projectMessage(n.message)) + 64, 0);
  if (selectedBytes < POLICY.minimumPrefixBytes) return null;
  return { start: view[first].seq, end: view[keep - 1].seq, selectedBytes,
    retainedBytes: view.slice(keep).reduce((s, n) => s + bytes(projectMessage(n.message)) + 64, 0),
    retainedNodes: view.length - keep };
}

/** Native pruning on an older prefix only. Proxy binds all replay/append calls
 * to the REAL session: no fabricated event log, unpaired range, or private state
 * is written. Only the native pruner's candidate inventory is narrowed.
 */
export function pruneWithRecentTail(ctx, session, pairing, record) {
  const pruner = ctx.get('toolResultPruner');
  if (!pruner) return;
  const range = selectRange(session, surfaceView(session), pairing.toolPairingBalancedBefore,
    pairing.toolPairingBalancedAfter);
  if (range) {
    // Replacement nodes have NEW log seqs at OLD surface positions; seqs are
    // not chronological surface indexes. Never use numeric <= for this range.
    const candidateNodes = session.surface.nodes.slice(0, session.surface.nodes.indexOf(range.end) + 1);
    const scoped = new Proxy(session, { get(target, key) {
      if (key === 'surface') return { nodes: candidateNodes };
      const value = Reflect.get(target, key, target);
      return typeof value === 'function' ? value.bind(target) : value;
    } });
    pruner.pruneSession(scoped);
    record({ event: 'byte_prune_older_only', through_seq: range.end, recent_raw_tail_protected: true });
  }
  // Only prune the latest raw group if it STILL cannot fit after replacing
  // the old prefix. Total envelope size alone is not this irreducible size!
  const view = surfaceView(session);
  const oldRange = selectRange(session, view, pairing.toolPairingBalancedBefore, pairing.toolPairingBalancedAfter);
  const endIndex = oldRange ? view.findIndex(n => n.seq === oldRange.end) : -1;
  const minimalView = endIndex >= 0 ? [
    ...(view[0]?.event.type === 'system/message' ? [view[0]] : []), ...view.slice(endIndex + 1)
  ] : view;
  const irreducibleBytes = footprint(session, minimalView) + 3000; // requested summary + framing reserve
  if (irreducibleBytes >= 48000) {
    pruner.pruneSession(session);
    record({ event: 'byte_prune_oversize_recent_group', recent_raw_tail_protected: false,
      irreducible_projected_bytes: irreducibleBytes,
      reason: 'recent_group_and_fixed_envelope_cannot_fit_even_without_old_history' });
  }
}

/** Install once, after native services exist; native auto hook dynamically calls
 * compactIfNeeded. Meter, summary generation, shrink verification, replay and
 * tool-read bookkeeping stay upstream-owned. No package/dist source is edited.
 */
export async function installBytePressure(ctx, record, pairing) {
  const engine = ctx.get('compaction');
  if (!engine || typeof engine.compactRegion !== 'function') throw new Error('LONGCLI_MISSING_NATIVE_COMPACTION');
  if (engine.__longcliBytePressure) return;
  const { toolPairingBalancedBefore, toolPairingBalancedAfter } = pairing;
  engine.compactIfNeeded = async (agent, trigger, signal) => {
    signal?.throwIfAborted();
    const session = agent.session;
    if (!session.requestHeader()) return null;
    let size = footprint(session);
    if (trigger === 'pressure' && size < POLICY.triggerBytes) return null;
    pruneWithRecentTail(ctx, session, pairing, record);
    size = footprint(session);
    record({ event: 'byte_pressure', trigger, projected_bytes: size, ...POLICY });
    if (trigger === 'pressure' && size < POLICY.triggerBytes) return null;
    const range = selectRange(session, surfaceView(session), toolPairingBalancedBefore,
      toolPairingBalancedAfter, trigger === 'context-overflow' ? 1 : POLICY.retainBytes);
    if (!range) { record({ event: 'byte_compaction_skipped', reason: 'no_useful_balanced_prefix', projected_bytes: size }); return null; }
    // One native transaction per boundary. Don't immediately summarize the
    // checkpoint just produced merely to chase an arbitrary token threshold.
    const result = await engine.compactRegion(range.start, range.end, agent, signal);
    record({ event: 'byte_compaction_committed', before_projected_bytes: size,
      after_projected_bytes: footprint(session), ...range });
    return result;
  };
  engine.__longcliBytePressure = true;
  record({ event: 'byte_pressure_installed', policy: POLICY, durable_owner: 'official DSH compactRegion' });
}
