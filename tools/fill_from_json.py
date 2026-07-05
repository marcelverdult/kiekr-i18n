#!/usr/bin/env python3
"""Fill null entries in community locales from a prepared translations JSON.

Session-flow companion to seed.py: when a maintainer session translates
new keys itself (instead of waiting for DeepL), it prepares ONE file

    {
      "fr": {
        "some_key": "Texte traduit",
        "some_plural_key": {"plural": {"one": "...", "other": "..."}}
      },
      "ru": { ... }
    }

and runs:  python tools/fill_from_json.py translations.json

Same invariants as seed.py, enforced atomically (validate everything
first, write only if ZERO violations):
  - only entries that are currently null are ever written
  - the key must exist in en.json; en.json / de.json are never touched
  - placeholder parity per string against en.json (validate.py pattern);
    for plurals, every category is checked against EN's "other"
  - plural objects must include the "other" category (schema rule)
  - written as {value, _ai: true, _seeded: <today>} (or plural variant)

Options:
  --require-complete   additionally fail unless the input covers EVERY
                       null in every community locale ("no stragglers"
                       gate before a publish)

Exit 0 = everything applied (or nothing to do). Exit 1 = at least one
guard tripped; NOTHING was written.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES_DIR = ROOT / "locales"
SOURCE_FILE = LOCALES_DIR / "en.json"
OWNED = {"en", "de"}
TODAY = date.today().isoformat()

# Same pattern validate.py enforces.
PLACEHOLDER_RE = re.compile(r"%\d+\$[sd]|%[sd@]|%(?:\.\d+)?[fld]+")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def en_source_text(entry) -> str | None:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        if "value" in entry:
            return entry["value"]
        if "plural" in entry:
            return entry["plural"].get("other")
    return None


def placeholders_ok(source: str, translated: str) -> bool:
    return sorted(PLACEHOLDER_RE.findall(source)) == sorted(
        PLACEHOLDER_RE.findall(translated)
    )


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    require_complete = "--require-complete" in sys.argv
    if len(args) != 1:
        print(__doc__.strip(), file=sys.stderr)
        return 2

    translations = load(Path(args[0]))
    en = load(SOURCE_FILE)

    errors: list[str] = []
    plan: list[tuple[Path, dict, dict]] = []  # (path, data, {key: entry})
    filled_per_lang: dict[str, int] = {}

    for lang, entries in translations.items():
        if lang in OWNED:
            errors.append(f"{lang}: en/de are owned — refusing to touch them")
            continue
        path = LOCALES_DIR / f"{lang}.json"
        if not path.exists():
            errors.append(f"{lang}: locales/{lang}.json does not exist")
            continue
        data = load(path)
        staged: dict[str, dict] = {}

        for key, tr in entries.items():
            if key not in en or key == "_meta":
                errors.append(f"{lang}/{key}: key not in en.json")
                continue
            if data.get(key) is not None:
                errors.append(
                    f"{lang}/{key}: target is not null "
                    f"(current: {data.get(key)!r}) — only null is ever filled"
                )
                continue
            src = en_source_text(en[key]) or ""

            if isinstance(tr, dict) and "plural" in tr:
                cats = tr["plural"]
                if "other" not in cats:
                    errors.append(f"{lang}/{key}: plural missing 'other'")
                    continue
                bad = [c for c, t in cats.items()
                       if not placeholders_ok(src, t)]
                if bad:
                    errors.append(
                        f"{lang}/{key}: placeholder mismatch in plural "
                        f"categories {bad} vs en 'other' {src!r}"
                    )
                    continue
                staged[key] = {"plural": cats, "_ai": True, "_seeded": TODAY}
            elif isinstance(tr, str):
                if not placeholders_ok(src, tr):
                    errors.append(
                        f"{lang}/{key}: placeholder mismatch "
                        f"({PLACEHOLDER_RE.findall(src)} vs "
                        f"{PLACEHOLDER_RE.findall(tr)})"
                    )
                    continue
                staged[key] = {"value": tr, "_ai": True, "_seeded": TODAY}
            else:
                errors.append(f"{lang}/{key}: value must be a string or "
                              f"{{'plural': {{...}}}}, got {type(tr).__name__}")
        if staged:
            plan.append((path, data, staged))
            filled_per_lang[lang] = len(staged)

    if require_complete:
        covered = {(lang, k) for lang, m in translations.items() for k in m}
        for path in sorted(LOCALES_DIR.glob("*.json")):
            if path.stem in OWNED:
                continue
            data = load(path)
            for k, v in data.items():
                if k != "_meta" and v is None and (path.stem, k) not in covered:
                    errors.append(
                        f"--require-complete: {path.stem}/{k} is null but "
                        f"not covered by the input"
                    )

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print(f"\n{len(errors)} violation(s) — nothing was written.",
              file=sys.stderr)
        return 1

    # All guards green — apply atomically.
    total = 0
    for path, data, staged in plan:
        for key, entry in staged.items():
            data[key] = entry
        data.setdefault("_meta", {"language": path.stem})["updated"] = TODAY
        dump(path, data)
        total += len(staged)
        print(f"{path.stem}: filled {len(staged)}")
    print(f"total: {total} value(s) filled across {len(plan)} locale(s)")
    if total == 0:
        print("nothing to do")
    return 0


if __name__ == "__main__":
    sys.exit(main())
