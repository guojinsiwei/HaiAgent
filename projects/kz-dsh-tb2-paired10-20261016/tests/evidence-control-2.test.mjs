import test from 'node:test';
import assert from 'node:assert/strict';
import {CompletionLedger} from '../src/completion.mjs';
import {Subgoals} from '../src/subgoals.mjs';
import {actionKey} from '../src/policy.mjs';
import {verificationKey} from '../src/verification-identity.mjs';
import {FullTask} from '../src/full-task.mjs';
const args={command:'python check.py',workdir:'/app'};
const row=(id,extra={})=>({id,key:actionKey({name:'bash',arguments:args}),arguments:args,tool:'bash',executed:true,
  complete:true,clean:true,exitCode:0,stdout:'passed',stderr:'',dependenciesBefore:{'check.py':'file:a'},dependenciesAfter:{'check.py':'file:a'},...extra});
test('EC2 intervening evidence survives A -> B -> A, identical copies do not buy reviews',()=>{
  const l=new CompletionLedger(),s={scope:'sha256:a',dependencies:{},evidence:{E1:row('E1')}};
  const first=l.token(s);s.evidence.E2=row('E2');assert.equal(l.token(s),first);
  s.evidence.E3=row('E3',{stdout:'new diagnostic'});s.evidence.E4=row('E4');assert.notEqual(l.token(s),first);
});
test('EC2 actual execution, background completion and archive retrieval are activity; prose is not',()=>{
  const l=new CompletionLedger(),s={evidence:{E1:row('E1')}};const a=l.activity(s);
  s.delivery='different final prose';assert.equal(l.activity(s),a);
  s.evidence.E2=row('E2');assert.notEqual(l.activity(s),a);
  const b=l.activity(s);s.evidence.E2.jobStage='final';assert.notEqual(l.activity(s),b);
  const c=l.activity(s);s.completionHistoryReads=1;assert.notEqual(l.activity(s),c);
  assert.equal(l.activity(s),l.activity(JSON.parse(JSON.stringify(s))));
});
test('EC2 reopening a gap changes review identity without inventing new file evidence',()=>{
  const l=new CompletionLedger(),s={evidence:{E1:row('E1')}};l.upsert('r',{});
  l.state.gaps[0].status='closed';const old=l.token(s);l.state.gaps[0].status='needs_reverification';assert.notEqual(l.token(s),old);
});
test('EC2 semantic history survives 64-row eviction and checkpoint restore without retaining raw history',()=>{
  const task=new FullTask({});task.state.evidence.E1=row('E1');const original=task.completion.token(task.state);
  task.state.evidence.E2=row('E2',{stdout:'intervening diagnostic'});task.trimEvidence();
  for(let n=3;n<=80;n++){task.state.evidence[`E${n}`]=row(`E${n}`);task.trimEvidence();}
  assert.equal(Object.keys(task.state.evidence).length,64);assert.equal(task.state.evidence.E2,undefined);
  assert.equal(task.completion.state.observationHistory.length,2);
  assert.notEqual(task.completion.token(task.state),original);
  const saved=JSON.parse(JSON.stringify(task.snapshot())),restored=new FullTask({},saved);
  assert.equal(restored.completion.token(restored.state),task.completion.token(task.state));
  assert.ok(!JSON.stringify(saved).includes('intervening diagnostic'));
});
test('EC2 literal absolute cd matches the same explicit cwd, unsafe shell remains distinct',()=>{
  assert.equal(verificationKey(args),verificationKey({command:'cd /app && python check.py'}));
  assert.equal(verificationKey(args),verificationKey({...args,description:'a different display label'}));
  for(const other of [
    {command:'cd /other && python check.py'}, {command:'cd /app/../other && python check.py'},
    {command:'bash -c "python check.py"',workdir:'/app'}, {command:'cd /app && python check.py | cat'},
    {...args,env:{MODE:'other'}}, {...args,timeoutMs:1}, {command:'cd "$ROOT" && python check.py'},
    {command:'cd /app && python check.py && true'}
  ])assert.notEqual(verificationKey(args),verificationKey(other));
});
test('EC2 actual equivalent check binds, newer failure cannot be bypassed by older proof',()=>{
  const g=new Subgoals();g.admit({subgoal_plan:[{id:'G1',title:'check',acceptance:'passes',targets:['check.py'],depends_on:[],verification:{arguments:args,stdout_contains:['passed']}}]});
  const actual={command:'cd /app && python check.py'};
  const e=row('E1',{arguments:actual,key:actionKey({name:'bash',arguments:actual})});
  assert.equal(g.observe(e)[0].passed,true);
  const failed=row('E2',{exitCode:1,clean:false});g.observe(failed);
  assert.equal(g.state.items.G1.status,'needs_work');
  assert.throws(()=>g.bindVerification({subgoal_id:'G1',revision:1,evidence_id:'E1'},{E1:e,E2:failed},{'check.py':'file:a'}),/later execution/);
});
