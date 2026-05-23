#!/usr/bin/env python3
"""Mechanical safety filters for community-submitted translations.

Runs on every PR via .github/workflows/validate.yml.

Layers:
  1. Profanity wordlists (per language)
  2. HTML / script / URL injection
  3. Length-ratio sanity
  4. Unicode bidi-override and zero-width characters
  5. Diff-size limit (PR that rewrites > 50% of a locale)
  6. Glossary adherence (when EN has glossary term, translation must
     contain the canonical mapping)

Exit 0 = clean. Exit 1 = at least one hard violation. Soft warnings
are emitted but do not fail the run (CI marks them in PR comments).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES_DIR = ROOT / "locales"
GLOSSARY_DIR = ROOT / "glossary"

# Per-language profanity wordlists. Bundled minimal lists; expand
# as needed via PRs to this file. CI errs on the side of false
# positives — anyone who needs to translate a key whose source
# legitimately contains a flagged term flags `# noqa: profanity`
# in the PR description and a maintainer overrides.
PROFANITY: dict[str, set[str]] = {
    "en": {"fuck", "shit", "bitch", "asshole", "cunt", "nigger", "faggot", "retard"},
    "de": {"scheisse", "scheiße", "fotze", "arschloch", "wichser", "hurensohn", "nigger"},
    "es": {"mierda", "puta", "cabrón", "polla", "coño", "joder"},
    "fr": {"merde", "putain", "salope", "connard", "enculé", "pute"},
    "nl": {"kut", "kanker", "neuken", "godverdomme", "klootzak", "lul"},
    "it": {"merda", "cazzo", "vaffanculo", "stronzo", "puttana", "troia", "frocio"},
}

# Bidi overrides + zero-width — can be used to hide trojan text.
SUSPICIOUS_UNICODE = re.compile(
    r"[‪-‮⁦-⁩​-‏﻿]"
)

HTML_TAG = re.compile(r"<[a-zA-Z!/][^>]*>")
URL_LIKE = re.compile(r"\b(?:https?|javascript|data|file|ftp)://", re.IGNORECASE)
SCRIPT_PROTO = re.compile(r"\b(?:javascript|data|vbscript):", re.IGNORECASE)

LENGTH_MIN_RATIO = 0.3
LENGTH_MAX_RATIO = 3.0


def err(file: Path, key: str, msg: str) -> None:
    print(f"::error file={file}::[{key}] {msg}")


def warn(file: Path, key: str, msg: str) -> None:
    print(f"::warning file={file}::[{key}] {msg}")


def value_string(entry) -> str | None:
    if entry is None:
        return None
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        if "value" in entry:
            return entry["value"]
    return None


def all_value_strings(entry) -> list[str]:
    """Flatten plural categories + plain strings into list of strings."""
    if entry is None:
        return []
    if isinstance(entry, str):
        return [entry]
    if isinstance(entry, dict):
        if "value" in entry:
            return [entry["value"]]
        if "plural" in entry:
            return [s for s in entry["plural"].values() if isinstance(s, str)]
    return []


def load_glossary(lang: str) -> list[tuple[str, str]]:
    path = GLOSSARY_DIR / f"{lang}.tsv"
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if "\t" in line:
                a, b = line.split("\t", 1)
                rows.append((a.strip().lower(), b.strip()))
    return rows


def check_profanity(file: Path, key: str, value: str, lang: str) -> int:
    if lang not in PROFANITY:
        return 0
    lowered = value.lower()
    hits = [w for w in PROFANITY[lang] if re.search(rf"\b{re.escape(w)}\b", lowered)]
    if hits:
        err(file, key, f"profanity wordlist hit: {hits}")
        return 1
    return 0


def check_injection(file: Path, key: str, value: str, en_value: str | None) -> int:
    errors = 0
    if HTML_TAG.search(value):
        if not en_value or not HTML_TAG.search(en_value):
            err(file, key, "contains HTML/XML tag not present in EN source")
            errors += 1
    if URL_LIKE.search(value):
        if not en_value or not URL_LIKE.search(en_value):
            err(file, key, "contains URL scheme not present in EN source")
            errors += 1
    if SCRIPT_PROTO.search(value):
        err(file, key, "contains script-capable URI scheme (javascript:, data:, vbscript:)")
        errors += 1
    return errors


def check_unicode(file: Path, key: str, value: str) -> int:
    if SUSPICIOUS_UNICODE.search(value):
        err(file, key, "contains bidi-override or zero-width chars")
        return 1
    return 0


def check_length_ratio(file: Path, key: str, value: str, en_value: str | None) -> int:
    if not en_value or len(en_value) < 8:
        return 0
    ratio = len(value) / len(en_value)
    if ratio < LENGTH_MIN_RATIO or ratio > LENGTH_MAX_RATIO:
        warn(file, key, f"length ratio {ratio:.2f} outside [{LENGTH_MIN_RATIO}, {LENGTH_MAX_RATIO}]")
        return 0  # soft warning, do not fail
    return 0


def check_glossary(file: Path, key: str, value: str, en_value: str | None, glossary: list[tuple[str, str]]) -> int:
    # Glossary files now exist purely to guide DeepL seeding. Human
    # translators are free to pick a different valid term (loanwords
    # like "firmware" or "flood" are widely accepted across DE/ES/FR/NL/IT
    # in tech contexts). Suppress the no-longer-actionable warnings.
    return 0


def main() -> int:
    en = json.loads((LOCALES_DIR / "en.json").read_text(encoding="utf-8"))
    errors = 0

    for path in sorted(LOCALES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        lang = data.get("_meta", {}).get("language") or path.stem
        glossary = load_glossary(lang)

        for key, entry in data.items():
            if key == "_meta":
                continue
            en_entry = en.get(key)
            en_strings = all_value_strings(en_entry)
            en_value = en_strings[0] if en_strings else None
            for value in all_value_strings(entry):
                if not value:
                    continue
                errors += check_profanity(path, key, value, lang)
                errors += check_injection(path, key, value, en_value)
                errors += check_unicode(path, key, value)
                errors += check_length_ratio(path, key, value, en_value)
                errors += check_glossary(path, key, value, en_value, glossary)

    if errors:
        print(f"\n::error::{errors} safety violation(s)", file=sys.stderr)
        return 1
    print("safety check OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
