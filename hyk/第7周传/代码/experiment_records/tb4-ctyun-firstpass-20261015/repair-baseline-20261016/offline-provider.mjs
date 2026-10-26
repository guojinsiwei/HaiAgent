// Loaded before every other wrapper only in unpaid preflight. It cannot issue
// network fetches. Reaching it proves boot/route checks and ledger admission.
import fs from 'node:fs';
globalThis.fetch=async()=>{
  fs.writeFileSync('/logs/agent/live/offline-transport.json',JSON.stringify({passed:true,paid_calls:0}));
  throw Object.assign(Error('Intentional offline transport stop'),{name:'OfflineTransportComplete'});
};
