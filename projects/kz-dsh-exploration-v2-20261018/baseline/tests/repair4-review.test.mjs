import test from 'node:test';
import assert from 'node:assert/strict';
import { FullTask } from '../src/full-task.mjs';
import { Policy } from '../src/policy.mjs';
import { nativeObservation } from '../src/workspace.mjs';
import { extractOutcome } from '../src/terminal.mjs';
import { StructuredContext } from '../src/structured-context.mjs';

const S='sha256:stable',deps={'main.py':'file:original'},args={command:'python test_main.py',description:'public check'};
const traceback='Traceback (most recent call last):\n  File "test_main.py", line 3, in <module>\n    assert answer == 42\nAssertionError: answer was incorrect\n';
const observation={executed:true,complete:true,exitCode:1,stdout:'',stderr:traceback};
const call=id=>({name:'bash',arguments:args,callId:id,commandDependencies:deps});

test('repair4 review complete nonzero Traceback becomes a genuine failed-command anchor',()=>{
  const f=new FullTask({}),p=new Policy();
  const {row}=f.observe(call('first'),observation,S,S,deps,deps,p,'fixture-first');
  assert.equal(row.complete,true);assert.equal(row.suspect,true);assert.equal(row.failureObserved,true);assert.equal(row.clean,false);
  assert.equal(p.state.memories.length,1);assert.equal(p.state.memories[0].outcome,'execution_failed');
  assert.equal(p.anchors()[0].id,row.id);
  assert.equal(f.before(call('retry'),p,S,deps).allowed,false);
});

test('repair4 review repeated real Traceback admits an observed conditional blocker, not a success',()=>{
  const f=new FullTask({}),p=new Policy();
  f.observe(call('first'),observation,S,S,deps,deps,p,'fixture-first');
  f.observe(call('second'),observation,S,S,deps,deps,p,'fixture-second');
  assert.equal(f.memory.state.items.length,1);
  const memory=f.memory.state.items[0];
  assert.equal(memory.kind,'blocker');assert.equal(memory.status,'observed_tool_outcome_not_causal_rule');
  assert.deepEqual(memory.evidence_ids,['E1','E2']);assert.match(memory.conclusion,/cause remains unknown/);
  assert.equal(f.state.evidence.E2.checkStatus,'unknown');assert.equal(f.state.evidence.E2.taskSuccess,null);
});

test('repair4 review exit zero with Traceback is not clean execution, passing check or a success memory',()=>{
  const f=new FullTask({}),p=new Policy();
  const {row}=f.observe(call('masked'),{...observation,exitCode:0},S,S,deps,deps,p,'fixture-masked');
  assert.equal(row.complete,true);assert.equal(row.suspect,true);assert.equal(row.clean,false);
  assert.equal(row.checkStatus,'unknown');assert.equal(row.failureObserved,false);
  assert.equal(p.state.memories.length,0);assert.equal(f.memory.state.items.length,0);
});

test('repair4 review a complete native rejection cannot enter failed command history even on a bash-shaped path',()=>{
  const error=nativeObservation({isError:true,error:{message:'native permission rejected'},content:[{type:'text',text:'native permission rejected before execution'}]});
  assert.equal(error.complete,true);
  const f=new FullTask({}),p=new Policy();
  const {row}=f.observe(call('native-error'),error,S,S,deps,deps,p,'fixture-native-error');
  assert.equal(row.nativeToolError,true);assert.equal(row.exitCode,null);assert.equal(row.clean,false);assert.equal(row.failureObserved,false);
  assert.equal(row.checkStatus,'unknown');assert.equal(p.state.memories.length,0);assert.equal(f.memory.state.items.length,0);
});

test('repair4 review malformed native error carrying a numeric exit cannot override the native error tag',()=>{
  for (const exitCode of [0,1]) {
    const out=extractOutcome({command:'pytest'},{...observation,exitCode,stdout:'=== 3 passed ===',stderr:'',nativeToolError:true});
    assert.equal(out.clean,false);assert.equal(out.failureObserved,false);assert.equal(out.checkStatus,'unknown');
  }
});

test('repair4 review partial failure evidence does not create a durable command anchor',()=>{
  const f=new FullTask({}),p=new Policy();
  f.observe(call('partial'),{...observation,complete:false},S,S,deps,deps,p,'fixture-partial');
  assert.equal(p.state.memories.length,0);assert.equal(f.memory.state.items.length,0);
});

test('repair4 review an unexecuted receipt cannot prove either success or command failure',()=>{
  for (const exitCode of [0,1]) {
    const out=extractOutcome({command:'pytest'},{...observation,executed:false,exitCode,stdout:'=== 3 passed ===',stderr:''});
    assert.equal(out.clean,false);assert.equal(out.failureObserved,false);assert.equal(out.checkStatus,'unknown');
  }
});

test('repair4 review complete native-error distinction survives the Solver context projection',()=>{
  const f=new FullTask({}),p=new Policy();
  const error=nativeObservation({isError:true,content:[{type:'text',text:'Read the existing file first.'}]});
  f.observeNative({name:'write',arguments:{file_path:'main.py',content:'new'},callId:'edit'},error,S,S,deps,deps,'fixture');
  const row=f.panel(p).result.evidence[0];
  assert.equal(row.complete,true);assert.equal(row.nativeToolError,true);assert.equal(row.commandExecuted,null);
  assert.equal(row.status,'tool_error_observation_not_command_outcome');assert.equal(row.clean,false);
});

test('repair4 review structured context rejects inherited, nonexistent and mismatched evidence IDs atomically',()=>{
  const c=new StructuredContext();
  const e={E1:{id:'E1',complete:true,stdout:'observed check failure',stderr:''}};
  for (const id of ['__proto__','constructor','toString','E2','foreign:E1'])
    assert.throws(()=>c.update({facts:[{text:'invented claim',evidence_ids:[id]}]},e),/real evidence IDs/);
  assert.throws(()=>c.update({facts:[{text:'invented claim',evidence_ids:['E1']}]},{E1:{id:'E2'}}),/real evidence IDs/);
  assert.deepEqual(c.state.facts,[]);
  c.update({unresolved_issues:[{text:'pending',evidence_ids:['E1']}]},e);
  assert.throws(()=>c.update({retire:[{field:'unresolved_issues',text:'pending',status:'resolved',evidence_id:'constructor',quote:'observed'}]},e),/real|complete evidence/);
  assert.equal(c.state.unresolved_issues.length,1);
});

test('repair4 review hydrating an older E record cannot replace the newest same-command prior',()=>{
  const f=new FullTask({}),p=new Policy();
  f.observe(call('old'),{...observation,stderr:'an older unrelated error'},S,S,deps,deps,p,'fixture-old');
  const archived=f.state.evidence.E1;
  f.observe(call('latest'),observation,S,S,deps,deps,p,'fixture-latest');
  delete f.state.evidence.E1;f.state.evidence.E1=archived;
  assert.deepEqual(Object.keys(f.state.evidence),['E2','E1'],'fixture reproduces archive insertion after a newer row');
  f.observe(call('repeat-latest'),observation,S,S,deps,deps,p,'fixture-repeat');
  assert.equal(f.memory.state.items.length,1);assert.deepEqual(f.memory.state.items[0].evidence_ids,['E2','E3']);
});

test('repair4 review trimming after archive hydration evicts chronological oldest, not newest receipts',()=>{
  const f=new FullTask({});let archived;
  for (let i=1;i<=65;i++) {
    f.observeNative({name:'read',arguments:{file_path:'main.py',offset:i},callId:`read-${i}`},nativeObservation({content:[{type:'text',text:`source ${i}`}]}),S,S,deps,deps,'fixture');
    if(i===1)archived=f.state.evidence.E1;
  }
  assert.equal(f.state.evidence.E1,undefined);f.state.evidence.E1=archived;
  f.observeNative({name:'read',arguments:{file_path:'main.py',offset:66},callId:'read-66'},nativeObservation({content:[{type:'text',text:'source 66'}]}),S,S,deps,deps,'fixture');
  assert.equal(Object.keys(f.state.evidence).length,64);
  assert.equal(f.state.evidence.E1,undefined);assert.equal(f.state.evidence.E2,undefined);
  assert.equal(f.state.evidence.E65.stdout,'source 65');assert.equal(f.state.evidence.E66.stdout,'source 66');
});

test('repair4 review a genuine repeated failure at the evidence-capacity boundary retains its conditional lesson',()=>{
  const f=new FullTask({}),p=new Policy();
  f.observe(call('first'),observation,S,S,deps,deps,p,'fixture-first');
  for(let i=0;i<63;i++)f.observeNative({name:'read',arguments:{file_path:'main.py',offset:i},callId:`page-${i}`},nativeObservation({content:[{type:'text',text:`page ${i}`}]}),S,S,deps,deps,'fixture');
  assert.equal(Object.keys(f.state.evidence).length,64);assert.ok(f.state.evidence.E1);
  f.observe(call('again'),observation,S,S,deps,deps,p,'fixture-repeat');
  assert.equal(f.memory.state.items.length,1,'evicting E1 during this observation must not discard the already-captured repeated failure');
  assert.deepEqual(f.memory.state.items[0].evidence_ids,['E1','E65']);
  assert.equal(Object.keys(f.state.evidence).length,64);
});
