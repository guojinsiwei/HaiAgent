import test from 'node:test';
import assert from 'node:assert/strict';
import {SemanticPlanner,SEMANTIC_V2,semanticTaskInstruction} from '../src/semantic-planner.mjs';
import {FULL_INSTRUCTION} from '../src/full-integration.mjs';
import {configuration} from '../src/policy.mjs';
import {CompletionLedger} from '../src/completion.mjs';
import {reviewAdmission,bindPlanGaps} from '../src/review-stability.mjs';
import {preflightChecks,coverageValid} from '../src/review-policy.mjs';
import {verificationReceipt} from '../src/verification-receipt.mjs';

const route=id=>({id,hypothesis:'premise '+id,mechanism:'approach '+id,target:'boundary '+id,steps:['inspect','repair','verify'],progress_signal:'public outcome improves',abandon_when:'premise refuted',evidence_ids:['E1']});
const plan=()=>({task_model:{problem:'public task',environment:'public APIs',unknowns:[]},new_routes:[route('N1')],evaluations:[{route_id:'N1',suitability:.9,disposition:'retain',reason:'public evidence',evidence_ids:['E1']}],reason:'select premise'});
const setup=()=>{
  process.env.KZ_APPWORLD='1';
  const p=new SemanticPlanner(configuration({semanticPlannerEnabled:true,semanticPlannerCooldown:1}));
  p.accept(plan(),{E1:{}},0);delete process.env.KZ_APPWORLD;return p;
};
const rows=()=>Object.fromEntries([2,3,4].map(i=>['E'+i,{id:'E'+i,semanticRoute:'D1',key:'same-query',complete:true,executed:true,exitCode:0,stdout:'same empty result',stderr:'',before:'sha256:same',after:'sha256:same',checkStatus:'unknown'}]));
const tick=(p,e)=>p.tick({state:{active:false,episode:{serial:0}}},e,[],4);

test('historical missing outer references uses only explicitly cited nested IDs',()=>{
  const p=setup();assert.equal(p.state.active,'D1');assert.deepEqual(p.state.history[0].evidence_ids,['E1']);
  process.env.KZ_APPWORLD='1';try {
    const bad=plan();bad.new_routes[0].evidence_ids=['E999'];
    const q=new SemanticPlanner(configuration({semanticPlannerEnabled:true}));
    assert.throws(()=>q.accept(bad,{E1:{}},1),/evidence_ids/);assert.equal(q.state.routes.length,0);
    const explicit=plan();explicit.evidence_ids=null;assert.throws(()=>q.accept(explicit,{E1:{}},1),/evidence_ids/);
  } finally { delete process.env.KZ_APPWORLD; }
});

test('single V2 schema explicitly requires all top-level fields and has no legacy routes schema',()=>{
  assert.match(SEMANTIC_V2,/"new_routes"/);assert.match(SEMANTIC_V2,/top-level evidence_ids/);
  assert.ok(!SEMANTIC_V2.includes('routes:[{id:"D1"'));
});

test('periodic review can retain productive direction without fabricating new routes; stagnation still requires an alternative',()=>{
  const p=setup();p.queue('route_window',['E1']);process.env.KZ_APPWORLD='1';
  try {
    const a={new_routes:[],evaluations:[{route_id:'D1',suitability:.9,disposition:'retain',reason:'public read-back supports continued work',evidence_ids:['E1']}],reason:'finish existing route',evidence_ids:['E1']};
    p.accept(a,{E1:{}},2);assert.equal(p.state.active,'D1');assert.equal(p.state.totalGenerated,1);
    p.queue('monitor_stalled',['E1']);assert.throws(()=>p.accept(a,{E1:{}},3),/new routes/);
  } finally {delete process.env.KZ_APPWORLD;}
});

test('identical successful observations trigger semantic replanning without a Monitor verdict',()=>{
  const p=setup(),e=rows();p.queue('route_window',['E2']);tick(p,e);
  assert.equal(p.state.pending.kind,'repeated_observation_loop');assert.deepEqual(p.state.pending.evidence_ids,['E2','E3','E4']);
  assert.equal(p.before({name:'bash',arguments:{command:'python repair.py'}}),null);
  assert.ok(p.drain().some(x=>x.event==='semantic_replan_queued'));
});

for(const [name,change] of Object.entries({
  'changed result':e=>{e.E4.stdout='new target found';},
  'partial':e=>{e.E4.complete=false;},
  'changed workspace':e=>{e.E4.after='sha256:changed';},
  'unknown workspace':e=>{for(const r of Object.values(e)){r.before='unknown';r.after='unknown';}},
  'passing public verification':e=>{e.E4.checkStatus='public_check_passed';},
  'different route':e=>{e.E4.semanticRoute='D2';}
}))test('no repeated-observation alarm for '+name,()=>{
  const p=setup(),e=rows();change(e);tick(p,e);assert.equal(p.state.pending,null);
});

test('loop trigger overrides delayed initial/periodic work and keeps its evidence under periodic ticks',()=>{
  const p=setup();p.queue('initial',['E1']);p.queue('monitor_stalled',['E2','E3']);p.queue('route_window',['E4']);
  assert.equal(p.state.pending.kind,'monitor_stalled');assert.deepEqual(p.state.pending.evidence_ids,['E2','E3']);
});

test('review guard admits new read-only evidence at unchanged application revision; identical renumbered receipts do not reset it',()=>{
  const s={evidence:rows()},l=new CompletionLedger(),w={revision:4,submitted:true};
  assert.equal(reviewAdmission(s,w,l).allowed,true);
  assert.equal(reviewAdmission(s,w,l).allowed,true);
  assert.equal(reviewAdmission(s,w,l).allowed,true);
  s.evidence.E5={...s.evidence.E4,id:'E5'};
  assert.equal(reviewAdmission(s,w,l).allowed,false);
  s.evidence.E6={...s.evidence.E4,id:'E6',stdout:'new public read-back'};
  assert.equal(reviewAdmission(s,w,l).allowed,true);
  assert.equal(l.state.status,'working'); // Admission never marks success.
});

test('review ceiling bounds endlessly varied evidence and closed-gap progress gets credit',()=>{
  const s={evidence:{}},l=new CompletionLedger(),w={revision:4,submitted:true};
  for(let i=0;i<8;i++){s.evidence['E'+i]={...rows().E2,key:'check-'+i};assert.equal(reviewAdmission(s,w,l).allowed,true);}
  s.evidence.E9={...rows().E2,key:'newer'};assert.equal(reviewAdmission(s,w,l).allowed,false);
  assert.equal(reviewAdmission(s,{...w,revision:5},l).allowed,true);
});

test('new gap can be explicitly targeted, checked and closed in one review; global accept still cannot close unrelated gaps',()=>{
  const task='Set amount to 45',ledger=new CompletionLedger();
  const check={arguments:{command:'python /app/check.py'},stdout_contains:['amount=45'],gap_ids:[],gap_refs:['amount unverified'],requirement_quotes:[task],provenance:{author:'critic',kind:'public_spec',expected_rule:'45',sources:[{kind:'task',quote:task}],independence:'Assert literal public requirement against public read-back'}};
  const plan={decision:'revise',requirements:[task],gaps:['amount unverified'],checks:[check]};
  assert.equal(preflightChecks(plan,{publicTask:task,evidence:{}}).ok,true);
  ledger.registerReview(plan,task);bindPlanGaps(plan,ledger);assert.deepEqual(check.gap_ids,['Gap-1']);
  const row={id:'E1',callId:'real-check',command:check.arguments.command,arguments:check.arguments,key:'check',complete:true,executed:true,exitCode:0,clean:true,stdout:'amount=45',stderr:''};
  const receipt=verificationReceipt(check,row,row,null,{publicTask:task});
  const verdict={decision:'accept',requirements:[task],checks:[],gaps:[],requirement_evidence:[{requirement_quote:task,evidence_ids:['E1'],reason:'public read-back matches literal amount'}],gap_updates:[{gap_id:'Gap-1',status:'closed',evidence_ids:['E1'],reason:'read-back asserts the original amount requirement'}]};
  assert.equal(coverageValid(verdict,[receipt],task),true);
  ledger.record(verdict,[receipt],{accepted:true,scope:'sha256:state',dependencies:{},evidence:{E1:row},observed:1,publicTask:task});
  assert.equal(ledger.state.status,'completed_publicly');assert.equal(ledger.open().length,0);
  ledger.upsert('unrelated',{detail:'unverified formula',proof_obligation:'correctness_basis'});
  ledger.record({...verdict,gap_updates:[]},[receipt],{accepted:true,evidence:{E1:row},publicTask:task});
  assert.equal(ledger.open().length,1);assert.equal(ledger.state.status,'repair_pending');
});

test('forged same-plan gap reference and invented public requirement cannot pass preflight',()=>{
  const plan={decision:'revise',gaps:['real'],checks:[{arguments:{command:'python check.py'},stdout_contains:[],gap_refs:['invented'],requirement_quotes:['hidden answer'],provenance:{author:'critic',kind:'public_spec',expected_rule:'rule'}}]};
  const result=preflightChecks(plan,{publicTask:'public task',evidence:{}});assert.equal(result.ok,false);assert.ok(result.errors.some(x=>x.includes('gap_refs')));
});

test('HLD task instructions consistently describe semantic direction replanning',()=>{const s=semanticTaskInstruction(FULL_INSTRUCTION);assert.match(s,/semantic direction replanning/);assert.doesNotMatch(s,/contrastive exploration|orthogonal|three-dimensional novelty|measured JSON predictions|eight probes/);});
