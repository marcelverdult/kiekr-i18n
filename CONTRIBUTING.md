# Contributing translations

Thanks for helping translate KiekR. This document explains the
file format, what to leave alone, and how to test your changes.

A German version is at [CONTRIBUTING.de.md](CONTRIBUTING.de.md).

## Quick reference

```
locales/
  en.json   ← source of truth — DO NOT EDIT (managed by KiekR team)
  de.json   ← managed by KiekR team — DO NOT EDIT
  es.json   ← edit this for Spanish
  fr.json   ← edit this for French
  nl.json   ← edit this for Dutch
  <code>.json ← create one for a new language
```

## File format

Every locale file is a flat JSON object. Each key is a stable
identifier; do **not** rename keys.

A value can be one of three shapes:

### 1. Plain string

```json
"login_title": "Anmelden"
```

The translation is human-reviewed and ready to ship.

### 2. Object with metadata

```json
"login_title": {
  "value": "Anmelden",
  "_human": true
}
```

Same as a plain string, plus a marker recording who or what produced
the value:

| Field        | Meaning                                                    |
|--------------|------------------------------------------------------------|
| `_human`     | A human translator reviewed and approved this value        |
| `_ai`        | Seeded by DeepL or another machine translator              |
| `_seeded`    | ISO-8601 date the AI seed was written                      |

When you edit an AI-seeded value, flip `_ai` to `_human` (or replace
the whole object with a plain string).

### 3. `null`

```json
"login_title": null
```

Not yet translated. The app falls back to English. Leave existing
`null` values in place if you cannot translate them; do **not**
delete the key.

## Placeholders

Some strings contain runtime placeholders. They are written in
positional Android style:

```
"chat_clear_confirm_body": "%1$d messages will be deleted. This cannot be undone."
```

- `%1$d`, `%2$d`, … — integers
- `%1$s`, `%2$s`, … — strings (names, regions, etc.)

**You must keep the same placeholders in the same order.** Re-ordering
across languages is supported by the `%1$`, `%2$` numbering — you may
move them within the sentence.

Examples:

```
en:  "Sent %1$d messages to %2$s"
de:  "%1$d Nachrichten an %2$s gesendet"
```

Both are valid because the numbered placeholders preserve binding.

## Plurals

A few keys use ICU plural format:

```json
"nodes_found": {
  "plural": {
    "one":   "# node found",
    "other": "# nodes found"
  }
}
```

`#` is replaced with the count at runtime. Use the categories your
language needs. For all currently shipped locales, `one` + `other`
is sufficient. If your language needs `few`, `many`, etc., add them.
`other` is mandatory.

## What you cannot change

CI will reject your PR if you:

- Rename a key
- Add a key that does not exist in `en.json`
- Change a value in `en.json` or `de.json` (unless you are on the
  KiekR team)
- Change `_meta.*` fields
- Translate an explicitly non-translatable string (e.g. the app name)
- Use a placeholder that is not in the English source
- Leave a plural without an `other` category

## Glossary

Tech terms have canonical translations to keep the app consistent.
See [glossary/](glossary/) for per-language lists. If a term you need
is not yet in the glossary and you think it should be standardized,
open an issue.

## Testing locally

You don't need the app source to translate. JSON syntax is verified
by CI. If you want to verify locally:

```sh
python3 tools/validate.py
```

(Requires Python 3.12+ and `jsonschema`.)

## Pull request etiquette

- One language per PR.
- Group related keys together in your edit (e.g. all keys in a
  given screen).
- If you change many keys, say why in the PR body.
- Be patient — reviews are best-effort.

## Code of conduct

Be kind. Translation is judgement, and reasonable translators
disagree. Defer to native speakers; argue about the term, not the
person.
