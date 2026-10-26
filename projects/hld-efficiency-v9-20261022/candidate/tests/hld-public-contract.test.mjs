import test from 'node:test';
import assert from 'node:assert/strict';
import {clip,extractStream} from '../src/terminal.mjs';
import {requirementCatalog,normalizeCritic} from '../src/public-contract.mjs';
import {preflightChecks,closureValid} from '../src/review-policy.mjs';
import {CompletionLedger} from '../src/completion.mjs';
import {SemanticPlanner,normalizePlanV3} from '../src/semantic-planner.mjs';

test('structured follow-up data is rendered without crashing planner context',()=>{
  const step={command:'check public module',description:'x'.repeat(900)};
  assert.equal(clip(step,2000),JSON.stringify(step));
  assert.ok(clip(step,200).length<=200);
  assert.equal(clip(null,100),'');
  assert.equal(extractStream({error:'TypeError: example'},'generic',100),JSON.stringify({error:'TypeError: example'}));
  assert.equal(step.description.length,900);
});
test('catalog resolves exact public quotes without inventing correctness or hiding conflicts',()=>{
  const task='# Requirements\n- The exported function accepts a callback.\n\n# New Interfaces\n- Input: callback\n# Constraints\n- Do not copy answers.';
  const catalog=requirementCatalog(task);assert.equal(catalog.length,6);
  const answer={decision:'revise',requirements:[],gaps:[],new_gaps:[{obligation_id:'callback',requirement_ref:'Q1',detail:'Need a real consumer check',proof_obligation:'correctness_basis',next_step:'Observe the public caller'}],checks:[],reason_kind:'missing_information',next_step:'Read the caller'};
  const n=normalizeCritic(answer,catalog);
  assert.equal(n.new_gaps[0].requirement_quote,catalog[0].quote);
  assert.equal(preflightChecks(n,{publicTask:task,existingGaps:[]}).ok,true);
  const ledger=new CompletionLedger();ledger.registerReview(n,task);
  assert.equal(ledger.open().length,1);
  assert.equal(closureValid(ledger.open()[0],{reason:'looks good',evidence_ids:[]},[],{}),false);
  assert.throws(()=>normalizeCritic({requirement_refs:['Q99']},catalog),/Unknown/);
  assert.throws(()=>normalizeCritic({requirements:['an uncovered obligation'],requirement_refs:['Q1']},catalog),/Conflicting/);
  assert.throws(()=>normalizeCritic({requirement_ref:'Q1',requirement_quote:'invented'},catalog),/Conflicting/);
  assert.throws(()=>normalizeCritic({checks:[{provenance:{sources:[{kind:'task',requirement_ref:'Q1',quote:'invented'}]}}]},catalog),/Conflicting/);
  assert.equal(answer.new_gaps[0].requirement_quote,undefined);
});
test('retirement aliases retain no rejected route and unknown evidence stays invalid',()=>{
  const state={routes:[{id:'D1',status:'active',hypothesis:'a',mechanism:'b',target:'c',evaluation:{suitability:.4,disposition:'retain'}}],active:'D1',pending:{kind:'route_window'},nextRouteId:2};
  const value={new_routes:[],existing_evaluations:{D1:{suitability:.6,disposition:'retain',reason:'new observation'}},reason:'continue',evidence_ids:[]};
  assert.deepEqual(normalizePlanV3(value,state).evaluations[0].evidence_ids,[]);
  for(const disposition of ['abandon','superseded','reject','discard']) {
    const v={...value,existing_evaluations:{D1:{suitability:.2,disposition,reason:'refuted'}},
      new_routes:[{hypothesis:'x',mechanism:'y',target:'z',evaluation:{suitability:.8,disposition:'retain',reason:'different'}}]};
    const n=normalizePlanV3(v,state);
    assert.equal(n.evaluations[0].disposition,'retire');assert.equal(n.selected_route_id,'D2');
  }
  const n=normalizePlanV3({...value,existing_evaluations:{D1:{suitability:.5,disposition:'retain',reason:'why',evidence_ids:['E999']}}},state);
  assert.deepEqual(n.evaluations[0].evidence_ids,['E999']); // Still rejected by the evidence validator, never silently dropped.
});
test('same failure across different commands triggers replan only at unchanged complete state',()=>{
  const make=()=>{
    const p=new SemanticPlanner({semanticPlannerEnabled:true,explorationEnabled:true,semanticRouteWindow:99});
    p.state.active='D1';p.state.phase='solving';
    p.state.routes=[{id:'D1',started_clock:0,executions:3,reviewed_at:0,evidence_ids_observed:['E1','E2','E3']}];
    return p;
  };
  const rows=Object.fromEntries([1,2,3].map(i=>['E'+i,{id:'E'+i,tool:'bash',executed:true,complete:true,semanticRoute:'D1',key:'distinct'+i,command:'different '+i,before:'sha256:abc',after:'sha256:abc',exitCode:1,stderr:'TypeError: callback is not callable',stdout:''}]));
  const policy={state:{episode:{serial:0},active:false}};
  const p=make();p.tick(policy,rows,[],3);assert.equal(p.state.pending.kind,'repeated_failure_family');
  for(const change of [{exitCode:0},{complete:false},{before:'sha256:changed'},{nativeToolError:true},{executed:false}]) {
    const q=make(),other=structuredClone(rows);Object.assign(other.E2,change);q.tick(policy,other,[],3);assert.equal(q.state.pending,null);
  }
});
