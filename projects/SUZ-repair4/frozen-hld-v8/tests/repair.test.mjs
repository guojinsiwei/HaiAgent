import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {FullTask} from '../src/full-task.mjs';
import {Policy,configuration} from '../src/policy.mjs';
import {commandTargets,dependencyState,nativeObservation} from '../src/workspace.mjs';
import {literalFileRead,maskedStages} from '../src/commands.mjs';
import {reserveCost,settleCost,validateCostPolicy} from '../src/budget.mjs';
import {deliveryPaths,progressView} from '../src/progress.mjs';
const S='sha256:unchanged',call={name:'bash',arguments:{command:'python check.py'}},out={executed:true,complete:true,exitCode:1,stdout:'',stderr:'failure'};
const cp={provider:'fixture',model:'fixture',priceBasis:'synthetic',limitCny:50,inputPerMillion:2,outputPerMillion:8,maxInputTokens:1000000,maxOutputTokens:32768};

test('freeze clears pending rollback on resume but retains old checkpoints and subgoal evidence',()=>{
  const original=new FullTask({backtracking:true});original.state.checkpoints=[{id:'C1',scope:S,goals:[]}];original.state.pendingRollback='C1';original.state.pendingSnapshots=[{scope:S}];
  const restored=new FullTask({},original.snapshot());assert.equal(restored.config.backtracking,false);assert.equal(restored.state.pendingRollback,null);assert.deepEqual(restored.state.pendingSnapshots,[]);assert.equal(restored.state.checkpoints.length,1);
});
test('quoted controls are data while actual pipeline, substitution and newline remain uncertain',()=>{
  assert.equal(maskedStages('python x.py --case "a;b|c"'),false);
  for(const cmd of ['a | b','a; b','a\nb','a & b','echo "$(false)"'])assert.equal(maskedStages(cmd),true);
});
test('dynamic queries and arbitrary successful programs are not classified as cached file reads',()=>{
  for(const cmd of ['tail -f app.log','tail --follow=name app.log','cat /proc/loadavg','cat /dev/stdin','python check.py','curl localhost','ls','cat -'])assert.equal(literalFileRead(cmd),false,cmd);
  assert.equal(literalFileRead('head -n 5 README'),true);
});
test('local imported source and dependency manifests count as relevant inputs, not random notes',async()=>{
  const base=fileURLToPath(new URL('../.runtime/',import.meta.url));await mkdir(base,{recursive:true});const root=await mkdtemp(path.join(base,'deps-'));
  await writeFile(path.join(root,'check.py'),'import helper\n');await writeFile(path.join(root,'helper.py'),'value=1');
  const targets=await commandTargets(root,call.arguments);assert.ok(targets.includes('helper.py'));assert.ok(targets.includes('requirements.txt'));assert.ok(!targets.includes('notes.txt'));
  const before=await dependencyState(root,targets);await writeFile(path.join(root,'helper.py'),'value=2');const after=await dependencyState(root,targets);
  const p=new Policy();p.observe(call,out,S,S,before);assert.equal(p.before(call,'sha256:other',{dependencies:before}).allowed,false);
  assert.equal(p.before(call,'sha256:other',{dependencies:after}).allowed,true);
  assert.ok((await commandTargets(root,{command:'cat README'})).includes('README'));
  for(const cmd of ['make test','npm test','python -m pytest tests','pytest tests/test_x.py'])assert.deepEqual(await commandTargets(root,{command:cmd}),[],cmd+' must not narrow whole-project inputs to just manifests');
});
test('unknown state is never treated as proof of unchanged dependencies',()=>{
  const p=new Policy();p.observe(call,out,'unknown','unknown',{'check.py':'unknown'});
  assert.equal(p.before(call,'unknown',{dependencies:{'check.py':'unknown'}}).allowed,true);
});
test('mutating failed operation is not treated as a cached stable failure',()=>{
  const p=new Policy();p.observe(call,out,S,'sha256:changed',{'check.py':'file:a'});
  assert.equal(p.before(call,'sha256:changed',{dependencies:{'check.py':'file:a'}}).allowed,true);
});
test('seven rejected proposals fall back to advice without stopping the task',()=>{
  const p=new Policy();p.observe(call,out,S,S);
  for(let i=0;i<7;i++)assert.equal(p.before(call,S).allowed,false);
  assert.equal(p.before(call,S).allowed,true);assert.equal(p.state.advisory,true);
});
test('one justified retry does not become an unlimited prose-only exemption',()=>{
  const p=new Policy();p.observe(call,out,S,S,{'check.py':'file:a'});
  assert.equal(p.before(call,S,{dependencies:{'check.py':'file:a'},justifiedRetry:true}).allowed,true);
  p.observe(call,out,S,S,{'check.py':'file:a'});
  assert.equal(p.before(call,S,{dependencies:{'check.py':'file:a'},justifiedRetry:true}).allowed,false);
});
test('native observations preserve text without inventing exit zero or completed checks',()=>{
  const row=nativeObservation({isError:false,value:{text:'actual'},content:[{type:'text',text:'actual'}]});assert.equal(row.stdout,'actual');assert.equal(row.exitCode,null);
  const f=new FullTask({});const r=f.observeNative({name:'read',arguments:{path:'a.py'}},row,S,S,{},{},'raw');assert.equal(r.clean,false);assert.equal(r.checkStatus,'unknown');assert.equal(f.state.observed,1);
  assert.equal(nativeObservation({isError:true,error:{message:'permission denied'}}).complete,false);
  assert.equal(nativeObservation({value:{truncated:true}}).complete,false);
});
test('native reconnaissance participates in advisor detection without declaring source text a failure',()=>{
  const f=new FullTask({});for(let i=0;i<14;i++)f.observeNative({name:'read',arguments:{path:`file${i}.py`}},nativeObservation({value:{text:'source'}}),S,S,{},{},'raw');
  assert.equal(f.advisory.state.pending.trigger,'extended_diagnosis');assert.equal(f.state.pendingEvidence.length,0);
});
test('monitor reviews are spread across the run and counters survive resume',()=>{
  let f=new FullTask({maxTools:600}),p=new Policy();const steps=[];
  for(let i=1;i<=600;i++) {
    f.observe({...call,arguments:{command:`python failure${i}.py`}},out,S,S,{},{},p,'raw');
    if(f.monitorDue()){steps.push(i);f.monitorStarted();}
    if(i===150)f=new FullTask({maxTools:600},f.snapshot());
  }
  assert.equal(steps.length,12);assert.ok(steps.filter(i=>i<=96).length<=3);assert.ok(steps.at(-1)>500);
});
test('pending failure IDs survive recent-window eviction and are removed only after valid review',()=>{
  const f=new FullTask({}),p=new Policy();for(let i=0;i<70;i++)f.observe({...call,arguments:{command:`python f${i}.py`}},out,S,S,{},{},p,'raw');
  assert.ok(f.state.pendingEvidence.includes('E1'));assert.ok(!f.state.evidence.E1);
  const supplied={E70:f.state.evidence.E70};f.acceptMonitor({verdict:'uncertain',reason:'needs more data',evidence_ids:['E70'],memories:[]},supplied);
  assert.ok(f.state.pendingEvidence.includes('E1'));assert.ok(!f.state.pendingEvidence.includes('E70'));
});
test('delivery extraction separates output section from input references and does not claim success',()=>{
  const goal='Required outputs:\n- result.json\nInputs:\n- input.csv\nWrite report.md\nUse tests/test_check.py';assert.deepEqual(deliveryPaths(goal),['result.json','report.md']);
  const f=new FullTask({});f.state.taskGoal=goal;progressView(f.state,{}, {'result.json':'missing','report.md':'file:hash'});
  assert.deepEqual(f.state.delivery.missing,['result.json']);assert.match(f.state.delivery.correctness,/unverified/);
});
test('60/85 percent budget reminders never grant new budget or end a task',()=>{
  const f=new FullTask({maxTools:100});f.state.usage.tools=60;progressView(f.state,f.config,{});assert.equal(f.state.budgetView.phase,'consolidate');
  f.state.usage.tools=85;progressView(f.state,f.config,{});assert.equal(f.state.budgetView.phase,'delivery_priority');assert.equal(f.state.usage.requests,0);
});
test('routing switches are independent and disabled monitor cannot spend calls',()=>{
  assert.throws(()=>configuration({criticEnabled:'false'}));
  const f=new FullTask({localCorrection:false,monitorEnabled:false});f.local('syntax','bad');assert.equal(f.state.local,null);f.state.observed=600;assert.equal(f.monitorDue(),false);
  const p=new Policy({explorationEnabled:false});p.state.active=true;assert.equal(p.before(call,S).allowed,true);
});
test('monetary reservation blocks before spending above ceiling and rejects unpriced routes',()=>{
  const s={};assert.throws(()=>reserveCost(s,cp,{provider:'other',model:'fixture'}),/mismatch/);
  const options={provider:'fixture',model:'fixture',maxTokens:32768};const r=reserveCost(s,cp,options);assert.ok(r>2);
  settleCost(s,cp,r,{inputTokens:1000,outputTokens:100,cacheReadTokens:500},true);assert.equal(s.cost.spentUpperCny,.0038);
  s.cost.spentUpperCny=49;assert.throws(()=>reserveCost(s,cp,options),/ceiling/);assert.equal(s.cost.attempts,1);
});
test('unknown billing remains charged conservatively across restart; no fake refund on network error',()=>{
  const s={},r=reserveCost(s,cp,{provider:'fixture',model:'fixture',maxTokens:32768});const resumed=JSON.parse(JSON.stringify(s));
  assert.equal(resumed.cost.pendingUpperCny,r);settleCost(resumed,cp,r,null,false);assert.equal(resumed.cost.spentUpperCny,r);assert.equal(resumed.cost.uncertainAttempts,1);
});
test('cost guard validates bounds, media and cumulative reservation for concurrent requests',()=>{
  assert.throws(()=>validateCostPolicy({...cp,inputPerMillion:NaN}));assert.throws(()=>reserveCost({},cp,{provider:'fixture',model:'fixture',messages:[{content:[{type:'image'}]}]}),/text-only/);
  assert.throws(()=>reserveCost({},cp,{provider:'fixture',model:'fixture'}),/output/);
  const s={},c={...cp,limitCny:3};reserveCost(s,c,{provider:'fixture',model:'fixture',maxTokens:32768});assert.throws(()=>reserveCost(s,c,{provider:'fixture',model:'fixture',maxTokens:32768}),/ceiling/);
});
