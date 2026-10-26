import test from 'node:test';
import assert from 'node:assert/strict';
import {fixture,tool,goal,update} from './fixture.mjs';

for(const valid of [true,false])test(`stop intent reconciles later ${valid?'passing':'failing'} actual verification`,{timeout:45000},async t=>{
  let n=0;
  const f=await fixture(t,'recuris',o=>{
    if(o.purpose==='recuris_initialize')return {goals:[goal]};
    if(o.purpose==='recuris_update'){
      const p=JSON.parse(o.messages[0].content[0].text);return update('done',[p.observation.id]);
    }
    if(++n===1)return [tool('recuris_stop',{reason:'initially cannot finish'})];
    if(n===2)return [tool('bash',{command:`printf '${valid?'verified':'wrong'}\\n' > result.txt`,description:'continue after stop intent'})];
    if(n===3)return [tool('recuris_verify',{goal_id:'artifact'})];
    return 'Deliver current result';
  },{commandTimeoutMs:undefined});
  await f.run();assert.equal(f.errors.length,0);assert.equal(f.api.state.faults.length,0);
  assert.equal(f.api.state.status,valid?'agent_stopped_no_official_score':'incomplete');
  assert.equal(f.api.state.panel.working_memory[0].status,valid?'done':'pending');
  const events=await f.events();assert.equal(events.some(e=>e.event==='incomplete_stop_superseded'),valid);
  assert.ok(events.some(e=>e.event==='algorithm_operation'&&e.op==='complete'));
});
