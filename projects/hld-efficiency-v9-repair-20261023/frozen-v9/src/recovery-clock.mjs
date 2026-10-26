import { actionKey, digest } from './policy.mjs';

// Scheduling events are not execution evidence. R IDs never enter the E store.
export class RecoveryClock {
  constructor(state,initial=0) {
    this.state=state??{steps:initial,executions:initial,rejections:0,next:1,seen:[],controls:[],consecutive:0};
  }
  execution(call) {
    if(!call?.callId||this.state.seen.includes(call.callId))return false;
    this.state.seen.push(call.callId);this.state.seen=this.state.seen.slice(-1024);
    this.state.steps++;this.state.executions++;this.state.consecutive=0;return true;
  }
  rejected(call,reason,scope,kind='gate') {
    if(!call?.callId||this.state.seen.includes(call.callId))return null;
    const s=this.state;s.seen.push(call.callId);s.seen=s.seen.slice(-1024);
    s.steps++;s.rejections++;s.consecutive++;
    const row={id:`R${s.next++}`,callId:call.callId,kind,reason:String(reason),key:actionKey(call),
      command:call.arguments?.command??`${call.name} proposal`,before:scope,after:scope,
      executed:false,complete:false,controlEvent:true,exitCode:null,clean:false,failureObserved:false,
      clock:s.steps,stdout:'',stderr:'',rawHashes:{control:digest([actionKey(call),reason])}};
    s.controls.push(row);s.controls=s.controls.slice(-16);return row;
  }
  evidence() {return Object.fromEntries(this.state.controls.map(r=>[r.id,r]));}
}
