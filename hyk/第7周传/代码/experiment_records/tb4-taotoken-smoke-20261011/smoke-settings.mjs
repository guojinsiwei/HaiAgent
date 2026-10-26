// Deployment-only settings, applied through DSH's native request waterfall.
// No solver loop or KZ algorithm is replaced.
export const name = 'tb4-smoke-settings';
export function apply(ctx) {
  ctx.on('agent/request', async (_payload, next) => ({
    ...await next(), temperature: 0, reasoningEffort: 'off', maxTokens: 8192,
  }));
}
