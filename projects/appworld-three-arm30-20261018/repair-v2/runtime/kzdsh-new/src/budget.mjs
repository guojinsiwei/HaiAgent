// Monetary guard for a pinned, text-only adapter with one HTTP generation attempt
// per llm/stream. The official DSH text route was source-audited; other transports
// need separate verification. Prices are experiment inputs, never a live invoice.
export function validateCostPolicy(c) {
  if(!c)return;
  for(const k of ['limitCny','inputPerMillion','outputPerMillion','maxInputTokens','maxOutputTokens'])
    if(!Number.isFinite(c[k])||c[k]<=0)throw new Error(`invalid costPolicy.${k}`);
  if(c.cacheReadPerMillion!==undefined&&(!Number.isFinite(c.cacheReadPerMillion)||c.cacheReadPerMillion<0||c.cacheReadPerMillion>c.inputPerMillion))throw new Error('invalid costPolicy.cacheReadPerMillion');
  if(!c.provider||!c.model||!c.priceBasis)throw new Error('cost policy requires pinned provider, model and price basis');
}
const upper=n=>Math.ceil(n*1e6)/1e6;
export function reserveCost(state,c,options) {
  if(!c)return null;
  validateCostPolicy(c);
  if(options.provider!==c.provider||options.model!==c.model)throw new Error('Cost guard route mismatch; verify pricing before dispatch');
  function hasMedia(value){if(!value||typeof value!=='object')return false;if(['image','file','audio','video'].includes(value.type))return true;return Object.values(value).some(v=>Array.isArray(v)?v.some(hasMedia):hasMedia(v));}
  if(hasMedia(options.messages))throw new Error('Cost guard verified for text-only CLI calls; media/file transport needs separate accounting');
  // DSH can otherwise resolve an adapter default (e.g. 256k) AFTER this hook.
  // Never reserve 32k while silently dispatching that larger default.
  const output=options.maxTokens;
  if(!Number.isInteger(output)||output<1||output>c.maxOutputTokens)throw new Error('Request output exceeds verified cost reservation bound');
  state.cost??={spentUpperCny:0,pendingUpperCny:0,uncertainAttempts:0,attempts:0};
  const amount=upper((c.maxInputTokens*c.inputPerMillion+output*c.outputPerMillion)/1e6);
  if(state.cost.spentUpperCny+state.cost.pendingUpperCny+amount>c.limitCny)throw new Error('KZ per-task monetary ceiling; next request not sent, artifacts retained');
  state.cost.pendingUpperCny=upper(state.cost.pendingUpperCny+amount);state.cost.attempts++;
  return amount;
}
export function settleCost(state,c,reservation,usage,completed) {
  if(reservation===null)return;
  let amount=reservation;
  // DSH usage fields are cumulative; sum only the final totals, not every delta.
  const input=usage?.inputTokens,output=usage?.outputTokens;
  const cacheRead=usage?.cacheReadTokens??0,cacheWrite=usage?.cacheWriteTokens??0;
  const known=completed&&[input,output,cacheRead,cacheWrite].every(x=>Number.isSafeInteger(x)&&x>=0);
  if(known)amount=upper(((input+cacheWrite)*c.inputPerMillion+cacheRead*(c.cacheReadPerMillion??c.inputPerMillion)+output*c.outputPerMillion)/1e6);
  else state.cost.uncertainAttempts++;
  state.cost.pendingUpperCny=Math.max(0,upper(state.cost.pendingUpperCny-reservation));
  state.cost.spentUpperCny=upper(state.cost.spentUpperCny+amount);
  if(amount>reservation){state.cost.boundExceeded=true;throw new Error('Provider usage exceeded verified reservation; block further calls');}
}
