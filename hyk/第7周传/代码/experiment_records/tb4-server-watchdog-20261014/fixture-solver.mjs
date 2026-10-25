import {spawn} from 'node:child_process';
spawn(process.execPath,['-e',"process.on('SIGTERM',()=>{});setInterval(()=>{},1000)"],{detached:true,stdio:'ignore'});
process.on('SIGTERM',()=>{});
setInterval(()=>{},1000);
