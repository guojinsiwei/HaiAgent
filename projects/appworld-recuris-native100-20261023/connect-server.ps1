$ErrorActionPreference = 'Stop'
$taskPublicKey = (Get-Content -LiteralPath 'C:/Users/54177/.ssh/cubestudio_notebook.pub' -Raw).Trim()
if ($taskPublicKey -notmatch '^ssh-ed25519 [A-Za-z0-9+/=]+(?: .*)?$') { throw 'Unexpected public key format' }
Write-Host 'Connecting to lizh639@172.16.156.27. Enter the existing server password here.'
Write-Host 'This adds your existing public SSH key to this account for the authorized deployment.'
$taskRemoteCommand = 'read -r key; key=$(printf "%s" "$key" | tr -d "\r"); test -n "$key" || exit 2; umask 077; mkdir -p "$HOME/.ssh"; touch "$HOME/.ssh/authorized_keys"; if ! grep -qxF "$key" "$HOME/.ssh/authorized_keys"; then printf "\n%s\n" "$key" >> "$HOME/.ssh/authorized_keys"; fi; chmod 700 "$HOME/.ssh"; chmod 600 "$HOME/.ssh/authorized_keys"; printf "DEPLOYMENT_ACCESS_READY\n"; id; hostname'
$taskPublicKey | & 'C:/Windows/System32/OpenSSH/ssh.exe' -o StrictHostKeyChecking=accept-new -o PreferredAuthentications=password,keyboard-interactive -o PubkeyAuthentication=no lizh639@172.16.156.27 $taskRemoteCommand
if ($LASTEXITCODE -ne 0) { Write-Host 'Connection did not complete. No experiment has started.'; exit $LASTEXITCODE }
Write-Host 'Login succeeded. Codex can now continue using your existing private key locally.'
