$ErrorActionPreference = 'Continue'
$root = '/mnt/lizh639/terminal-paired30-20260922-01'
$python = "$root/runtime/bin/python"
$helper = "$root/control/remote_terminal_pair.py"
& ssh -o BatchMode=yes -o ConnectTimeout=15 cubestudio_container `
  "$python $helper status --method bestfgs"
& ssh -o BatchMode=yes -o ConnectTimeout=15 cubestudio_container2 `
  "$python $helper status --method raw"
