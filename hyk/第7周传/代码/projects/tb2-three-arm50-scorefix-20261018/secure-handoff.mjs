// Only RSA ciphertext is stored locally. Private key and API key stay in RAM.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
const pub=path.join(root,'handoff-public.pem'),enc=path.join(root,'handoff-encrypted.bin');
const pair=crypto.generateKeyPairSync('rsa',{modulusLength:3072});
fs.writeFileSync(pub,pair.publicKey.export({type:'spki',format:'pem'}),{flag:'wx'});
let ticks=0;
const timer=setInterval(()=>{
 if(++ticks>180){clearInterval(timer);fs.unlinkSync(pub);console.log('Handoff expired');process.exitCode=1;return;}
 if(!fs.existsSync(enc))return;
 const encrypted=fs.readFileSync(enc);if(encrypted.length!==384)return;
 clearInterval(timer);
 let key=crypto.privateDecrypt({key:pair.privateKey,oaepHash:'sha256'},encrypted).toString('utf8');
 fs.unlinkSync(pub);fs.unlinkSync(enc);
 const remote='/mnt/sdb/home/lizh639/tb2-three-arm50-scorefix-20261018';
 const child=spawn('C:/Windows/System32/OpenSSH/ssh.exe',['-o','BatchMode=yes','-o','ConnectTimeout=12','-o','StrictHostKeyChecking=yes','-i','C:/Users/54177/.ssh/cubestudio_notebook','lizh639@172.16.108.236',`${remote}/venv/bin/python ${remote}/score_retry.py --launch`],{windowsHide:true,stdio:['pipe','pipe','pipe']});
 let out='',err='';child.stdout.on('data',d=>out+=d);child.stderr.on('data',d=>err+=d);
 child.stdin.end(JSON.stringify({key})+'\n');key='';
 child.on('close',code=>{console.log(JSON.stringify({exit_code:code,output:out,stderr:err}));process.exitCode=code??1;});
},1000);
console.log('WAITING_FOR_ENCRYPTED_HANDOFF');

