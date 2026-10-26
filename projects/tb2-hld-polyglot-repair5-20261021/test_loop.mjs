// Execute the actual installed turn() method against deterministic step fixtures.
// No model, provider, network, or benchmark solution is involved.
import fs from 'node:fs';
import assert from 'node:assert/strict';
const file=process.argv[2] ?? '/opt/kz/node_modules/@deepseek-ai/dsh-agent-loop/lib/index.js';
const old=fs.readFileSync(file+'.before-max-tokens','utf8');
const fixed=fs.readFileSync(file,'utf8');
function compile(source){
  const start=source.indexOf('\tasync turn() {');
  const end=source.indexOf('\n\tasync step(decision)',start);
  assert(start>0&&end>start);
  const method=source.slice(start,end).trim();
  return Function('ToolCallRecovery','abortedCancelCause','LlmError',
    `return ({${method}}).turn`)(class {observe(){} results(){return [];}},
      signal=>signal.aborted?'user':undefined,Error);
}
async function run(source,steps,{resume=[],resumeSteps=[],abortAt=0,rejectAt=0}={}){
  const events=[],inbox={nextStep:[],hasPending:false};let index=0,stops=0;
  const runtime={id:'fixture',phase:{kind:'running',abort:new AbortController(),turn:0,step:0},
    inbox,session:{append(type,data){events.push({type,data});}},
    ctx:{on(){return ()=>{};}},throwError(e){throw e;},
    async preStep(){inbox.nextStep.length=0;return {kind:rejectAt===index+1?'reject':'enter',messages:[{}]};},
    async step(){index++;if(abortAt===index){runtime.phase.abort.abort();runtime.phase.abort.signal.throwIfAborted();}
      assert(index<=steps.length,'Unexpected extra model step');return steps[index-1];},
    dispatch:{async serial(){stops++;if(resume.includes(stops)||resumeSteps.includes(index))inbox.nextStep.push({});}}
  };
  let thrown=false;try{await compile(source).call(runtime);}catch(e){if(!runtime.phase.abort.signal.aborted)throw e;thrown=true;}
  return {steps:index,reason:events.findLast(e=>e.type==='turn/end').data.reason,stops,thrown};
}
const max={kind:'max-tokens'},done={kind:'completed'};
const previous=await run(old,[max,null,null,done],{resume:[1]});
assert.equal(previous.steps,2);assert.equal(previous.reason.kind,'max-tokens');
const repaired=await run(fixed,[max,null,null,done],{resume:[1]});
assert.equal(repaired.steps,4);assert.equal(repaired.reason.kind,'completed');
assert.deepEqual(await run(fixed,[max]),await run(old,[max]));
assert.deepEqual(await run(fixed,[null,null,done]),await run(old,[null,null,done]));
assert.equal((await run(fixed,[max,null,max],{resume:[1]})).reason.kind,'max-tokens');
assert.equal((await run(fixed,[max,null,done],{resume:[1],rejectAt:2})).reason.kind,'blocked');
const aborted=await run(fixed,[max,null,done],{resume:[1],abortAt:2});
assert.equal(aborted.reason.kind,'aborted');assert.equal(aborted.thrown,true);
// Match the observed sequence: step 6 truncated, HLD continued through step 13.
const observed=[null,null,null,null,null,max,null,null,null,null,null,null,null,done];
assert.equal((await run(old,observed,{resumeSteps:[6,7,8,9,10,11,12]})).steps,13);
assert.equal((await run(fixed,observed,{resumeSteps:[6,7,8,9,10,11,12]})).steps,14);
console.log(JSON.stringify({passed:true,checks:8,original_bug_reproduced:true,paid_calls:0}));
