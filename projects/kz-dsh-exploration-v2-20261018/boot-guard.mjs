// Fail closed before network if either arm's common guard, or KZ, failed to load.
import {readFileSync,readdirSync} from 'node:fs';
import path from 'node:path';
const fetch=globalThis.fetch;
globalThis.fetch=async function(input,init){
  const url=typeof input==='string'?input:input?.url??String(input);
  if(url!==process.env.DSH_EXPECT_ENDPOINT)throw Error('PAIRED_BOOT_GUARD: unexpected provider endpoint');
  let state;
  try {state=JSON.parse(readFileSync(path.join(process.env.PAIRED_AUDIT_DIR,'shared-state.json'),'utf8'));}catch{}
  if(!(state?.requests>=1&&state.budgetMode==='bounded_peak_price_estimate'))throw Error('PAIRED_BOOT_GUARD: bounded accounting unavailable');
  const arm=process.env.PAIRED_ARM;
  if(!['kz','dsh'].includes(arm))throw Error('PAIRED_BOOT_GUARD: missing arm');
  if(arm==='kz'){
    let states=[];
    try {states=readdirSync(process.env.KZ_AUDIT_DIR).filter(n=>n.endsWith('.json')).map(n=>JSON.parse(readFileSync(path.join(process.env.KZ_AUDIT_DIR,n),'utf8')));}catch{}
    if(!states.some(s=>s.full?.taskInstruction?.path===(process.env.KZ_TASK_INSTRUCTION_PATH??'BENCHMARK_INSTRUCTION.md')&&s.full?.usage?.requests>=1&&s.full?.subgoalController?.version===1&&s.full?.recoveryClock))
      throw Error('PAIRED_BOOT_GUARD: KZ missing; paid request blocked');
  }
  return fetch.call(this,input,init);
};
