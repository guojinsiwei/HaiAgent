import {readFileSync,readdirSync} from 'node:fs';
import path from 'node:path';
const original=globalThis.fetch;
globalThis.fetch=async function(input,init){
  const url=typeof input==='string'?input:input?.url??String(input);
  if(url!==process.env.DSH_EXPECT_ENDPOINT)throw Error('BOOT_GUARD: unexpected endpoint');
  const audit=process.env.PAIRED_AUDIT_DIR;
  const shared=JSON.parse(readFileSync(path.join(audit,'shared-state.json'),'utf8'));
  if(!(shared.requests>=1&&shared.budgetMode==='bounded_peak_price_estimate'))throw Error('BOOT_GUARD: missing shared budget');
  const arm=process.env.EXPERIMENT_ARM;
  if(['hld','kzdsh-new'].includes(arm)){
    const states=readdirSync(process.env.KZ_AUDIT_DIR).filter(n=>n.endsWith('.json')).map(n=>JSON.parse(readFileSync(path.join(process.env.KZ_AUDIT_DIR,n),'utf8')));
    if(!states.some(s=>s.full?.taskInstruction?.path==='INSTRUCTION.md'&&s.full?.usage?.requests>=1&&s.full?.subgoalController?.version===1))throw Error('BOOT_GUARD: KZ unavailable');
  }else if(arm==='recuris'){
    const state=JSON.parse(readFileSync(path.join(audit,'recuris/state.json'),'utf8'));
    if(state.algorithm!=='recuris'||!state.session)throw Error('BOOT_GUARD: Recuris unavailable');
  }else if(arm!=='dsh')throw Error('BOOT_GUARD: unknown arm');
  return original.call(this,input,init);
};
