import { createHash } from 'node:crypto';

const ROLES = new Set(['planner', 'solver', 'monitor', 'advisor', 'critic']);
const MIME = new Set(['image/png', 'image/jpeg', 'image/webp']);
const text = value => typeof value === 'string' && value.trim().length > 0;

// Task-local attachment sidecar. It does not infer visual state, award progress,
// close completion gaps, or change the original HLD memory admission/retrieval.
export class VisualEvidence {
  #task;
  #frames = new Map();
  #transitions = new Map();
  #memory = new Map();

  constructor(taskId) {
    if (!text(taskId)) throw new Error('taskId required');
    this.#task = taskId;
  }

  #scope(taskId) {
    if (taskId !== this.#task) throw new Error('cross-task evidence rejected');
  }

  #frame(id) {
    const frame = this.#frames.get(id);
    if (!frame) throw new Error(`unknown frame: ${id}`);
    return frame;
  }

  addFrame({ taskId, id, step, phase, bytes, mime }) {
    this.#scope(taskId);
    if (!text(id) || this.#frames.has(id)) throw new Error('unique frame id required');
    if (!Number.isSafeInteger(step) || step < 0 || !['before', 'after', 'observation'].includes(phase))
      throw new Error('valid step and phase required');
    if (!Buffer.isBuffer(bytes) || !bytes.length || bytes.length > 20 * 1024 * 1024 || !MIME.has(mime))
      throw new Error('supported image bytes and MIME required');
    const signature = mime === 'image/png' ? bytes.subarray(0, 8).equals(Buffer.from('89504e470d0a1a0a', 'hex'))
      : mime === 'image/jpeg' ? bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff
      : bytes.subarray(0, 4).toString() === 'RIFF' && bytes.subarray(8, 12).toString() === 'WEBP';
    if (!signature) throw new Error('image header does not match MIME');
    const sha256 = createHash('sha256').update(bytes).digest('hex');
    this.#frames.set(id, { id, step, phase, sha256, mime, bytes: Buffer.from(bytes) });
    return { id, step, phase, sha256, mime };
  }

  addTransition({ taskId, id, before, after, action, receipt }) {
    this.#scope(taskId);
    if (!text(id) || this.#transitions.has(id)) throw new Error('unique transition id required');
    const a = this.#frame(before), b = this.#frame(after);
    if (before === after || a.step > b.step || a.phase === 'after' || b.phase === 'before')
      throw new Error('invalid observation ordering');
    if (!text(action?.name) || !['success', 'failure', 'unknown'].includes(receipt?.status))
      throw new Error('action and explicit tool receipt required');
    // Whitelist public receipt fields; no reward, hidden state or grader payload.
    const row = { id, before, after, action: structuredClone(action),
      receipt: { status: receipt.status, publicMessage: String(receipt.publicMessage ?? '') },
      taskProgress: 'unassessed', taskComplete: 'unassessed' };
    this.#transitions.set(id, row);
    return structuredClone(row);
  }

  attachMemory({ taskId, memory, memoryId, transitionIds }) {
    this.#scope(taskId);
    if (!memory?.state?.items?.some(item => item.id === memoryId)) throw new Error('unknown HLD memory id');
    if (!Array.isArray(transitionIds) || !transitionIds.length || transitionIds.some(id => !this.#transitions.has(id)))
      throw new Error('known visual transitions required');
    this.#memory.set(memoryId, [...new Set(transitionIds)]);
  }

  forRole({ taskId, role, currentFrameId, memory, recalledMemoryIds = [], transitionIds = [], extraFrameIds = [] }) {
    this.#scope(taskId);
    if (!ROLES.has(role)) throw new Error('unknown HLD role');
    this.#frame(currentFrameId);
    const ids = new Set(transitionIds);
    for (const memoryId of recalledMemoryIds) {
      if (!memory?.state?.items?.some(item => item.id === memoryId)) throw new Error('unknown HLD memory id');
      for (const id of this.#memory.get(memoryId) ?? []) ids.add(id);
    }
    const transitions = [...ids].map(id => {
      if (!this.#transitions.has(id)) throw new Error('unknown transition');
      return this.#transitions.get(id);
    });
    const frameIds = [...new Set([currentFrameId, ...extraFrameIds, ...transitions.flatMap(row => [row.before, row.after])])];
    const frames = frameIds.map(id => {
      const { bytes, ...metadata } = this.#frame(id);
      return { ...metadata, dataUrl: `data:${metadata.mime};base64,${bytes.toString('base64')}` };
    });
    return structuredClone({ taskId, role, currentFrameId, transitions, frames,
      evidenceSemantics: 'Image identity and tool success do not establish task progress. Visual interpretations remain attributed claims.' });
  }
}
