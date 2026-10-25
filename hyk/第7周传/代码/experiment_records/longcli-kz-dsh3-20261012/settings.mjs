// Deployment settings only; KZ's algorithm and native DSH loop are unchanged.
export const name = 'longcli-kz-large-settings';
export function apply(ctx) {
  ctx.on('agent/request', async (_payload, next) => ({
    ...await next(), temperature: 0, reasoningEffort: 'off', maxTokens: 32768,
  }));
}
