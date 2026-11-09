import test from 'node:test';
import assert from 'node:assert/strict';
import {fixture,tool,goal,update} from './fixture.mjs';
import {LlmError} from '@deepseek-ai/dsh-llm';

test('DSH retry makes two real HTTP attempts and both consume shared budget',{timeout:30000},async t=>{
  let n=0;const f=await fixture(t,'native',()=>++n===1?new LlmError('temporary','SERVER_ERROR',{retryable:true}):'Recovered');
  await f.run();assert.equal(f.httpCount(),2);assert.equal(f.api.state.usage.httpRequests,2);
});
test('actual request cap prevents second dispatch without losing first-attempt accounting',{timeout:30000},async t=>{
  const f=await fixture(t,'native',()=>[tool('bash',{command:'pwd',description:'Inspect working directory'})],{budget:{apiRequests:1,tools:10,wallSeconds:30}});
  await f.run();assert.equal(f.httpCount(),1);assert.equal(f.api.state.usage.httpRequests,1);
  assert.ok(f.errors.length);assert.equal(f.api.state.status,'engineering_error');
});
test('permission denial does not execute the native command or become a verification receipt',{timeout:30000},async t=>{
  let n=0;const f=await fixture(t,'native',()=>++n===1?[tool('bash',{command:'exit 9',description:'Denied public command'})]:'Permission denied, incomplete');
  f.ctx.on('tools/pre-execute',()=>({kind:'deny',reason:'test host permission denied'}));
  await f.run();assert.equal(f.api.state.usage.nativeTools,0);
  assert.ok((await f.events()).some(e=>e.event==='tool_error'));
});
test('Recuris protocol repair survives more than two malformed responses and accounts all roles',{timeout:30000},async t=>{
  let initial=0;
  const f=await fixture(t,'recuris',o=>o.purpose==='recuris_initialize'?(++initial<=3?'invalid JSON':{goals:[goal]}):[tool('recuris_stop',{reason:'offline fixture stops incomplete'})]);
  // After stop the solver can return a final answer rather than calling it again.
  const original=f.adapter.respond;let solver=0;f.adapter.respond=o=>!o.purpose&&++solver>1?'Incomplete':original(o);
  await f.run();assert.equal(initial,4);assert.equal(f.api.state.usage.roles.recuris_initialize.httpRequests,4);
  assert.equal((await f.events()).filter(e=>e.event==='protocol_repair').length,3);
  assert.equal(f.api.state.status,'incomplete');
});
test('TACO uncovered output spawns a rule, then next identical command uses it',{timeout:30000},async t=>{
  let n=0;const cmd="for i in {1..600}; do printf 'uncovered noise %s\\n' $i; done";
  const f=await fixture(t,'taco',o=>{
    if(o.purpose==='taco_planner')return {selected_rule_ids:[],modified_rules:[],new_rules:[]};
    if(o.purpose==='taco_compress')return {is_safe_to_compress:false,has_error:false};
    if(o.purpose==='taco_spawn')return {rule_id:'new_noise',trigger_regex:'for',strip_patterns:['^uncovered'],keep_first_n:1,keep_last_n:1,summary_header:'removed uncovered noise'};
    return ++n<=2?[tool('bash',{command:cmd,description:'Public verbose output'})]:'Finished';
  });
  await f.run();assert.ok(f.api.state.panel.rules.some(r=>r.rule_id==='new_noise'));
  assert.ok((await f.events()).some(e=>e.event==='observation_projection'&&e.applied?.includes('new_noise')));
});
test('TACO nonzero exit preserves full diagnostics and does not invent a complaint',{timeout:30000},async t=>{
  let n=0;const f=await fixture(t,'taco',o=>{
    if(o.purpose==='taco_planner')return {selected_rule_ids:[],modified_rules:[],new_rules:[{rule_id:'unsafe',trigger_regex:'printf',strip_patterns:['.*'],keep_first_n:1,keep_last_n:1}]};
    return ++n===1?[tool('bash',{command:"for i in {1..100}; do printf 'diagnostic %s\\n' $i; done; exit 7",description:'Public failing check'})]:'Observed failure, no missing output complaint';
  });
  await f.run();assert.match(JSON.stringify(f.adapter.requests.at(-1)),/diagnostic 50/);
  assert.equal(f.api.state.panel.feedback.length,0);assert.equal(f.api.state.usage.roles.taco_repair,undefined);
});
test('two fresh tasks cannot inherit TACO rules or Recuris state',{timeout:30000},async t=>{
  const a=await fixture(t,'taco',o=>o.purpose==='taco_planner'?{selected_rule_ids:[],modified_rules:[],new_rules:[{rule_id:'task_a_only',trigger_regex:'foo'}]}:'Done A');
  await a.run();
  const b=await fixture(t,'taco',o=>{
    assert.ok(!JSON.stringify(o).includes('task_a_only'));
    return o.purpose==='taco_planner'?{selected_rule_ids:[],modified_rules:[],new_rules:[]}:'Done B';
  });
  await b.run();assert.notEqual(a.workspace,b.workspace);assert.notEqual(a.agent.session.id,b.agent.session.id);
  assert.equal(b.api.state.panel.rules.length,0);
});
test('engineering worker crash is surfaced as error, not normal completion',{timeout:30000},async t=>{
  const f=await fixture(t,'recuris',()=>{throw new Error('broken fixture response');});
  await f.run();assert.ok(f.errors.length);assert.equal(f.api.state.status,'engineering_error');
});

test('TACO malformed planner response retains author empty-plan behavior but records engineering degradation',{timeout:30000},async t=>{
  const f=await fixture(t,'taco',o=>o.purpose==='taco_planner'?'not JSON':'Completed with fallback');
  await f.run();assert.equal(f.api.state.status,'degraded_engineering_error');
  assert.equal(f.api.state.panel.rules.length,0);
});

test('Recuris update API fault preserves native output and cannot masquerade as normal completion',{timeout:30000},async t=>{
  let solver=0;
  const f=await fixture(t,'recuris',o=>{
    if(o.purpose==='recuris_initialize')return {goals:[goal]};
    if(o.purpose==='recuris_update')return new Error('simulated auxiliary transport failure');
    if(++solver===1)return [tool('bash',{command:'printf observed',description:'Public observation'})];
    if(solver===2)return [tool('recuris_stop',{reason:'Engineering failure in W update'})];
    return 'Incomplete';
  });
  await f.run();assert.equal(f.api.state.status,'incomplete_engineering_error');
  assert.match(JSON.stringify(f.adapter.requests),/observed/);assert.equal(f.api.state.usage.nativeTools,1);
});

test('TACO rule pool survives real DSH compaction and influences later native observations',{timeout:30000},async t=>{
  let n=0;
  const f=await fixture(t,'taco',o=>{
    if(o.purpose==='taco_planner')return {selected_rule_ids:[],modified_rules:[],new_rules:[{rule_id:'persistent',trigger_regex:'printf',strip_patterns:['^noise'],keep_first_n:1,keep_last_n:1,summary_header:'persistent rule filtered'}]};
    if(o.purpose==='compaction')return 'Task in progress. Preserve algorithm state.';
    if(o.purpose==='taco_compress')return {is_safe_to_compress:false,has_error:false};
    n++;
    if(n<=2)return 'Public progress description. '.repeat(2000);
    if(n===3)return [tool('bash',{command:"for i in {1..40}; do printf 'noise %s\\n' $i; done",description:'Check preserved compression rule'})];
    assert.match(JSON.stringify(o),/persistent rule filtered/);return 'Done';
  });
  await f.run();await f.run('Continue the progress report.');assert.ok(await f.ctx.compaction.compactNow(f.agent,new AbortController().signal));
  await f.run('Continue checking the task.');assert.equal(f.api.state.usage.roles.taco_planner.httpRequests,1);
  assert.equal(f.api.state.usage.roles.compaction.httpRequests,1);
});
