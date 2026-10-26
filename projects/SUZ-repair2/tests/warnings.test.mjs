import {test} from 'node:test';
import assert from 'node:assert/strict';
import {VisualWarnings} from '../src/visual-warnings.mjs';
import {SUZController} from '../src/controller.mjs';

const frame={id:'F2',step:2,sha256:'abc'};
const evidence={E1:{frame_ids:['F0','F1'],action:{points:[{x:.5,y:.5}]}},
  E2:{frame_ids:['F1','F2'],action:{points:[{x:.5,y:.5}]}}};
const candidate={frame_id:'F2',target:'Save',condition:'disabled button on editor',diagnosis:'grey and two clicks ineffective',
  cause:'disabled',confidence:.9,box:[.4,.4,.6,.6],evidence_ids:['E1','E2']};
test('warning expires, becomes stale on screen change, and requires explicit revalidation',()=>{
  const w=new VisualWarnings();w.add(candidate,frame,evidence,'M1');assert.equal(w.view()[0].style,'red_cross');
  w.observe({id:'F3',step:3,sha256:'changed'});assert.equal(w.view()[0].status,'needs_revalidation');
  w.observe({id:'F3',step:3,sha256:'abc'});assert.equal(w.view()[0].status,'needs_revalidation');
  w.update({id:'V1',decision:'revalidate',frame_id:'F3',reason:'same disabled Save in current image',box:[.4,.4,.6,.6],condition:'still disabled'},
    {id:'F3',step:3,sha256:'changed'});
  assert.equal(w.view()[0].status,'active');assert.equal(w.view()[0].expires_step,5);
  w.observe({id:'F5',step:5,sha256:'changed'});assert.equal(w.view().length,0);
  assert.throws(()=>w.update({id:'V1',decision:'revalidate',frame_id:'F5',reason:'again'},{id:'F5',step:5}),/live ID/);
});
test('warning admission rejects hallucinated targets, single-step proof and huge boxes',()=>{
  for(const patch of [{evidence_ids:['E1']},{frame_id:'F99'},{box:[0,0,1,1]},{box:[0,0,.1,.1]}])
    assert.throws(()=>new VisualWarnings().add({...candidate,...patch},frame,evidence,'M1'));
  const w=new VisualWarnings();w.add({...candidate,cause:'loading'},frame,evidence,'M1');assert.equal(w.view()[0].style,'amber_box');
  w.update({id:'V1',decision:'clear',frame_id:'F2',reason:'now enabled'},frame);assert.equal(w.view().length,0);
});
test('warning does not prohibit an evidenced target retry',()=>{
  const png='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jZ/0AAAAASUVORK5CYII=';
  const c=new SUZController({taskId:'a',instruction:'save'});c.observe({base64:png});
  c.warnings.state.items.push({id:'V1',status:'active',box:[.4,.4,.6,.6]});
  assert.equal(c.propose({actions:['pyautogui.click(50, 50)'],points:[{x:.5,y:.5}]}).allowed,true);
});
test('A-B-A-B-A triggers Monitor immediately without certifying semantic failure',()=>{
  const png='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jZ/0AAAAASUVORK5CYII=';
  const c=new SUZController({taskId:'a',instruction:'compare pages',monitorEvery:20});
  for(let i=0;i<5;i++) {
    c.observe({base64:png,metrics:{pixel_sha256:(i%2?'b':'a').repeat(64)}});
    if(i<4)c.propose({actions:[`pyautogui.click(${i}, 20)`]});
  }
  assert.equal(c.state.loopCandidate.kind,'page_oscillation_ABABA');assert.equal(c.schedule().monitor,true);
  assert.equal(c.planner.state.pending.kind,'initial');
});
