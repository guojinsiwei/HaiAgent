import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const runtime=process.argv[2];
const require=createRequire(path.join(runtime,'package.json'));
const yaml=require('js-yaml');
const {applyEntryPatches,entryListSchema}=require('@deepseek-ai/cordis-plugin-include');
const compose=file=>applyEntryPatches([],yaml.load(fs.readFileSync(path.join(runtime,file),'utf8'),{schema:entryListSchema}),()=>{});
const original=compose('.runtime/kz.patch.yml')[0],high=compose('.runtime/kz-high-limits.patch.yml')[0];
assert.deepEqual(high,{...original,config:{...original.config,maxRequests:800,costPolicy:{...original.config.costPolicy,maxOutputTokens:32768}}});
assert.equal(high.config.costPolicy.limitCny,24);
const route=compose('route-high-output.patch.yml');
// Provider replacement entries need an existing provider to apply; inspect raw
// patch config as well as the real plugin insertion above.
const raw=yaml.load(fs.readFileSync(path.join(runtime,'route-high-output.patch.yml'),'utf8'),{schema:entryListSchema});
assert.equal(raw[0].config.maxTokens,32768);assert.equal(raw[0].config.models[0].maxTokens,32768);
assert.equal(raw[0].config.models[0].contextWindow,128000);
assert.ok(route.some(x=>x.name?.endsWith('/shared-budget-high.mjs')));
const dir=fs.mkdtempSync(path.join(os.tmpdir(),'hld-limit-preflight-'));
process.env.PAIRED_AUDIT_DIR=dir;
const {apply}=await import('file://'+runtime+'/shared-budget-high.mjs');
const handlers={};apply({on:(name,fn)=>{handlers[name]=fn;}});
assert.equal((await handlers['agent/request']({},async()=>({}))).maxTokens,32768);
for(let i=0;i<800;i++)for await(const _ of handlers['llm/stream']({sessionId:'test'},async function*(){yield {type:'usage',usage:{inputTokens:0,outputTokens:0}};yield {type:'finish',reason:{kind:'stop'}};})){}
await assert.rejects(async()=>{for await(const _ of handlers['llm/stream']({sessionId:'test'},async function*(){})){}},/per_task_request_limit/);
const state=JSON.parse(fs.readFileSync(path.join(dir,'shared-state.json')));assert.equal(state.requests,800);
// This uniquely created temporary directory contains only this test's files.
fs.rmSync(dir,{recursive:true});
console.log(JSON.stringify({passed:true,model_calls:0,exact_config_delta:true,shared_request_guard:800,output_limit:32768,cny_per_task:24}));
