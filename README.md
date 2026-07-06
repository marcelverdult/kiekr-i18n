# KiekR Translations

Community-managed translations for the [KiekR](https://kiekr.app) app
(iOS + Android), a mesh-radio companion for MeshCore.

## Status

<!-- status:begin -->

| Language       | Code | Completion | Human | AI seeded | Manager    |
|----------------|------|-----------:|------:|----------:|------------|
| English        | `en` |       100% |  1494 |         0 | kiekr-team |
| Deutsch        | `de` |       100% |  1494 |         0 | kiekr-team |
| Español        | `es` |       100% |  1279 |       215 | community  |
| Français       | `fr` |       100% |  1279 |       215 | community  |
| Nederlands     | `nl` |       100% |  1279 |       215 | community  |
| Italiano       | `it` |       100% |  1365 |       129 | community  |
| Português (Brasil) | `pt-BR` |       100% |     1 |      1493 | community  |
| Polski         | `pl` |       100% |    11 |      1483 | community  |
| Български      | `bg` |       100% |     0 |      1494 | community  |
| Čeština        | `cs` |       100% |     0 |      1494 | community  |
| Dansk          | `da` |       100% |     0 |      1494 | community  |
| Ελληνικά       | `el` |       100% |     0 |      1494 | community  |
| Eesti          | `et` |       100% |     0 |      1494 | community  |
| Suomi          | `fi` |       100% |     0 |      1494 | community  |
| Gaeilge        | `ga` |       100% |     0 |      1494 | community  |
| Hrvatski       | `hr` |       100% |     0 |      1494 | community  |
| Magyar         | `hu` |       100% |     0 |      1494 | community  |
| Lietuvių       | `lt` |       100% |     0 |      1494 | community  |
| Latviešu       | `lv` |       100% |     0 |      1494 | community  |
| Malti          | `mt` |       100% |     0 |      1494 | community  |
| Norsk bokmål   | `nb` |       100% |     0 |      1494 | community  |
| Português (Portugal) | `pt-PT` |       100% |     0 |      1494 | community  |
| Română         | `ro` |       100% |     0 |      1494 | community  |
| Русский        | `ru` |       100% |     0 |      1494 | community  |
| Slovenčina     | `sk` |       100% |     0 |      1494 | community  |
| Slovenščina    | `sl` |       100% |     0 |      1494 | community  |
| Svenska        | `sv` |       100% |     0 |      1494 | community  |
| Українська     | `uk` |       100% |     0 |      1494 | community  |

<!-- status:end -->

"AI seeded" rows are flagged `_ai: true` in the locale JSON — they
were machine-translated by DeepL and await human review. Flip to
`_human: true` (or replace the entry with a plain string) once a
native speaker has approved.

The table is regenerated automatically by
[`tools/update_readme.py`](tools/update_readme.py) on every push that
touches `locales/` — do not edit it by hand.

## What this repo is

Flat JSON files, one per language. Each key is a stable identifier;
its value is the translated string. The app reads from these files at
release build time and ships them inside the binary.

```
locales/
  en.json   ← source of truth (English; managed by us)
  de.json   ← German (managed by us; we are native speakers)
  es.json   ← Spanish (community)
  fr.json   ← French (community)
  nl.json   ← Dutch (community)
```

## Improving an existing language

1. Fork this repo.
2. Edit `locales/<lang>.json`.
3. Replace `null` (or `"_ai": true` AI-seeded values) with a human
   translation.
4. Open a PR. CI checks placeholder parity, plural categories, and
   JSON schema.
5. Maintainers review and merge.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide.

## Adding a new language

1. Open an issue first with the
   [new-language template](.github/ISSUE_TEMPLATE/new_language.md) so
   we can confirm the locale code and add it to the app build.
2. Once approved, fork and create `locales/<code>.json` with whatever
   subset of keys you can translate. Missing keys fall back to English
   in the app — partial coverage is fine.

## How translations reach the app

- New keys usually arrive **already translated**: the maintainer
  session that adds a key also fills all community locales via
  [`tools/fill_from_json.py`](tools/fill_from_json.py) (same guards
  as the seeder: only-null targets, placeholder parity, `_ai: true`).
- Every push to `main` that touches `locales/` runs one pipeline
  ([`i18n.yml`](.github/workflows/i18n.yml)): missing keys are
  materialized, DeepL fills whatever is still null (`_ai: true`),
  everything is validated, and only then is a single dated GitHub
  Release cut with a tarball of `locales/` and a `SHA256SUM`. The
  latest release is therefore always the complete, post-seed state.
- A nightly run retries anything left untranslated.
- The KiekR app build scripts fetch the latest release tarball at
  release-build time and embed it.
- We do not ship community translations to end users until they
  appear in a tagged release.

## What you cannot change here

- **`locales/en.json`** — owned by the KiekR team (the source of
  truth for every other locale).
- **`locales/de.json`** — owned by the KiekR team (we are native
  German speakers).
- **`_meta.*` fields in any file** — bookkeeping data.
- **App name "KiekR"** — non-translatable brand. Same for
  protocol tokens like `MeshCore`, `#zephyr`, region names.

CI rejects PRs that violate these.

## License

Translations in this repository are licensed under
[CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Contributors retain copyright; by submitting a pull request you agree
to license your contribution under CC-BY 4.0. Attribution is
satisfied by a credit in the KiekR app and a link back to this repo.

See [LICENSE](LICENSE) for the full text.

## Contact

- Issues: <https://github.com/marcelverdult/kiekr-i18n/issues>
- App: <https://kiekr.app>
