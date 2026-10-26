import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import yaml from 'js-yaml';
import {applyEntryPatches,entryListSchema} from '@deepseek-ai/cordis-plugin-include';
import {renderConfig,renderTransportConfig} from '../scripts/prepare-config.mjs';
const template=readFileSync(new URL('../config/kz.patch.yml',import.meta.url),'utf8');
const parse=source=>yaml.load(source,{schema:entryListSchema});
const compose=source=>applyEntryPatches([],parse(source),message=>{throw Error(message)}).find(e=>e.id==='kz-policy');
test('LongCLI materialization retains every original KZ config field under actual DSH patch semantics',()=>{
  const base=compose(renderConfig(template,'/opt/kz/src/plugin.mjs'));
  const actual=compose(renderConfig(template,'/opt/kz/src/plugin.mjs',{longcli:true}));
  assert.deepEqual(actual,{...base,config:{...base.config,taskInstructionPath:'INSTRUCTION.md',shellReceipts:true}});
  for(const field of ['workspace','auditDir','maxRequests','maxTools','wallSeconds','costPolicy','monitorEnabled','backtracking'])assert.deepEqual(actual.config[field],base.config[field]);
  assert.equal(actual.config.maxRequests,800);assert.equal(actual.config.maxTools,600);assert.equal(actual.config.backtracking,false);
});
test('DSH partial config patches REPLACE rather than merge; regression must not silently drop KZ setup',()=>{
  const base=compose(renderConfig(template,'/opt/kz/src/plugin.mjs'));
  const wrong=applyEntryPatches([base],[{id:'kz-policy',config:{taskInstructionPath:'INSTRUCTION.md'}}],()=>{})[0];
  assert.equal(wrong.config.workspace,undefined);assert.equal(wrong.config.maxRequests,undefined);
  assert.throws(()=>renderConfig(template.replace('shellReceipts: false','shellReceipts: null'),'/opt/kz/src/plugin.mjs',{longcli:true}),/mismatch/);
});

test('shared transport recovery patch loads independently of KZ without replacing provider config',()=>{
  const template=readFileSync(new URL('../config/transport.patch.yml',import.meta.url),'utf8');
  const source=renderTransportConfig(template,'/opt/kz/src/plugin.mjs');
  const original={id:'provider',config:{maxTokens:32768,temperature:0}};
  const result=applyEntryPatches([original],parse(source),()=>{throw Error('unexpected missing entry')});
  assert.deepEqual(result[0],original);
  assert.equal(result[1].name,'/opt/kz/src/transport-recovery.mjs');
  assert.equal(result[1].id,'tool-json-recovery');
});
