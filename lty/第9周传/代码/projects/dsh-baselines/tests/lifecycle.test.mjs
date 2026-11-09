import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {fixture,tool,goal,update,task} from './fixture.mjs';

test('native DSH lifecycle actually executes bash; HTTP ledger equals server count', {timeout:60000},async t=>{
  let n=0;const f=await fixture(t,'native',()=>++n===1?[tool('bash',{command:"printf 'verified\\n' > result.txt",description:'Write requested artifact'})]:'Finished');
  await f.run();
  assert.equal(await readFile(path.join(f.workspace,'result.txt'),'utf8'),'verified\n');
  assert.equal(f.api.state.usage.httpRequests,2);assert.equal(f.httpCount(),2);assert.equal(f.api.state.usage.nativeTools,1);
});

test('Recuris W, retrieval, real verification, writeback and next decision use official lifecycle',{timeout:60000},async t=>{
  let n=0,updates=0;
  const f=await fixture(t,'recuris',o=>{
    if(o.purpose==='recuris_initialize')return {goals:[goal]};
    if(o.purpose==='recuris_update'){
      updates++;const p=JSON.parse(o.messages[0].content[0].text);
      assert.equal(p.original_task,task);
      return update(p.observation.kind==='verification'?'done':'pending',[p.observation.id]);
    }
    if(o.purpose==='compaction')return 'Created result.txt; public check passed. Continue using durable working memory.';
    n++;
    if(n===1){assert.match(JSON.stringify(o),/terminal_closed_loop/);return [tool('bash',{command:"printf 'verified\\n' > result.txt",description:'Create artifact'})];}
    if(n===2)return [tool('recuris_verify',{goal_id:'artifact'})];
    assert.match(JSON.stringify(o),/"status":\\?"done|status\\":\\"done/);
    return 'Verified artifact complete. '+(n===3?'detail '.repeat(3000):'');
  });
  await f.run();
  assert.equal(updates,2);assert.equal(f.api.state.panel.working_memory[0].status,'done');
  assert.equal(f.api.state.usage.nativeTools,2);assert.equal(f.api.state.usage.metadataTools,1);
  assert.equal(f.httpCount(),f.api.state.usage.httpRequests);
  const result=await f.ctx.compaction.compactNow(f.agent,new AbortController().signal);
  assert.ok(result,'real DSH compaction committed');
  await f.run('State the verified result without changing files.');
  assert.equal(f.api.state.panel.working_memory[0].status,'done');
  assert.ok(f.api.state.usage.roles.compaction.httpRequests>=1);
});

test('TACO planner compresses actual tool result; explicit complaint restores raw and freezes/replaces rule',{timeout:60000},async t=>{
  let n=0;const rule={rule_id:'noise',trigger_regex:'printf',strip_patterns:['^noise'],keep_first_n:1,keep_last_n:1,summary_header:'noise removed'};
  const f=await fixture(t,'taco',o=>{
    if(o.purpose==='taco_planner')return {selected_rule_ids:[],modified_rules:[],new_rules:[rule]};
    if(o.purpose==='taco_repair')return {...rule,rule_id:'repaired',strip_patterns:[]};
    if(o.purpose==='taco_compress')return {is_safe_to_compress:false,has_error:false};
    n++;
    if(n===1)return [tool('bash',{command:"printf 'head\\n'; for i in {1..30}; do printf 'noise %s\\n' $i; done; printf 'tail\\n'",description:'Generate public diagnostic output'})];
    if(n===2){assert.match(JSON.stringify(o),/noise removed/);return [tool('taco_feedback',{feedback:'need_full_output'})];}
    assert.match(JSON.stringify(o),/noise 15/);return 'Read restored output.';
  });
  await f.run();
  assert.equal(n,3);assert.equal(f.api.state.panel.rules.find(r=>r.rule_id==='noise').confidence,0);
  assert.ok(f.api.state.panel.rules.some(r=>r.rule_id==='repaired'));
  assert.equal(f.api.state.usage.roles.taco_repair.httpRequests,1);
  assert.equal(f.api.state.usage.httpRequests,f.httpCount());
});
