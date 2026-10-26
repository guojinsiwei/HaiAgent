// Task-local correlation only: DSH still starts, schedules, cancels and owns jobs.
// readAt is a NON-consuming observer cursor; never steal the model's job_output.
const terminal = status => ['completed','failed','killed','unavailable'].includes(status);
const cap = 262144; // bounded evidence projection, NOT an execution/output limit
export class BackgroundJobs {
  constructor(state) { this.state=state??{items:{}}; }
  start(call,value,snapshot) {
    if(!['promoted','background'].includes(value?.kind)||typeof value.jobId!=='string'||!value.jobId)return null;
    if(Object.hasOwn(this.state.items,value.jobId))return null;
    const row={id:value.jobId,call:{name:'bash',arguments:structuredClone(call.arguments),callId:call.callId,turn:call.turn??null},
      snapshot:structuredClone(snapshot),status:'running',offset:0,stdout:'',stderr:'',lossy:false,channelUnknown:false,
      interleaved:this.active().length>0,finalized:false,registry:false,launchEvidence:null};
    this.state.items[row.id]=row;
    // Promoted output is a rendered delta. Preserve it but do not mistake it for
    // complete, channel-separated evidence; registry observation supersedes it.
    this.append(row,String(value.output??''),'stdout');row.channelUnknown=true;
    return row;
  }
  append(row,text,channel) {
    if(channel!=='stdout'&&channel!=='stderr'){row.channelUnknown=true;channel='stdout';}
    row[channel]+=text;
    if(row.stdout.length+row.stderr.length>cap) {
      row.lossy=true;row.stdout=row.stdout.slice(-cap/2);row.stderr=row.stderr.slice(-cap/2);
    }
    if(/\[(?:some output was dropped|output truncated)/iu.test(text))row.lossy=true;
  }
  active() {return Object.values(this.state.items).filter(j=>!j.finalized);}
  markInterleaved(callId) {for(const j of this.active())if(j.call.callId!==callId)j.interleaved=true;}
  // A restored process must not trust a recycled registry id or an old cursor.
  abandon() {for(const j of this.active()){j.finalized=true;j.status='unavailable';j.abandoned=true;j.stdout='';j.stderr='';}}
  update(row,job,read=null,text=null) {
    if(row.finalized||job.id!==row.id||job.kind!=='bash')return null;
    const previous=[row.status,row.offset,row.stdout,row.stderr,row.lossy];
    if(read) {
      if(!row.registry){row.stdout='';row.stderr='';row.lossy=false;row.channelUnknown=false;row.registry=true;}
      row.lossy||=read.lossy;
      for(const chunk of read.chunks) {
        row.lossy||=!!chunk.gapBefore;
        this.append(row,chunk.text,chunk.channel);
      }
      row.offset=read.next;
    } else if(!row.registry&&typeof text==='string')this.append(row,text,'stdout');
    row.status=job.status;row.detail=job.detail??null;
    if(!terminal(row.status)&&JSON.stringify(previous)===JSON.stringify([row.status,row.offset,row.stdout,row.stderr,row.lossy]))return null;
    const observation=this.observation(row,terminal(row.status)?'final':'output');
    if(terminal(row.status)){row.finalized=true;row.stdout='';row.stderr='';}
    return observation;
  }
  observation(row,stage='launch') {
    // Only the pinned producer's exact status grammar supplies an exit code.
    // Sandbox runner/denial suffixes, kills and missing statuses stay unknown.
    const match=row.status==='completed'?/^exit code: (-?\d+)$/u.exec(row.detail??''):null;
    const exitCode=match&&Number.isSafeInteger(Number(match[1]))?Number(match[1]):null;
    return {executed:true,complete:stage==='final'&&row.registry&&!row.lossy&&!row.channelUnknown&&exitCode!==null,
      exitCode,stdout:row.stdout,stderr:row.stderr,jobId:row.id,jobStage:stage,jobStatus:row.status,jobDetail:row.detail??null,
      launchEvidence:row.launchEvidence,outputCoverage:row.registry&&!row.lossy?'observer_stream':'partial_or_rendered',
      stateAttribution:row.interleaved?'interleaved_unknown':'observed_interval_external_state_unverified'};
  }
}
