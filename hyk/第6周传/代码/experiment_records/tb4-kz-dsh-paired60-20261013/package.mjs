// Allowlist only: never include sessions, runtime homes, credentials or old logs.
import {readdirSync,readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
const dest=fileURLToPath(new URL('.',import.meta.url));
const root=fileURLToPath(new URL('../../projects/kz-dsh/',import.meta.url));
const files=['package.json','package-lock.json',...['src','config','scripts','tests'].flatMap(dir=>readdirSync(path.join(root,dir),{withFileTypes:true}).filter(e=>e.isFile()&&/\.(mjs|yml)$/.test(e.name)).map(e=>dir+'/'+e.name))];
const hashes=Object.fromEntries(files.map(n=>[n,createHash('sha256').update(readFileSync(path.join(root,n))).digest('hex')]));
if(JSON.parse(readFileSync(path.join(root,'package.json'))).version!=='0.2.7')throw Error('Version drift');
execFileSync('tar',['-czf',path.join(dest,'candidate.tar.gz'),...files],{cwd:root});
writeFileSync(path.join(dest,'source-manifest.json'),JSON.stringify({version:'0.2.7',files:hashes,paid_calls:0},null,2));
console.log(JSON.stringify({files:files.length,sha256:createHash('sha256').update(readFileSync(path.join(dest,'candidate.tar.gz'))).digest('hex')}));
