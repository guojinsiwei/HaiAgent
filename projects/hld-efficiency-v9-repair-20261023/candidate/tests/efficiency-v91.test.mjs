import test from 'node:test';
import assert from 'node:assert/strict';
import {SemanticPlanner} from '../src/semantic-planner.mjs';
import {configuration} from '../src/policy.mjs';
import {plannerRouteView,plannerOutputContract} from '../src/efficiency.mjs';

function fixture(efficient=true) {
  const p=new SemanticPlanner(configuration({semanticPlannerEnabled:true,efficiencyEnabled:efficient}));
  p.state.phase='solving';p.state.active='D1';p.state.nextRouteId=2;
  p.state.routes=[{id:'D1',hypothesis:'input encoding determines result',mechanism:'decode then check public fixtures',target:'parser',steps:['decode','check'],progress_signal:'fixture match',abandon_when:'decoded fixture differs',status:'active',executions:0,reviewed_at:0,evidence_ids:['E1'],evidence_ids_observed:[],evaluation:{suitability:.7,disposition:'retain',reason:'public fixture',evidence_ids:['E1']},started_clock:0}];
  return p;
}
const policy={state:{active:false,episode:{serial:0}}};
test('routine planner calls halve across a 96-action no-alarm trace; baseline retains its cadence',()=>{
  for(const [enabled,expected] of [[true,4],[false,8]]) {
    const p=fixture(enabled);let calls=0;
    for(let i=1;i<=96;i++) {
      p.dispatch({name:'read',callId:`a${i}`});p.tick(policy,{},[],i);
      if(p.due(i)){calls++;p.started(i);p.active().reviewed_at=p.active().executions;p.state.pending=null;}
    }
    assert.equal(calls,expected);
  }
});
test('three unchanged observations trigger a route change before the longer routine window',()=>{
  const p=fixture();p.active().executions=3;
  const evidence=Object.fromEntries([1,2,3].map(i=>[`E${i}`,{id:`E${i}`,semanticRoute:'D1',complete:true,executed:true,key:'same',exitCode:0,stdout:'unchanged',stderr:'',before:'sha256:abc',after:'sha256:abc'}]));
  p.tick(policy,evidence,[],3);assert.equal(p.state.pending.kind,'repeated_observation_loop');assert.equal(p.due(3),true);
});
test('background polling retains evidence binding without spending periodic route actions',()=>{
  const p=fixture();
  for(let i=0;i<40;i++)p.dispatch({name:i%2?'job_output':'job_list',callId:`poll${i}`});
  assert.equal(p.active().executions,0);assert.equal(p.state.bindings.poll0.route,'D1');
  p.dispatch({name:'bash',callId:'real-action'});assert.equal(p.active().executions,1);
});
test('concise retention protocol works without environment switches and never manufactures a new route',()=>{
  const p=fixture();p.state.pending={kind:'route_window',evidence_ids:['E2']};
  p.accept({new_routes:[],existing_evaluations:{D1:{suitability:.8,disposition:'retain',reason:'new public fixture agrees',evidence_ids:['E2']}},reason:'continue current useful approach',evidence_ids:['E2']},{E2:{id:'E2'}},24);
  assert.equal(p.state.active,'D1');assert.equal(p.state.nextRouteId,2);assert.equal(p.state.pending,null);
});
test('planner diagnostic names missing abandonment condition and rejects without mutating registry',()=>{
  const p=fixture();p.state.pending={kind:'monitor_stalled',evidence_ids:['E2']};
  const original=JSON.stringify(p.state);
  assert.throws(()=>p.accept({new_routes:[{hypothesis:'different premise',mechanism:'different mechanism',target:'parser',steps:['read','check'],progress_signal:'matched',evidence_ids:['E2'],evaluation:{suitability:.9,disposition:'retain',reason:'different public input',evidence_ids:['E2']}}],existing_evaluations:{},reason:'new direction',evidence_ids:['E2'],contrast:{dimension:'mechanism',reason:'new algorithm'}},{E2:{id:'E2'}},24),/new_routes\[0\].*abandon_when/);
  assert.equal(JSON.stringify(p.state),original);
});
test('Q IDs and unseen evidence remain rejected, including in periodic retention',()=>{
  for(const id of ['Q1','E999']) {
    const p=fixture();p.state.pending={kind:'route_window',evidence_ids:['E2']};
    assert.throws(()=>p.accept({new_routes:[],existing_evaluations:{D1:{suitability:.8,disposition:'retain',reason:'claim',evidence_ids:[id]}},reason:'claim',evidence_ids:['E2']},{E2:{}},24),/supplied E\/R IDs/);
  }
});
test('planner input preserves route meaning and removes misleading archived citation rosters',()=>{
  const p=fixture(),r=p.active();r.evidence_ids_observed=['E999'];r.evaluation.evidence_ids=['E999'];
  const before=JSON.stringify(r),view=plannerRouteView(r);
  assert.equal(view.mechanism,r.mechanism);assert.deepEqual(view.steps,r.steps);assert.equal(JSON.stringify(r),before);
  assert.ok(!JSON.stringify(view).includes('E999'));assert.ok(!Object.hasOwn(view,'evidence_ids'));
  assert.match(plannerOutputContract({kind:'route_window'},'D1').preferred_response,/new_routes:\[\]/);
  assert.match(plannerOutputContract({kind:'monitor_stalled'},'D1').preferred_response,/different eligible direction/);
});
