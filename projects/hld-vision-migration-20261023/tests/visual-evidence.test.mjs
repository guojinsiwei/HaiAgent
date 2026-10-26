import { test } from 'node:test';
import assert from 'node:assert/strict';
import { VisualEvidence } from '../src/visual-evidence.mjs';
import { TaskMemory } from '../frozen-hld-v8/src/memory.mjs';

const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jZ/0AAAAASUVORK5CYII=', 'base64');
function setup() {
  const visual = new VisualEvidence('task-1');
  for (const [id, phase, step] of [['f1', 'before', 1], ['f2', 'after', 1], ['f3', 'observation', 2]])
    visual.addFrame({ taskId: 'task-1', id, phase, step, bytes: png, mime: 'image/png' });
  visual.addTransition({ taskId: 'task-1', id: 't1', before: 'f1', after: 'f2',
    action: { name: 'pickup', arguments: { target: 'cup' } },
    receipt: { status: 'success', publicMessage: 'action dispatched', reward: 1, hiddenState: 'secret' } });
  const memory = new TaskMemory();
  memory.admit({ kind: 'finding', conclusion: 'cup pickup returned success', condition: 'reported action outcome only',
    operation: 'pickup cup', evidence_ids: ['E1'] },
  { E1: { complete: true, after: 'unknown:visual_state', stdout: 'action dispatched' } },
  ['E1'], 'unknown:visual_state', {}, 'observer');
  return { visual, memory };
}

test('all five roles receive actual images and retrieved memory evidence without mutating TaskMemory', () => {
  const { visual, memory } = setup();
  const original = JSON.stringify(memory.state);
  const recalled = memory.recall('pickup cup', 'unknown:visual_state', {});
  assert.equal(recalled.length, 1);
  visual.attachMemory({ taskId: 'task-1', memory, memoryId: recalled[0].id, transitionIds: ['t1'] });
  for (const role of ['planner', 'solver', 'monitor', 'advisor', 'critic']) {
    const packet = visual.forRole({ taskId: 'task-1', role, currentFrameId: 'f3', memory, recalledMemoryIds: [recalled[0].id] });
    assert.deepEqual(packet.frames.map(row => row.id), ['f3', 'f1', 'f2']);
    assert.ok(packet.frames.every(row => row.dataUrl.startsWith('data:image/png;base64,')));
    assert.equal(packet.transitions[0].taskProgress, 'unassessed');
    assert.equal(packet.transitions[0].taskComplete, 'unassessed');
    assert.equal('reward' in packet.transitions[0].receipt, false);
    assert.equal('hiddenState' in packet.transitions[0].receipt, false);
  }
  assert.equal(JSON.stringify(memory.state), original);
});

test('rejects cross-task references, invented memory IDs and invalid ordering', () => {
  const { visual, memory } = setup();
  assert.throws(() => visual.forRole({ taskId: 'task-2', role: 'solver', currentFrameId: 'f3' }), /cross-task/);
  assert.throws(() => visual.attachMemory({ taskId: 'task-1', memory, memoryId: 'M999', transitionIds: ['t1'] }), /unknown HLD/);
  assert.throws(() => visual.attachMemory({ taskId: 'task-1', memory, memoryId: 'M1', transitionIds: ['t999'] }), /known visual/);
  assert.throws(() => visual.addTransition({ taskId: 'task-1', id: 't2', before: 'f3', after: 'f2', action: { name: 'pickup' }, receipt: { status: 'success' } }), /ordering/);
});

test('packets are detached copies and identical image bytes are not treated as semantic state proof', () => {
  const { visual } = setup();
  const args = { taskId: 'task-1', role: 'monitor', currentFrameId: 'f2', transitionIds: ['t1'] };
  const packet = visual.forRole(args);
  assert.equal(packet.frames[0].sha256, packet.frames[1].sha256);
  assert.equal(packet.transitions[0].taskProgress, 'unassessed');
  packet.transitions[0].taskProgress = 'made-up-success';
  assert.equal(visual.forRole(args).transitions[0].taskProgress, 'unassessed');
});

test('rejects mislabeled image data', () => {
  assert.throws(() => new VisualEvidence('task-1').addFrame({ taskId: 'task-1', id: 'f1', step: 0,
    phase: 'observation', bytes: Buffer.from('text is not an image'), mime: 'image/png' }), /header/);
});
