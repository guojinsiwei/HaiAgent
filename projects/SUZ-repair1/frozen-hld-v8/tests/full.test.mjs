import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Policy, actionKey } from '../src/policy.mjs';
import { FullTask, reconnaissance } from '../src/full-task.mjs';
import { TaskMemory } from '../src/memory.mjs';
import { Subgoals } from '../src/subgoals.mjs';
import { StructuredContext } from '../src/structured-context.mjs';
import { projectTerminal, extractStream, extractOutcome } from '../src/terminal.mjs';
import { dependencyState, fingerprint } from '../src/workspace.mjs';
import { saveCheckpoint, restoreCheckpoint } from '../src/checkpoints.mjs';

const S='sha256:first',T='sha256:second',deps={'main.py':'file:a'};
const args={command:'python test_main.py',description:'public check'};
const call={name:'bash',arguments:args,callId:'c1'};
const outcome={executed:true,complete:true,exitCode:1,stdout:'assertion failed',stderr:''};
const ev={E1:{id:'E1',command:args.command,category:'test',complete:true,after:S,stdout:'assertion failed',stderr:'',dependenciesAfter:deps}};
const candidate={kind:'blocker',conclusion:'Check failed on this version',condition:'For main.py as observed',targets:['main.py'],evidence_ids:['E1']};
const definition={id:'G1',title:'implement parser',acceptance:'public parser checks',depends_on:[],targets:['main.py'],verification:{arguments:args,stdout_contains:['passed']}};
async function dirs() {
  const base=fileURLToPath(new URL('../.runtime/',import.meta.url));await mkdir(base,{recursive:true});
  const parent=await mkdtemp(path.join(base,'full-')),root=path.join(parent,'task'),audit=path.join(parent,'snapshots');
  await mkdir(root);await mkdir(audit);await writeFile(path.join(root,'main.py'),'first');return{parent,root,audit};
}
test('terminal cleaning preserves earlier error frames and handles OSC/CSI/C1 controls',()=>{
  const value=projectTerminal('\x1b[31mERROR\x1b[0m\rOK\x1b]0;title\x07\x9b2K');
  assert.equal(value.text,'ERROR\nOK');assert.equal(value.incomplete,false);
  assert.equal(projectTerminal('ok\x1b[').incomplete,true);
});
test('diagnostic extraction retains a middle failure and footer, not just head/tail',()=>{
  const lines=Array.from({length:1000},(_,i)=>`noise ${i}`);lines[500]='ERROR middle failure';lines[999]='3 passed';
  const view=extractStream(lines.join('\n'),'test',600);assert.match(view,/ERROR middle/);assert.match(view,/3 passed/);assert.ok(view.length<=600);
});
test('grep no-match is not a failed strategy',()=>{
  const row=extractOutcome({command:'rg missing .'}, {...outcome,stdout:''});assert.equal(row.noMatch,true);assert.equal(row.failureObserved,false);
});
test('zero exit plus traceback does not prove clean execution',()=>{
  const row=extractOutcome(args,{...outcome,exitCode:0,stdout:'Traceback (most recent call last):\nValueError: invalid'});
  assert.equal(row.clean,false);assert.equal(row.taskSuccess,null);
});
test('masked pipeline status and mixed failed/passed summary cannot pass a public check',()=>{
  assert.equal(extractOutcome({command:'pytest | tail'}, {...outcome,exitCode:0,stdout:'passed'}).clean,false);
  assert.equal(extractOutcome({command:'pytest'}, {...outcome,exitCode:0,stdout:'=== 3 passed, 2 failed ==='}).clean,false);
});
test('complete task memory deduplicates, reinforces and detects changed dependencies',()=>{
  const m=new TaskMemory();const first=m.admit(candidate,ev,['E1'],S,deps);
  assert.equal(m.admit(candidate,ev,['E1'],S,deps).id,first.id);assert.equal(first.reinforcements,2);
  assert.match(m.recall('main.py check',S,deps)[0].applicability,/unchanged/);
  assert.match(m.recall('main.py check',T,{'main.py':'file:b'})[0].applicability,/recheck_required/);
});
test('monitor memory requires exact quotes and never promotes a claim to truth',()=>{
  const m=new TaskMemory();assert.throws(()=>m.admit(candidate,ev,['E1'],S,deps,'monitor'),/quotes/);
  const row=m.admit({...candidate,support:[{evidence_id:'E1',field:'stdout',quote:'assertion failed'}]},ev,['E1'],S,deps,'monitor');
  assert.equal(row.status,'evidence_linked_model_claim_not_verified');
});
test('unknown and unadvertised evidence cannot become a memory',()=>{
  const m=new TaskMemory();assert.throws(()=>m.admit(candidate,ev,[],S,deps));
  assert.throws(()=>m.admit(candidate,{E1:{...ev.E1,complete:false}},['E1'],S,deps));
});
test('memory review checks applicability fields; long explanation stays valid',()=>{
  const m=new TaskMemory();assert.throws(()=>m.review({ids:['M1']},['M1']));
  assert.doesNotThrow(()=>m.review({ids:['M1'],decision:'justified_retry',observed_result:'failed',applicability:'changed source',reason:'x'.repeat(10000),new_evidence:'patched main.py'},['M1']));
});
test('subgoal definitions are atomic, immutable and acyclic',()=>{
  const g=new Subgoals();assert.throws(()=>g.define({subgoal_plan:[{...definition,depends_on:['G2']}]}));assert.deepEqual(g.state.items,{});
  g.define({subgoal_plan:[definition]});assert.throws(()=>g.define({subgoal_plan:[{...definition,title:'changed'}]}));
  assert.throws(()=>g.define({subgoal_update:{id:'G1',status:'check_passed',reason:'I said so'}}));
});
test('subgoal only passes a matching actual check on stable dependencies and invalidates downstream',()=>{
  const g=new Subgoals();g.define({subgoal_plan:[definition,{...definition,id:'G2',depends_on:['G1'],verification:{arguments:{...args,command:'python integration.py'},stdout_contains:['passed']}}]});
  const row={id:'E1',tool:'bash',executed:true,complete:true,exitCode:0,key:actionKey(call),stdout:'passed',clean:true,dependenciesBefore:deps,dependenciesAfter:deps,after:S};
  assert.equal(g.observe(row)[0].passed,true);assert.equal(g.state.items.G1.status,'check_passed');
  g.observe({...row,key:actionKey({name:'bash',arguments:{...args,command:'python integration.py'}})});
  assert.equal(g.state.items.G2.status,'check_passed');g.sync({'main.py':'file:b'});
  assert.equal(g.state.items.G1.status,'needs_recheck');assert.equal(g.state.items.G2.status,'needs_recheck');
});
test('subgoal cannot pass when its own verification changes relevant files',()=>{
  const g=new Subgoals();g.define({subgoal_plan:[definition]});
  assert.equal(g.observe({id:'E1',tool:'bash',executed:true,complete:true,exitCode:0,key:actionKey(call),stdout:'passed',clean:true,dependenciesBefore:deps,dependenciesAfter:{'main.py':'file:b'},after:T})[0].passed,false);
});
test('structured context retains omitted open items and requires evidence to retire',()=>{
  const c=new StructuredContext();c.update({unresolved_issues:[{text:'parser broken',evidence_ids:['E1']}]},ev);c.update({},ev);
  assert.equal(c.state.unresolved_issues.length,1);
  assert.throws(()=>c.update({retire:[{field:'unresolved_issues',text:'parser broken',status:'resolved',evidence_id:'E1',quote:'made up'}]},ev));
  c.update({retire:[{field:'unresolved_issues',text:'parser broken',status:'invalidated',evidence_id:'E1',quote:'assertion failed'}]},ev);
  assert.equal(c.state.unresolved_issues.length,0);assert.equal(c.state.retired.length,1);
});
test('syntax route does not become an algorithmic failure; reconnaissance bypasses novelty',()=>{
  const f=new FullTask({memoryCapacity:24}),p=new Policy();
  f.observe(call,{...outcome,stderr:'SyntaxError: bad colon'},S,S,deps,deps,p,'raw');
  assert.equal(p.state.active,false);assert.equal(p.state.memories.length,0);assert.equal(f.state.local.kind,'syntax');
  p.state.active=true;
  assert.equal(f.before({name:'bash',arguments:{command:'ls -la'}},p,S).allowed,true);
  assert.equal(reconnaissance('ls; rm a'),false);assert.equal(reconnaissance('rg --pre=bad needle'),false);
});
test('two regressed fixed checks request rollback; a different new check does not',()=>{
  const f=new FullTask({memoryCapacity:24,backtracking:true}),p=new Policy();f.goals.define({subgoal_plan:[definition]});
  f.state.checkpoints=[{id:'C1',scope:S,goals:['G1'],definitions:{G1:definition}}];
  f.observe(call,outcome,T,T,deps,deps,p,'raw');assert.equal(f.state.pendingRollback,null);
  f.observe(call,outcome,T,T,deps,deps,p,'raw');assert.equal(f.state.pendingRollback,'C1');
});
test('full panel reserves memories and state is restorable, not reset by view generation',()=>{
  const f=new FullTask({memoryCapacity:24}),p=new Policy();f.state.evidence=ev;f.state.scope=S;f.state.dependencies=deps;f.state.taskGoal='main.py check';
  f.memory.admit(candidate,ev,['E1'],S,deps);const view=f.panel(p);assert.equal(view.result.memories[0].id,'M1');
  const restored=new FullTask({memoryCapacity:24},JSON.parse(JSON.stringify(f.snapshot())));assert.equal(restored.memory.state.items[0].id,'M1');
});
test('dependency snapshots cover missing files and changes',async()=>{
  const d=await dirs();const before=await dependencyState(d.root,['main.py','missing']);assert.equal(before.missing,'missing');
  await writeFile(path.join(d.root,'main.py'),'changed');assert.notEqual((await dependencyState(d.root,['main.py']))['main.py'],before['main.py']);
});
test('real checkpoint restores files while preserving all current work',async()=>{
  const d=await dirs();const c=await saveCheckpoint(d.root,d.audit,'C1');await writeFile(path.join(d.root,'main.py'),'changed');await writeFile(path.join(d.root,'new.txt'),'new');
  const preserve=path.join(d.audit,'preserved');await restoreCheckpoint(d.root,c.path,preserve);
  assert.equal(await readFile(path.join(d.root,'main.py'),'utf8'),'first');assert.equal(await readFile(path.join(preserve,'main.py'),'utf8'),'changed');
  assert.equal(await readFile(path.join(preserve,'new.txt'),'utf8'),'new');assert.equal(await fingerprint(d.root),c.scope);
});
test('oversized memory and context prose cannot overflow the protected panel or erase memory',()=>{
  const f=new FullTask({memoryCapacity:24,fullContextChars:8000,memoryReserveChars:3000}),p=new Policy();
  f.state.evidence=ev;f.state.scope=S;f.state.dependencies=deps;f.state.taskGoal='main.py check';
  f.memory.admit({...candidate,conclusion:'check '+ 'x'.repeat(80000),condition:'condition '.repeat(10000)},ev,['E1'],S,deps);
  f.state.critic.receipts=[{stdout:'z'.repeat(100000)}];f.state.monitor={verdict:'uncertain',reason:'r'.repeat(90000),evidence_ids:['E1']};
  f.state.notices=['n'.repeat(60000)];
  const panel=f.panel(p);assert.ok(panel.text.length<=8000);assert.equal(panel.result.memories[0].id,'M1');
  assert.equal(panel.result.memories[0].partial,true);assert.ok(f.memory.state.items[0].conclusion.length>80000);
});
test('monitor cannot cite synthetic line labels added only by compression',()=>{
  const f=new FullTask({memoryCapacity:24});f.state.evidence=ev;f.state.scope=S;f.state.dependencies=deps;
  f.acceptMonitor({verdict:'uncertain',reason:'evidence incomplete',evidence_ids:['E1'],next_check:'check',memories:[{...candidate,support:[{evidence_id:'E1',field:'stdout',quote:'[L4] assertion failed'}]}]},
    {E1:{...ev.E1,stdout:'[L4] assertion failed'}});
  assert.equal(f.memory.state.items.length,0);assert.match(f.state.notices[0],/rejected/);
});
test('a new failing check cannot trigger rollback to an unrelated passed subgoal',()=>{
  const f=new FullTask({memoryCapacity:24}),p=new Policy();f.goals.define({subgoal_plan:[definition]});
  f.state.checkpoints=[{id:'C1',scope:S,goals:['G1'],definitions:{G1:definition}}];
  const other={name:'bash',arguments:{...args,command:'python different.py'}};
  for(let i=0;i<3;i++)f.observe(other,outcome,T,T,deps,deps,p,'raw');
  assert.equal(f.state.pendingRollback,null);
});
test('checkpoint corruption is rejected before modifying the current workspace',async()=>{
  const d=await dirs();const c=await saveCheckpoint(d.root,d.audit,'C1');
  await writeFile(path.join(c.path,'files','main.py'),'tampered');await writeFile(path.join(d.root,'main.py'),'valuable current work');
  await assert.rejects(restoreCheckpoint(d.root,c.path,path.join(d.audit,'preserved')),/corruption/);
  assert.equal(await readFile(path.join(d.root,'main.py'),'utf8'),'valuable current work');
});
