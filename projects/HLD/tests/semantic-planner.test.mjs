import test from 'node:test';
import assert from 'node:assert/strict';
import { SemanticPlanner, reconnaissanceAction } from '../src/semantic-planner.mjs';
import { Policy, configuration } from '../src/policy.mjs';
import { FullTask } from '../src/full-task.mjs';

const config = (extra={}) => configuration({semanticPlannerEnabled:true,semanticReconnaissanceSteps:3,...extra});
const planner = extra => new SemanticPlanner(config(extra));
const call = (id, command='ls', name='bash') => ({callId:id,name,arguments:{command}});
const row = (id, c, extra={}) => ({id,callId:c.callId,key:c.arguments.command,complete:true,nativeToolError:false,checkStatus:'unknown',...extra});
export const routes = () => [
  {id:'D1',hypothesis:'parser drops boundary tokens',mechanism:'trace parse then repair tokenizer',target:'parser',steps:['inspect token boundaries','repair tokenizer','run original parser test'],progress_signal:'boundary tokens retained',abandon_when:'token stream is already correct',evidence_ids:['E1']},
  {id:'D2',hypothesis:'serialization loses valid tokens',mechanism:'compare roundtrip then repair serializer',target:'serializer',steps:['trace roundtrip','repair serialization','run public roundtrip test'],progress_signal:'roundtrip preserves tokens',abandon_when:'serialization is already lossless',evidence_ids:['E1']},
];
const novel = n => ({...routes()[0],id:`D${n}`,hypothesis:`boundary loss at subsystem ${n}`,mechanism:`trace subsystem ${n} inputs and outputs`,evidence_ids:[]});
const assess = (rs,selected) => rs.map(r=>({route_id:r.id,suitability:r.id===selected?0.9:0.5,disposition:'retain',reason:'compare evidence, feasibility and expected progress',evidence_ids:[]}));
export const initial = () => ({task_model:{problem:'restore public parser behavior',environment:'source and public test available',unknowns:['loss location']},routes:routes(),evaluations:assess(routes(),'D1'),selected_route_id:'D1',reason:'check source-side boundary first',evidence_ids:['E1']});
const activate = p => {p.queue('initial',['E1']);p.started(3);p.accept(initial(),{E1:{}},3);};
const switchAnswer = () => ({routes:[novel(3)],evaluations:assess([...routes(),novel(3)],'D2'),selected_route_id:'D2',reason:'test the independent serialization premise',evidence_ids:['E2'],contrast:{dimension:'hypothesis',previous:routes()[0].hypothesis,next:routes()[1].hypothesis,reason:'move from input parsing to output loss'}});

test('eight distinct complete reconnaissance observations precede planning; metadata/duplicates/incomplete receipts do not count',()=>{
  const p=new SemanticPlanner(configuration({semanticPlannerEnabled:true}));
  assert.equal(p.config.semanticReconnaissanceSteps,8);
  assert.equal(p.before(call('edit','x','edit')).allowed,false);
  for(const [i,cmd,complete] of [[1,'pwd',true],[2,'pwd',true],[3,'ls',false],[4,'ls',true],[5,'cat task.txt',true]]) {
    const c=call(`c${i}`,cmd);p.dispatch(c);p.observe(row(`E${i}`,c,{complete}));
  }
  assert.equal(p.state.reconnaissance.length,3);assert.equal(p.state.phase,'reconnaissance');
  for(let i=6;i<=10;i++) {
    const c=call(`c${i}`,`cat public-${i}.txt`);p.dispatch(c);p.observe(row(`E${i}`,c));
    if(i<10)assert.equal(p.state.phase,'reconnaissance');
  }
  assert.equal(p.state.reconnaissance.length,8);assert.equal(p.state.phase,'planning');
  assert.equal(p.before(call('work','python repair.py')).allowed,false);
  assert.equal(p.before(call('read','cat source.py')),null);
  assert.equal(p.due(5),true);
});

test('reconnaissance excludes command substitution, redirection, arbitrary tools and executable rg hooks',()=>{
  for(const command of ['cat a > b','ls; touch x','echo $(touch x)','rg --pre=sh x','python script.py','tail -f log'])
    assert.equal(reconnaissanceAction(call('x',command)),false,command);
  assert.equal(reconnaissanceAction(call('x','pwd')),true);
  assert.equal(reconnaissanceAction(call('x','x','read')),true);
});

test('macro route persists through repairs and repeated original checks; observations are attributed to dispatch',()=>{
  const p=planner();activate(p);
  for(let i=1;i<=5;i++){const c=call(`c${i}`,i%2?'python test.py':'source.py',i%2?'bash':'edit');p.dispatch(c);p.observe(row(`E${i+1}`,c));}
  assert.equal(p.active().executions,5);assert.equal(p.state.active,'D1');assert.equal(p.state.switches,0);
  assert.equal(p.active().complete_observations,5);
  assert.equal(p.before(call('repair','source.py','edit')),null);
});

test('switch selects a preplanned untried macro route with exact contrast and retains history on restore',()=>{
  const p=planner();activate(p);p.queue('monitor_stalled',['E2']);p.accept(switchAnswer(),{E2:{}},9);
  assert.equal(p.state.active,'D2');assert.equal(p.state.routes[0].status,'stalled');assert.equal(p.state.switches,1);
  const q=new SemanticPlanner(config(),structuredClone(p.state));
  assert.equal(q.state.active,'D2');assert.equal(q.view().metrics.route_coverage,0);
  q.dispatch(call('d2-action','python roundtrip.py'));assert.equal(q.view().metrics.route_coverage,1/3);
  q.queue('failed_check_loop',['E3']);
  assert.throws(()=>q.accept({routes:[novel(4)],evaluations:assess([...q.state.routes,novel(4)],'D1'),selected_route_id:'D1',reason:'try again',evidence_ids:[]},{E1:{}},14),/ready route/);
});

test('unknown evidence, duplicate premises, rewritten IDs and false contrast leave the plan atomic',()=>{
  for(const change of [a=>a.evidence_ids=['E999'],a=>a.routes[1]={...a.routes[0],id:'D2'},a=>a.routes[1].id='D1']){
    const p=planner(),a=initial();change(a);assert.throws(()=>p.accept(a,{E1:{}},3));assert.equal(p.state.routes.length,0);
  }
  const p=planner();activate(p);p.queue('monitor_stalled',['E2']);
  const a=switchAnswer();a.contrast.previous='invented premise';
  assert.throws(()=>p.accept(a,{E2:{}},8),/exact changed/);assert.equal(p.state.active,'D1');
  assert.throws(()=>p.accept({...a,selected_route_id:'D1'},{E1:{},E2:{}},8),/different macro/);
});

test('Monitor must cite recent complete active-route evidence, never an old route or partial receipt',()=>{
  for(const bad of [{complete:false},{semanticRoute:'D9'},{checkStatus:'public_check_passed'}]){
    const p=planner();activate(p);p.active().evidence_ids_observed=['E2','E3'];
    p.monitor({verdict:'stalled',evidence_ids:['E2','E3']},{E2:{id:'E2',complete:true,semanticRoute:'D1'},E3:{id:'E3',complete:true,semanticRoute:'D1',...bad}});
    assert.equal(p.state.pending,null);
  }
  const p=planner();activate(p);p.active().evidence_ids_observed=['E2','E3'];
  p.monitor({verdict:'stalled',evidence_ids:['E2','E3']},{E2:{id:'E2',complete:true,semanticRoute:'D1'},E3:{id:'E3',complete:true,semanticRoute:'D1'}});
  assert.equal(p.state.pending.kind,'monitor_stalled');
});

test('late background completion belongs to original route and cannot trigger a new-route stall',()=>{
  const p=planner();activate(p);const c=call('job','python long.py');p.dispatch(c);
  p.observe(row('E2',c,{complete:false,jobStage:'started'}));
  p.queue('monitor_stalled',['E3']);p.accept({...switchAnswer(),evidence_ids:['E3']},{E3:{}},9);
  const r=row('E4',c,{jobStage:'final'});p.observe(r);p.observe(r);
  assert.equal(r.semanticRoute,'D1');assert.equal(p.state.routes[0].complete_observations,1);assert.equal(p.active().complete_observations,0);
});

test('newer public progress supersedes an older Monitor alarm',()=>{
  const p=planner();activate(p);p.active().evidence_ids_observed=['E2','E3','E4'];
  p.monitor({verdict:'stalled',evidence_ids:['E2','E3']},Object.fromEntries([2,3,4].map(i=>[`E${i}`,{
    id:`E${i}`,complete:true,semanticRoute:'D1',checkStatus:i===4?'public_check_passed':'unknown'}])));
  assert.equal(p.state.pending,null);
});

test('unavailable planner falls back to retained alternative and never injects a command',()=>{
  const p=planner();activate(p);p.queue('failed_check_loop',['E2']);p.started(9);p.unavailable('invalid JSON',9);
  assert.equal(p.state.active,'D2');assert.equal(p.state.history.at(-1).source,'fallback_last_evaluation');
  assert.equal(p.active().executions,0);assert.equal(p.state.pending,null);
  const q=planner();q.queue('initial');q.started(3);q.unavailable('network unavailable',3);
  assert.equal(q.state.phase,'degraded');assert.equal(q.before(call('repair','x','write')),null);
  assert.equal(q.due(6),false);assert.equal(q.due(7),true);
});

test('route window requests review without calling an execution failure; a supported route may continue',()=>{
  const p=planner({semanticRouteWindow:2});activate(p);p.active().executions=2;
  p.tick(new Policy(),{},[],6);assert.equal(p.state.pending.kind,'route_window');
  p.accept({routes:[novel(3)],evaluations:assess([...p.state.routes,novel(3)],'D1'),selected_route_id:'D1',reason:'public boundary test is improving',evidence_ids:[]},{E1:{}},6);
  assert.equal(p.state.switches,0);assert.equal(p.active().reviewed_at,2);assert.equal(p.state.routes[1].status,'ready');
});

test('rejection loops advance planning without fabricating execution evidence',()=>{
  const p=planner();const controls=[1,2,3].map(i=>({id:`R${i}`,clock:i}));
  p.tick(new Policy(),{},controls,3);assert.equal(p.state.phase,'planning');assert.equal(p.state.reconnaissance.length,0);
  assert.deepEqual(p.state.pending.evidence_ids,['R1','R2','R3']);
});

test('semantic mode removes single-action orthogonality gate while preserving unchanged failed-command guard',()=>{
  const p=new Policy(config()),c=call('a','python test.py');p.state.active=true;
  assert.equal(p.before(c,'sha256:x').allowed,true);
  p.observe(c,{executed:true,complete:true,exitCode:1,stdout:'failed',stderr:''},'sha256:x','sha256:x');
  assert.equal(p.before(call('b','python test.py'),'sha256:x').reason,'same_failed_command_in_unchanged_workspace');
  assert.equal(p.before(call('c','python test.py'),'sha256:y').allowed,true);
  assert.equal(p.propose({tool:'bash',arguments:{command:'python other.py'}}).accepted,true);
});

test('route capacity, disabled mode and incompatible config are explicit',()=>{
  assert.throws(()=>configuration({semanticMaxRoutes:1}));
  assert.throws(()=>configuration({semanticPlannerCooldown:0}));
  const p=planner({semanticMaxRoutes:2});activate(p);p.queue('route_window');
  p.accept({routes:[novel(3)],evaluations:assess([...p.state.routes,novel(3)],'D1'),selected_route_id:'D1',reason:'current route remains strongest',evidence_ids:[]},{E1:{}},8);
  assert.equal(p.state.routes.length,2);assert.equal(p.state.archive.length,1);assert.equal(p.state.totalGenerated,3);
  const disabled=new SemanticPlanner(config({explorationEnabled:false}));
  disabled.queue('initial');assert.equal(disabled.due(8),false);assert.equal(disabled.before(call('w','x','write')),null);
});

test('planner state is retained in FullTask snapshot and compact context without a required command form',()=>{
  const t=new FullTask(config()),p=new Policy(config());activate(t.planner);p.state.active=true;
  const panel=t.panel(p).result;assert.equal(panel.semantic_planner.active_route.id,'D1');assert.equal(panel.memory_action_contract.required,false);
  const restored=new FullTask(config(),structuredClone(t.snapshot()));assert.equal(restored.planner.active().id,'D1');
});

test('every wake, including initial planning, requires one or two novel routes',()=>{
  const p=planner();const one=initial();one.routes=one.routes.slice(0,1);one.evaluations=one.evaluations.slice(0,1);
  p.accept(one,{E1:{}},3);assert.equal(p.state.routes.length,1);
  for(const count of [0,3]) {
    const q=planner();activate(q);q.queue('route_window');
    const a={routes:Array.from({length:count},(_,i)=>novel(i+3)),selected_route_id:'D1',reason:'evaluate',evidence_ids:[]};
    const before=structuredClone(q.state);
    assert.throws(()=>q.accept(a,{},7),/1-2 new/);assert.deepEqual(q.state,before);
  }
});

test('all old and new candidates need real evaluations and selected route must rank highest among eligible ones',()=>{
  const p=planner();activate(p);p.queue('route_window');
  const valid={routes:[novel(3)],evaluations:assess([...p.state.routes,novel(3)],'D1'),selected_route_id:'D1',reason:'keep evidenced progress',evidence_ids:[]};
  for(const mutate of [a=>a.evaluations.pop(),a=>a.evaluations[1]=a.evaluations[0],a=>a.evaluations[1].evidence_ids=['E999'],
    a=>a.evaluations[2].suitability=1,a=>a.evaluations[0].disposition='retire']) {
    const a=structuredClone(valid),before=structuredClone(p.state);mutate(a);
    assert.throws(()=>p.accept(a,{},7));assert.deepEqual(p.state,before);
  }
  p.accept(valid,{},7);assert.equal(p.state.active,'D1');assert.equal(p.state.totalGenerated,3);
});

test('window can refresh beyond lifetime capacity while preserving strong old routes and monotonic IDs',()=>{
  let p=planner({semanticMaxRoutes:2});activate(p);p.dispatch(call('started','python check.py'));
  for(let n=3;n<=9;n++) {
    const fresh=novel(n);p.queue('route_window');
    p.accept({routes:[fresh],evaluations:assess([...p.state.routes,fresh],'D1'),selected_route_id:'D1',reason:'original approach still strongest',evidence_ids:[]},{},n*4);
    assert.equal(p.state.routes.length,2);assert.equal(p.state.active,'D1');
    assert.ok(p.state.routes.some(r=>r.id===`D${n}`));
    p=new SemanticPlanner(config({semanticMaxRoutes:2}),structuredClone(p.state));
  }
  assert.equal(p.state.totalGenerated,9);assert.equal(p.state.nextRouteId,10);assert.equal(p.state.evicted,7);
  assert.equal(p.view().metrics.visited,1);assert.equal(p.view().metrics.route_coverage,1/9);
  assert.equal(p.state.archive.length,7);
});

test('explicit retirement removes a route even below capacity and late jobs retain original attribution',()=>{
  const p=planner();activate(p);const c=call('job','python slow.py');p.dispatch(c);
  p.queue('monitor_stalled',['E2']);const a=switchAnswer();a.evaluations[0].disposition='retire';
  p.accept(a,{E2:{}},7);
  assert.ok(!p.state.routes.some(r=>r.id==='D1'));
  const archived=p.state.archive.find(r=>r.id==='D1');assert.equal(archived.eviction_reason,'planner_retired');
  const receipt=row('E3',c,{jobStage:'final'});p.observe(receipt);
  assert.equal(receipt.semanticRoute,'D1');assert.equal(archived.complete_observations,1);assert.equal(p.active().complete_observations,0);
  assert.ok(p.drain().some(e=>e.event==='semantic_route_evicted'&&e.route.steps.length));
});

test('evicted IDs and recently rejected premises cannot be silently recycled',()=>{
  const p=planner({semanticMaxRoutes:2});activate(p);p.queue('route_window');
  p.accept({routes:[novel(3)],evaluations:assess([...p.state.routes,novel(3)],'D1'),selected_route_id:'D1',reason:'retain current evidence',evidence_ids:[]},{},7);
  p.queue('route_window');
  assert.throws(()=>p.accept({routes:[routes()[1]],selected_route_id:'D1',reason:'reuse ID',evidence_ids:[]},{E1:{}},11),/rewritten/);
  assert.throws(()=>p.accept({routes:[{...routes()[1],id:'D4'}],selected_route_id:'D1',reason:'reword ID',evidence_ids:[]},{E1:{}},11),/duplicate macro/);
  assert.equal(p.state.nextRouteId,4);
});
