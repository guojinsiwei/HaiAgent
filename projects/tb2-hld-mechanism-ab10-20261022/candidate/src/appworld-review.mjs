import http from 'node:http';

export function worldControl(readOnly) {
  if(process.env.KZ_APPWORLD!=='1')return Promise.resolve(null);
  return new Promise((resolve,reject)=>{
    const data=readOnly===undefined?null:JSON.stringify({read_only:readOnly});
    const req=http.request({hostname:'world',port:8080,path:data?'/review-mode':'/health',method:data?'POST':'GET',
      headers:data?{'Content-Type':'application/json','Content-Length':Buffer.byteLength(data)}:{}},res=>{
      let raw='';res.on('data',b=>raw+=b);res.on('end',()=>{try{
        if(res.statusCode!==200)throw new Error('AppWorld review control unavailable');
        resolve(JSON.parse(raw).guard);
      }catch(e){reject(e);}});
    });
    req.setTimeout(5000,()=>req.destroy(new Error('AppWorld review control timeout')));req.on('error',reject);req.end(data??undefined);
  });
}

// Exact commands remain structured and untruncated. Large outputs remain in the
// archive; retrieval is explicit. No evidence is converted into a pass here.
export function reviewEvidence(state,limit=12) {
  const rows=Object.values(state.evidence??{}).filter(r=>r.complete).sort((a,b)=>Number(b.id.slice(1))-Number(a.id.slice(1))).slice(0,limit);
  return rows.map(r=>({id:r.id,tool:r.tool,arguments:r.arguments??null,command:r.command,
    complete:r.complete,executed:r.executed,exitCode:r.exitCode,clean:r.clean,
    stdout:String(r.stdout??'').slice(0,6000),stderr:String(r.stderr??'').slice(0,1500),
    output_partial:String(r.stdout??'').length>6000||String(r.stderr??'').length>1500,
    retrieval:{tool:'kz_history',id:r.id},before:r.before,after:r.after}));
}

export const APPWORLD_REVIEW_RULES=`AppWorld operations affect persistent application state.
Prioritize original task scope: exact identities/relationships, time windows, intended record set, complete pagination, values, and absence of unrelated changes.
An API default page is a sample. "All" requires exhausting relevant pages. Distinguish evening/dinner from the entire calendar date; inspect timestamps and semantic descriptions BEFORE deleting original records.
Verification is READ ONLY. Never send a marker, transaction, request, notification or export to prove a write path. Deleting a probe may leave global effects. Use the original write receipt plus a read-back from a public API.
Task submission is terminal for mutations; do it once, after read-back. State-only tasks use complete_task() without an explanatory answer. Only public tasks asking for information get an answer.
Python scripts using apis run in the AppWorld interpreter, never ordinary local Python. Use the exact direct command: python /opt/experiment/client.py --read-only --file /app/check.py. This preserves native exit status and supports assertion checks without heredocs.
Use exact_commands supplied alongside the panel, or kz_history for full output. Do not demand command reformatting when the actual command and exit status are already available.
For transfer tasks prefer an eligible payment card directly; do not fund a balance, email/export statements or create payments in another app as evidence. A prerequisite must be necessary for the public task, and its side effects must be considered.
Do not invent documentation-only or send-path-probe subgoals after the public operation and read-back are complete.`;
