import http from 'node:http';
export function worldControl(readOnly) {
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
export const APPWORLD_RULES=`Use the original public task as the scope for working-memory goals and verification.
AppWorld checks must read back actual app state and explicitly exhaust relevant pages; a default first page cannot prove all records are handled.
Python using apis executes inside the AppWorld interpreter: python /opt/experiment/client.py --read-only --file /app/check.py. Ordinary local Python has no apis object.
recuris_verify enforces read-only API operations. Check the existing operation receipt and public read-back; never send a probe, create a transfer, export a statement, or email data as verification.
Before a mutation, resolve the exact target identity and every public constraint. Prefer an eligible payment card directly when the task requires a payment. Any prerequisite write must be necessary for the requested task; avoid unrelated cross-app operations.
Submit through supervisor.complete_task exactly once after completing the requested operation and public read-back. State-only tasks omit answer; information requests keep the required answer. Submission seals mutations.
Submission is a solver action, not a write performed inside recuris_verify. Verify submission through its prior receipt and read-only supervisor.show_active_task status using public documentation. Keep goals tied to the user's requirements; do not introduce documentation or probe subgoals after completion.
If a check fails, preserve the failure, repair the substantive problem or the incorrect check, and verify again. An exit code alone cannot prove a checker implements every requirement.`;
