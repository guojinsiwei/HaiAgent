import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, symlink } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { TaskMemory, normalizeMemoryTargets, normalizeMemorySupport } from '../src/memory.mjs';
import { nativeObservation } from '../src/workspace.mjs';
import { FullTask } from '../src/full-task.mjs';
import { Policy } from '../src/policy.mjs';
import { MONITOR, CRITIC } from '../src/roles.mjs';

const S='sha256:task',deps={'ingredient.h':'file:unchanged'};
const errorText='cannot modify "/app/ingredient.h": file has not been read — read the file, then retry';
const errorResult={isError:true,content:[{type:'text',text:errorText}],error:{message:errorText}};
const candidate={kind:'procedure',conclusion:'The native write tool requires a preceding read of an existing file.',condition:'The tool rejected this unread file; no algorithm or command failure is established.',targets:['ingredient.h'],
  evidence_ids:['E1'],next_step:'Read the existing file before retrying the edit.',support:[{evidence_id:'E1',field:'stderr',quote:'file has not been read'}]};
const evidence=()=>({E1:{...nativeObservation(errorResult),id:'E1',after:S,dependenciesAfter:deps}});

test('repair4 returned native error is complete evidence, never CLI execution or test success',()=>{
  const row=nativeObservation(errorResult);
  assert.equal(row.complete,true);assert.equal(row.nativeToolError,true);assert.equal(row.exitCode,null);
  assert.equal(row.clean,false);assert.equal(row.failureObserved,false);assert.equal(row.commandExecuted,null);
  assert.equal(row.checkStatus,'unknown');assert.equal(row.taskSuccess,null);
  const f=new FullTask({}),p=new Policy();
  const observed=f.observeNative({name:'write',arguments:{file_path:'ingredient.h',content:'new'},callId:'write-1'},row,S,S,deps,deps,'fixture');
  assert.equal(observed.complete,true);assert.equal(observed.failureObserved,false);assert.equal(observed.clean,false);
  assert.equal(p.state.memories.length,0);assert.equal(f.memory.state.items.length,0);
});

test('repair4 complete native precondition errors support a conditional procedure and survive persistence',()=>{
  const m=new TaskMemory();const item=m.admit(candidate,evidence(),['E1'],S,deps,'monitor');
  assert.equal(item.kind,'procedure');assert.equal(item.status,'observed_native_tool_error_not_command_outcome');
  assert.equal(item.commandKey,null);
  assert.deepEqual(m.matchAction({name:'write',arguments:{file_path:'ingredient.h'}},S,deps,['ingredient.h']),[]);
  const restored=new TaskMemory(JSON.parse(JSON.stringify(m.state)));
  assert.equal(restored.recall('write ingredient.h',S,deps)[0].id,item.id);
  assert.match(restored.recall('write ingredient.h',S,{'ingredient.h':'file:changed'})[0].applicability,/recheck_required/);
});

test('repair4 native errors cannot become command-specific or route-blocking memories',()=>{
  const m=new TaskMemory();
  assert.throws(()=>m.admit({...candidate,kind:'blocker'},evidence(),['E1'],S,deps,'monitor'),/not failed command or route blockers/);
  assert.throws(()=>m.admit({...candidate,commandKey:'pretend-executed'},evidence(),['E1'],S,deps,'monitor'),/not failed command or route blockers/);
  assert.equal(m.state.items.length,0);
});

test('repair4 partial pages, a missing returned error page, and fabricated quotes remain rejected',()=>{
  const m=new TaskMemory();
  for (const result of [{...errorResult,meta:{truncated:true}},{...errorResult,value:{partial:true}},{isError:true,error:{message:errorText}}]) {
    const row=nativeObservation(result);assert.equal(row.complete,false);
    assert.throws(()=>m.admit(candidate,{E1:{...row,id:'E1',after:S}},['E1'],S,deps,'monitor'),/incomplete evidence/);
  }
  assert.throws(()=>m.admit({...candidate,support:[{evidence_id:'E1',field:'stderr',quote:'all tests passed'}]},evidence(),['E1'],S,deps,'monitor'),/exact quotes/);
  assert.throws(()=>m.admit(candidate,evidence(),[],S,deps,'monitor'),/supplied evidence/);
});

test('repair4 exact monitor quote may correct the stdout/stderr label without changing text',()=>{
  const ev=evidence();ev.E1.stderr='native tool error';
  const fixed=normalizeMemorySupport(candidate,ev);
  assert.equal(fixed.support[0].field,'stdout');assert.equal(fixed.support[0].declared_field,'stderr');
  assert.equal(fixed.support[0].quote,candidate.support[0].quote);assert.equal(candidate.support[0].field,'stderr');
  const stored=new TaskMemory().admit(candidate,ev,['E1'],S,deps,'monitor');
  assert.equal(stored.support[0].field,'stdout');assert.equal(stored.support[0].declared_field,'stderr');
  // A quotation present in both streams is acceptable only in its declared field.
  assert.equal(normalizeMemorySupport(candidate,evidence()).support[0].field,'stderr');
});

test('repair4 support normalization does not accept unavailable view content or synthetic labels',()=>{
  for (const support of [null,[null],[{evidence_id:'E1',field:'text',quote:'file has not been read'}],
    [{evidence_id:'E2',field:'stderr',quote:'file has not been read'}],[{evidence_id:'E1',field:'stdout',quote:'[L1] '+errorText}],
    [{evidence_id:'E1',field:'stderr',quote:'display omitted'}]])
    assert.throws(()=>normalizeMemorySupport({...candidate,support},evidence()),/exact quotes/);
  assert.throws(()=>normalizeMemorySupport(candidate,{E1:{stdout:'only a shorter excerpt',stderr:''}}),/exact quotes/);
});

async function dirs() {
  const base=fileURLToPath(new URL('../.runtime/',import.meta.url));await mkdir(base,{recursive:true});
  const parent=await mkdtemp(path.join(base,'memory-repair4-'));const root=path.join(parent,'task');await mkdir(root);
  await writeFile(path.join(root,'ingredient.h'),'original');return {parent,root};
}

test('repair4 explicit workspace root safely converts absolute targets and preserves missing targets',async()=>{
  const {root}=await dirs();
  const fixed=await normalizeMemoryTargets({...candidate,targets:[path.join(root,'ingredient.h'),'ingredient.h',path.join(root,'new','file.py')]},root);
  assert.deepEqual(fixed.targets,['ingredient.h','new/file.py']);
  assert.equal(candidate.targets[0],'ingredient.h');
  assert.equal(new TaskMemory().admit({...fixed,targets:['ingredient.h']},evidence(),['E1'],S,deps,'monitor').targets[0],'ingredient.h');
});

test('repair4 normalization cannot escape roots, touch git, or remove evidence/target count limits',async()=>{
  const {root,parent}=await dirs();
  for (const target of [parent,path.join(parent,'outside.py'),'../outside.py',`${root}/linked/../ingredient.h`,'.git/config',path.join(root,'.git','config'),root])
    await assert.rejects(normalizeMemoryTargets({...candidate,targets:[target]},root));
  await assert.rejects(normalizeMemoryTargets(candidate,'.'));
  await assert.rejects(normalizeMemoryTargets(candidate,path.parse(root).root));
  await assert.rejects(normalizeMemoryTargets({...candidate,targets:['a','b','c','d','e']},root),/four target paths/);
  assert.throws(()=>new TaskMemory().admit({...candidate,evidence_ids:['E1','E2','E3','E4']},evidence(),['E1','E2','E3','E4'],S,deps,'monitor'),/1–3 supplied evidence/);
});

test('repair4 target normalization rejects a symbolic-link traversal even when it resolves inside root',async()=>{
  const {root,parent}=await dirs();const directory=path.join(root,'real');await mkdir(directory);
  await writeFile(path.join(directory,'file.py'),'source');
  // Directory junctions need no Windows symlink privilege and are detected by lstat.
  await symlink(directory,path.join(root,'linked'),process.platform==='win32'?'junction':'dir');
  await symlink(parent,path.join(root,'outside'),process.platform==='win32'?'junction':'dir');
  for (const target of ['linked/file.py','outside/unknown.py',path.join(root,'linked','file.py')])
    await assert.rejects(normalizeMemoryTargets({...candidate,targets:[target]},root),/symbolic link/);
});

// These are instruction-contract tests, not claims that a real model obeys the
// prompt. Admission/receipt behavior is tested separately above and by the host.
test('repair4 monitor instruction describes evidence completeness separately from execution outcome',()=>{
  for (const text of ['finding|blocker|procedure','1–3 supplied evidence IDs','actual stdout or stderr channel','nativeToolError','conditional finding/procedure','Do not create a blocker or commandKey','memories:[]'])
    assert.ok(MONITOR.includes(text),text);
});

test('repair4 critic instruction grounds checks in observed public APIs and does not accept empty checks',()=>{
  for (const text of ['signatures/argument counts','never invent an API','direct test commands','check defect','checks:[] never proves success','complete actual check receipts','unavailable, partial, masked or invalid'])
    assert.ok(CRITIC.includes(text),text);
});
