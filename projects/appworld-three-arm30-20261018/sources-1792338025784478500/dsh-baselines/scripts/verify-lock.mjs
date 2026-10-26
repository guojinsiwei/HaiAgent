import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url)),projects=path.dirname(root);
const lock=JSON.parse(await readFile(path.join(root,'source-lock.json'),'utf8'));
async function verify(file,expected){const actual=createHash('sha256').update(await readFile(file)).digest('hex');if(actual!==expected)throw new Error('Hash drift: '+file);}
for(const [file,digest] of Object.entries(lock.sourceFiles))await verify(path.join(projects,file),digest);
for(const [pkg,entry] of Object.entries(lock.dsh.packages))for(const [file,digest] of Object.entries(entry.files))await verify(path.join(root,'node_modules/@deepseek-ai',pkg,'lib',file),digest);
console.log('Source, configuration and official DSH runtime hashes match lock.');
