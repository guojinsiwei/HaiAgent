import { commandIdentity } from './policy.mjs';

// Only inspect syntax. Never rewrite commands or claim to fully parse shell programs.
export function maskedStages(command) {
  let quote=null, escape=false;
  for(let i=0;i<command.length;i++) {
    const c=command[i];
    if(escape){escape=false;continue;}
    if(c==='\\'&&quote!=="'"){escape=true;continue;}
    if(quote){if(c===quote)quote=null;else if(quote==='"'&&(c==='$'||c==='`'))return true;continue;}
    if(c==='"'||c==="'"){quote=c;continue;}
    if(c==='&'){if(command[i+1]==='&'){i++;continue;}return true;}
    if(';|\n\r`$'.includes(c))return true;
  }
  return !!quote;
}

export function literalFileRead(command) {
  const [kind,exe,args]=commandIdentity(command);
  if(kind!=='literal'||!['cat','head','tail','wc'].includes(exe))return false;
  // A follow/read-from-process operation is not a reusable file observation.
  if(args.some(x=>x==='-'||x==='/dev/stdin'||x.startsWith('/proc/')||x.startsWith('/dev/')||x==='--follow'||/^--follow=/.test(x)||/^-[^-]*[fF]/.test(x)))return false;
  return args.some(x=>!x.startsWith('-')&&!/^\d+$/.test(x));
}
