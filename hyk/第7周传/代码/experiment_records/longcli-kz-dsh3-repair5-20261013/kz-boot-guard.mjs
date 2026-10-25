// Deployment-only fail-closed check. No body, credential or prompt is read/logged.
// A missing KZ plugin must never silently run as raw DSH against the paid route.
import {readdirSync,readFileSync} from 'node:fs';
import path from 'node:path';
const nativeFetch=globalThis.fetch;
globalThis.fetch=async function(input,init) {
  const url=typeof input==='string'?input:input?.url??String(input);
  if(url===process.env.DSH_EXPECT_ENDPOINT) {
    const directory=process.env.KZ_AUDIT_DIR;
    let states=[];
    try {states=readdirSync(directory).filter(n=>n.endsWith('.json')).map(n=>JSON.parse(readFileSync(path.join(directory,n),'utf8')));}catch{}
    if(!states.some(s=>s.full?.taskInstruction?.path==='INSTRUCTION.md'&&s.full?.usage?.requests>=1&&s.full?.subgoalController?.version===1&&s.full?.recoveryClock))
      throw Error('KZ_BOOT_GUARD: no initialized KZ task, canonical instruction or shared request admission; provider call blocked before network');
  }
  return nativeFetch.call(this,input,init);
};
