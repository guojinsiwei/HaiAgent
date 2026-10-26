"""Interactive, masked one-time SSH public-key enrollment. No password persistence."""
import msvcrt
from pathlib import Path
import re
import sys
import paramiko

HOST = '172.16.156.27'
USER = 'lizh639'


def masked_password():
    print('服务器密码（每个字符显示 *，支持退格，回车提交）：', end='', flush=True)
    chars = []
    while True:
        char = msvcrt.getwch()
        if char in ('\r', '\n'):
            print()
            return ''.join(chars)
        if char == '\x03':
            raise KeyboardInterrupt
        if char in ('\x00', '\xe0'):
            msvcrt.getwch()
        elif char == '\b':
            if chars:
                chars.pop()
                print('\b \b', end='', flush=True)
        elif char.isprintable():
            chars.append(char)
            print('*', end='', flush=True)


def main():
    key_dir = Path.home() / '.ssh'
    public_key = (key_dir / 'cubestudio_notebook.pub').read_text().strip()
    if not re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/=]+(?: [^\r\n]*)?', public_key):
        raise ValueError('Unexpected public key format')
    client = paramiko.SSHClient()
    client.load_host_keys(str(key_dir / 'known_hosts'))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    print(f'连接 {USER}@{HOST}，只登记现有公钥，不启动实验。')
    password = masked_password()
    try:
        client.connect(HOST, username=USER, password=password, allow_agent=False,
                       look_for_keys=False, timeout=12, auth_timeout=25, banner_timeout=12)
        password = None
        command = ('read -r key; test -n "$key" || exit 2; umask 077; '
                   'mkdir -p "$HOME/.ssh"; touch "$HOME/.ssh/authorized_keys"; '
                   'if ! grep -qxF "$key" "$HOME/.ssh/authorized_keys"; then '
                   'printf "\\n%s\\n" "$key" >> "$HOME/.ssh/authorized_keys"; fi; '
                   'chmod 700 "$HOME/.ssh"; chmod 600 "$HOME/.ssh/authorized_keys"')
        stdin, stdout, stderr = client.exec_command(command, timeout=20)
        stdin.write(public_key + '\n')
        stdin.flush()
        stdin.channel.shutdown_write()
        if stdout.channel.recv_exit_status() != 0:
            raise RuntimeError('Public-key enrollment failed')
        print('登录成功，公钥已登记。可以关闭此窗口，回到聊天回复“已连接”。')
    finally:
        password = None
        client.close()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n已取消。')
    except Exception as exc:
        print('连接未完成：' + type(exc).__name__ + '。密码未写入文件，请回到聊天反馈错误类型。')
        sys.exit(1)
