import test from 'node:test';
import assert from 'node:assert/strict';
import {fixture,tool,goal} from './fixture.mjs';
import {renderContextSections} from '@deepseek-ai/dsh-system-prompt';
import {scopeOf} from '@deepseek-ai/dsh-scope';

test('Recuris memory preserves source braces through the real DSH context renderer', {timeout:30000}, async t=>{
  const literals=['[]netlink.Message{{Data: buf}}','{{unknown_template}}','{{baseline_memory_literal}}','{{nested {{value}} }}'];
  let solver=0;
  const f=await fixture(t,'recuris',o=>{
    if(o.purpose==='recuris_initialize')return {goals:[{...goal,description:goal.description+' '+literals.join(' ')}]};
    return ++solver===1?[tool('recuris_stop',{reason:'Offline rendering test complete; task incomplete'})]:'Incomplete';
  });
  await f.run();
  assert.deepEqual(f.errors,[]);
  assert.ok(solver>=1);
  const assembly=await f.ctx.systemPrompt.assemble({scope:scopeOf(f.agent.ctx)});
  const rendered=renderContextSections(assembly).find(s=>s.name==='baseline:memory').text;
  for(const literal of literals)assert.ok(rendered.includes(literal),literal);
  assert.equal(f.api.state.status,'incomplete');
});
