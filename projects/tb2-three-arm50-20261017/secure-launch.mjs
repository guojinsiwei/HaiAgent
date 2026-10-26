// One-use local named pipe -> SSH stdin. No credential files or command arguments.
import net from 'node:net';
import {spawn} from 'node:child_process';
const pipe='\\\\.\\pipe\\codex-tb2-three50-20261017';
const remote='/mnt/sdb/home/lizh639/tb2-three-arm50-20261017';
const server=net.createServer(socket=>{
  server.close();let body='';
  socket.setEncoding('utf8');socket.on('data',chunk=>{body+=chunk;if(body.length>8192)socket.destroy();});
  socket.on('end',()=>{
    const bundle=JSON.parse(body);body='';
    if(typeof bundle.key!=='string'||bundle.key.length<20)throw new Error('No key received');
    const child=spawn('C:/Windows/System32/OpenSSH/ssh.exe',['-o','BatchMode=yes','-o','ConnectTimeout=12','-o','StrictHostKeyChecking=yes','-i','C:/Users/54177/.ssh/cubestudio_notebook','lizh639@172.16.108.236',`${remote}/venv/bin/python ${remote}/campaign.py --launch`],{windowsHide:true,stdio:['pipe','pipe','pipe']});
    let out='',err='';child.stdout.on('data',d=>out+=d);child.stderr.on('data',d=>err+=d);
    child.stdin.end(JSON.stringify({key:bundle.key})+'\n');bundle.key='';
    child.on('close',code=>{clearTimeout(timer);console.log(JSON.stringify({exit_code:code,output:out,stderr:err}));process.exitCode=code??1;});
  });
});
const timer=setTimeout(()=>{server.close();console.log('Key handoff expired');process.exitCode=1;},180000);
server.listen(pipe,()=>console.log('WAITING_FOR_PRIVATE_KEY_PIPE'));
