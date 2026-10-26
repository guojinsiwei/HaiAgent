import fs from 'node:fs';
import {Policy as Old} from './baseline/src/policy.mjs';
import {Policy as New} from './candidate/src/policy.mjs';
const S='sha256:before',T='sha256:after';
const call=(id,command)=>({name:'bash',callId:id,arguments:{command,workdir:'/app'}});
const out=(extra={})=>({executed:true,complete:true,exitCode:1,stdout:'',stderr:'AssertionError: boundary mismatch',clean:true,...extra});
const fail=(p,id,cmd,extra={})=>p.observe(call(id,cmd),out(extra),S,S);
function active(P){const p=new P();fail(p,'1','python test.py');fail(p,'2','python test.py');return p;}
const cases=[
  ['related_failures_across_commands',true,P=>{const p=new P();p.state.focus={goal:'G1',targets:['parser.py']};fail(p,'1','python boundary.py');fail(p,'2','python interior.py');return p.state.active;}],
  ['monitor_stall_with_successful_observations',true,P=>{const p=new P();return p.observeMonitor?.({verdict:'stalled',evidence_ids:['E1','E2'],next_check:'test a boundary condition'},{E1:{id:'E1',complete:true},E2:{id:'E2',complete:true}})??false;}],
  ['filename_cannot_support_content_equality','unknown',P=>{const p=active(P),c=call('probe','inspect certificate');
    p.propose({tool:'bash',arguments:c.arguments,changed_dimensions:['target_dimension'],orthogonality_proof:{dependency_dimension:'same',target_dimension:'certificate bytes',command_dimension:'inspect'},
      exploration:{hypothesis:'certificate bytes are identical',supports:{field:'stdout',contains:'/app/cert.pem'},refutes:{field:'stdout',contains:'absent'}}});
    p.before(c,S);p.observe(c,out({exitCode:0,stderr:'',stdout:'/app/cert.pem'}),S,S);return p.state.experiments.at(-1)?.status;}],
  ['auxiliary_steps_end_exploration_window',false,P=>{const p=active(P);for(let i=0;i<16;i++)p.executionStep('read'+i);return p.state.active;}],
  ['timeout_is_not_stable_failure_memory',0,P=>{const p=new P();fail(p,'1','make qemu',{timedOut:true,exitCode:124});return p.state.memories.length;}],
  ['repaired_original_check_remains_executable',true,P=>{const p=active(P);return p.before(call('retry','python test.py'),T).allowed;}],
  ['different_goals_do_not_aggregate',false,P=>{const p=new P();p.state.focus={goal:'G1',targets:['parser.py']};fail(p,'1','python boundary.py');p.state.focus.goal='G2';fail(p,'2','python interior.py');return p.state.active;}],
  ['two_format_errors_release_gate',false,P=>{const p=active(P);for(let i=0;i<2;i++)p.deny('Active exploration requires a comparison');return p.state.active;}],
];
const rows=cases.map(([scenario,expected,run])=>({scenario,expected,baseline:run(Old),candidate:run(New)}));
const report={kind:'deterministic_policy_regression_comparison',model_calls:0,benchmark_tasks_solved:0,
  limitation:'Constructed policy-level cases grounded in observed failure patterns; these are not LLM task-success results.',
  baseline_passed:rows.filter(r=>r.baseline===r.expected).length,candidate_passed:rows.filter(r=>r.candidate===r.expected).length,total:rows.length,rows};
fs.writeFileSync(new URL('./offline-comparison.json',import.meta.url),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
