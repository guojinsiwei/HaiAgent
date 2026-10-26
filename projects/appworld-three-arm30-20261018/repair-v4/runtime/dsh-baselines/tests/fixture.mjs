import { Context } from '@deepseek-ai/cordis';
import SystemPrompt from '@deepseek-ai/dsh-system-prompt';
import ToolRuntime from '@deepseek-ai/dsh-tools';
import SessionStore from '@deepseek-ai/dsh-session';
import LlmRuntime,{LlmAdapter,createUserMessage} from '@deepseek-ai/dsh-llm';
import AgentRegistry from '@deepseek-ai/dsh-agent';
import AgentLoop from '@deepseek-ai/dsh-agent-loop';
import SessionProjections from '@deepseek-ai/dsh-session-projection';
import LocalSubprocess from '@deepseek-ai/dsh-subprocess-local';
import LocalBash from '@deepseek-ai/dsh-bash-local';
import * as ShellEnv from '@deepseek-ai/dsh-shell-env';
import * as BashTool from '@deepseek-ai/dsh-tool-bash';
import TokenMeter from '@deepseek-ai/dsh-token-meter';
import Compactor from '@deepseek-ai/dsh-compaction-basic';
import * as Retry from '@deepseek-ai/dsh-llm-retry';
import { resolveRetryPolicy } from '@deepseek-ai/dsh-llm';
import {createServer} from 'node:http';
import {mkdtemp,mkdir,readFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {applyBaseline} from '../src/plugin.mjs';

export const python=process.env.BASELINE_PYTHON??'C:/Users/54177/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe';
const root=process.env.BASELINE_TEST_ROOT??fileURLToPath(new URL('../.runtime/',import.meta.url));
export const task='Create result.txt containing verified. Run the public check; all requirements remain authoritative.';
export const goal={id:'artifact',description:task,verification:{command:"grep -q '^verified$' result.txt",contains:[]}};
export const update=(status,ids=[])=>({updates:[{goal_id:'artifact',status,evidence_ids:ids,blocker:''}],new_goals:[],revised_verifications:[]});
export const tool=(name,args)=>({type:'tool-call',id:crypto.randomUUID(),name,arguments:JSON.stringify(args)});

class ScriptedAdapter extends LlmAdapter {
  constructor(url,respond){super();this.url=url;this.respond=respond;this.requests=[];}
  async resolveModel(provider,model){return {provider,id:model,name:model,context:{contextWindow:1000000},defaultMaxTokens:32768};}
  providerRetryPolicy(){return resolveRetryPolicy({mode:'normal',maxRetries:2,backoff:{initialDelayMs:1,maxDelayMs:1,jitterRatio:0},retryableCodes:['SERVER_ERROR']},'fixture');}
  async *stream(options){
    this.requests.push(structuredClone({...options,signal:undefined}));
    await fetch(this.url,{method:'POST',body:JSON.stringify({purpose:options.purpose??'solver'})});
    const value=await this.respond(options,this.requests);
    if(value instanceof Error)throw value;
    const blocks=Array.isArray(value)?value:[{type:'text',text:typeof value==='string'?value:JSON.stringify(value)}];
    for(const [index,block] of blocks.entries()){
      yield {type:'block-start',index,blockType:block.type};
      if(block.type==='tool-call')yield {type:'tool-call-delta',index,id:block.id,name:block.name,argumentsDelta:block.arguments};
      else yield {type:'text-delta',index,text:block.text};
      yield {type:'block-end',index,block};
    }
    yield {type:'usage',usage:{inputTokens:20,outputTokens:10}};
    yield {type:'finish',reason:{kind:blocks.some(b=>b.type==='tool-call')?'tool-calls':'stop'}};
  }
}
export async function fixture(t,algorithm,respond,overrides={}){
  await mkdir(root,{recursive:true});const dir=await mkdtemp(path.join(root,algorithm+'-'));
  const workspace=path.join(dir,'workspace');await mkdir(workspace);
  let httpCount=0;
  const server=createServer(async(req,res)=>{for await(const _ of req){}httpCount++;res.end('{}');});
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  t.after(()=>new Promise(r=>server.close(r)));
  const ctx=new Context();t.after(()=>ctx.fiber.dispose());
  await ctx.plugin(LlmRuntime);await ctx.plugin(SessionStore);await ctx.plugin(SessionProjections);
  await ctx.plugin(AgentRegistry);await ctx.plugin(SystemPrompt,{});await ctx.plugin(ToolRuntime,{mode:'native'});
  await ctx.plugin(Retry,{});
  await ctx.plugin(TokenMeter);await ctx.plugin(Compactor,{auto:false,maxTokens:32768});
  // Real official tool -> real official bash -> real official subprocess.
  if(process.platform==='win32')process.env.PATH='C:\\Program Files\\Git\\bin;'+process.env.PATH;
  await ctx.plugin(LocalSubprocess);await ctx.plugin(LocalBash,{cwd:workspace,timeoutMs:30000,maxTimeoutMs:300000});
  await ctx.plugin(ShellEnv,{dshHome:path.join(dir,'dsh-home')});
  await ctx.plugin(BashTool,{enableRunInBackground:false,promoteOnTimeout:false});
  const config={instruction:task,workspace,auditDir:path.join(dir,'audit'),python,
    algorithm,worker:algorithm==='native'?undefined:new URL(`../../${algorithm}-dsh/worker.py`,import.meta.url),
    route:{provider:'fixture',model:'fixture',maxTokens:32768},budget:{apiRequests:800,tools:600,wallSeconds:60},commandTimeoutMs:30000,offline:true,...overrides};
  // Worker paths are siblings of dsh-baselines, hence one extra parent from tests.
  let api;await ctx.plugin({name:'baseline-test',inject:['tools','systemPrompt','llm'],apply(c){api=applyBaseline(c,config);}});
  t.after(()=>api.worker()?.close());
  await ctx.plugin(AgentLoop,{agents:[],maxParallelToolCalls:1});
  const adapter=new ScriptedAdapter(`http://127.0.0.1:${server.address().port}/messages`,respond);
  ctx.llm.registerAdapter(['fixture'],adapter);
  const agent=await ctx.agentLoop.create('isolated-'+path.basename(dir),config.route,{cwd:workspace});
  const errors=[];ctx.on('agent/error',e=>{errors.push(e.error??e);});
  async function run(message=task){
    const idle=new Promise(resolve=>{const off=ctx.on('agent/status',({agent:a,status})=>{if(a===agent&&status==='idle'){off();resolve();}});});
    agent.followup(createUserMessage({content:[{type:'text',text:message}],source:{kind:'user'}}));
    await idle;
  }
  return {ctx,agent,run,api,adapter,workspace,dir,config,errors,httpCount:()=>httpCount,
    events:async()=> (await readFile(path.join(dir,'audit/events.jsonl'),'utf8')).trim().split('\n').map(JSON.parse)};
}
