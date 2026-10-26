import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
import { SUZController } from './controller.mjs';
// Isolated process only. Frozen v8 v2 protocol permits retaining a productive route.
process.env.HLD_PLANNER_PROTOCOL='2';
let controller=null, directory=null, eventIndex=0;
function save() {
  const state=controller.snapshot();
  for(const e of state.events.slice(eventIndex)) fs.appendFileSync(path.join(directory,'mechanisms.jsonl'),JSON.stringify(e)+'\n');
  eventIndex=state.events.length;
  const temp=path.join(directory,'controller.tmp');
  fs.writeFileSync(temp,JSON.stringify(state,null,2));fs.renameSync(temp,path.join(directory,'controller.json'));
}
const input=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
for await(const line of input) {
  try {
    const request=JSON.parse(line);let result;
    if(request.op==='init') {
      if(controller)throw new Error('already initialized');
      directory=path.resolve(request.directory);fs.mkdirSync(directory,{recursive:true});
      if(fs.existsSync(path.join(directory,'controller.json')))throw new Error('existing run directory: use a fresh run; live resume requires explicit environment reconciliation');
      controller=new SUZController(request.config);result={ready:true};
    } else {
      if(!controller)throw new Error('init required');
      if(request.op==='observe') {
        result=controller.observe(request.value);
        fs.mkdirSync(path.join(directory,'frames'),{recursive:true});
        fs.writeFileSync(path.join(directory,'frames',`${controller.state.current}.png`),Buffer.from(request.value.base64,'base64'));
      } else if(request.op==='context')result=controller.context(request.role,request.stage);
      else if(request.op==='apply')result=controller.apply(request.role,request.value,request.stage);
      else if(request.op==='error')result=controller.roleError(request.role,request.reason);
      else if(request.op==='propose')result=controller.propose(request.value);
      else if(request.op==='schedule')result=controller.schedule();
      else if(request.op==='snapshot')result=controller.snapshot();
      else if(request.op==='halt')result=controller.halt(request.reason);
      else throw new Error('unknown operation');
    }
    save();process.stdout.write(JSON.stringify({ok:true,result:result??null})+'\n');
  } catch(error) {process.stdout.write(JSON.stringify({ok:false,error:error.message})+'\n');}
}
