import { AsyncLocalStorage } from 'node:async_hooks';
export const requestScope = new AsyncLocalStorage();
const marker = Symbol.for('dsh-baselines.fetch-meter');
// Hook the transport, not just logical llm.stream calls. Every retry passes here.
export function installTransport() {
  if(globalThis[marker])return;
  const original=globalThis.fetch;
  globalThis.fetch=async function(input,init){
    const scope=requestScope.getStore();
    if(!scope)throw new Error('Unattributed network request refused in isolated baseline process');
    const url=new URL(typeof input==='string'||input instanceof URL?input:input.url);
    if(scope.offline&&!['127.0.0.1','localhost','[::1]'].includes(url.hostname))throw new Error('Offline mode forbids external model requests');
    scope.admitHttp({origin:url.origin,path:url.pathname});
    return original(input,init);
  };
  globalThis[marker]=true;
}
