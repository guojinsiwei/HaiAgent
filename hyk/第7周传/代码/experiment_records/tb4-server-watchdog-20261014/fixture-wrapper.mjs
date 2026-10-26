import {spawn} from 'node:child_process';
import fs from 'node:fs';
fs.mkdirSync('/logs/agent/live',{recursive:true});
const service=spawn(process.execPath,['-e','setInterval(()=>{},1000)'],{detached:true,stdio:'ignore'});
fs.writeFileSync('/logs/agent/live/service.json',JSON.stringify({pid:service.pid}));
const child=spawn(process.execPath,['/opt/kz/node_modules/@deepseek-ai/dsh/lib/bin.js'],{detached:true,stdio:'ignore'});
child.on('exit',(code,signal)=>fs.writeFileSync('/logs/agent/live/agent-exit.json',JSON.stringify({code,signal,grading_can_start:true})));
setInterval(()=>{},1000);
