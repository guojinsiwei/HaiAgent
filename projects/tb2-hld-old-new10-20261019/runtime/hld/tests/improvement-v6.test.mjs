import test from 'node:test';
import assert from 'node:assert/strict';
import {CompletionLedger} from '../src/completion.mjs';
import {reviewAdmission,reviewRecovery} from '../src/review-stability.mjs';
import {SemanticPlanner} from '../src/semantic-planner.mjs';
import {configuration} from '../src/policy.mjs';

test('CLI review admission is bounded despite new command spellings and scratch revisions',()=>{
 const s={scope:'sha256:initial',dependencies:{},evidence:{}},l=new CompletionLedger();
 for(let i=0;i<12;i++) {s.scope='sha256:scratch'+i;s.evidence['E'+i]={executed:true,complete:true,key:'new command '+i,stdout:'new',exitCode:0};assert.equal(reviewAdmission(s,null,l).allowed,true);}
 assert.equal(reviewAdmission(s,null,l).allowed,false);assert.equal(l.state.status,'working');
});
test('followup progress tracks original target and closures, not renamed read commands',()=>{
 const s={dependencies:{'main.py':'file:a'},subgoals:{items:{G1:{definition:{targets:['main.py']},status:'working'}}}},l=new CompletionLedger();
 const r=reviewRecovery(s,l);r.followups=3;s.dependencies['scratch.py']='file:new';
 assert.equal(reviewRecovery(s,l).followups,3);s.dependencies['main.py']='file:b';assert.equal(reviewRecovery(s,l).followups,0);
});
test('paraphrased existing gaps are rejected atomically; explicit assessment retains original obligation',()=>{
 const l=new CompletionLedger();l.registerReview({gaps:['Proof missing']});
 assert.throws(()=>l.registerReview({gaps:['Still no completed proof']}),/existing gap IDs/);
 assert.equal(l.state.gaps.length,1);
 l.registerReview({gaps:[],gap_updates:[{gap_id:'Gap-1',detail:'Main.v still contains Admitted',status:'closed'}]});
 assert.equal(l.open().length,1);assert.equal(l.state.gaps[0].detail,'Proof missing');
});
test('structured obligation identity survives rewording and distinct predicates stay distinct',()=>{
 const l=new CompletionLedger(),mk=(id,detail)=>({gaps:[],new_gaps:[{obligation_id:id,requirement_quote:'Complete proof',detail}]});
 l.registerReview(mk('proof-qed','Proof missing'),'Complete proof');
 l.registerReview(mk('proof-qed','Proof still missing'),'Complete proof');
 l.registerReview(mk('no-axioms','Check axiom constraint'),'Complete proof');
 assert.equal(l.state.gaps.length,2);assert.equal(l.state.gaps[0].id,'Gap-1');
 assert.throws(()=>l.registerReview({new_gaps:[{detail:'unanchored'}]},'Complete proof'),/obligation_id/);
});
const fresh=()=>({hypothesis:'input boundary is mishandled',mechanism:'inspect and repair input parsing',target:'parser',steps:['check public input boundary','repair and verify'],progress_signal:'public boundary passes',abandon_when:'input parsing correct',evidence_ids:['E1'],evaluation:{suitability:.8,disposition:'retain',reason:'public evidence',evidence_ids:['E1']}});
const initial=()=>({task_model:{problem:'public task',environment:'CLI',unknowns:[]},new_routes:[fresh()],existing_evaluations:{},reason:'test input',evidence_ids:['E1']});
test('V3 owns IDs, admits explicit delta evaluations, and never selects an unassessed old route',()=>{
 process.env.HLD_PLANNER_PROTOCOL='3';
 try {
  const p=new SemanticPlanner(configuration({semanticPlannerEnabled:true}));p.accept(initial(),{E1:{}},0);
  assert.equal(p.state.active,'D1');p.queue('completion_review_stalled',['E1']);
  const next=fresh();next.hypothesis='output serialization drops data';next.mechanism='inspect serializer';next.evaluation.suitability=.6;
  p.accept({new_routes:[next],existing_evaluations:{},reason:'inspect output',evidence_ids:['E1'],contrast:{dimension:'mechanism',reason:'test output boundary after input stalled'}},{E1:{}},1);
  assert.equal(p.state.active,'D2');assert.equal(p.state.routes.find(r=>r.id==='D1').evaluation.assessment_source,'carried_history');
  p.queue('route_window',['E1']);
  assert.throws(()=>p.accept({new_routes:[],existing_evaluations:{},reason:'no judgement',evidence_ids:[]},{E1:{}},2),/eligible/);
  assert.equal(p.state.active,'D2');
 } finally {delete process.env.HLD_PLANNER_PROTOCOL;}
});
test('V3 rejects fabricated IDs and evidence without mutating the route registry',()=>{
 process.env.HLD_PLANNER_PROTOCOL='3';try {
  const p=new SemanticPlanner(configuration({semanticPlannerEnabled:true}));const a=initial();a.existing_evaluations.D99={};assert.throws(()=>p.accept(a,{E1:{}},0),/unknown existing/);assert.equal(p.state.routes.length,0);
  const b=initial();b.new_routes[0].evidence_ids=['E999'];assert.throws(()=>p.accept(b,{E1:{}},0),/route/);assert.equal(p.state.routes.length,0);
 }finally{delete process.env.HLD_PLANNER_PROTOCOL;}
});
test('route memory binding records association without inventing an action change or gain',()=>{
 const p=new SemanticPlanner(configuration({semanticPlannerEnabled:true}));p.state.phase='solving';p.state.active='D1';p.state.routes=[{id:'D1',executions:0,memory_use:[{id:'M1',decision:'recheck',reason:'condition may have changed'}]}];
 p.dispatch({callId:'real-call',name:'bash',arguments:{command:'python check.py'}});
 const e=p.drain().find(e=>e.event==='semantic_memory_action_association');assert.equal(e.callId,'real-call');assert.equal(e.action_changed,null);assert.equal(e.causal_benefit_proven,false);
});
