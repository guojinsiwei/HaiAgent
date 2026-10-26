import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {SemanticPlanner} from './runtime/kz/src/semantic-planner.mjs';
import {configuration} from './runtime/kz/src/policy.mjs';
import {worldControl} from './runtime/kz/src/appworld-review.mjs';
test('TB4 enables v5 semantic protocol without activating AppWorld APIs',async()=>{
 delete process.env.KZ_APPWORLD;process.env.HLD_PLANNER_PROTOCOL='2';
 assert.equal(await worldControl(),null);
 const p=new SemanticPlanner(configuration({semanticPlannerEnabled:true}));
 p.accept({task_model:{problem:'public task',environment:'CLI',unknowns:[]},new_routes:[{id:'N1',hypothesis:'input boundary wrong',mechanism:'inspect and repair input',target:'parser',steps:['inspect','repair','verify'],progress_signal:'public test improves',abandon_when:'premise refuted',evidence_ids:['E1']}],evaluations:[{route_id:'N1',suitability:.9,disposition:'retain',reason:'public evidence',evidence_ids:['E1']}],reason:'first direction'},{E1:{}},0);
 assert.equal(p.state.active,'D1');assert.deepEqual(p.state.history[0].evidence_ids,['E1']);
 p.queue('route_window',['E1']);p.accept({new_routes:[],evaluations:[{route_id:'D1',suitability:.9,disposition:'retain',reason:'continue useful direction',evidence_ids:['E1']}],reason:'retain'},{E1:{}},4);
 assert.equal(p.state.totalGenerated,1);
 const wrapper=fs.readFileSync(new URL('./container-run.mjs',import.meta.url),'utf8');
 assert.match(wrapper,/HLD_PLANNER_PROTOCOL:'2'/);assert.match(wrapper,/delete env\[k\]/);assert.match(wrapper,/deadline\(child,7200/);
});
