#!/usr/bin/env python3
"""Re-render the Status table in README.md from the current locale files.

The table lives between `<!-- status:begin -->` and `<!-- status:end -->`
markers. Run on every push that touches locales/.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES_DIR = ROOT / "locales"
README = ROOT / "README.md"

# Display order + native names + manager
ROWS = [
    ("en",    "English",            "kiekr-team"),
    ("de",    "Deutsch",            "kiekr-team"),
    ("es",    "Español",            "community"),
    ("fr",    "Français",           "community"),
    ("nl",    "Nederlands",         "community"),
    ("it",    "Italiano",           "community"),
    ("pt-BR", "Português (Brasil)", "community"),
    ("pl",    "Polski",             "community"),
    ("bg",    "Български",          "community"),
    ("cs",    "Čeština",            "community"),
    ("da",    "Dansk",              "community"),
    ("el",    "Ελληνικά",           "community"),
    ("et",    "Eesti",              "community"),
    ("fi",    "Suomi",              "community"),
    ("ga",    "Gaeilge",            "community"),
    ("hr",    "Hrvatski",           "community"),
    ("hu",    "Magyar",             "community"),
    ("lt",    "Lietuvių",           "community"),
    ("lv",    "Latviešu",           "community"),
    ("mt",    "Malti",              "community"),
    ("nb",    "Norsk bokmål",       "community"),
    ("pt-PT", "Português (Portugal)", "community"),
    ("ro",    "Română",             "community"),
    ("ru",    "Русский",            "community"),
    ("sk",    "Slovenčina",         "community"),
    ("sl",    "Slovenščina",        "community"),
    ("sv",    "Svenska",            "community"),
    ("uk",    "Українська",         "community"),
]

BEGIN = "<!-- status:begin -->"
END = "<!-- status:end -->"


def count(entry, en_total) -> tuple[int, int, int]:
    """Return (translated, human, ai) counts for one locale dict."""
    translated = human = ai = 0
    for k, v in entry.items():
        if k == "_meta":
            continue
        if v is None:
            continue
        if isinstance(v, str):
            translated += 1
            human += 1
        elif isinstance(v, dict):
            has_value = "value" in v or "plural" in v
            if has_value:
                translated += 1
                if v.get("_ai") and not v.get("_human"):
                    ai += 1
                else:
                    human += 1
    return translated, human, ai


def main() -> int:
    en = json.loads((LOCALES_DIR / "en.json").read_text(encoding="utf-8"))
    en_total = sum(1 for k in en if k != "_meta")

    lines = [
        BEGIN,
        "",
        "| Language       | Code | Completion | Human | AI seeded | Manager    |",
        "|----------------|------|-----------:|------:|----------:|------------|",
    ]
    for code, name, mgr in ROWS:
        path = LOCALES_DIR / f"{code}.json"
        if not path.exists():
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        translated, human, ai = count(d, en_total)
        pct = translated / en_total * 100 if en_total else 0
        pct_str = f"{pct:.1f}%" if pct < 100 else "100%"
        lines.append(
            f"| {name:<14} | `{code}` | {pct_str:>10} | {human:>5} | {ai:>9} | {mgr:<10} |"
        )
    lines.append("")
    lines.append(END)

    new_block = "\n".join(lines)
    readme = README.read_text(encoding="utf-8")
    if BEGIN not in readme or END not in readme:
        print(
            f"ERROR: README is missing {BEGIN!r} or {END!r} markers — "
            "edit README.md to insert them around the status table.",
            file=sys.stderr,
        )
        return 1

    pattern = re.compile(
        re.escape(BEGIN) + r".*?" + re.escape(END), re.DOTALL
    )
    updated = pattern.sub(new_block, readme, count=1)

    if updated == readme:
        print("README unchanged")
        return 0
    README.write_text(updated, encoding="utf-8")
    print("README updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
