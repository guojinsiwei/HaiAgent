import test from 'node:test';
import assert from 'node:assert/strict';
import { Policy } from '../src/policy.mjs';
import { checkIdentity } from '../src/exploration-trigger.mjs';
import { FullTask } from '../src/full-task.mjs';
const S='sha256:before',T='sha256:repaired';
const call=(id,command='gcc main.c -o main',name='bash')=>({callId:id,name,arguments:{command,workdir:'/app'}});
function outcome(p,c,{before=S,after=before,exitCode=1,stdout='compile error',clean=exitCode===0,complete=true}={}) {
 p.noteAction(c);p.executionStep(c.callId);
 return p.observe(c,{executed:true,complete,exitCode,stdout,stderr:'',clean},before,after);
}
test('changed diagnostics and edited source retain failures for the same check',()=>{
 const p=new Policy();outcome(p,call('a'));
 p.noteAction(call('edit','main.c','edit'));
 assert.equal(p.before(call('b'),T).reason,'observed_workspace_change');
 outcome(p,call('b'),{before:T,stdout:'different line and error'});
 assert.equal(p.state.active,true);assert.deepEqual(p.state.episode.trigger.evidence,['E1','E2']);
});
test('reading evidence between failed checks does not erase attempts',()=>{
 const p=new Policy();outcome(p,call('a'));p.noteAction(call('read','main.c','read'));
 outcome(p,call('b'),{stdout:'new details'});assert.equal(p.state.active,true);
});
test('different compiler flags and wrappers target the same source, other source/cwd do not',()=>{
 assert.equal(checkIdentity('cd /app && gcc -Wall main.c -o /tmp/a; echo done'),checkIdentity('gcc main.c -o b','/app'));
 assert.notEqual(checkIdentity('gcc other.c -o b','/app'),checkIdentity('gcc main.c -o b','/app'));
 assert.notEqual(checkIdentity('gcc main.c -o b','/elsewhere'),checkIdentity('gcc main.c -o b','/app'));
 const p=new Policy();outcome(p,call('a'));outcome(p,call('b','gcc other.c -o main'));assert.equal(p.state.active,false);
});
test('same telnet endpoint aggregates changed probes, separate ports stay separate',()=>{
 assert.equal(checkIdentity('(sleep 8) | timeout 25 telnet 127.0.0.1 6665 | grep login'),checkIdentity('timeout 15 telnet 127.0.0.1 6665 | head'));
 assert.notEqual(checkIdentity('telnet 127.0.0.1 6665'),checkIdentity('telnet 127.0.0.1 7777'));
});
test('clean success of the same check clears only that check',()=>{
 const p=new Policy();outcome(p,call('a'));outcome(p,call('ok'),{exitCode:0,stdout:'ok'});
 outcome(p,call('b'));assert.equal(p.state.active,false);
 const q=new Policy();outcome(q,call('a'));outcome(q,call('ls','ls'),{exitCode:0,stdout:'main.c'});
 outcome(q,call('b'));assert.equal(q.state.active,true);
});
test('uncertain zero exit preserves the ledger without inventing another failure',()=>{
 const p=new Policy();outcome(p,call('a'));outcome(p,call('uncertain'),{exitCode:0,clean:false,stdout:'possibly failed'});
 assert.equal(p.state.active,false);assert.equal(p.trigger.state.checks[0].failures,1);
 outcome(p,call('b'));assert.equal(p.state.active,true);
});
test('incomplete outcomes, disabled exploration and duplicate receipt IDs do not activate',()=>{
 const p=new Policy();outcome(p,call('a'));outcome(p,call('b'),{complete:false});assert.equal(p.state.active,false);
 const q=new Policy({explorationEnabled:false});outcome(q,call('a'));outcome(q,call('b'));assert.equal(q.state.active,false);
 const r=new Policy();r.trigger.observe('check','E1','failed');r.trigger.observe('check','E1','failed');assert.equal(r.trigger.pending(2),undefined);
});
test('unchanged failed request activates before denial, once per failed receipt',()=>{
 const p=new Policy();outcome(p,call('a'));
 assert.equal(p.before(call('b'),S).allowed,false);assert.equal(p.state.active,true);
 p.endEpisode('orthogonal_rejections');
 for(let i=0;i<20;i++)p.before(call('retry'+i),S);
 assert.equal(p.state.episode.serial,1);assert.equal(p.state.active,false);
});
test('recovery cannot rearm from failures accumulated inside the previous episode',()=>{
 const p=new Policy();outcome(p,call('a'));outcome(p,call('b'));outcome(p,call('c'));
 p.endEpisode('orthogonal_rejections');for(let i=0;i<4;i++)p.executionStep('cooldown'+i);
 p.activatePending();assert.equal(p.state.active,false);
 outcome(p,call('d'));assert.equal(p.state.active,false);
 outcome(p,call('e'));assert.equal(p.state.active,false);
 outcome(p,call('f'),{before:T,stdout:'new failure after repair'});assert.equal(p.state.active,true);
});
test('trigger state survives context/session restoration',()=>{
 const p=new Policy();outcome(p,call('a'));const q=new Policy({},structuredClone(p.state));
 outcome(q,call('b'),{stdout:'different failure'});assert.equal(q.state.active,true);
});

test('full-task evidence path activates across edits while local syntax fixes remain exempt',()=>{
 const p=new Policy(),task=new FullTask({});
 const fail={executed:true,complete:true,exitCode:1,stdout:'',stderr:'compiler check failed'};
 const observe=(id,command,before,stderr=fail.stderr)=>task.observe(call(id,command),{...fail,stderr},before,before,{}, {},p,'fixture');
 observe('a','gcc main.c -o main',S);
 task.state.local=null;
 observe('b','gcc main.c -o main',T);
 assert.equal(p.state.active,true);assert.deepEqual(p.state.episode.trigger.evidence,['E1','E2']);
 const q=new Policy(),other=new FullTask({});
 other.observe(call('syntax','python broken.py'),{...fail,stderr:'SyntaxError: invalid syntax'},S,S,{}, {},q,'fixture');
 assert.equal(q.trigger.state.checks.length,0);assert.equal(q.state.active,false);
});
