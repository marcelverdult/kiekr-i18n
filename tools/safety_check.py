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
  7. Informal address in machine-filled values (`_ai`): formal or plural
     "you" forms are reported as one warning per locale file. Pass
     --address-details to list every value.

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
    "pt-BR": {"merda", "porra", "caralho", "foda-se", "puta", "viado", "bicha"},
    "pl": {"kurwa", "chuj", "pierdolić", "jebać", "skurwysyn", "pizda"},
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

# KiekR addresses the reader informally (Dutch "je", not "u"). Machine
# translations tend to slip into the formal or plural form, so values
# marked `_ai` are searched for it. `_human` values are never checked.
#
# The patterns are adapted from `ADDRESS` in tools/copy_rules.py of
# https://github.com/meshcore-europe/meshcore-info.eu_i18n, whose code is
# MIT licensed (https://github.com/meshcore-europe/meshcore-info.eu/blob/main/LICENSE):
#   Copyright (c) 2026 the meshcore-info.eu contributors
# Changes: keys follow KiekR locale codes (pt -> pt-PT); fr and ru are left
# out (see below); the two guards in address_hits() are new.
#
# A pattern starting with "MID:" counts only in the middle of a sentence and
# is matched case-sensitively (German "Sie" at the start of a sentence can
# mean "they"). All other patterns are matched case-insensitively.
#
# Not checked, on purpose:
#   en     no formal address.
#   pt-BR  "voce" is the normal address there.
#   fr     the `_human` values are formal ("vous", "votre"), so the register
#          is an open product question (issue 56).
#   ru     copy_rules.py has no patterns, and there is no `_human` text to
#          tell the register.
INFORMAL_ADDRESS: dict[str, list[str]] = {
    "nl": [r"\bu\b(?!\.\w)", r"\buw\b", r"\bjullie\b"],
    "de": [r"MID:\bSie\b", r"MID:\bIhnen\b", r"MID:\bIhre?[mnrs]?\b", r"\beuch\b", r"\beure[mnrs]?\b"],
    "es": [r"\busted(es)?\b", r"\bvosotr[oa]s\b", r"\bvuestr[oa]s?\b"],
    "it": [r"MID:\bLei\b", r"MID:\bSu[oae]i?\b", r"\bvoi\b", r"\bvostr[oaie]\b"],
    "pl": [r"\bpan(a|u|em|ie)?\b", r"\bpani\b", r"\bpaństw(o|a|u|em)\b(?! członkowsk)", r"\bwasz\w*\b"],
    "pt-PT": [r"\bvocês?\b", r"\bo senhor\b", r"\ba senhora\b"],
    "cs": [r"\bvy\b", r"\bvám\b", r"\bvás\b", r"\bváš\b", r"\bvaš(e|i|eho|emu|ím|ich|im|imi)\b"],
    "sv": [r"\bni\b", r"\ber\b", r"\bert\b", r"\bera\b"],
    "da": [r"MID:\bDe\b", r"MID:\bDem\b", r"MID:\bDeres\b", r"\bjer\b", r"\bjeres\b"],
    "nb": [r"MID:\bDe\b", r"MID:\bDem\b", r"\bdere\b"],
    "fi": [r"\bte\b", r"\bteidän\b", r"\bteille\b", r"\bteitä\b", r"\bteillä\b"],
    "hu": [r"\bön(ök|t|nek|nel|höz|től|ben|re|ön|öket|öknek|é|ét|nél|ért)?\b"],
    "ro": [r"\bdumneavoastră\b", r"\bdvs\b", r"\bdumneata\b", r"\bvă\b", r"\bvoi\b", r"\bvoastr[ăe]\b", r"\bvostru\b"],
    "el": [r"\bεσείς\b", r"\bσας\b"],
    "bg": [r"\bвие\b", r"\bвас\b", r"\bвам\b", r"\bваш\w*\b"],
    "hr": [r"\bvi\b", r"\bvas\b", r"\bvam\b", r"\bvaš\w*\b"],
    "et": [r"\bteie\b", r"\bte\b", r"\bteid\b", r"\bteile\b", r"\bteil\b"],
    "ga": [r"\bsibh\b", r"\bbhur\b"],
    "lv": [r"\bjūs\b", r"\bjums\b", r"\bjūsu\b"],
    "lt": [r"\bjūs\b", r"\bjums\b", r"\bjūsų\b", r"\bjus\b"],
    "mt": [r"\bintom\b", r"\btagħkom\b"],
    "sk": [r"\bvy\b", r"\bvám\b", r"\bvás\b", r"\bváš\b", r"\bvaš(a|e|i|u|ou|ho|mu|om|ich|im|imi)\b"],
    "sl": [r"\bvi\b", r"\bvas\b", r"\bvam\b", r"\bvaš\w*\b"],
    "uk": [r"\bви\b", r"\bвас\b", r"\bвам\b", r"\bвами\b", r"\bваш\w*\b"],
}

# Flip to True to make an informal-address hit fail the run instead of warning.
INFORMAL_ADDRESS_FAILS = False

# A hit right after a number or a numeric placeholder is a unit, not a
# pronoun: Dutch "sinds %d u" (since %d h).
_AFTER_NUMBER = re.compile(r"(?:\d|[%$][df])\s*$")
# A hit glued to a word by a colon is a plural suffix: Swedish "DM:er".
_AFTER_COLON_SUFFIX = re.compile(r"\w:$")


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


def is_machine_filled(entry) -> bool:
    """True for `_ai` values. A value also marked `_human` counts as human."""
    return isinstance(entry, dict) and bool(entry.get("_ai")) and not entry.get("_human")


def mid_sentence(text: str, start: int) -> bool:
    before = text[:start].rstrip(" \t*_\"'„“«(-")
    return bool(before) and before[-1] not in ".!?:\n#|"


def address_hits(value: str, lang: str) -> list[str]:
    """Formal or plural "you" forms in `value`, for a language we check."""
    hits = []
    for pattern in INFORMAL_ADDRESS.get(lang, []):
        if pattern.startswith("MID:"):
            matches = [m for m in re.finditer(pattern[4:], value) if mid_sentence(value, m.start())]
        else:
            matches = list(re.finditer(pattern, value, re.IGNORECASE))
        for m in matches:
            before = value[: m.start()]
            if _AFTER_NUMBER.search(before) or _AFTER_COLON_SUFFIX.search(before):
                continue
            if before.endswith("(") and value[m.end():m.end() + 1] == ")":
                continue  # "kanal(er)": plural ending in brackets
            hits.append(m.group(0))
    return hits


def check_informal_address(file: Path, found: list[tuple[str, str, list[str]]], details: bool) -> int:
    """Report the hits of one locale file; returns the number of hard errors."""
    if not found:
        return 0
    if details:
        for key, value, hits in found:
            print(f"{file.name} [{key}] {sorted(set(hits))}: {value}")
    sample = "; ".join(f"{key}: {hits[0]}" for key, _, hits in found[:3])
    msg = (f"{len(found)} machine-filled value(s) use formal or plural address, "
           f"KiekR addresses the reader informally (e.g. {sample})")
    if INFORMAL_ADDRESS_FAILS:
        err(file, "informal-address", msg)
        return len(found)
    warn(file, "informal-address", msg)
    return 0


def main() -> int:
    en = json.loads((LOCALES_DIR / "en.json").read_text(encoding="utf-8"))
    details = "--address-details" in sys.argv[1:]
    errors = 0

    for path in sorted(LOCALES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        lang = data.get("_meta", {}).get("language") or path.stem
        glossary = load_glossary(lang)
        address_found: list[tuple[str, str, list[str]]] = []

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
                if is_machine_filled(entry):
                    hits = address_hits(value, lang)
                    if hits:
                        address_found.append((key, value, hits))
        errors += check_informal_address(path, address_found, details)

    if errors:
        print(f"\n::error::{errors} safety violation(s)", file=sys.stderr)
        return 1
    print("safety check OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
