import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
const root=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const manifest=JSON.parse(fs.readFileSync(path.join(root,'SOURCE-MANIFEST.json'),'utf8'));
for(const [name,expected] of Object.entries(manifest)) {
  const actual=crypto.createHash('sha256').update(fs.readFileSync(path.join(root,name))).digest('hex');
  if(actual!==expected)throw Error('Snapshot differs: '+name);
}
console.log(`Verified ${Object.keys(manifest).length} frozen source/config/dependency files.`);
