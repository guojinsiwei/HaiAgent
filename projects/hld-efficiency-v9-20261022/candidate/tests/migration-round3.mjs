// New acceptance probes, deliberately separate from the passing regression suite.
// No runtime changes; failures remain failures in the audit report.
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,readdir} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Context} from '@deepseek-ai/cordis';
import LlmRuntime from '@deepseek-ai/dsh-llm';
import ToolRuntime from '@deepseek-ai/dsh-tools';
import SystemPrompt from '@deepseek-ai/dsh-system-prompt';
import {Session} from '@deepseek-ai/dsh-session';
import {createScope} from '@deepseek-ai/dsh-scope';
import * as plugin from '../src/plugin.mjs';
import {FullTask} from '../src/full-task.mjs';
import {Policy} from '../src/policy.mjs';
import {CriticCache} from '../src/critic-cache.mjs';

const S='sha256:a',deps={'main.py':'file:a'},args={command:'python main.py'};
const c={name:'bash',arguments:args,callId:'a',commandDependencies:deps};
const failed={executed:true,complete:true,exitCode:1,stdout:'',stderr:'assertion failed'};
function setup() {
  const f=new FullTask({}),p=new Policy();f.observe(c,failed,S,S,deps,deps,p,'raw1');
  const m=f.memory.admit({kind:'blocker',conclusion:'main failure',condition:'same source',operation:'compile',targets:['main.py'],evidence_ids:['E1']},f.state.evidence,['E1'],S,deps);
  f.state.visibleMemories=[m.id];
  return {f,p};
}
function proposal(tool='bash',arguments_=args) {return {tool,arguments:arguments_,evidence_ids:['E1'],strategy_adjustment:'inspect then repair',memory_review:{ids:['M1'],decision:'apply',observed_result:'failure',applicability:'same source',reason:'repair relevant source'}};}
async function host(t) {
  const base=fileURLToPath(new URL('../.runtime/',import.meta.url));await mkdir(base,{recursive:true});
  const dir=await mkdtemp(path.join(base,'round3-')),workspace=path.join(dir,'task'),auditDir=path.join(dir,'audit');
  await mkdir(workspace);await writeFile(path.join(workspace,'main.py'),'original');
  const ctx=new Context();await ctx.plugin(LlmRuntime);await ctx.plugin(SystemPrompt,{});await ctx.plugin(ToolRuntime,{mode:'native'});
  await ctx.plugin(plugin,{workspace,auditDir,full:true});t.after(()=>ctx.fiber.dispose());
  // Shapes taken from the pinned official dsh-tool-bash / dsh-tool-jobs source.
  ctx.tools.register({name:'bash',description:'official promoted DTO fixture',parameters:{type:'object'},output:{schema:{type:'object'},render:()=>[{type:'text',text:'job J1 still running'}]},execute:()=>({kind:'promoted',jobId:'J1',timeoutMs:1000,output:'compiling...'})});
  ctx.tools.register({name:'job_output',description:'official completed job DTO fixture',parameters:{type:'object'},output:{schema:{type:'object'},render:(_a,v)=>[{type:'text',text:v.text+'\n[status: completed, exit code: 1]'}]},execute:()=>({text:'assertion failed',job:{id:'J1',kind:'bash',label:'python main.py',status:'completed',detail:'exit code: 1',startedAt:1,finishedAt:2}})});
  const agent={session:Session.create('round3'),ctx:createScope(ctx,{}).ctx};agent.id=agent.session.id;let n=0;
  const execute=(name,arguments_)=>ctx.tools.execute({name,arguments:arguments_,callId:`c${++n}`,agent,signal:new AbortController().signal});
  const state=async()=>{const files=await readdir(auditDir);return JSON.parse(await readFile(path.join(auditDir,files.find(x=>x.endsWith('.json'))),'utf8'));};
  return {execute,state};
}

test('R3-01 a promoted bash command must retain launch/job identity as incomplete executed evidence',async t=>{
  const h=await host(t);assert.equal((await h.execute('bash',args)).isError,false);
  const s=await h.state(),rows=Object.values(s.full.evidence);
  assert.ok(rows.some(r=>r.command===args.command&&(r.jobId==='J1'||r.job_id==='J1')),'successful promotion produced no E row linking J1 to the command');
});
test('R3-02 job completion must reconnect to the original command and pending failure review',async t=>{
  const h=await host(t);await h.execute('bash',args);await h.execute('job_output',{job_id:'J1',wait:true});
  const s=await h.state(),rows=Object.values(s.full.evidence);
  assert.ok(rows.some(r=>r.command===args.command&&s.full.pendingEvidence.includes(r.id)),'completed failing job is only a generic native observation, not linked failure evidence');
});
test('R3-03 malformed retry support is recoverable input, not an uncaught property-access error',()=>{
  const {f,p}=setup(),next=proposal();Object.assign(next.memory_review,{decision:'justified_retry',new_evidence:'new',hypothesis:'inspect hypothesis',support:[null]});
  assert.equal(p.propose(next,{visibleEvidence:['E1']}).accepted,true);
  assert.doesNotThrow(()=>f.before(c,p,S,deps));
});
test('R3-04 retry support from an intervening source version must be revalidated against current inputs',()=>{
  const {f,p}=setup(),b={'main.py':'file:b'};
  f.observe({...c,callId:'read',arguments:{command:'cat main.py'},commandDependencies:b},{...failed,exitCode:0,stderr:'',stdout:'SPECIAL_CASE = 2'},'sha256:b','sha256:b',b,b,p,'raw2');
  f.state.scope=S;f.state.dependencies=deps; // source returned to the original failed version
  const next=proposal();next.evidence_ids=['E2'];Object.assign(next.memory_review,{decision:'justified_retry',new_evidence:'special case exists',hypothesis:'new source branch may pass',support:[{evidence_id:'E2',target:'main.py',field:'stdout',quote:'SPECIAL_CASE = 2'}]});
  f.reviewProposal(next);assert.equal(p.propose(next,{visibleEvidence:['E1','E2']}).accepted,true);
  assert.equal(f.before(c,p,S,deps).allowed,false,'stale source quote incorrectly allowed same-version failed retry');
});
test('R3-05 reviewing an unrelated visible memory does not satisfy the matched target blocker',()=>{
  const {f,p}=setup();f.state.evidence.E2={id:'E2',complete:true,after:S,stdout:'notes',stderr:'',dependenciesAfter:{'other.txt':'file:b'}};
  const unrelated=f.memory.admit({kind:'finding',conclusion:'unrelated notes',condition:'other file',targets:['other.txt'],evidence_ids:['E2']},f.state.evidence,['E2'],S,{'other.txt':'file:b'});
  f.state.visibleMemories=['M1',unrelated.id];
  const change={file_path:'main.py',content:'changed'},next=proposal('write',change);next.memory_review.ids=[unrelated.id];
  f.reviewProposal(next);assert.equal(p.propose(next,{visibleEvidence:['E1','E2']}).accepted,true);
  assert.equal(f.before({name:'write',arguments:change,callId:'w'},p,S,deps).allowed,false,'reviewing unrelated M2 bypassed matching blocker M1');
});
test('R3-06 a rejected replacement proposal must invalidate the previous pending action authorization',()=>{
  const {f,p}=setup(),change={file_path:'main.py',content:'fixed'};
  assert.equal(p.propose(proposal('write',change),{visibleEvidence:['E1']}).accepted,true);
  assert.equal(p.propose({...proposal('write',change),evidence_ids:['E999']},{visibleEvidence:['E1']}).accepted,false);
  assert.equal(f.before({name:'write',arguments:change,callId:'w'},p,S,deps).allowed,false,'previous proposal remained executable after replacement was rejected');
});
test('R3-07 current deployed-template candidate serializes tools and leaves delegated solvers disabled',async()=>{
  const config=await readFile(new URL('../config/common.patch.yml',import.meta.url),'utf8');
  assert.match(config,/maxParallelToolCalls: 1/);assert.match(config,/- id: tool-subagent\s+disabled: true/);
});
test('R3-08 new task restores neither active rollback nor a previous process Critic cache',()=>{
  const f=new FullTask({});assert.equal(f.config.backtracking,false);assert.equal(f.state.pendingRollback,null);
  assert.equal(new CriticCache().get({arguments:args,cache_scope:'workspace'},f),null);
});
