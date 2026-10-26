import {readFileSync,existsSync,readdirSync} from 'node:fs';
import path from 'node:path';
import {isDeepStrictEqual} from 'node:util';
export function loadResume(c) {
  if(!c.resumeSession)return null;
  const read=n=>JSON.parse(readFileSync(path.join(c.auditDir,n),'utf8'));
  const prior=read('run.json'),state=read('state.json');
  for(const key of ['algorithm','instruction','workspace','route'])
    if(!isDeepStrictEqual(prior[key],c[key]))throw Error('Resume configuration differs: '+key);
  if(state.session!==c.resumeSession||state.algorithm!=='recuris')throw Error('Resume session mismatch');
  const events=readFileSync(path.join(c.auditDir,'events.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
  const operations=[];let replies=[],receipt=null,roleSerial=0;
  for(const e of events){
    if(e.event==='role_response')replies.push({role:e.role,text:e.output});
    if(e.event==='tool_observation')receipt=read(e.id+'.json').receipt;
    if(e.event==='tool_dispatch'&&e.callId?.startsWith('recuris-check-'))roleSerial=Math.max(roleSerial,Number(e.callId.split('-').at(-1)));
    if(e.event!=='algorithm_operation')continue;
    let payload={};
    if(e.op==='init')payload={instruction:c.instruction,environment:`DSH workspace: ${c.workspace}. Native tools, permissions and task-local sessions apply.`};
    else if(e.op==='observe'){
      if(!receipt)throw Error('Missing original observation');
      payload={receipt,action:{tool:receipt.tool,arguments:receipt.arguments},mutation:receipt.kind!=='verification'&&!['read','glob','grep','job_output','job_list'].includes(receipt.tool)};
    }else if(e.op==='verification')payload={goal_id:e.result.goal.id};
    else if(!['step','complete','snapshot'].includes(e.op))throw Error('Unsupported resume operation '+e.op);
    operations.push({op:e.op,payload,replies,expected:e.result});replies=[];
  }
  if(!operations.length)throw Error('No committed algorithm state');
  const evidenceSerial=Math.max(0,...readdirSync(c.auditDir).filter(n=>/^E\d+\.json$/.test(n)).map(n=>Number(n.slice(1,-5))));
  return {state,operations,evidenceSerial,roleSerial};
}
export async function replayResume(resume,worker,setReplies){
  let last;
  for(const row of resume.operations){
    const pending=row.replies.slice();setReplies(pending);
    last=await worker.call(row.op,row.payload);
    if(pending.length||!isDeepStrictEqual(last,row.expected))throw Error('Original Recuris operation failed exact replay: '+row.op);
  }
  setReplies(null);return last;
}
