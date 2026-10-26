import test from 'node:test';
import {fixtureReview} from './review-fixture.mjs';
import assert from 'node:assert/strict';
import { Context } from '@deepseek-ai/cordis';
import SystemPrompt, { renderContextSections } from '@deepseek-ai/dsh-system-prompt';
import ToolRuntime from '@deepseek-ai/dsh-tools';
import { createScope, scopeOf } from '@deepseek-ai/dsh-scope';
import { Session } from '@deepseek-ai/dsh-session';
import SessionStore from '@deepseek-ai/dsh-session';
import LlmRuntime, { LlmAdapter, createUserMessage } from '@deepseek-ai/dsh-llm';
import AgentRegistry from '@deepseek-ai/dsh-agent';
import AgentLoop from '@deepseek-ai/dsh-agent-loop';
import SessionProjections from '@deepseek-ai/dsh-session-projection';
import * as plugin from '../src/plugin.mjs';
import { mkdtemp, mkdir, writeFile, readdir, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const args = { command: 'python check.py', description: 'run a public check' };
const outcome = () => ({ kind: 'foreground', exitCode: 1, timedOut: false, aborted: false,
  signal: null, timeoutMs: 600000, stdout: { text: '', truncated: false },
  stderr: { text: '\x1b[31mMissing dependency\x1b[0m', truncated: false } });

async function fixture(t, options = {}) {
  const runtime = fileURLToPath(new URL('../.runtime/', import.meta.url));
  await mkdir(runtime, { recursive: true });
  const base = await mkdtemp(path.join(runtime, 'host-'));
  const workspace = path.join(base, 'task'), auditDir = path.join(base, 'audit');
  await mkdir(workspace);
  await writeFile(path.join(workspace, 'check.py'), 'original');
  if(options.publicTask)await writeFile(path.join(workspace,options.taskInstructionPath),options.publicTask);
  const ctx = new Context();
  await ctx.plugin(LlmRuntime);
  if (options.realLoop) {
    await ctx.plugin(SessionStore);
    await ctx.plugin(SessionProjections);
    await ctx.plugin(AgentRegistry);
  }
  await ctx.plugin(SystemPrompt, {});
  await ctx.plugin(ToolRuntime, { mode: 'native' });
  const fiber = ctx.plugin(plugin, { workspace, auditDir, full: false, ...options });
  await fiber;
  if (options.realLoop) await ctx.plugin(AgentLoop, { agents: [], maxParallelToolCalls: 1 });
  let executions = 0;
  ctx.tools.register({ name: 'bash', description: 'Scripted shell DTO fixture; no process or API call.',
    parameters: { type: 'object', additionalProperties: true },
    output: { schema: { type: 'object', additionalProperties: true }, render: () => [{ type: 'text', text: 'native-result-unchanged' }] },
    async execute(a,exec) { executions++; return options.shell?options.shell(a,exec,executions):outcome(); }, isConcurrencySafe: () => false });
  const session = Session.create('test-session');
  const agent = { id: session.id, session, ctx: createScope(ctx, {}).ctx };
  const execute = (name = 'bash', arguments_ = args, who = agent) => ctx.tools.execute({
    name, arguments: arguments_, callId: `call-${Math.random()}`, agent: who, signal: new AbortController().signal });
  t.after(() => ctx.fiber.dispose());
  return { ctx, execute, agent, workspace, auditDir, executions: () => executions };
}

test('prompt assembly refreshes evidence without leaking another session', async t => {
  const f = await fixture(t); await f.execute();
  const scope = scopeOf(f.agent.ctx);
  for (let i = 0; i < 2; i++) {
    const prompt = await f.ctx.systemPrompt.assemble({ scope });
    assert.match(renderContextSections(prompt).find(x => x.name === 'kz:evidence').text, /"id":"E1"/);
  }
  const other = await f.ctx.systemPrompt.assemble({ scope: {} });
  assert.ok(!JSON.stringify(renderContextSections(other)).includes('E1'));
});

test('evidence braces survive the REAL host renderer as literal values across sessions', async t => {
  const literal = `{{'k','A',1,false},{'z','B',2,true}} {{unknown_name}} {{ nested {{x}} }}\n"quotes" \\path\\file {{unterminated`;
  const f = await fixture(t, {shell:()=>({...outcome(),stderr:{text:literal,truncated:false}})});
  await f.execute();
  const assembly = await f.ctx.systemPrompt.assemble({scope:scopeOf(f.agent.ctx)});
  const expected=assembly.variables.kz_evidence_literal;
  assert.ok(expected.includes("{{'k','A',1,false}"));
  assert.ok(expected.includes('{{unknown_name}}'));
  assert.equal(renderContextSections(assembly).find(x=>x.name==='kz:evidence').text,expected);
  const other=await f.ctx.systemPrompt.assemble({scope:{}});
  assert.ok(!JSON.stringify(renderContextSections(other)).includes('{{unknown_name}}'));
});

test('outside-workspace calls are not classified as unchanged state', async t => {
  const f = await fixture(t);
  const outside = { ...args, workdir: path.dirname(f.workspace) };
  await f.execute('bash', outside);
  assert.equal((await f.execute('bash', outside)).isError, false);
  assert.equal(f.executions(), 2);
});

test('native strategy tool binds its proposal to the subsequent bash call', async t => {
  const f = await fixture(t);
  await f.execute(); await f.execute('bash', { ...args, command: 'node check.js' });
  const next = { command: 'find packages -type f', description: 'inspect declarations' };
  const proposal = await f.execute('kz_strategy', { tool: 'bash', arguments: next,
    memory_review: 'E1 and E2 failed.', strategy_adjustment: 'Inspect declarations.', evidence_ids: ['E1', 'E2'],
    orthogonality_proof: { dependency_dimension: 'inspect installed packages', target_dimension: 'package declarations', command_dimension: 'inspection' } });
  assert.equal(proposal.isError, false); assert.equal(proposal.value.accepted, true);
  assert.equal((await f.execute('bash', next)).isError, false);
});

class ScriptedAdapter extends LlmAdapter {
  requests = [];
  async resolveModel(provider, model) { return { provider, id: model, name: model }; }
  async *stream(options) {
    this.requests.push(options);
    const index = this.requests.length;
    if (index > 3) throw new Error('unexpected extra model turn');
    const block = index < 3
      ? { type: 'tool-call', id: `test-${index}`, name: 'bash', arguments: JSON.stringify(args) }
      : { type: 'text', text: 'Stopped repeating after reading the evidence.' };
    yield { type: 'block-start', index: 0, blockType: block.type };
    if (block.type === 'tool-call') yield { type: 'tool-call-delta', index: 0, id: block.id, name: block.name, argumentsDelta: block.arguments };
    else yield { type: 'text-delta', index: 0, text: block.text };
    yield { type: 'block-end', index: 0, block };
    yield { type: 'usage', usage: { inputTokens: 10, outputTokens: 5 } };
    yield { type: 'finish', reason: { kind: index < 3 ? 'tool-calls' : 'stop' } };
  }
}

test('real official agent loop receives evidence and recovers from gate denial, zero API', { timeout: 10000 }, async t => {
  const f = await fixture(t, { realLoop: true });
  const adapter = new ScriptedAdapter();
  f.ctx.llm.registerAdapter(['fixture'], adapter);
  const agent = await f.ctx.agentLoop.create('real-loop-test', { provider: 'fixture', model: 'fixture' }, { cwd: f.workspace });
  const idle = new Promise(resolve => {
    const stop = f.ctx.on('agent/status', ({ agent: who, status }) => {
      if (who === agent && status === 'idle') { stop(); resolve(); }
    });
  });
  agent.followup(createUserMessage({ content: [{ type: 'text', text: 'Run the local check.' }], source: { kind: 'user' } }));
  await idle;
  assert.equal(adapter.requests.length, 3);
  assert.equal(f.executions(), 1);
  assert.match(JSON.stringify(adapter.requests[1]), /E1/);
  assert.match(JSON.stringify(adapter.requests[2]), /same_failed_command_in_unchanged_workspace/);
});

test('actual DSH registry loads plugin and preserves native result; next repeat denied', async t => {
  const f = await fixture(t);
  const first = await f.execute();
  assert.equal(first.isError, false);
  assert.equal(first.value.exitCode, 1); // tool infrastructure succeeded, command failed
  assert.deepEqual(first.content, [{ type: 'text', text: 'native-result-unchanged' }]);
  const second = await f.execute();
  assert.equal(second.isError, true); assert.equal(f.executions(), 1);
  const files = await readdir(f.auditDir);
  const checkpoint = JSON.parse(await readFile(path.join(f.auditDir, files.find(x => x.endsWith('.json')))));
  assert.equal(checkpoint.state.memories.length, 1);
  assert.equal(checkpoint.state.counters.denied, 1);
});
test('actual DSH registry permits re-test after workspace edit', async t => {
  const f = await fixture(t); await f.execute();
  await writeFile(path.join(f.workspace, 'check.py'), 'repaired');
  assert.equal((await f.execute()).isError, false); assert.equal(f.executions(), 2);
});
test('host permission denial is preserved and not admitted into failure memory', async t => {
  const f = await fixture(t);
  f.ctx.on('tools/pre-execute', () => ({ kind: 'deny', reason: 'host-permission-denied' }));
  const result = await f.execute();
  assert.equal(result.isError, true); assert.equal(f.executions(), 0);
});
test('different sessions do not share evidence', async t => {
  const f = await fixture(t); await f.execute();
  const session = Session.create('another-task');
  const other = { id: session.id, session, ctx: createScope(f.ctx, {}).ctx };
  assert.equal((await f.execute('bash', args, other)).isError, false);
  assert.equal(f.executions(), 2);
});

test('recreated agent restores task evidence and invalidates pending proposal', async t => {
  const f = await fixture(t); await f.execute();
  await f.execute('kz_strategy', { tool: 'bash', arguments: { ...args, command: 'node changed.js' },
    memory_review: 'E1 failed.', strategy_adjustment: 'Inspect another runtime.', evidence_ids: ['E1'] });
  const resumed = { id: f.agent.id, session: f.agent.session, ctx: createScope(f.ctx, {}).ctx };
  assert.equal((await f.execute('bash', args, resumed)).isError, true);
  const files = await readdir(f.auditDir);
  const checkpoint = JSON.parse(await readFile(path.join(f.auditDir, files.find(x => x.endsWith('.json')))));
  assert.equal(checkpoint.state.pending, null);
  assert.equal(checkpoint.state.memories.length, 1);
});

test('workspace mismatch fails explicitly instead of reading another task', async t => {
  const f = await fixture(t);
  const base = Session.create('mismatched');
  const session = Session.create(base.id, [], { ...base.header, cwd: path.dirname(f.workspace) });
  const agent = { id: session.id, session, ctx: createScope(f.ctx, {}).ctx };
  const result = await f.execute('bash', args, agent);
  assert.equal(result.isError, true); assert.equal(f.executions(), 0);
});
test('seven denials leave native loop runnable, not terminated', async t => {
  const f = await fixture(t); await f.execute();
  for (let i = 0; i < 7; i++) assert.equal((await f.execute()).isError, true);
  assert.equal((await f.execute()).isError, false); assert.equal(f.executions(), 2);
});
test('disabled plugin is a true no-op with no strategy tool or audit', async t => {
  const f = await fixture(t, { enabled: false });
  assert.equal((await f.execute()).isError, false);
  assert.equal((await f.execute()).isError, false); assert.equal(f.executions(), 2);
  assert.equal((await f.execute('kz_strategy', {})).isError, true);
});

class FullAdapter extends LlmAdapter {
  requests=[]; solver=0;
  constructor(script,roleReply=null) { super();this.script=script;this.roleReply=roleReply; }
  async resolveModel(provider,model) {return{provider,id:model,name:model};}
  async *stream(options) {
    this.requests.push(options);
    let block;
    if(options.system) {
      const payload=JSON.parse(options.messages[0].content[0].text);
      let value;
      if(payload.question)value={alternatives:[{hypothesis:'check the dependency declaration',check:'inspect manifest',difference:'inspect before retry',evidence_ids:[payload.handover?.failed_attempts_and_trigger_evidence[0]?.id??'E1']}]};
      else if(payload.stage==='plan_checks')value={decision:'accept',requirements:['public check'],gaps:[],checks:[{arguments:args,stdout_contains:['passed']}]};
      else if(payload.stage==='verdict')value={decision:'accept',requirements:['public check'],gaps:[],checks:[]};
      else {
        const row=Object.values(payload.evidence).at(-1),field=row.stderr?'stderr':'stdout';
        value={verdict:'uncertain',reason:'Only public receipts are available.',evidence_ids:[row.id],next_check:'run check after repair',
          memories:[{kind:'blocker',conclusion:'check.py had a conditional result',condition:'On the observed check.py version',targets:['check.py'],evidence_ids:[row.id],support:[{evidence_id:row.id,field,quote:row[field]}]}]};
      }
      if(this.roleReply)value=this.roleReply(payload,value);
      if(!this.rawReview)value=fixtureReview(payload,value);
      block={type:'text',text:JSON.stringify(value)};
    } else {
      const action=this.script[this.solver++];if(!action)throw new Error('solver script exhausted');
      block=typeof action==='string'?{type:'text',text:action}:{type:'tool-call',id:`full-${this.solver}`,name:action.name,arguments:JSON.stringify(action.args)};
    }
    yield{type:'block-start',index:0,blockType:block.type};
    if(block.type==='text')yield{type:'text-delta',index:0,text:block.text};
    else yield{type:'tool-call-delta',index:0,id:block.id,name:block.name,argumentsDelta:block.arguments};
    yield{type:'block-end',index:0,block};yield{type:'usage',usage:{inputTokens:10,outputTokens:5}};
    yield{type:'finish',reason:{kind:block.type==='text'?'stop':'tool-calls'}};
  }
}

test('V9.1 malformed verdict retries only the verdict and retains the single native check',{timeout:15000},async t=>{
  const f=await fixture(t,{full:true,realLoop:true,monitorEnabled:false,efficiencyEnabled:true,
    shell:()=>({...outcome(),exitCode:0,stdout:{text:'passed',truncated:false},stderr:{text:'',truncated:false}})});
  let verdicts=0;
  const adapter=new FullAdapter(['Ready','Done'],(p,v)=>p.stage==='verdict'&&++verdicts===1?{...v,decision:'invalid_format'}:v);
  const saved=await runFull(f,adapter);
  const stages=adapter.requests.filter(r=>r.system).map(r=>JSON.parse(r.messages[0].content[0].text).stage);
  assert.deepEqual(stages,['plan_checks','verdict','verdict']);
  assert.equal(f.executions(),1);assert.equal(saved.full.usage.roles.critic,3);
  assert.equal(saved.full.critic.decision,'public_review_accepted');
});
test('EC3 actual AgentLoop accepts missing-information plan without executing a check or buying a verdict',{timeout:15000},async t=>{
  const f=await fixture(t,{full:true,realLoop:true,monitorEnabled:false});
  const adapter=new FullAdapter(['Ready','No public source available','Still blocked'],payload=>({decision:'revise',reason_kind:'missing_information',requirements:[],gaps:['Expected premise has no independent source'],checks:[],next_step:'Read the public specification before deriving expectations.'}));
  adapter.rawReview=true;
  const saved=await runFull(f,adapter);
  assert.equal(f.executions(),0);assert.equal(saved.full.usage.roles.critic,1);
  assert.equal(saved.full.critic.decision,'missing_information');assert.ok(saved.full.completion.gaps.some(g=>g.status==='open'));
});
test('EC3 actual AgentLoop rejects composite check before shell execution',{timeout:15000},async t=>{
  const f=await fixture(t,{full:true,realLoop:true,monitorEnabled:false});
  const adapter=new FullAdapter(['Ready','Need a script','Still blocked'],(p,v)=>p.stage==='plan_checks'?{...v,checks:[{arguments:{command:'python check.py; echo passed'},stdout_contains:['passed']}]}:v);
  const saved=await runFull(f,adapter);
  assert.equal(f.executions(),0);assert.equal(saved.full.usage.roles.critic,1);assert.equal(saved.full.critic.decision,'repair_check');
});
test('EC3 actual AgentLoop retains plan-stage formula gap despite global accept of a self-check',{timeout:15000},async t=>{
  const f=await fixture(t,{full:true,realLoop:true,monitorEnabled:false,shell:cleanOutcome});
  const adapter=new FullAdapter(['Ready','No further evidence','Still unverified'],(p,v)=>{
    if(p.stage==='plan_checks')return {decision:'revise',requirements:[p.original_task],gaps:['Underlying formula has not been independently verified'],checks:[{arguments:args,stdout_contains:['passed'],gap_ids:[],requirement_quotes:[p.original_task],provenance:{author:'solver',kind:'self_consistency',expected_rule:'match candidate output'}}]};
    return {decision:'accept',requirements:[p.original_task],gaps:[],checks:[]};
  });adapter.rawReview=true;
  const saved=await runFull(f,adapter);
  assert.equal(f.executions(),1);assert.equal(saved.full.usage.roles.critic,2);
  assert.notEqual(saved.full.completion.status,'completed_publicly');assert.equal(saved.full.completion.gaps[0].status,'open');
});
async function runFull(f,adapter) {
  f.ctx.llm.registerAdapter(['full-fixture'],adapter);
  const agent=await f.ctx.agentLoop.create('full-test',{provider:'full-fixture',model:'fixture'},{cwd:f.workspace});
  const done=new Promise(resolve=>{const dispose=f.ctx.on('agent/status',({agent:a,status})=>{if(a===agent&&status==='idle'){dispose();resolve();}});});
  agent.followup(createUserMessage({content:[{type:'text',text:'Repair check.py and pass its public check.'}],source:{kind:'user'}}));await done;
  const files=await readdir(f.auditDir);return JSON.parse(await readFile(path.join(f.auditDir,files.find(x=>x.endsWith('.json')))));
}

for(const efficiencyEnabled of [false,true])for(const publicTask of ['Repair check.py and pass its public check.','# Requirements\n- Repair check.py and pass its public check.\n','Repair check.py.\n\nKeep empty inputs valid.'])test((efficiencyEnabled?'EFFICIENCY ':'')+'HLD v8 complete public catalog binds all requirements and closes targeted gap: '+publicTask,{timeout:20000},async t=>{
  const f=await fixture(t,{full:true,realLoop:true,efficiencyEnabled,monitorEnabled:false,taskInstructionPath:'PUBLIC_TASK.md',publicTask,shell:()=>({...outcome(),exitCode:0,stdout:{text:'passed',truncated:false},stderr:{text:'',truncated:false}})});
  const adapter=new FullAdapter(['Ready for public review.'],p=>{
    assert.equal(p.requirement_catalog[0].id,'Q1');
    if(p.stage==='plan_checks')return {decision:'revise',requirements:[],gaps:[],
      new_gaps:[{obligation_id:'public_check',requirement_ref:'Q1',detail:'Public check is unverified',proof_obligation:'correctness_basis',next_step:'Execute the supplied public check'}],
      checks:[{arguments:args,stdout_contains:['passed'],gap_ids:[],gap_refs:['Public check is unverified'],requirement_refs:p.requirement_catalog.map(q=>q.id),
        provenance:{author:'task-provided',kind:'public_spec',expected_rule:p.requirement_catalog[0].quote,
          sources:[{kind:'task',requirement_ref:'Q1'}],independence:'This fixture checks the provided public requirement.'}}]};
    const ids=p.actual_check_observations.map(x=>x.evidence_id);
    return {decision:'accept',requirements:[],requirement_refs:p.requirement_catalog.map(q=>q.id),gaps:[],checks:[],
      gap_updates:p.existing_gaps.map(g=>({gap_id:g.id,status:'closed',evidence_ids:ids,reason:'Actual public test receipt covers the original obligation'})),
      requirement_evidence:p.requirement_catalog.map(q=>({requirement_ref:q.id,evidence_ids:ids,reason:'Actual public test covers the fixture requirement'}))};
  });adapter.rawReview=true;
  const saved=await runFull(f,adapter);
  assert.equal(saved.full.critic.decision,'public_review_accepted');
  assert.equal(saved.full.completion.gaps.length,1);
  assert.equal(saved.full.completion.gaps[0].status,'closed');
  assert.equal(f.executions(),1);
  assert.equal(adapter.requests.length,3);
});

test('empty Critic plan recovers only after a new public observation, not a repeated final',{timeout:15000},async t=>{
  const f=await fixture(t,{full:true,realLoop:true,monitorEnabled:false,shell:()=>({...outcome(),exitCode:0,stderr:{text:'',truncated:false},stdout:{text:'passed',truncated:false}})});
  let plans=0;
  const adapter=new FullAdapter(['Ready for review.',{name:'bash',args},'The public check has now run.'],(payload,value)=>{
    if(payload.stage==='plan_checks'&&++plans===1)return{decision:'revise',requirements:['public check'],gaps:['need a valid check'],checks:[]};
    return value;
  });
  const saved=await runFull(f,adapter);
  assert.equal(saved.full.critic.rounds,2);assert.equal(saved.full.usage.roles.critic,3);
  assert.equal(saved.full.critic.decision,'public_review_accepted');assert.equal(f.executions(),2);
  assert.match(JSON.stringify(adapter.requests.filter(r=>!r.system)[1]),/missing_information/);
  assert.equal(saved.full.usage.requests,adapter.requests.length);
});

test('REPAIR4 repeatedly empty Critic plans never become success or an unbounded review loop',{timeout:15000},async t=>{
  const f=await fixture(t,{full:true,realLoop:true,monitorEnabled:false});
  const adapter=new FullAdapter(['Ready.','Partial delivery; review unavailable.','Still no action.'],(payload,value)=>payload.stage==='plan_checks'?{decision:'accept',requirements:['public check'],gaps:[],checks:[]}:value);
  const saved=await runFull(f,adapter);
  assert.equal(saved.full.critic.rounds,1);assert.equal(saved.full.critic.decision,'repair_check');
  assert.equal(saved.full.usage.roles.critic,1);assert.equal(adapter.solver,3);assert.equal(f.executions(),0);
  assert.equal(saved.full.completion.status,'incomplete_repeated_submission');
});
test('EC official loop: three substantive completion reviews retain the same gap and do not auto-deliver after two',{timeout:15000},async t=>{
  const f=await fixture(t,{full:true,realLoop:true,monitorEnabled:false,shell:cleanOutcome});let verdicts=0;
  const adapter=new FullAdapter(['Ready',{name:'bash',args:{command:'cat check.py'}},'Rechecked',{name:'bash',args:{command:'head -n 1 check.py'}},'Checked again'],(payload,value)=>{
    if(payload.stage==='verdict'&&++verdicts<3)return {...value,decision:'revise',gaps:[`public behavior gap wording ${verdicts}`]};
    return value;
  });
  const saved=await runFull(f,adapter);
  assert.equal(saved.full.critic.rounds,3);assert.equal(saved.full.completion.status,'completed_publicly');
  assert.equal(saved.full.completion.gaps.length,2);assert.equal(saved.full.completion.gaps[0].id,'Gap-1');assert.ok(saved.full.completion.gaps.every(g=>g.status==='closed'));
  assert.equal(saved.full.usage.roles.critic,6);assert.equal(saved.full.usage.nativeActions,5);
  assert.equal(saved.full.usage.requests,adapter.requests.length);
});
for(const completeManifest of [true,false])test(`EC official loop: unavailable Critic fallback needs operator coverage=${completeManifest}`,{timeout:15000},async t=>{
  const f=await fixture(t,{full:true,realLoop:true,monitorEnabled:false,shell:cleanOutcome,
    ...(completeManifest?{completionRequirements:[{id:'R1',goalIds:['G1']}]}:{})});
  const adapter=new FullAdapter([
    {name:'kz_update',args:{subgoal_plan:[{id:'G1',title:'public behavior',acceptance:'public check passes',targets:['check.py'],depends_on:[],verification:{arguments:args,stdout_contains:['passed']}}]}},
    {name:'bash',args},'Ready',...(!completeManifest?['Again','Still done']:[])
  ],(payload,value)=>payload.stage?{}:value);
  const saved=await runFull(f,adapter);
  assert.equal(saved.full.critic.rounds,completeManifest?2:1);
  assert.equal(saved.full.completion.status,completeManifest?'completed_with_unverified_critic':'incomplete_repeated_submission');
  assert.notEqual(saved.full.critic.decision,'public_review_accepted');assert.equal(f.executions(),1);
});
test('EC dynamic command uses output-side intervention, not filesystem equality',{timeout:15000},async t=>{
  const f=await fixture(t,{full:true,explorationEnabled:false});
  const arguments_={command:'curl http://localhost:8080/health'};
  for(let i=0;i<3;i++)assert.equal((await f.execute('bash',arguments_)).isError,false);
  assert.equal((await f.execute('bash',arguments_)).isError,true);assert.equal(f.executions(),3);
  const event=(await auditEvents(f)).filter(x=>x.event==='gate').at(-1);
  assert.equal(event.decision.reason,'repeated_identical_failure_output_state_unknown');
});

test('EC2 real Linux shell: literal cd receipt verifies the planned explicit cwd',{skip:process.platform==='win32',timeout:15000},async t=>{
  const f=await fixture(t,{full:true,realLoop:true,monitorEnabled:false,shell:async a=>{
    const result=await promisify(execFile)('/bin/sh',['-c',a.command],{cwd:a.workdir??f.workspace});
    return {...cleanOutcome(),stdout:{text:result.stdout,truncated:false},stderr:{text:result.stderr,truncated:false}};
  }});
  await writeFile(path.join(f.workspace,'check-public.mjs'),'console.log("passed")');
  const planned={command:`${process.execPath} check-public.mjs`,workdir:f.workspace};
  const actual={command:`cd ${f.workspace} && ${process.execPath} check-public.mjs`};
  const adapter=new FullAdapter([
    {name:'kz_update',args:{subgoal_plan:[{id:'G1',title:'public check',acceptance:'passes',targets:['check-public.mjs'],depends_on:[],verification:{arguments:planned,stdout_contains:['passed']}}]}},
    {name:'bash',args:actual},'Delivered.'
  ],(p,v)=>p.stage==='plan_checks'?{...v,checks:[{arguments:planned,stdout_contains:['passed']}]}:v);
  const saved=await runFull(f,adapter);
  assert.equal(saved.full.subgoals.items.G1.status,'check_passed');
  const row=Object.values(saved.full.evidence).find(r=>r.arguments?.command===actual.command);
  assert.ok(row?.executed);assert.equal(row.exitCode,0);assert.match(row.stdout,/passed/);
  assert.equal(saved.full.usage.requests,adapter.requests.length);
});

for(const action of ['execute','archive'])test(`EC2 official loop: ${action} after diagnosis is activity even with identical evidence`,{timeout:15000},async t=>{
  const f=await fixture(t,{full:true,realLoop:true,monitorEnabled:false,shell:cleanOutcome});
  const extra=action==='execute'?{name:'bash',args}:{name:'kz_history',args:{id:'E1'}};
  const adapter=new FullAdapter([{name:'bash',args},'Ready','Same conclusion',extra,'After actual observation','Now no further action'],
    (payload,value)=>payload.stage==='verdict'?{...value,decision:'revise',gaps:['public behavior still needs work']}:value);
  const saved=await runFull(f,adapter);
  assert.equal(adapter.solver,6,'fresh activity must not be mistaken for an unchanged no-action submission');
  assert.equal(saved.full.critic.rounds,1,'identical evidence must not buy another paid review');
  assert.equal(saved.full.completion.status,'incomplete_repeated_submission');
  assert.equal(saved.full.usage.requests,adapter.requests.length);
});
test('EC malformed optional review cannot block an otherwise ordinary executable action',async t=>{
  const f=await fixture(t,{full:true});await f.execute();
  await f.execute('kz_update',{memory:{kind:'blocker',conclusion:'check failed',condition:'same source',targets:['check.py'],evidence_ids:['E1']}});
  await f.ctx.systemPrompt.assemble({scope:scopeOf(f.agent.ctx)});
  const result=await f.execute('kz_strategy',{tool:'bash',arguments:{command:'cat check.py'},memory_review:{ids:['M1']},execute:true});
  assert.equal(result.isError,false);assert.equal(result.value.accepted,true);assert.ok(result.value.metadata.memory_review.ignored);assert.equal(f.executions(),2);
});
test('FULL official-loop chain: subgoal → failure → quoted memory → edit → reviewed retry → snapshot → independent Critic', {timeout:15000}, async t=>{
  const f=await fixture(t,{realLoop:true,full:true,backtracking:true,monitorCooldown:1,shell:(_a,_e,n)=>n===1?outcome():{...outcome(),exitCode:0,stderr:{text:'',truncated:false},stdout:{text:'passed',truncated:false}}});
  f.ctx.tools.register({name:'write',description:'fixture edit',parameters:{type:'object',additionalProperties:true},output:{schema:{type:'object'},render:()=>[{type:'text',text:'edited'}]},
    async execute(){await writeFile(path.join(f.workspace,'check.py'),'repaired');return{};}});
  const adapter=new FullAdapter([
    {name:'kz_update',args:{subgoal_plan:[{id:'G1',title:'repair check',acceptance:'public check passes',depends_on:[],targets:['check.py'],verification:{arguments:args,stdout_contains:['passed']}}]}},
    {name:'bash',args},
    {name:'kz_strategy',args:{tool:'write',arguments:{},evidence_ids:['E1'],memory_review:{ids:['M1'],observed_result:'missing dependency',applicability:'same source',decision:'apply',reason:'repair the observed source'},strategy_adjustment:'Repair the source before revalidating'}},
    {name:'write',args:{}},
    {name:'kz_strategy',args:{tool:'bash',arguments:args,evidence_ids:['E1'],memory_review:{ids:['M1'],observed_result:'missing dependency',applicability:'source changed',decision:'justified_retry',reason:'validate repair',new_evidence:'check.py edited'},strategy_adjustment:'Repeat original public test on changed source'}},
    {name:'bash',args},'Delivered the repair.'
  ]);
  const saved=await runFull(f,adapter);
  assert.equal(adapter.solver,7);assert.equal(saved.full.subgoals.items.G1.status,'check_passed');
  assert.ok(saved.full.memory.items.length>=1);assert.equal(saved.full.critic.decision,'public_review_accepted');
  assert.equal(saved.full.checkpoints.length,1);assert.equal(saved.full.usage.requests,adapter.requests.length);
  assert.equal(saved.full.usage.roles.critic,2);assert.equal(saved.full.usage.roles.monitor,1); // early anomaly lane; later quota reserved
  assert.equal(saved.full.usage.tools,7);assert.equal(f.executions(),3);
  assert.match(JSON.stringify(adapter.requests.filter(r=>!r.system)[3]),/M1/);
  for(const r of adapter.requests.filter(r=>r.system))assert.equal(r.messages.length,1);
});
test('FULL auxiliary roles share the task request budget; no extra hidden allowance',{timeout:15000},async t=>{
  const f=await fixture(t,{realLoop:true,full:true,maxRequests:3,monitorCooldown:1});
  const adapter=new FullAdapter([{name:'bash',args},'done']);const saved=await runFull(f,adapter);
  assert.equal(adapter.requests.length,3);assert.equal(saved.full.usage.requests,3);assert.equal(saved.full.usage.roles.monitor,1);
});
test('FULL malformed strategy is recoverable and enters local correction without failure memory',async t=>{
  const f=await fixture(t,{full:true});const result=await f.execute('kz_strategy',{});assert.equal(result.isError,false);assert.equal(result.value.accepted,false);
  const files=await readdir(f.auditDir),saved=JSON.parse(await readFile(path.join(f.auditDir,files.find(x=>x.endsWith('.json')))));
  assert.equal(saved.full.local.kind,'protocol');assert.deepEqual(saved.full.evidence,{});
});
test('FULL optional adviser uses an independent request and the same task budget',{timeout:15000},async t=>{
  const f=await fixture(t,{full:true,realLoop:true,monitorCooldown:1000,shell:()=>({...outcome(),exitCode:0,stdout:{text:'passed',truncated:false},stderr:{text:'',truncated:false}})});
  const adapter=new FullAdapter([{name:'bash',args},{name:'kz_consult',args:{question:'Which premise should I check?'}},'Delivered.']);
  const saved=await runFull(f,adapter);assert.equal(saved.full.usage.roles.advisor,1);
  assert.equal(saved.full.advice.alternatives[0].evidence_ids[0],'E1');assert.equal(saved.full.usage.requests,adapter.requests.length);
  assert.equal(saved.full.critic.decision,'public_review_accepted');
});

test('FULL native INVALID_ARGS uses structured error metadata, not an executed failure',async t=>{
  const f=await fixture(t,{full:true});
  f.ctx.on('tools/pre-execute',async(exec,next)=>exec.name==='bash'?{kind:'deny',reason:'bad parameters',info:{name:'ToolArgumentsError',code:'INVALID_ARGS'}}:next());
  const result=await f.execute();assert.equal(result.isError,true);
  const files=await readdir(f.auditDir),s=JSON.parse(await readFile(path.join(f.auditDir,files.find(x=>x.endsWith('.json')))));
  assert.equal(s.full.local.kind,'protocol');assert.deepEqual(s.full.evidence,{});assert.equal(f.executions(),0);
});

test('FULL Critic cannot turn a host-denied check into acceptance',{timeout:15000},async t=>{
  const f=await fixture(t,{full:true,realLoop:true,monitorCooldown:1000});
  f.ctx.on('tools/pre-execute',async(exec,next)=>exec.callId.startsWith('kz-critic-check-')?{kind:'deny',reason:'fixture host policy'}:next());
  const adapter=new FullAdapter(['Delivered.','Partial delivery: host denied public checks.','Blocked by host policy.']);
  const saved=await runFull(f,adapter);assert.equal(saved.full.critic.decision,'needs_revision');
  assert.equal(saved.full.critic.receipts.length,1);assert.ok(saved.full.critic.receipts.every(r=>r.passed===false&&r.evidence_id===null));
  assert.equal(f.executions(),0);assert.deepEqual(saved.full.evidence,{});
});

test('FULL a final Critic check saves its checkpoint without needing another solver step',{timeout:15000},async t=>{
  const f=await fixture(t,{full:true,realLoop:true,backtracking:true,shell:()=>({...outcome(),exitCode:0,stderr:{text:'',truncated:false},stdout:{text:'passed',truncated:false}})});
  const adapter=new FullAdapter([
    {name:'kz_update',args:{subgoal_plan:[{id:'G1',title:'public requirement',acceptance:'check passes',depends_on:[],targets:['check.py'],verification:{arguments:args,stdout_contains:['passed']}}]}},
    'Ready for public review.'
  ]);
  const saved=await runFull(f,adapter);assert.equal(saved.full.critic.decision,'public_review_accepted');
  assert.equal(saved.full.checkpoints.length,1);assert.equal(saved.full.subgoals.items.G1.status,'check_passed');
  assert.equal(adapter.solver,2);assert.equal(f.executions(),1);
});

const cleanOutcome=()=>({...outcome(),exitCode:0,stdout:{text:'passed',truncated:false},stderr:{text:'',truncated:false}});
const stallReply=(payload,value)=>payload.evidence?{verdict:'stalled',reason:'two different tests failed',next_check:'inspect declared dependencies',evidence_ids:Object.keys(payload.evidence).slice(-2),memories:[]}:value;
const twoFailures=[{name:'bash',args},{name:'bash',args:{...args,command:'node check.js'}}];
async function auditEvents(f) {const files=await readdir(f.auditDir);return (await readFile(path.join(f.auditDir,files.find(x=>x.endsWith('.jsonl'))),'utf8')).trim().split('\n').map(JSON.parse);}

test('EFFICIENCY actual AgentLoop delivers same-step advice and counts all auxiliary calls', {timeout:15000},async t=>{
  const f=await fixture(t,{full:true,realLoop:true,efficiencyEnabled:true,monitorCooldown:2,shell:(_a,_e,n)=>n<=2?outcome():cleanOutcome()});
  const adapter=new FullAdapter([...twoFailures,'Delivered.'],stallReply);const saved=await runFull(f,adapter);
  const index=adapter.requests.findIndex(r=>r.sessionId.includes(':advisor:'));
  assert.ok(index>=0);assert.match(JSON.stringify(adapter.requests[index+1].messages),/check the dependency declaration/);
  assert.equal(saved.full.usage.requests,adapter.requests.length);
  assert.equal(saved.full.critic.decision,'public_review_accepted');
  const events=(await auditEvents(f)).filter(x=>x.event==='pre_step_context_update');
  assert.ok(events.length);assert.ok(events.every(x=>x.efficiency));
  assert.ok(events.some(x=>x.updateChars<x.fullChars));
  const requests=(await auditEvents(f)).filter(x=>x.event==='request_completed');
  assert.equal(requests.length,adapter.requests.length);
  assert.equal(new Set(requests.map(x=>x.requestId)).size,requests.length);
  assert.equal(requests.reduce((sum,x)=>sum+x.requestUsage.inputTokens,0),saved.full.usage.inputTokens);
  assert.ok(requests.every(x=>x.durationMs>=0&&x.finishKind));
});
test('EFFICIENCY actual Critic keeps substantive acceptance gates and rejects host-denied checks', {timeout:15000},async t=>{
  const f=await fixture(t,{full:true,realLoop:true,efficiencyEnabled:true,monitorEnabled:false});
  f.ctx.on('tools/pre-execute',async(exec,next)=>exec.callId.startsWith('kz-critic-check-')?{kind:'deny',reason:'fixture host policy'}:next());
  const adapter=new FullAdapter(['Delivered.','Blocked by host policy.','Still blocked.']);
  const saved=await runFull(f,adapter);assert.equal(f.executions(),0);
  assert.notEqual(saved.full.completion.status,'completed_publicly');
  assert.equal(saved.full.critic.decision,'needs_revision');
  assert.ok(saved.full.critic.receipts.every(r=>r.passed===false));
});

test('AUTO monitor stall calls Advisor before next Solver, with handover and shared budget',{timeout:15000},async t=>{
  const f=await fixture(t,{full:true,realLoop:true,monitorCooldown:2,shell:(_a,_e,n)=>n<=2?outcome():cleanOutcome()});
  const adapter=new FullAdapter([...twoFailures,'Delivered.'],stallReply);const saved=await runFull(f,adapter);
  assert.equal(saved.full.usage.roles.advisor,1);assert.equal(saved.full.advice.trigger,'semantic_stall');assert.equal(saved.full.advice.automatic,true);
  const index=adapter.requests.findIndex(r=>r.sessionId.includes(':advisor:'));
  const handover=JSON.parse(adapter.requests[index].messages[0].content[0].text).handover;
  assert.equal(handover.failed_attempts_and_trigger_evidence.length,2);assert.match(handover.goal,/Repair check.py/);
  assert.equal(adapter.requests[index+1].system,undefined);assert.match(JSON.stringify(adapter.requests[index+1].messages),/check the dependency declaration/);
  assert.equal(saved.full.usage.requests,adapter.requests.length);assert.equal(f.executions(),3);
  assert.ok((await auditEvents(f)).some(x=>x.event==='advisor_trigger'&&x.trigger==='semantic_stall'));
});
test('AUTO and manual advice share cooldown rather than allocating another role budget',{timeout:15000},async t=>{
  const f=await fixture(t,{full:true,realLoop:true,monitorCooldown:2,shell:(_a,_e,n)=>n<=2?outcome():cleanOutcome()});
  const adapter=new FullAdapter([...twoFailures,{name:'kz_consult',args:{question:'Another idea?'}},'Delivered.'],stallReply);
  const saved=await runFull(f,adapter);assert.equal(saved.full.usage.roles.advisor,1);
  assert.ok((await auditEvents(f)).some(x=>x.event==='advisor_skipped'&&x.trigger==='main_requested'&&x.reason==='cooldown'));
});
test('AUTO preserves the final request for Solver and logs budget skip',{timeout:15000},async t=>{
  const f=await fixture(t,{full:true,realLoop:true,monitorCooldown:2,maxRequests:4});
  const adapter=new FullAdapter([...twoFailures,'Partial result.'],stallReply);const saved=await runFull(f,adapter);
  assert.equal(saved.full.usage.requests,4);assert.equal(saved.full.usage.roles.advisor??0,0);assert.equal(adapter.solver,3);
  assert.ok((await auditEvents(f)).some(x=>x.event==='advisor_skipped'&&x.reason==='shared_budget_reserve_solver'));
});
test('AUTO adviser failure is nonfatal and does not recursively retry the same evidence',{timeout:15000},async t=>{
  const f=await fixture(t,{full:true,realLoop:true,monitorCooldown:2,shell:(_a,_e,n)=>n<=2?outcome():cleanOutcome()});
  const adapter=new FullAdapter([...twoFailures,'Delivered.'],(p,v)=>{if(p.question)throw new Error('fixture provider unavailable');return stallReply(p,v);});
  const saved=await runFull(f,adapter);assert.equal(saved.full.usage.roles.advisor,1);assert.equal(adapter.solver,3);assert.equal(saved.full.critic.decision,'public_review_accepted');
  assert.ok((await auditEvents(f)).some(x=>x.event==='advisor_unavailable'&&x.automatic));
});
test('AUTO three real duplicate failures trigger advice; blocked calls are not failure evidence',{timeout:15000},async t=>{
  const f=await fixture(t,{full:true,realLoop:true,monitorCooldown:1000,maxConsecutiveRejections:1,shell:(_a,_e,n)=>n<=3?outcome():cleanOutcome()});
  const adapter=new FullAdapter([{name:'bash',args},{name:'bash',args},{name:'bash',args},{name:'bash',args},'Delivered.']);
  const saved=await runFull(f,adapter);assert.equal(saved.full.usage.roles.advisor,1);assert.equal(saved.full.advice.trigger,'repeated_failure');
  const event=(await auditEvents(f)).find(x=>x.event==='advisor_trigger');assert.deepEqual(event.evidence_ids,['E1','E2','E3']);assert.equal(f.executions(),4);
});
test('AUTO extended terminal reconnaissance triggers once without changing native commands',{timeout:15000},async t=>{
  const f=await fixture(t,{full:true,realLoop:true,monitorCooldown:1000,shell:cleanOutcome});
  const adapter=new FullAdapter([...Array.from({length:14},(_,i)=>({name:'bash',args:{...args,command:`head -n ${i+1} check.py`}})),'Delivered.']);
  const saved=await runFull(f,adapter);assert.equal(saved.full.usage.roles.advisor,1);assert.equal(saved.full.advice.trigger,'extended_diagnosis');
  assert.equal(f.executions(),15);assert.equal(saved.full.usage.tools,15);
});
test('AUTO configured adviser capacity zero skips assistance without stopping Solver',{timeout:15000},async t=>{
  const f=await fixture(t,{full:true,realLoop:true,monitorCooldown:2,maxAdvisorCalls:0,shell:(_a,_e,n)=>n<=2?outcome():cleanOutcome()});
  const adapter=new FullAdapter([...twoFailures,'Delivered.'],stallReply);const saved=await runFull(f,adapter);
  assert.equal(saved.full.usage.roles.advisor??0,0);assert.equal(adapter.solver,3);assert.equal(saved.full.critic.decision,'public_review_accepted');
  assert.ok((await auditEvents(f)).some(x=>x.event==='advisor_skipped'&&x.reason==='capacity'));
});

for(const denied of [false,true])test(`AUDIT rollback traverses actual host permissions and ${denied?'preserves changed files on denial':'runs the real restore helper in an isolated process'}`,{timeout:15000},async t=>{
  let restoreExecutions=0;
  const f=await fixture(t,{full:true,realLoop:true,backtracking:true,monitorCooldown:1000,shell:async(a,exec)=>{
    if(exec.callId.startsWith('kz-rollback-')) {
      const argv=[...a.command.matchAll(/'([^']*)'/g)].map(x=>x[1]);
      assert.equal(argv.length,5);assert.equal(argv[0],process.execPath);assert.equal(argv[2],f.workspace);
      assert.equal(argv[1],fileURLToPath(new URL('../scripts/restore-checkpoint.mjs',import.meta.url)));
      for(const location of argv.slice(3))assert.ok(location.startsWith(f.auditDir+path.sep));
      restoreExecutions++;const output=await promisify(execFile)(process.execPath,argv.slice(1));return{...cleanOutcome(),stdout:{text:output.stdout,truncated:false}};
    }
    return await readFile(path.join(f.workspace,'check.py'),'utf8')==='original'?cleanOutcome():outcome();
  }});
  f.ctx.tools.register({name:'write',description:'isolated fixture edit',parameters:{type:'object'},output:{schema:{type:'object'},render:()=>[{type:'text',text:'changed'}]},
    execute:async a=>{await writeFile(path.join(f.workspace,'check.py'),a.text);return{};}});
  if(denied)f.ctx.on('tools/pre-execute',async(exec,next)=>exec.callId.startsWith('kz-rollback-')?{kind:'deny',reason:'fixture rejects rollback'}:next());
  const adapter=new FullAdapter([
    {name:'kz_update',args:{subgoal_plan:[{id:'G1',title:'public check',acceptance:'test passes',depends_on:[],targets:['check.py'],verification:{arguments:args,stdout_contains:['passed']}}]}},
    {name:'bash',args},{name:'write',args:{text:'bad1'}},{name:'bash',args},{name:'write',args:{text:'bad2'}},{name:'bash',args},'Delivery.',
    ...(denied?['Partial delivery; rollback was denied.']:[])
  ]);
  const saved=await runFull(f,adapter);
  assert.equal(restoreExecutions,denied?0:1);assert.equal(saved.full.rollbacks,denied?0:1);
  assert.equal(await readFile(path.join(f.workspace,'check.py'),'utf8'),denied?'bad2':'original');
  const events=await auditEvents(f);
  if(!denied){const event=events.find(x=>x.event==='rollback_completed');assert.ok(event);assert.equal(await readFile(path.join(event.preserved,'check.py'),'utf8'),'bad2');assert.equal(saved.full.critic.decision,'public_review_accepted');}
  else{assert.ok(events.some(x=>x.event==='rollback_unavailable'));assert.notEqual(saved.full.critic.decision,'public_review_accepted');}
});

test('REPAIR frozen default does not create snapshots even after actor and Critic pass the same goal',async t=>{
  const f=await fixture(t,{full:true,realLoop:true,monitorCooldown:1000,shell:cleanOutcome});
  const adapter=new FullAdapter([{name:'kz_update',args:{subgoal_plan:[{id:'G1',title:'public check',acceptance:'test passes',depends_on:[],targets:['check.py'],verification:{arguments:args,stdout_contains:['passed']}}]}},{name:'bash',args},'Done']);
  const saved=await runFull(f,adapter);assert.equal(saved.full.subgoals.items.G1.status,'check_passed');assert.equal(saved.full.critic.decision,'public_review_accepted');
  assert.deepEqual(saved.full.checkpoints,[]);assert.equal(saved.full.rollbacks,0);assert.ok(!(await auditEvents(f)).some(e=>/checkpoint_created|rollback_completed/.test(e.event)));
});

test('REPAIR native absolute file paths supply dependency evidence; native execution errors are visible but not clean checks',async t=>{
  const f=await fixture(t,{full:true});
  f.ctx.tools.register({name:'read',description:'fixture reader',parameters:{type:'object'},output:{schema:{type:'object'},render:()=>[{type:'text',text:'original source'}]},execute:()=>({text:'original source'})});
  f.ctx.tools.register({name:'grep',description:'fixture search',parameters:{type:'object'},output:{schema:{type:'object'},render:()=>[]},execute:()=>{throw new Error('fixture search failed');}});
  await f.execute('read',{file_path:path.join(f.workspace,'check.py')});await f.execute('grep',{});
  const events=await auditEvents(f),rows=events.filter(e=>e.event==='outcome'&&e.evidence).map(e=>e.evidence);
  assert.equal(rows.length,2);assert.match(rows[0].dependenciesAfter['check.py'],/^file:/);assert.equal(rows[0].exitCode,null);
  assert.equal(rows[1].nativeToolError,true);assert.equal(rows[1].clean,false);
});

class BudgetAdapter extends LlmAdapter {
  calls=0;
  async resolveModel(provider,model){return {provider,id:model,name:model};}
  async *stream(){this.calls++;yield {type:'usage',usage:{inputTokens:10,outputTokens:2}};yield {type:'usage',usage:{inputTokens:20,outputTokens:3}};yield {type:'finish',reason:{kind:'stop'}};}
}

for(const tool of ['write','edit'])test(`REPAIR2 actual DSH ${tool} reviews memory, binds receipt, and retains host denial`,async t=>{
  const f=await fixture(t,{full:true});let edits=0,denied=false;
  f.ctx.tools.register({name:tool,description:'local source change',parameters:{type:'object',additionalProperties:true},output:{schema:{type:'object'},render:()=>[{type:'text',text:'changed'}]},execute:async()=>{edits++;await writeFile(path.join(f.workspace,'check.py'),'repaired');return {changed:true};}});
  f.ctx.on('tools/pre-execute',async(exec,next)=>denied&&exec.name===tool?{kind:'deny',reason:'fixture host permission'}:next());
  await f.execute();await f.ctx.systemPrompt.assemble({scope:scopeOf(f.agent.ctx)});
  const m=await f.execute('kz_update',{memory:{kind:'blocker',conclusion:'check.py failed',condition:'same source',targets:['check.py'],evidence_ids:['E1']}});assert.equal(m.value.memory.id,'M1');
  await f.ctx.systemPrompt.assemble({scope:scopeOf(f.agent.ctx)});
  const change={file_path:path.join(f.workspace,'check.py'),content:'repaired'};
  assert.equal((await f.execute(tool,change)).isError,false);assert.equal(edits,1);
  const review={tool,arguments:change,evidence_ids:['E1'],strategy_adjustment:'repair source before test',memory_review:{ids:['M1'],decision:'apply',observed_result:'failed',applicability:'same source',reason:'correct source'}};
  assert.equal((await f.execute('kz_strategy',review)).value.accepted,true);
  assert.equal((await f.execute(tool,change)).isError,false);assert.equal(edits,2);
  const events=await auditEvents(f),follow=events.find(x=>x.event==='memory_followup_outcome'&&x.tool===tool);
  assert.ok(follow.evidence_id);assert.equal(follow.workspace_changed,true);assert.equal(follow.clean_check,false);assert.equal(follow.causal_benefit_proven,false);
  denied=true;await f.execute('kz_strategy',review);assert.equal((await f.execute(tool,change)).isError,true);assert.equal(edits,2);
});

for(const fresh of [false,true])test(`REPAIR2 actual Critic cache fresh=${fresh} preserves receipts and counts executions`,async t=>{
  const f=await fixture(t,{full:true,realLoop:true,monitorCooldown:1000,shell:cleanOutcome});
  const adapter=new FullAdapter([
    {name:'kz_update',args:{subgoal_plan:[{id:'G1',title:'public test',acceptance:'passes',targets:['check.py'],depends_on:[],verification:{arguments:args,stdout_contains:['passed']}}]}},'Done'
  ],(payload,value)=>payload.stage==='plan_checks'?{...value,checks:[{arguments:args,stdout_contains:['passed'],cache_scope:'workspace'},{arguments:args,stdout_contains:['passed'],cache_scope:'workspace',fresh}]}:value);
  const saved=await runFull(f,adapter);assert.equal(saved.full.critic.decision,'public_review_accepted');
  assert.equal(f.executions(),fresh?2:1);assert.equal(saved.full.critic.receipts[1].reused_current_receipt,!fresh);
  assert.equal(saved.full.usage.tools,fresh?3:2);assert.equal(saved.full.usage.requests,adapter.requests.length);
});
test('REPAIR actual host stream counts cumulative usage once and blocks a third adapter dispatch',async t=>{
  const cp={provider:'fixture',model:'fixture',priceBasis:'synthetic',limitCny:50,inputPerMillion:2,outputPerMillion:8,maxInputTokens:1000000,maxOutputTokens:32768};
  const f=await fixture(t,{full:true,maxRequests:2,costPolicy:cp});await f.execute('bash',args);
  const adapter=new BudgetAdapter();f.ctx.llm.registerAdapter(['fixture'],adapter);
  const options={provider:'fixture',model:'fixture',maxTokens:32768,sessionId:f.agent.session.id,messages:[]};
  for(let i=0;i<2;i++)for await(const _ of f.ctx.llm.stream(options)){}
  await assert.rejects(async()=>{for await(const _ of f.ctx.llm.stream(options)){}},/budget/);
  assert.equal(adapter.calls,2);
  const finished=(await auditEvents(f)).filter(e=>e.event==='request_completed').at(-1);
  assert.equal(finished.usage.inputTokens,40);assert.equal(finished.usage.outputTokens,6);assert.equal(finished.cost.attempts,2);assert.equal(finished.cost.pendingUpperCny,0);
});

test('REPAIR cost guard stops before dispatch when request output cap is implicit or monetary ceiling is too low',async t=>{
  const cp={provider:'fixture',model:'fixture',priceBasis:'synthetic',limitCny:1,inputPerMillion:2,outputPerMillion:8,maxInputTokens:1000000,maxOutputTokens:32768};
  const f=await fixture(t,{full:true,costPolicy:cp});await f.execute();const adapter=new BudgetAdapter();f.ctx.llm.registerAdapter(['fixture'],adapter);
  const options={provider:'fixture',model:'fixture',sessionId:f.agent.session.id,messages:[]};
  await assert.rejects(async()=>{for await(const _ of f.ctx.llm.stream(options)){}},/output/);
  await assert.rejects(async()=>{for await(const _ of f.ctx.llm.stream({...options,maxTokens:32768})){}},/ceiling/);
  assert.equal(adapter.calls,0);
});
