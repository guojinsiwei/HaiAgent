import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {verificationMatches,verificationKey} from './runtime/hld/src/verification-identity.mjs';
import {actionKey,configuration} from './runtime/hld/src/policy.mjs';
import {SemanticPlanner,normalizePlan,reconnaissanceAction} from './runtime/hld/src/semantic-planner.mjs';
import {parseRoleOutput} from './runtime/hld/src/roles.mjs';
import {reviewEvidence} from './appworld-review.mjs';
import {preflightChecks,coverageValid} from './runtime/hld/src/review-policy.mjs';

test('both deployed arms accept exact historical command with different description',async()=>{
 const c=JSON.parse(fs.readFileSync(new URL('../audit/method-analysis-20261019/binding-case.json',import.meta.url)));
 for(const arm of ['hld','kzdsh-new']){
  const {verificationMatches:match}=await import(`./runtime/${arm}/src/verification-identity.mjs`);
  assert.equal(match(c.args,c.row),true);
 }
});
test('heredoc equivalence ignores only description; changed command/cwd/timeout and forged row rejected',()=>{
 const args={command:"python client.py <<'PY'\nassert value == 4\nPY",description:'A',timeoutMs:1000};
 const row={arguments:args,key:actionKey({name:'bash',arguments:args})};
 assert.equal(verificationMatches({...args,description:'B'},row),true);
 for(const change of [{command:args.command.replace('4','5')},{workdir:'/other'},{timeoutMs:2000}])assert.equal(verificationMatches({...args,...change},row),false);
 assert.equal(verificationMatches(args,{...row,key:'forged'}),false);
});
const route=id=>({id,hypothesis:'premise '+id,mechanism:'mechanism '+id,target:'target '+id,steps:['inspect input','check boundary'],progress_signal:'observed boundary changes',abandon_when:'premise refuted',evidence_ids:['E1']});
const evals=rs=>rs.map((r,i)=>({route_id:r.id,suitability:.2+i*.1,disposition:'retain',reason:'public observations',evidence_ids:['E1']}));
test('HLD temporary IDs, selection and exact contrast strings are controller-owned',()=>{
 process.env.KZ_APPWORLD='1';
 try{
  const planner=new SemanticPlanner(configuration({semanticPlannerEnabled:true}));
  const init={new_routes:[route('N1'),route('N2')],evaluations:evals([route('N1'),route('N2')]),reason:'test',evidence_ids:['E1'],task_model:{problem:'x',environment:'y',unknowns:[]}};
  planner.accept(init,{E1:{}},1);assert.equal(planner.state.active,'D2');
  const old=structuredClone(planner.state.routes),fresh={...route('N1'),hypothesis:'a new premise',mechanism:'test a distinct subsystem'};
  const next={new_routes:[fresh],evaluations:[...evals(old).map(x=>({...x,suitability:.1})),{...evals([fresh])[0],suitability:.9}],reason:'new premise',evidence_ids:['E1'],contrast:{dimension:'mechanism',reason:'a different subsystem'}};
  planner.accept(next,{E1:{}},2);assert.equal(planner.state.active,'D3');assert.equal(planner.state.routes.find(r=>r.id==='D2').mechanism,old.find(r=>r.id==='D2').mechanism);
 }finally{delete process.env.KZ_APPWORLD;}
});
test('HLD invalid evidence is still rejected atomically',()=>{
 process.env.KZ_APPWORLD='1';try{
  const p=new SemanticPlanner(configuration({semanticPlannerEnabled:true}));const x=route('N1');x.evidence_ids=['E999'];
  assert.throws(()=>p.accept({new_routes:[x],evaluations:evals([x]),reason:'x',evidence_ids:[],task_model:{problem:'x',environment:'y',unknowns:[]}}, {E1:{}},1));assert.deepEqual(p.state.routes,[]);
 }finally{delete process.env.KZ_APPWORLD;}
});
test('repeated planner protocol failures back off without blocking ordinary actions',()=>{
 const p=new SemanticPlanner(configuration({semanticPlannerEnabled:true}));p.queue('initial',[]);p.started(0);p.unavailable('bad JSON',0);
 assert.equal(p.due(4),false);assert.equal(p.due(8),true);assert.equal(p.before({name:'bash',arguments:{command:'python solve.py'}}),null);
});
test('HLD accepts only guarded read-only client commands during reconnaissance',()=>{
 process.env.KZ_APPWORLD='1';try{
  assert.equal(reconnaissanceAction({name:'bash',arguments:{command:'python /opt/experiment/client.py --read-only --file /app/check.py'}}),true);
  assert.equal(reconnaissanceAction({name:'bash',arguments:{command:'python /opt/experiment/client.py --file /app/check.py'}}),false);
 }finally{delete process.env.KZ_APPWORLD;}
});
test('role parser accepts one complete JSON surrounded by prose, rejects malformed or multiple objects',()=>{
 assert.deepEqual(parseRoleOutput('Result:\n{"reason":"brace } inside string"}\nDone.'),{reason:'brace } inside string'});
 assert.throws(()=>parseRoleOutput('{"x":1}{"x":2}'));assert.throws(()=>parseRoleOutput('{"x": "unfinished}'));
});
test('review context keeps exact command and explicit truncation/retrieval',()=>{
 const cmd='python '+ 'x'.repeat(900);const rows=reviewEvidence({evidence:{E1:{id:'E1',complete:true,command:cmd,arguments:{command:cmd},stdout:'a'.repeat(9000)}}});
 assert.equal(rows[0].command,cmd);assert.equal(rows[0].arguments.command,cmd);assert.equal(rows[0].output_partial,true);assert.equal(rows[0].retrieval.id,'E1');
});
test('no-check accept cannot bypass requirement coverage or produce fake success',()=>{
 assert.equal(preflightChecks({decision:'accept',checks:[],gaps:[]},{publicTask:'Task'}).ok,false);
 assert.equal(coverageValid({requirements:['Task'],requirement_evidence:[{requirement_quote:'Task',reason:'trust me',evidence_ids:['E1']}]},[],'Task'),false);
});
