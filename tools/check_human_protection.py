#!/usr/bin/env python3
"""Backstop: a bot PR must never overwrite an existing translated value.

Runs on bot-authored PRs (branch `bot/*`) in validate.yml. Compares each
locale file against its base-branch version and fails if any key that
already had a non-null value has been *changed* to a different value.

The DeepL automation (sync_keys.py + seed.py) is only ever allowed to:
  - fill a `null` entry (null -> value), and
  - add or drop keys to track en.json.

It is NEVER allowed to mutate an existing populated value — that is how
human (`_human`) and already-reviewed text would get clobbered. seed.py
already refuses to do this by construction; this check is the enforcement
layer so a future regression cannot merge.

Removals are allowed (sync_keys.py legitimately drops keys no longer in
en.json). Only value *changes* on populated keys are violations.

Base version is read via `git show $BASE_REF:locales/<file>`. If BASE_REF
is unset (local run / non-PR), the check is a no-op and exits 0.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES_DIR = ROOT / "locales"
META_KEYS = {"_meta"}


def err(file: str, msg: str) -> None:
    print(f"::error file={file}::{msg}")


def value_string(entry) -> str | None:
    """User-visible string of an entry, or None if it has no real value."""
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


def base_version(base_ref: str, rel_path: str) -> dict | None:
    """Load locales/<file> as it exists at base_ref, or None if absent."""
    try:
        out = subprocess.run(
            ["git", "show", f"{base_ref}:{rel_path}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return None  # file did not exist on base (new locale)
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        return None


def main() -> int:
    base_ref = os.environ.get("BASE_REF")
    if not base_ref:
        print("BASE_REF not set — skipping human-text protection check")
        return 0

    violations = 0
    for path in sorted(LOCALES_DIR.glob("*.json")):
        rel = f"locales/{path.name}"
        base = base_version(base_ref, rel)
        if base is None:
            continue
        head = json.loads(path.read_text(encoding="utf-8"))

        for k, base_entry in base.items():
            if k in META_KEYS:
                continue
            base_val = value_string(base_entry)
            if base_val is None:
                continue  # was null/empty — filling it is allowed
            if k not in head:
                continue  # removed (en.json drop) — allowed
            head_val = value_string(head[k])
            if head_val is None:
                # populated -> null is also a clobber of existing text
                err(rel, f"key {k!r}: existing value was blanked to null")
                violations += 1
            elif head_val != base_val:
                err(
                    rel,
                    f"key {k!r}: bot PR changed an existing value "
                    f"({base_val!r} -> {head_val!r}); human/reviewed text "
                    f"must never be overwritten",
                )
                violations += 1

    if violations:
        print(f"\n::error::{violations} human-text protection violation(s)")
        return 1

    print("OK — no existing values overwritten")
    return 0


if __name__ == "__main__":
    sys.exit(main())
