// Materialize a portable template; no credentials, model calls or DSH launch.
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

export function renderTransportConfig(template, plugin) {
  if (template.split('__TRANSPORT_PLUGIN_PATH__').length !== 2) throw Error('Transport template mismatch');
  // Accept both Windows target paths and Linux deployment target paths.
  const paths = /^[A-Za-z]:[\\/]/u.test(plugin) ? path.win32 : path.posix;
  return template.replace('__TRANSPORT_PLUGIN_PATH__', JSON.stringify(paths.join(paths.dirname(plugin), 'transport-recovery.mjs')));
}

export function renderConfig(template,plugin,{longcli=false}={}) {
  if(template.split('__KZ_PLUGIN_PATH__').length!==2)throw Error('Expected exactly one plugin placeholder');
  let source=template.replace('__KZ_PLUGIN_PATH__',JSON.stringify(plugin));
  if(longcli) {
    const task='taskInstructionPath: !!js process.env.KZ_TASK_INSTRUCTION_PATH';
    const shell='shellReceipts: false';
    if(source.split(task).length!==2||source.split(shell).length!==2)throw Error('LongCLI config template mismatch');
    source=source.replace(task,'taskInstructionPath: INSTRUCTION.md').replace(shell,'shellReceipts: true');
  }
  return source;
}
if(process.argv[1]&&pathToFileURL(process.argv[1]).href===import.meta.url) {
  const template=await readFile(new URL('../config/kz.patch.yml',import.meta.url),'utf8');
  const at=process.argv.indexOf('--plugin-path');
  const plugin=at<0?fileURLToPath(new URL('../src/plugin.mjs',import.meta.url)):process.argv[at+1];
  if(!plugin||!(/^(?:[A-Za-z]:[\\/]|\/)/u.test(plugin)))throw Error('Explicit absolute plugin path required');
  const destination=new URL('../.runtime/kz.patch.yml',import.meta.url);
  await mkdir(new URL('../.runtime/',import.meta.url),{recursive:true});
  await writeFile(destination,renderConfig(template,plugin,{longcli:process.argv.includes('--longcli')}));
  const transport = new URL('../.runtime/transport.patch.yml', import.meta.url);
  await writeFile(transport, renderTransportConfig(await readFile(new URL('../config/transport.patch.yml', import.meta.url), 'utf8'), plugin));
  console.log(fileURLToPath(destination));
  console.log(fileURLToPath(transport));
}
