import fs from 'node:fs';
import {zstdDecompressSync as dec} from 'node:zlib';
let input=fs.readFileSync(process.argv[2]), parts=[];
while(input.length){const r=dec(input,{info:true});parts.push(r.buffer);if(!r.engine.bytesWritten)throw Error('no progress');input=input.subarray(r.engine.bytesWritten);}
const rows=Buffer.concat(parts).toString().split('\n').filter(Boolean).map(JSON.parse);
const messages=rows.filter(r=>['user/message','system/message'].includes(r.type)).map(r=>{
 const m=r.data.message??r.data;
 const content=m.content??[];
 const t=content.filter(x=>x.type==='text').map(x=>x.text).join('\n');
 return {seq:r.seq,type:r.type,source:m.source?.kind,chars:t.length,is_kz_update:t.startsWith('Updated KZ task state'),keys:Object.keys(r.data)};
});
const compactions=rows.filter(r=>r.type==='compaction/summary').map(r=>({seq:r.seq,usage:r.data.usage,shadowedTokenCount:r.data.shadowedTokenCount,maxTokens:r.data.maxTokens}));
const updates=messages.filter(x=>x.is_kz_update);
const sourceStats=Object.fromEntries([...new Set(messages.map(x=>x.source))].map(kind=>{const m=messages.filter(x=>x.source===kind);return [kind,{count:m.length,totalChars:m.reduce((a,x)=>a+x.chars,0),minChars:Math.min(...m.map(x=>x.chars)),maxChars:Math.max(...m.map(x=>x.chars))}];}));
console.log(JSON.stringify({sourceStats,updateCharsTotal:updates.reduce((a,x)=>a+x.chars,0),compactionOutputTokens:compactions.reduce((a,x)=>a+x.usage.outputTokens,0),compactions,ends:rows.filter(r=>r.type==='compaction/end').map(r=>({seq:r.seq,...r.data}))},null,2));
