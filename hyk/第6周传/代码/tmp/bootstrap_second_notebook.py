"""Install the user's existing public key on the explicitly named second notebook.

Reads only that notebook's platform-issued login instructions. Never logs credentials.
The host key was previously saved by OpenSSH for this exact platform-advertised port.
"""
from pathlib import Path
import re
import subprocess
import sys
import socket
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'.codex-second-notebook-tools'))
import paramiko

profile=Path('C:/Users/54177')
info=subprocess.run(['ssh','-o','BatchMode=yes','cubestudio_container',
                     'cat /mnt/lizh639/ssh连接'],capture_output=True,text=True,encoding='utf-8',check=True).stdout
match=re.search(r'登录密码:\s*(\S+)',info)
if not match or not re.search(r'Port\s+31121\b',info):
    raise SystemExit('Platform SSH instructions do not match the expected second notebook')
public=(profile/'.ssh/cubestudio_notebook.pub').read_text(encoding='utf-8').strip()
parts=public.split()
if len(parts)<2 or not parts[0].startswith('ssh-'):
    raise SystemExit('Invalid existing public key')

client=paramiko.SSHClient()
client.load_host_keys(str(profile/'.ssh/known_hosts'))
client.set_missing_host_key_policy(paramiko.RejectPolicy())
with socket.socket() as probe:
    probe.bind(('127.0.0.1',0))
    local_port=probe.getsockname()[1]
tunnel=subprocess.Popen(['ssh','-N','-o','BatchMode=yes','-o','ExitOnForwardFailure=yes',
                         '-o','ConnectTimeout=15','-L',f'127.0.0.1:{local_port}:172.16.108.241:31121','jumpServer'],
                         stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
                         creationflags=subprocess.CREATE_NO_WINDOW)
proxy=None
try:
    for attempt in range(40):
        if tunnel.poll() is not None:
            raise SystemExit('SSH bootstrap tunnel exited before connection')
        try:
            proxy=socket.create_connection(('127.0.0.1',local_port),timeout=1)
            break
        except OSError:
            time.sleep(.25)
    if proxy is None:
        raise SystemExit('SSH bootstrap tunnel not ready')
    client.connect('172.16.108.241',port=31121,username='root',password=match.group(1),
                   sock=proxy,allow_agent=False,look_for_keys=False,timeout=20,auth_timeout=20,banner_timeout=20)
    _,out,err=client.exec_command('hostname',timeout=20)
    hostname=out.read().decode().strip()
    if hostname!='lizh639-8e64':
        raise SystemExit('Target hostname mismatch; no authorized_keys change made')
    with client.open_sftp() as sftp:
        directory='/root/.ssh'
        try:
            sftp.stat(directory)
        except FileNotFoundError:
            sftp.mkdir(directory,mode=0o700)
        path=directory+'/authorized_keys'
        existed=True
        try:
            with sftp.open(path,'rb') as stream:
                original=stream.read()
        except FileNotFoundError:
            existed=False
            original=b''
        if not any(len(line.split())>=2 and line.split()[1]==parts[1].encode() for line in original.splitlines()):
            token=uuid.uuid4().hex[:12]
            if existed:
                backup=path+'.before-second-notebook-'+token
                with sftp.open(backup,'wx') as stream:
                    stream.write(original)
                sftp.chmod(backup,0o600)
            temporary=path+'.'+token+'.tmp'
            with sftp.open(temporary,'wx') as stream:
                stream.write(original.rstrip(b'\n')+b'\n'+public.encode()+b'\n')
            sftp.chmod(temporary,0o600)
            sftp.posix_rename(temporary,path)
        sftp.chmod(directory,0o700)
        sftp.chmod(path,0o600)
    print('Verified second notebook:',hostname)
    print('Existing user public key authorized; other authorized keys preserved')
finally:
    client.close()
    if proxy is not None:
        proxy.close()
    if tunnel.poll() is None:
        tunnel.terminate()
    tunnel.wait(timeout=10)
