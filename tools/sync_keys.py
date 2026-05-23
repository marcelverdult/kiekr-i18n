#!/usr/bin/env python3
"""Align every non-source locale to the key set of en.json.

- Missing keys are inserted as JSON null (signals "needs translation").
- Keys not in en.json are removed.
- _meta is preserved.
- en.json and de.json are never modified (we own those).
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES_DIR = ROOT / "locales"
SOURCE_FILE = LOCALES_DIR / "en.json"
OWNED = {"en.json", "de.json"}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    en = load(SOURCE_FILE)
    canonical_keys = [k for k in en if k != "_meta"]
    canonical_set = set(canonical_keys)

    changed = []
    for path in sorted(LOCALES_DIR.glob("*.json")):
        if path.name in OWNED:
            continue
        data = load(path)
        meta = data.get("_meta", {"language": path.stem})

        out = {"_meta": meta}
        # preserve order from en.json
        for k in canonical_keys:
            out[k] = data.get(k, None)

        # report dropped keys
        dropped = [k for k in data if k not in canonical_set and k != "_meta"]
        for k in dropped:
            print(f"{path.name}: drop {k!r} (not in en.json)")

        if json.dumps(out, sort_keys=True) != json.dumps(data, sort_keys=True):
            meta["updated"] = date.today().isoformat()
            dump(path, out)
            changed.append(path.name)

    if changed:
        print(f"updated: {', '.join(changed)}")
    else:
        print("no key drift")
    return 0


if __name__ == "__main__":
    sys.exit(main())
