import test from 'node:test';
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fixture,tool,goal,update} from './fixture.mjs';
import {worldControl} from '../src/appworld-review.mjs';

for(const write of [false,true])test(`actual AppWorld verifier ${write?'blocks writes':'executes read-only public checks and commits evidence'}`,{timeout:60000,skip:process.env.KZ_APPWORLD!=='1'},async t=>{
  let n=0;
  const g={...goal,verification:{command:'',contains:write?[]:['PUBLIC_CHECK_OK']}};
  const f=await fixture(t,'recuris',o=>{
    if(o.purpose==='recuris_initialize')return {goals:[g]};
    if(o.purpose==='recuris_update'){const p=JSON.parse(o.messages[0].content[0].text);return update('done',[p.observation.id]);}
    if(++n===1)return [tool('recuris_verify',{goal_id:'artifact'})];
    if(write&&n===2)return [tool('recuris_stop',{reason:'Write check correctly blocked'})];
    return 'Checked';
  },{commandTimeoutMs:undefined});
  const script=path.join(f.workspace,'check.py');
  await writeFile(script,write?'apis.supervisor.complete_task()':"task=apis.supervisor.show_active_task()\nassert task['instruction']\nprint('PUBLIC_CHECK_OK')\n");
  g.verification.command=`python /opt/experiment/client.py --file ${script}`;
  const before=await worldControl();await f.run();const after=await worldControl();
  assert.equal(after.submitted,before.submitted);assert.equal(after.revision,before.revision);assert.equal(after.read_only,false);
  assert.equal(f.api.state.panel.working_memory[0].status,write?'pending':'done');
  assert.equal(f.api.state.faults.length,0);
  assert.ok((await f.events()).some(e=>e.event==='verification_execution_complete'&&(write?e.exit_code!==0:e.exit_code===0)));
});
