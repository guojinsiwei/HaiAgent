import { relativeTarget } from './memory.mjs';
import { artifactTarget } from './artifacts.mjs';

export function deliveryPaths(goal,root=null) {
  const paths=new Set();let section=false;
  for(const raw of goal.split('\n')) {
    const line=raw.trim(),heading=line.replace(/^#+/,'').trim();
    if(/required\s+(output|artifacts?|files?)|deliverables?|outputs?\s+required|交付物|需要(?:的)?(?:输出|交付)/i.test(heading)){section=true;}
    else if(section&&(line.startsWith('#')||heading.endsWith(':')&&!/^[-*+]/.test(line)))section=false;
    if(!section&&!/generate|create|produce|write|save|deliver|must\s+include|输出|生成|创建|保存|交付/i.test(line))continue;
    for(const m of line.matchAll(/(?<![\w.\/-])(?:\/|\.\/)?(?:[\w.-]+\/)*[\w.-]+\.(?:jsonl?|csv|tsv|md|txt|py|sh|ya?ml|toml|xml|html|pdf|png|np[yz]|parquet|c|cpp|cc|h|rs|js|mjs|ts|go|java|bin|so|elf|ppm|7z|fasta)(?![\w-]|\.[\w])/g)) {
      try{const p=root?artifactTarget(root,m[0]):relativeTarget(m[0].replace(/^\/app\//,''));if(!/^(tests|solution|logs\/verifier|\.git)\//.test(p))paths.add(p);}catch{}
    }
  }
  return [...paths].slice(0,24);
}
export function progressView(state,config,dependencies,root=null) {
  const requested=deliveryPaths(state.taskGoal,root);
  state.delivery={requested_artifacts:requested,missing:requested.filter(p=>dependencies[p]==='missing'),unverified:requested.filter(p=>!dependencies[p]||dependencies[p]==='unknown'),
    correctness:'unverified; path existence and zero exit are not task completion'};
  if(config.budgetDisabled===true){
    state.budgetView={requests:state.usage.requests,tools:state.usage.tools,maxRequests:null,maxTools:null,phase:'unlimited',
      instruction:'No request, tool or monetary cap. The separately configured server wall-time deadline still applies; never assume unlimited time. Continue useful work and verify delivery.',
      server_wall_seconds:config.serverWallSeconds??null,cost_guard:'disabled'};
    return;
  }
  const ratios=[state.usage.requests/(config.maxRequests??800),state.usage.tools/(config.maxTools??600)];
  if(config.costPolicy?.limitCny)ratios.push(((state.cost?.spentUpperCny??0)+(state.cost?.pendingUpperCny??0))/config.costPolicy.limitCny);
  if(config.wallSeconds)ratios.push((Date.now()-state.startedAt)/(config.wallSeconds*1000));
  const ratio=Math.max(...ratios);
  state.budgetView={requests:state.usage.requests,tools:state.usage.tools,maxRequests:config.maxRequests??800,maxTools:config.maxTools??600,
    phase:ratio>=.85?'delivery_priority':ratio>=.6?'consolidate':'ordinary',
    instruction:ratio>=.85?'Prioritize public verification and preserve a usable partial delivery; no extra budget.':ratio>=.6?'Consolidate working changes, inspect remaining requirements, avoid open-ended exploration.':'Continue evidence-driven work.',
    cost_guard:config.costPolicy?'enabled_conservative_reservation':'not_configured'};
}
