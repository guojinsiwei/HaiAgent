import { applyBaseline } from '../../dsh-baselines/src/plugin.mjs';
export const name='taco-dsh';
export const inject=['tools','systemPrompt','llm'];
export function apply(ctx,config){return applyBaseline(ctx,{...config,algorithm:'taco',worker:new URL('../worker.py',import.meta.url)});}
