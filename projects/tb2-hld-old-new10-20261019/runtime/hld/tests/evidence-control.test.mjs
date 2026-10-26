import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdir,mkdtemp,writeFile,symlink} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {CompletionLedger} from '../src/completion.mjs';
import {verificationReceipt} from '../src/verification-receipt.mjs';
import {Policy,actionKey} from '../src/policy.mjs';
import {Subgoals} from '../src/subgoals.mjs';
import {SubgoalController} from '../src/subgoal-controller.mjs';
import {adviserSuggestions,parseRoleOutput} from '../src/roles.mjs';
import {configureArtifactRoots,artifactTarget,recordArtifactStates} from '../src/artifacts.mjs';
import {dependencyState,fingerprint} from '../src/workspace.mjs';
import {deliveryPaths} from '../src/progress.mjs';
import {FullTask} from '../src/full-task.mjs';

const S='sha256:one',U='unknown:external_service';
const call=n=>({name:'bash',callId:`C${n}`,arguments:{command:'python check.py'}});
const failure={executed:true,complete:true,exitCode:1,stdout:'',stderr:'RuntimeError: not ready'};
const check={arguments:call(1).arguments,stdout_contains:['EXIT=0']};
const row=(extra={})=>({id:'E1',command:check.arguments.command,key:actionKey(call(1)),executed:true,complete:true,exitCode:0,clean:true,stdout:'EXIT=0',stderr:'',...extra});
const goal=(id,extra={})=>({id,title:'public behavior',acceptance:'public test passes',targets:['a.py'],depends_on:[],...extra});
const accepted={decision:'accept',requirements:['public behavior'],gaps:[],gap_updates:[{gap_id:'Gap-1',status:'closed',evidence_ids:['E1'],reason:'targeted current public check resolves this requirement'}]};
const targetedReceipt={evidence_id:'E1',passed:true,gap_ids:['Gap-1'],requirement_quotes:['parser'],basis:{level:'attributed_correctness_basis'}};

test('EC receipts: marker fact, command exit and evidence validity are independent',()=>{
  const r=verificationReceipt(check,row({clean:false,shellStageCoverage:'unknown_composite_statuses'}),{});
  assert.equal(r.command_execution,'succeeded');assert.equal(r.assertions[0].status,'met');
  assert.equal(r.passed,false);assert.match(r.harness_diagnostic.join(' '),/composite shell/);
});
test('EC receipts: absence in incomplete output is unknown; complete absence is unmet',()=>{
  assert.equal(verificationReceipt(check,row({stdout:'',complete:false}),{}).assertions[0].status,'unknown');
  assert.equal(verificationReceipt(check,row({stdout:''}),{}).assertions[0].status,'not_met');
  assert.equal(verificationReceipt(check,row({exitCode:1}),{}).passed,false);
  assert.equal(verificationReceipt(check,row({executed:false}),{}).passed,false);
});
test('EC ledger: paraphrased gaps keep the same harness-owned ID and survive restore',()=>{
  const ledger=new CompletionLedger();
  ledger.record({gaps:['bad parser'],requirements:['parse']},[],{accepted:false,scope:S,dependencies:{}});
  ledger.record({gaps:[],gap_updates:[{gap_id:'Gap-1',status:'open',detail:'parser still incorrect'}]},[],{accepted:false,scope:S,dependencies:{}});
  assert.equal(ledger.open().length,1);assert.equal(ledger.open()[0].id,'Gap-1');
  const restored=new CompletionLedger(JSON.parse(JSON.stringify(ledger.state)));
  assert.equal(restored.open()[0].id,'Gap-1');
});
test('EC ledger: changed related file reopens proof without changing its Gap ID',()=>{
  const ledger=new CompletionLedger();ledger.upsert('parser',{detail:'parser failure'});
  ledger.record(accepted,[targetedReceipt],{accepted:true,scope:S,dependencies:{'a.py':'file:old'},observed:1,evidence:{E1:row()}});
  assert.deepEqual(ledger.sync(S,{'a.py':'file:old',irrelevant:'file:x'},{},1),[]);
  assert.deepEqual(ledger.sync(S,{'a.py':'file:new'},{},2),['Gap-1']);
  assert.equal(ledger.open()[0].status,'needs_reverification');assert.equal(ledger.state.status,'repair_pending');
});
test('EC ledger: incremental close needs current receipts, stable new gap keys come from public requirement quotes',()=>{
  const ledger=new CompletionLedger(),context={accepted:false,scope:S,dependencies:{'a.py':'file:a'},observed:1,publicTask:'Implement parser and encoder.',evidence:{E1:row()}};
  ledger.record({gaps:[],new_gaps:[{obligation_id:'parser-behavior',requirement_quote:'parser',detail:'parser broken'},{obligation_id:'encoder-behavior',requirement_quote:'encoder',detail:'encoder broken'}]},[],context);
  assert.equal(ledger.open().length,2);
  ledger.record({gaps:[],gap_updates:[{gap_id:'Gap-1',status:'closed',evidence_ids:['fake']}]},[],context);
  assert.equal(ledger.open().length,2);
  ledger.record({gaps:[],gap_updates:[{gap_id:'Gap-1',status:'closed',evidence_ids:['E1'],reason:'targeted current check resolves parser requirement'}]},[targetedReceipt],context);
  assert.deepEqual(ledger.open().map(x=>x.id),['Gap-2']);
  assert.deepEqual(ledger.sync(S,{'a.py':'file:b'},{},2),['Gap-1']);
  ledger.record({gaps:[],gap_updates:[{gap_id:'Gap-2',status:'open',detail:'rephrased encoder problem'}]},[],context);
  assert.equal(ledger.state.gaps.length,2);
});
test('EC ledger: a newer execution supersedes old acceptance despite identical files',()=>{
  const ledger=new CompletionLedger();ledger.upsert('parser',{});
  ledger.record(accepted,[targetedReceipt],{accepted:true,scope:S,dependencies:{'a.py':'file:a'},evidence:{E1:row()},observed:1});
  assert.deepEqual(ledger.sync(S,{'a.py':'file:a'},{E2:row({id:'E2',exitCode:1})},2),['Gap-1']);
});
test('EC identical receipt renumbering is not new completion evidence; changed output is',()=>{
  const ledger=new CompletionLedger(),s={scope:S,dependencies:{},observed:1,evidence:{E1:row()}};
  const token=ledger.token(s);s.observed=2;s.evidence.E2=row({id:'E2'});
  assert.equal(ledger.token(s),token);s.evidence.E2.stdout='Different result';assert.notEqual(ledger.token(s),token);
});
test('EC ledger: unknown state never proves cross-action stability, same-observation refresh is not an action',()=>{
  const ledger=new CompletionLedger();ledger.upsert('parser',{});
  ledger.record(accepted,[targetedReceipt],{accepted:true,scope:U,dependencies:{'a.py':'unknown'},observed:4,evidence:{E1:row()}});
  assert.deepEqual(ledger.sync(U,{'a.py':'unknown'},{},4),[]);
  assert.deepEqual(ledger.sync(U,{'a.py':'unknown'},{},5),['Gap-1']);
});
test('EC ledger: failed/weak receipts become deterministic gaps even when Critic gives no gap',()=>{
  const ledger=new CompletionLedger(),receipt=verificationReceipt(check,row({clean:false}),{});
  ledger.record(accepted,[receipt],{accepted:false,scope:S,dependencies:{}});
  assert.equal(ledger.open()[0].kind,'verification_missing');assert.equal(ledger.open()[0].evidence_ids[0],'E1');
});
test('EC unavailable Critic: fallback uses real unmet goal and never treats model plan as full coverage',()=>{
  const goals=new Subgoals();goals.admit({subgoal_plan:[goal('G1')]});
  const ledger=new CompletionLedger();ledger.fallback(goals,{});
  assert.equal(ledger.open()[0].key,'goal:G1');assert.equal(ledger.deterministicCoverage(undefined,goals),false);
  assert.equal(ledger.deterministicCoverage([{id:'R1',goalIds:['G1']}],goals),false);
});
test('EC a missing-verification gap closes on current deterministic goal proof, then reopens after a source edit',()=>{
  const goals=new Subgoals();goals.admit({subgoal_plan:[goal('G1',{verification:{arguments:check.arguments,stdout_contains:['EXIT=0']}})]});
  const ledger=new CompletionLedger();ledger.fallback(goals,{});
  const deps={'a.py':'file:a'},e=row({dependenciesBefore:deps,dependenciesAfter:deps,after:S});
  goals.observe(e);ledger.reconcileGoals(goals,{E1:e},1);
  assert.equal(ledger.open().length,0);assert.equal(ledger.deterministicCoverage([{id:'R1',goalIds:['G1']}],goals),true);
  goals.sync({'a.py':'file:b'});ledger.sync(S,{'a.py':'file:b'},{E1:e},2);ledger.reconcileGoals(goals,{E1:e},2);
  assert.equal(ledger.open()[0].id,'Gap-1');
});
test('EC unknown-state three complete identical failures intervene without claiming unchanged environment',()=>{
  const p=new Policy({explorationEnabled:false});
  for(let n=1;n<=3;n++){assert.equal(p.before(call(n),U).allowed,true);p.noteAction(call(n));p.observe(call(n),failure,U,U);}
  const verdict=p.before(call(4),U);
  assert.equal(verdict.allowed,false);assert.equal(verdict.evidence.environment_unchanged,false);assert.equal(p.state.counters.observed,3);
});
test('EC an unknown explicit dependency cannot be rescued by a known whole-workspace hash',()=>{
  const p=new Policy({explorationEnabled:false});p.observe(call(1),failure,S,S,{'external':'unknown'});
  assert.equal(p.before(call(2),S,{dependencies:{external:'unknown'}}).allowed,true);
});
test('EC known failed input is blocked on second attempt, changed input can be re-tested',()=>{
  const p=new Policy({explorationEnabled:false});p.observe(call(1),failure,U,U,{'a.py':'file:a'});
  assert.equal(p.before(call(2),U,{dependencies:{'a.py':'file:a'}}).allowed,false);
  assert.equal(p.before(call(3),U,{dependencies:{'a.py':'file:b'}}).allowed,true);
});
for(const mode of ['edit','different_error','incomplete','unclean_zero'])test(`EC output stagnation is broken by ${mode}`,()=>{
  const p=new Policy({explorationEnabled:false});
  for(let n=1;n<=3;n++){p.noteAction(call(n));p.observe(call(n),failure,U,U);}
  if(mode==='edit')p.noteAction({name:'write',callId:'write',arguments:{file_path:'a.py'}});
  else {const observation=mode==='different_error'?{...failure,stderr:'New problem'}:mode==='incomplete'?{...failure,complete:false}:{...failure,exitCode:0,clean:false};p.noteAction(call(4));p.observe(call(4),observation,U,U);}
  assert.equal(p.before(call(5),U).allowed,true);
});
test('EC Advisor preserves usable partial hypotheses without granting execution authority',()=>{
  const answer=adviserSuggestions({alternatives:[{hypothesis:'check dependencies',evidence_ids:['E1','fake']},{bad:'row'}]},new Set(['E1']));
  assert.equal(answer.status,'partial');assert.equal(answer.alternatives.length,1);assert.equal(answer.alternatives[0].executable,false);
  assert.deepEqual(answer.alternatives[0].evidence_ids,['E1']);assert.equal(answer.alternatives[0].status,'unverified_suggestion');
  assert.throws(()=>parseRoleOutput('{"command":"unterminated'),SyntaxError);
});
test('EC subgoals retain all six and a malformed checker loses only verification',()=>{
  const goals=new Subgoals(),plan=Array.from({length:6},(_,i)=>goal(`G${i+1}`,{depends_on:i?[`G${i}`]:[]}));
  plan[0].verification={arguments:{command:'echo PASS'},stdout_contains:['PASS']};
  const result=goals.admit({subgoal_plan:plan});
  assert.equal(result.status,'partial');assert.equal(Object.keys(goals.state.items).length,6);assert.equal(goals.state.active,'G1');assert.equal(goals.state.items.G1.definition.verification,undefined);
});
test('EC dependency cycle has a diagnostic focus, not permission to bypass prerequisites; repair restores readiness',()=>{
  const goals=new Subgoals();goals.admit({subgoal_plan:[goal('G1',{depends_on:['G2']}),goal('G2',{depends_on:['G1']})]});
  const c=new SubgoalController(),v=c.tick(goals,{}).view;
  assert.equal(v.active,null);assert.equal(v.diagnostic_focus,'G1');assert.equal(v.dependency_unresolved,true);assert.equal(v.blocking,false);
  goals.admit({subgoal_update:{id:'G2',reason:'correct dependency direction',depends_on:[]}});
  assert.equal(goals.state.active,'G2');assert.equal(goals.view().diagnostic_focus,null);
});
test('EC malformed prerequisite goal stays a draft without deleting valid goals',()=>{
  const goals=new Subgoals();goals.admit({subgoal_plan:[{id:'G1'},goal('G2',{depends_on:['G1']})]});
  assert.equal(goals.state.drafts.length,1);assert.equal(goals.state.items.G2.dependencyProblem,'missing_prerequisite');assert.equal(goals.view().diagnostic_focus,'G2');
});
async function dirs(){const base=fileURLToPath(new URL('../.runtime/',import.meta.url));await mkdir(base,{recursive:true});const dir=await mkdtemp(path.join(base,'artifact-ec-'));const workspace=path.join(dir,'task'),external=path.join(dir,'results');await mkdir(workspace);await mkdir(external);configureArtifactRoots(workspace,[external]);return {workspace,external};}
test('EC external artifacts have explicit authority, baseline and change tracking; late registration is not called task-initial',async()=>{
  const {workspace,external}=await dirs(),file=path.join(external,'output.json'),key=artifactTarget(workspace,file),s={observed:0};
  assert.equal(key,'@artifacts/root1/output.json');recordArtifactStates(s,await dependencyState(workspace,[key]));
  assert.equal(s.artifacts[key].baseline,'missing');await writeFile(file,'{}');s.observed++;
  recordArtifactStates(s,await dependencyState(workspace,[key]));assert.equal(s.artifacts[key].change,'created_since_registration');
  recordArtifactStates(s,{'later.txt':'file:old'});assert.equal(s.artifacts['later.txt'].baseline_kind,'first_registered_observation');
  assert.throws(()=>artifactTarget(workspace,path.join(external,'..','other','secret')),/explicit/);
  const task=new FullTask({});task.state.artifacts=s.artifacts;assert.ok(task.targets().includes(key));
});
test('EC original public /results path is registered through configured roots and existing artifact remains unchanged',async()=>{
  const {workspace,external}=await dirs(),file=path.join(external,'output.json');await writeFile(file,'old');
  const targets=deliveryPaths('Create '+file.split(path.sep).join('/')+' as output',workspace);
  // Windows drive syntax is handled by the explicit path registry regardless
  // of prose path discovery; production CLI uses POSIX absolute paths.
  if(process.platform!=='win32')assert.ok(targets.includes('@artifacts/root1/output.json'));
  const key=artifactTarget(workspace,file),s={observed:0},deps=await dependencyState(workspace,[key]);recordArtifactStates(s,deps);recordArtifactStates(s,deps);
  assert.equal(s.artifacts[key].change,'unchanged_since_registration');
});
test('EC symlink state is unknown, declared external roots do not authorize linked escapes',async()=>{
  const {workspace,external}=await dirs(),link=path.join(external,'link');await symlink(workspace,link,process.platform==='win32'?'junction':'dir');
  const key=artifactTarget(workspace,path.join(link,'hidden.json'));
  assert.equal((await dependencyState(workspace,[key]))[key],'unknown');
});
test('EC an oversized global snapshot does not erase known targeted file evidence',async()=>{
  const {workspace}=await dirs();await writeFile(path.join(workspace,'a.py'),'12345');
  assert.match(await fingerprint(workspace,{maxBytes:1}),/^unknown:/);assert.match((await dependencyState(workspace,['a.py']))['a.py'],/^file:/);
});
