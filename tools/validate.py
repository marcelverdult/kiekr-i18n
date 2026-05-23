#!/usr/bin/env python3
"""Validate every locale file in locales/ against the schema and the
cross-locale invariants documented in CONTRIBUTING.md.

Exit code 0 = clean, 1 = one or more violations. Errors are printed
in GitHub-Actions error syntax so they show up inline on PRs.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("::error::jsonschema not installed; run `pip install jsonschema`")
    sys.exit(1)


ROOT = Path(__file__).resolve().parent.parent
LOCALES_DIR = ROOT / "locales"
SCHEMA_FILE = ROOT / "schema" / "i18n.schema.json"

PLACEHOLDER_RE = re.compile(r"%(\d+)\$[sd]|%[sd@]|%(?:\.\d+)?[fld]+")
META_KEYS = {"_meta"}


def err(file: Path, msg: str) -> None:
    print(f"::error file={file}::{msg}")


def warn(file: Path, msg: str) -> None:
    print(f"::warning file={file}::{msg}")


def load_schema() -> dict:
    return json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


def load_locale(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def value_string(entry) -> str | None:
    """Extract the user-visible string from an entry (or None)."""
    if entry is None:
        return None
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        if "value" in entry:
            return entry["value"]
        if "plural" in entry:
            return entry["plural"].get("other")
    return None


def placeholders(s: str | None) -> set[str]:
    if not s:
        return set()
    return set(m.group(0) for m in PLACEHOLDER_RE.finditer(s))


def main() -> int:
    schema = load_schema()
    errors = 0

    files = sorted(LOCALES_DIR.glob("*.json"))
    if not files:
        print("::error::no locale files found in locales/")
        return 1

    en_path = LOCALES_DIR / "en.json"
    if not en_path.exists():
        print("::error::locales/en.json missing — this is the source of truth")
        return 1

    en = load_locale(en_path)
    en_keys = {k for k in en if k not in META_KEYS}

    for path in files:
        try:
            data = load_locale(path)
        except json.JSONDecodeError as e:
            err(path, f"invalid JSON: {e}")
            errors += 1
            continue

        try:
            jsonschema.validate(data, schema)
        except jsonschema.ValidationError as e:
            err(path, f"schema violation: {e.message}")
            errors += 1
            continue

        lang_code = data.get("_meta", {}).get("language")
        if not lang_code or lang_code != path.stem:
            err(path, f"_meta.language ({lang_code!r}) does not match filename")
            errors += 1

        # extra keys not in en.json
        for k in data:
            if k in META_KEYS:
                continue
            if k not in en_keys:
                err(path, f"key {k!r} is not present in en.json")
                errors += 1

        # placeholder parity vs en.json (skip en itself)
        if path.name != "en.json":
            for k in en_keys:
                if k not in data:
                    continue
                en_val = value_string(en[k])
                tr_val = value_string(data[k])
                if tr_val is None:
                    continue
                en_ph = placeholders(en_val)
                tr_ph = placeholders(tr_val)
                if en_ph != tr_ph:
                    err(
                        path,
                        f"key {k!r}: placeholders {sorted(tr_ph)} "
                        f"differ from en {sorted(en_ph)}",
                    )
                    errors += 1

        # plural sanity
        for k, v in data.items():
            if k in META_KEYS:
                continue
            if isinstance(v, dict) and "plural" in v:
                cats = v["plural"]
                if "other" not in cats:
                    err(path, f"key {k!r}: plural missing 'other' category")
                    errors += 1

    if errors:
        print(f"\n::error::{errors} validation error(s)")
        return 1

    print("OK — all locale files valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
