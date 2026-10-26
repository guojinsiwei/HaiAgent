import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const sha=file=>createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const hld=JSON.parse(fs.readFileSync(path.join(root,'hld-source-lock.json'),'utf8'));
const upstream=JSON.parse(fs.readFileSync(path.join(root,'upstream-lock.json'),'utf8'));
for(const [base,files] of [['frozen-hld-v8',hld.files],['vendor/opencua',upstream.files]])
  for(const f of files)if(sha(path.join(root,base,f.path))!==f.sha256)throw new Error('Frozen source changed: '+base+'/'+f.path);
const cfg=JSON.parse(fs.readFileSync(path.join(root,'config/example.json'),'utf8'));
if(cfg.allow_live!==false||cfg.budget_cny!==0)throw new Error('Example must remain unarmed');
console.log(JSON.stringify({frozen_hld_files:hld.files.length,official_opencua_files:upstream.files.length,
  upstream_commit:upstream.commit,source_integrity:'pass',default_live_calls:false,
  live_readiness:'requires visual model endpoint, configured rates/budget, OSWorld VM and end-to-end smoke test'},null,2));
