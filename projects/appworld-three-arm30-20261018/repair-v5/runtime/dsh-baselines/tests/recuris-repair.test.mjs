import test from 'node:test';
import assert from 'node:assert/strict';
import {fixture,tool,goal,update} from './fixture.mjs';

test('omitted timeout executes actual DSH bash and commits a genuine matching verification receipt',{timeout:45000},async t=>{
  let n=0;
  const f=await fixture(t,'recuris',o=>{
    if(o.purpose==='recuris_initialize')return {goals:[goal]};
    if(o.purpose==='recuris_update'){
      const p=JSON.parse(o.messages[0].content[0].text);
      return update(p.observation.kind==='verification'?'done':'pending',[p.observation.id]);
    }
    if(++n===1)return [tool('bash',{command:"printf 'verified\\n' > result.txt",description:'Create artifact'})];
    if(n===2)return [tool('recuris_verify',{goal_id:'artifact'})];
    return 'Complete';
  },{commandTimeoutMs:undefined});
  await f.run();assert.equal(f.errors.length,0);assert.equal(f.api.state.faults.length,0);
  assert.equal(f.api.state.panel.working_memory[0].status,'done');
  const events=await f.events();const dispatch=events.find(e=>e.event==='tool_dispatch'&&e.callId?.startsWith('recuris-check-'));
  assert.ok(dispatch);assert.equal(Object.hasOwn(dispatch.arguments,'timeoutMs'),false);
  assert.ok(events.some(e=>e.event==='working_commit'&&e.receipt?.kind==='verification'&&e.decisions?.some(d=>d.accepted&&d.requested_status==='done')));
});

test('invalid or missing goal is actionable input feedback and leaves the worker healthy',{timeout:45000},async t=>{
  let n=0;const f=await fixture(t,'recuris',o=>{
    if(o.purpose==='recuris_initialize')return {goals:[goal]};
    ++n;if(n===1)return [tool('recuris_verify',{})];
    if(n===2)return [tool('recuris_verify',{goal_id:'unknown'})];
    if(n===3)return [tool('recuris_stop',{reason:'Input validation fixture'})];
    return 'Incomplete';
  },{commandTimeoutMs:undefined});
  await f.run();assert.equal(f.api.state.usage.nativeTools,0);assert.equal(f.api.state.faults.length,0);
  assert.equal(f.api.state.status,'incomplete');assert.equal(f.api.state.panel.working_memory[0].status,'pending');
  assert.ok((await f.events()).some(e=>e.event==='verification_input_rejected'));
});

test('native verification execution errors are visible in faults and cannot become successful receipts',{timeout:45000},async t=>{
  let n=0;const f=await fixture(t,'recuris',o=>{
    if(o.purpose==='recuris_initialize')return {goals:[goal]};
    if(++n===1)return [tool('recuris_verify',{goal_id:'artifact'})];
    if(n===2)return [tool('recuris_stop',{reason:'Native verification could not execute'})];
    return 'Incomplete';
  },{commandTimeoutMs:undefined});
  f.ctx.on('tools/pre-execute',(exec,next)=>exec.name==='bash'?{kind:'deny',reason:'fixture execution denied'}:next());
  await f.run();assert.equal(f.api.state.status,'incomplete_engineering_error');
  assert.ok(f.api.state.faults.some(x=>x.op==='recuris_verify'));
  assert.equal(f.api.state.panel.working_memory[0].status,'pending');
  assert.ok((await f.events()).some(e=>e.event==='tool_error'&&e.name==='recuris_verify'));
});

test('real check nonzero exit preserves pending status without inventing an engineering fault',{timeout:45000},async t=>{
  let n=0;const bad={...goal,verification:{command:'test -f absent-file',contains:[]}};
  const f=await fixture(t,'recuris',o=>{
    if(o.purpose==='recuris_initialize')return {goals:[bad]};
    if(o.purpose==='recuris_update'){const p=JSON.parse(o.messages[0].content[0].text);return update('done',[p.observation.id]);}
    if(++n===1)return [tool('recuris_verify',{goal_id:'artifact'})];
    if(n===2)return [tool('recuris_stop',{reason:'Public check failed'})];
    return 'Incomplete';
  },{commandTimeoutMs:undefined});
  await f.run();assert.equal(f.api.state.panel.working_memory[0].status,'pending');
  assert.equal(f.api.state.faults.length,0);
  assert.ok((await f.events()).some(e=>e.event==='verification_execution_complete'&&e.exit_code===1));
});

test('invalid explicit timeout fails before execution',{timeout:45000},async t=>{
  await assert.rejects(fixture(t,'recuris',()=>'',{commandTimeoutMs:null}),/positive integer/);
});
