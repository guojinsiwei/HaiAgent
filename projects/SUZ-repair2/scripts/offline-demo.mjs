import {spawnSync} from 'node:child_process';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const python=process.env.SUZ_PYTHON??path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
const directory=path.join(root,'runs',`offline-${Date.now()}`);
const result=spawnSync(python,['-m','python.offline_demo','--output',directory],{cwd:root,stdio:'inherit'});
if(result.error)throw result.error;
process.exitCode=result.status??1;
