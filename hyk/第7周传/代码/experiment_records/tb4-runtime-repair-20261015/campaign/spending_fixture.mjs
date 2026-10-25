// Real loopback ledger, fake model fetch: no external requests.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {guardedFetch} from './provider-guard.mjs';
process.env.DSH_EXPECT_ENDPOINT=process.env.MODEL_MESSAGES_ENDPOINT;
const directory=fs.mkdtempSync(path.join(os.tmpdir(),'spending-stream-'));
let called=0;
const response='data: {"type":"message_start","message":{"usage":{"input_tokens":10,"output_tokens":1,"cache_read_input_tokens":25}}}\n\n'
 +'data: {"type":"message_delta","usage":{"output_tokens":5}}\n\ndata: {"type":"message_stop"}\n\n';
const fetch=guardedFetch(async()=>{called++;return new Response(response,{headers:{'content-type':'text/event-stream'}});},{directory});
assert.equal(await (await fetch(process.env.MODEL_MESSAGES_ENDPOINT,{body:JSON.stringify({model:'fixture',max_tokens:10})})).text(),response);
assert.equal(called,1);
