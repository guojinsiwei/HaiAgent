import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';

// Algorithm worker only. It has no model client, shell tool or solver loop.
export class Bridge {
  constructor(python, script, ask, audit) {
    this.pending = null; this.closed = false;
    const env = Object.fromEntries(['PATH','SystemRoot','WINDIR','TEMP','TMP'].filter(k=>process.env[k]).map(k=>[k,process.env[k]]));
    env.PYTHONIOENCODING = 'utf-8'; env.PYTHONDONTWRITEBYTECODE = '1';
    this.child = spawn(python, ['-u', script], { env, windowsHide: true, stdio: ['pipe','pipe','pipe'] });
    this.child.stderr.on('data', b => audit('worker_diagnostic',{text:b.toString()}));
    this.child.on('error', e=>this.fail(e));
    this.child.on('exit', (code,signal)=>{this.closed=true; this.fail(new Error(`algorithm worker exited: ${code}/${signal}`));});
    this.lines = createInterface({input:this.child.stdout});
    this.lines.on('line', async line => {
      try {
        const message=JSON.parse(line);
        if(message.type==='llm') {
          try { this.send({type:'llm_reply',...(await ask(message))}); }
          catch(e) {this.send({type:'llm_reply',error:e.message});}
        } else if(message.type==='event') audit(message.event,message.detail);
        else if(message.type==='result') {
          const p=this.pending; this.pending=null;
          if(!p)throw new Error('unsolicited worker result');
          if(message.error)p.reject(new Error(message.error));else p.resolve(message.value);
        } else throw new Error('invalid worker protocol');
      } catch(e) {this.fail(e);}
    });
  }
  send(value) {if(this.closed)throw new Error('worker closed');this.child.stdin.write(JSON.stringify(value)+'\n');}
  fail(error) {if(this.pending){this.pending.reject(error);this.pending=null;}}
  call(op,payload={}) {
    if(this.pending)throw new Error('concurrent algorithm operation');
    if(this.closed)throw new Error('worker closed');
    return new Promise((resolve,reject)=>{this.pending={resolve,reject};this.send({op,...payload});});
  }
  close(){this.fail(new Error('worker disposed'));this.child.stdin.end();this.child.kill();this.lines.close();}
}
