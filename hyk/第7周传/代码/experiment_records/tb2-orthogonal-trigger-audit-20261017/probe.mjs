// Offline probes against the exact policy.mjs fetched from the deployed bundle.
// No task commands executed and no model/network calls.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {Policy} from './frozen/policy.mjs';
const scope='sha256:unchanged',changed='sha256:changed';
const results=[];
function call(i,command='gcc target.c -o target',name='bash'){return {name,callId:'call'+i,arguments:{command}};}
function obs(p,c,stdout='compile error',exitCode=1,before=scope,after=scope,clean=exitCode===0){
 p.noteAction(c);return p.observe(c,{executed:true,complete:true,exitCode,stdout,stderr:'',clean},before,after,{});
}
function test(name,fn){const value=fn();results.push({name,...value});}
test('two identical observed failures activate (positive control)',()=>{const p=new Policy();obs(p,call(1));obs(p,call(2));assert.equal(p.state.active,true);return {active:p.state.active,streak:p.state.failureStreak};});
test('changing only diagnostic text prevents activation',()=>{const p=new Policy();for(let i=0;i<5;i++)obs(p,call(i),'compile error at line '+i);assert.equal(p.state.active,false);assert.equal(p.state.failureStreak,1);return {active:p.state.active,streak:p.state.failureStreak};});
test('read between identical failures prevents activation',()=>{const p=new Policy();obs(p,call(1));p.noteAction(call(2,'cat target.c','read'));obs(p,call(3));assert.equal(p.state.active,false);return {active:p.state.active,streak:p.state.failureStreak};});
test('changed source between failed checks prevents accumulation',()=>{const p=new Policy();obs(p,call(1));obs(p,call(2),'compile error',1,changed,changed);assert.equal(p.state.active,false);return {active:p.state.active,streak:p.state.failureStreak};});
test('exit zero with unclean result clears streak',()=>{const p=new Policy();obs(p,call(1));obs(p,call(2,'gcc target.c; echo done'),'error; done',0,scope,scope,false);assert.equal(p.state.failureStreak,0);return {active:p.state.active,streak:p.state.failureStreak};});
test('actual before gate blocks second identical known-state failure without activating',()=>{const p=new Policy();obs(p,call(1));const decision=p.before(call(2),scope,{dependencies:{}});assert.equal(decision.allowed,false);assert.equal(p.state.active,false);return {decision,active:p.state.active,streak:p.state.failureStreak};});
fs.writeFileSync(new URL('./probe-results.json',import.meta.url),JSON.stringify(results,null,2));
console.log(JSON.stringify(results,null,2));
