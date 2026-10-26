import test from 'node:test';
import assert from 'node:assert/strict';
import { FullTask } from '../src/full-task.mjs';

const call = index => ({ name: 'bash', callId: `restore-r5-${index}`, arguments: { command: 'python public_check.py' } });

test('R5 restore review: a fresh task has no fabricated previous Advisor timestamp', () => {
  const fresh = new FullTask({});
  assert.equal(fresh.state.advisorCalls ?? 0, 0);
  assert.equal(fresh.state.lastAdvisorClock, undefined);
  for (let index = 1; index <= 3; index++) fresh.recoveryRejected(call(index), 'invalid proposal');
  const restored = new FullTask({}, JSON.parse(JSON.stringify(fresh.snapshot())));
  assert.equal(restored.state.lastAdvisorClock, undefined);
  assert.equal(restored.advisory.state.pending.trigger, 'rejection_stall');
});

test('R5 restore review: JSON persistence retains R identity, deduplication and new-clock cooldown', () => {
  const task = new FullTask({ monitorCooldown: 3 }); task.state.scope = 'sha256:unchanged';
  for (let index = 1; index <= 3; index++) task.recoveryRejected(call(index), 'invalid proposal');
  assert.equal(task.monitorStarted(), 'anomaly');
  task.state.advisorCalls = 1; task.state.lastAdvisorClock = 3;
  const resumed = new FullTask({ monitorCooldown: 3 }, JSON.parse(JSON.stringify(task.snapshot())));
  assert.equal(resumed.clock.state.steps, 3); assert.equal(resumed.state.lastMonitorClock, 3);
  assert.equal(resumed.state.lastAdvisorClock, 3); assert.equal(resumed.monitorDue(), false);
  assert.equal(resumed.recoveryRejected(call(3), 'duplicate result dispatch'), null);
  assert.equal(resumed.clock.execution(call(3)), false);
  assert.equal(resumed.clock.state.steps, 3);
  for (let index = 4; index <= 6; index++) resumed.recoveryRejected(call(index), 'invalid proposal');
  assert.equal(resumed.clock.state.steps, 6); assert.equal(resumed.monitorDue(), true);
  assert.deepEqual(resumed.clock.state.controls.map(row => row.id), ['R1', 'R2', 'R3', 'R4', 'R5', 'R6']);
  assert.deepEqual(resumed.state.evidence, {}); assert.deepEqual(resumed.memory.state.items, []);
});

test('R5 restore review: legacy all-tool Advisor timestamp does not become a future recovery-clock deadline', () => {
  const base = new FullTask({}).snapshot();
  base.observed = 40; base.usage.tools = 200; base.advisorCalls = 1;
  base.lastAdvisorTool = 195; base.lastMonitor = 35;
  delete base.recoveryClock; delete base.lastAdvisorClock; delete base.lastMonitorClock;
  const restored = new FullTask({}, JSON.parse(JSON.stringify(base)));
  assert.equal(restored.clock.state.steps, 40);
  assert.equal(restored.state.lastAdvisorClock, 40, 'restart only a bounded cooldown in the new clock units');
  assert.equal(restored.state.lastMonitorClock, 35);
  for (let index = 1; index <= 5; index++) restored.recoveryRejected(call(index), 'unexecuted repair');
  assert.equal(restored.clock.state.steps - restored.state.lastAdvisorClock, 5);
  assert.equal(restored.clock.state.steps - restored.state.lastMonitorClock, 10);
  assert.deepEqual(restored.state.evidence, {});
});
