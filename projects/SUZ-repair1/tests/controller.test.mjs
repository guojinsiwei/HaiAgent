import {test} from 'node:test';
import assert from 'node:assert/strict';
import {SUZController} from '../src/controller.mjs';
process.env.HLD_PLANNER_PROTOCOL='2';
const base64='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jZ/0AAAAASUVORK5CYII=';
const instruction='Save the document as report.txt';
function setup() {const c=new SUZController({taskId:'T1',instruction});c.observe({base64});return c;}
export function plan(c, second=false, frameEvidence=false) {
  c.context('planner');
  const ids=frameEvidence?['F0']:c.state.recent.slice(-2), key=second?'Use Save As dialog':'Use keyboard save';
  const answer={task_model:{problem:instruction,environment:'visible editor',unknowns:[]},
    new_routes:[{id:'N1',hypothesis:key,mechanism:key,target:'editor',steps:['open save','inspect saved file'],
      progress_signal:'saved filename visible',abandon_when:'dialog does not open',evidence_ids:ids}],
    evaluations:[...c.planner.state.routes.map(r=>({route_id:r.id,suitability:0.1,disposition:'retain',reason:'prior failed',evidence_ids:ids})),
      {route_id:'N1',suitability:0.9,disposition:'retain',reason:'available workflow',evidence_ids:ids}],
    reason:'visible evidence',evidence_ids:ids,contrast:{dimension:'mechanism',reason:'use different UI workflow'}};
  if(c.state.supplied.planner.memory_ids.length)answer.memory_review={ids:c.state.supplied.planner.memory_ids,decision:'different_route',
    observed_result:'clicks unchanged',applicability:'same editor must recheck',reason:'use another save workflow'};
  c.apply('planner',answer);return answer;
}
test('planner may cite supplied screenshots without promoting them to execution evidence',()=>{
  const c=setup();plan(c,false,true);
  assert.deepEqual(c.planner.active().evidence_ids,['F0']);
  assert.equal(c.planner.active().executions,0);
  assert.equal(c.state.evidence.F0,undefined);
  const d=setup();const answer=plan(d);d.planner.queue('route_window');d.context('planner');
  answer.evidence_ids=['F999'];assert.throws(()=>d.apply('planner',answer),/evidence_ids/);
});
function act(c, action="pyautogui.click(20, 20)") {
  c.propose({actions:[action],description:'Save document'});c.observe({base64,receipt:{status:'success',publicMessage:'dispatched',reward:1}});
}
function contract(c) {c.context('critic','plan');c.apply('critic',{obligations:[{id:'G1',quote:'report.txt',predicate:'saved filename'}]},'plan');}
function verdict(c,frame=c.state.current) {
  return {decision:'accept',assessments:c.state.obligations.map(o=>({id:o.id,status:'met',frame_ids:[frame],reason:'saved filename in title',basis:'visible_result'}))};
}

test('planning G0 echo preserves original goal and every predicate without weakening quote checks',()=>{
  const c=setup();c.context('critic','plan');
  const obligations=[{id:'G0',quote:instruction,predicate:'saved document'},
    {id:'G1',quote:'report.txt',predicate:'exact filename'}];
  c.apply('critic',{obligations},'plan');
  assert.deepEqual(c.state.obligations.map(o=>o.id),['G0','G1','G2']);
  assert.equal(c.state.obligations[0].predicate,instruction);
  assert.deepEqual(c.state.obligations.slice(1).map(o=>o.predicate),['saved document','exact filename']);
  const d=setup();d.context('critic','plan');
  assert.throws(()=>d.apply('critic',{obligations:[{id:'G0',quote:'invented task',predicate:'wrong'}]},'plan'),/invalid public obligation/);
});
test('three unchanged clicks trigger semantic replan and preserve memory',()=>{
  const c=setup();plan(c);act(c);act(c);
  c.context('monitor');c.apply('monitor',{verdict:'uncertain',reason:'same page',evidence_ids:['E1','E2'],
    memories:[{kind:'blocker',conclusion:'Save button ineffective',condition:'visible editor and same button',operation:'Save document',evidence_ids:['E1','E2']}]});
  act(c);assert.equal(c.planner.state.pending.kind,'repeated_visual_action');
  assert.equal(c.state.evidence.E3.task_progress,'unassessed');
  assert.equal('reward' in c.state.transitions[0].receipt,false);
  const original=JSON.stringify(c.memory.state);plan(c,true);
  assert.equal(c.planner.state.active,'D2');assert.equal(c.planner.state.switches,1);
  assert.equal(JSON.stringify(c.memory.state),original);
  assert.equal(c.state.memoryEffects.length,1);
  const snapshot=c.snapshot();assert.throws(()=>new SUZController({taskId:'T2',instruction,state:snapshot}),/cross-task/);
});
test('unchanged screenshots with different actions do not automatically label a loop',()=>{
  const c=setup();plan(c);act(c,'pyautogui.moveTo(1, 1)');act(c,'pyautogui.moveTo(2, 2)');act(c,'pyautogui.moveTo(3, 3)');
  assert.equal(c.planner.state.pending,null);
});
test('Critic cannot bulk-close obligations, use unknown or stale frames, or accept tool receipts',()=>{
  const c=setup();contract(c);c.context('critic','review');
  assert.throws(()=>c.apply('critic',{decision:'accept',assessments:[]},'review'),/every obligation/);
  const bad=verdict(c);bad.assessments[0].basis='tool_success';
  assert.throws(()=>c.apply('critic',bad,'review'),/current visual/);
  assert.throws(()=>c.apply('critic',verdict(c,'F99'),'review'),/unknown critic/);
  c.apply('critic',verdict(c),'review');assert.equal(c.propose({actions:['DONE']}).allowed,true);
  assert.equal(c.state.review.official_success,null);
  act(c);assert.equal(c.propose({actions:['DONE']}).allowed,false);
  c.context('critic','review');assert.throws(()=>c.apply('critic',verdict(c,'F0'),'review'),/current visual/);
});
test('fabricated evidence and single-step stagnation cannot trigger Monitor',()=>{
  const c=setup();plan(c);act(c);c.context('monitor');
  assert.throws(()=>c.apply('monitor',{verdict:'stalled',reason:'loop',evidence_ids:['E1']}),/evidence IDs/);
  assert.throws(()=>c.apply('monitor',{verdict:'progress',reason:'yes',evidence_ids:['E999']}),/evidence IDs/);
});
test('monitor separates known frame citations without manufacturing execution evidence',()=>{
  const c=setup();plan(c);act(c);act(c);c.context('monitor');
  c.apply('monitor',{verdict:'progress',reason:'visible change',evidence_ids:['E2','F1','F2'],memories:[]});
  assert.deepEqual(c.state.feedback.at(-1).evidence_ids,['E2']);
  assert.equal(c.state.evidence.F2,undefined);
  assert.throws(()=>c.apply('monitor',{verdict:'stalled',reason:'same page',evidence_ids:['F1','F2'],memories:[]}),/evidence IDs/);
  assert.throws(()=>c.apply('monitor',{verdict:'progress',reason:'same page',evidence_ids:['E2','F999'],memories:[]}),/unknown monitor frame/);
  assert.throws(()=>c.apply('monitor',{verdict:'progress',reason:'same page',evidence_ids:['E2'],memories:[{evidence_ids:['F2']}]}),/evidence IDs/);
});
test('periodic review may retain a productive route without forced novelty',()=>{
  const c=setup();plan(c);c.planner.queue('route_window');c.context('planner');
  c.apply('planner',{new_routes:[],evaluations:[{route_id:'D1',suitability:0.9,disposition:'retain',reason:'working',evidence_ids:[]}],reason:'continue',evidence_ids:[]});
  assert.equal(c.planner.state.active,'D1');assert.equal(c.planner.state.switches,0);
});
test('restored frame archive and memories reconstruct identical role evidence',()=>{
  const c=setup();plan(c);act(c);const snapshot=c.snapshot();
  const d=new SUZController({taskId:'T1',instruction,state:snapshot});
  d.restoreFrames(c.state.frames.map(f=>({...f,base64})));
  assert.deepEqual(d.context('monitor').images,c.context('monitor').images);
});
