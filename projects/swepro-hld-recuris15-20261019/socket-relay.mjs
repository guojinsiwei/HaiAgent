import net from 'node:net';
export async function relay() {
  const servers=[];
  for(const [port,socket] of [[19051,'proxy.sock'],[19052,'budget.sock']]) {
    const server=net.createServer(client=>{
      const peer=net.createConnection('/relay/'+socket);
      client.on('error',()=>peer.destroy());peer.on('error',()=>client.destroy());
      client.pipe(peer);peer.pipe(client);
    });
    await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(port,'127.0.0.1',resolve);});servers.push(server);
  }
  return ()=>servers.forEach(s=>s.close());
}
