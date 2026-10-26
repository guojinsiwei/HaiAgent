import path from 'node:path';
import {actionKey,commandIdentity,digest} from './policy.mjs';

// Verification-only equivalence. Never change policy gates or executed commands.
// A single literal cd prefix can describe the same explicit working directory.
// Startup scripts, shell wrappers, expansions, symlinks/.. and compound commands
// are not guessed equivalent: the existing update+bind tool handles those.
export function verificationKey(args) {
  if(!args||typeof args.command!=='string')return null;
  let command=args.command,cwd=args.workdir??'.';
  const parts=[];let quote=null,start=0;
  for(let i=0;i<command.length;i++) {
    const c=command[i];
    if(c==='\\'||c==='$'||c==='`'||c==='\n'||c==='\r')return digest(['exact',args]);
    if(quote){if(c===quote)quote=null;continue;}
    if(c==='"'||c==="'"){quote=c;continue;}
    if(command.slice(i,i+2)==='&&'){parts.push(command.slice(start,i));start=i+2;i++;}
  }
  parts.push(command.slice(start));
  if(parts.length===2) {
    const cd=commandIdentity(parts[0]),next=commandIdentity(parts[1]);
    if(cd[0]!=='literal'||cd[1]!=='cd'||cd[2].length!==1||next[0]!=='literal')return digest(['exact',args]);
    const target=cd[2][0];
    // Do not collapse .. through a possible symlink, or assume a workspace root.
    if(!target.startsWith('/')||target.split('/').some(x=>x==='..'||x==='.'))return digest(['exact',args]);
    cwd=target;command=parts[1];
  }else if(parts.length!==1)return digest(['exact',args]);
  const identity=commandIdentity(command);
  if(identity[0]!=='literal'||['bash','sh','dash','zsh'].includes(identity[1].split('/').at(-1)))return digest(['exact',args]);
  const rest={...args};delete rest.command;delete rest.workdir;delete rest.description;
  return digest(['verification',identity,path.posix.isAbsolute(cwd)?cwd.replace(/\/+$/,'')||'/':cwd,rest]);
}
export function verificationMatches(args,row) {
  if(row.arguments)return actionKey({name:'bash',arguments:row.arguments})===row.key&&verificationKey(args)===verificationKey(row.arguments);
  // Legacy evidence without complete arguments supports only its original key.
  return actionKey({name:'bash',arguments:args})===row.key;
}
