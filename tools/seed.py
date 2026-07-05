#!/usr/bin/env python3
"""Seed missing translations in non-source locales using DeepL.

For each locale other than en/de:
  - find every key whose value is None (after sync_keys.py)
  - translate from en.json using DeepL with the per-language glossary
  - write back as { "value": "...", "_ai": true, "_seeded": "<today>" }

Requires:
  pip install deepl
  env: DEEPL_API_KEY

Plurals: each category translated independently.
Placeholders: DeepL preserves %1$s / %@ via XML-tag handling.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

try:
    import deepl
except ImportError:
    print("ERROR: deepl not installed; run `pip install deepl`", file=sys.stderr)
    sys.exit(1)


ROOT = Path(__file__).resolve().parent.parent
LOCALES_DIR = ROOT / "locales"
GLOSSARY_DIR = ROOT / "glossary"
SOURCE_FILE = LOCALES_DIR / "en.json"
OWNED = {"en.json", "de.json"}
TODAY = date.today().isoformat()

PLACEHOLDER_RE = re.compile(r"(%\d+\$[sd]|%[sd@]|%(?:\.\d+)?[fld]+|#)")

# Same pattern validate.py enforces — used to self-check every translation
# before it is written, so one mangled DeepL result can no longer turn the
# whole run red downstream.
VALIDATE_PLACEHOLDER_RE = re.compile(r"%\d+\$[sd]|%[sd@]|%(?:\.\d+)?[fld]+")


def placeholders_ok(source: str, translated: str) -> bool:
    """True when the translation carries exactly the placeholders of the
    source (as a multiset — order may legitimately differ across languages).
    """
    return sorted(VALIDATE_PLACEHOLDER_RE.findall(source)) == sorted(
        VALIDATE_PLACEHOLDER_RE.findall(translated)
    )


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def protect(text: str) -> tuple[str, list[str]]:
    """Wrap placeholders in <x>…</x> + XML-escape literal `<`, `>`, `&`
    so DeepL's xml tag_handling doesn't mis-parse the source.
    """
    parts: list[str] = []

    def sub(m):
        parts.append(m.group(0))
        return f"\x00PH{len(parts) - 1}\x00"

    # 1. swap placeholders out for a non-XML sentinel
    tmp = PLACEHOLDER_RE.sub(sub, text)
    # 2. escape any remaining XML-special chars in the literal content
    tmp = tmp.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # 3. restore placeholders as <x> tags
    def back(m):
        return f"<x>{m.group(1)}</x>"
    protected = re.sub(r"\x00PH(\d+)\x00", back, tmp)
    return protected, parts


def restore(text: str, parts: list[str]) -> str:
    # 1. expand <x>N</x> tags back to placeholder strings
    def sub(m):
        return parts[int(m.group(1))]
    out = re.sub(r"<x>(\d+)</x>", sub, text)
    # 2. unescape XML entities
    out = out.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return out


def load_glossary_tsv(path: Path) -> list[tuple[str, str]]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or "\t" not in line:
                continue
            en, tr = line.split("\t", 1)
            rows.append((en.strip(), tr.strip()))
    return rows


def translate_batch(
    translator: deepl.Translator,
    texts: list[str],
    target_lang: str,
    glossary_id: str | None,
) -> list[str]:
    """Translate a batch of strings in one DeepL API call. DeepL accepts
    up to 50 texts per request; this caller already chunks to that.
    """
    protected: list[str] = []
    parts_lists: list[list[str]] = []
    for t in texts:
        p, parts = protect(t)
        protected.append(p)
        parts_lists.append(parts)

    results = translator.translate_text(
        protected,
        source_lang="EN",
        target_lang=target_lang,
        glossary=glossary_id,
        tag_handling="xml",
        ignore_tags=["x"],
    )
    # deepl returns a TextResult list (1:1 with input) for list input,
    # or a single TextResult for a single string. Normalize.
    if not isinstance(results, list):
        results = [results]
    return [restore(r.text, parts_lists[i]) for i, r in enumerate(results)]


BATCH_SIZE = 50


def needs_translation(entry) -> bool:
    if entry is None:
        return True
    if isinstance(entry, dict):
        if "_ai" in entry and not entry.get("_human"):
            return False  # already AI-seeded; let humans take it
        if "value" in entry:
            return False
        if "plural" in entry:
            return False  # plurals seeded by separate pass
    return False


def en_value(entry) -> str | None:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return entry.get("value")
    return None


def _sanitize(msg: str, secret: str | None) -> str:
    """Strip the API key from any string before printing."""
    if not secret:
        return msg
    return msg.replace(secret, "***")


def main() -> int:
    api_key = os.environ.get("DEEPL_API_KEY")
    if not api_key:
        print("ERROR: DEEPL_API_KEY not set", file=sys.stderr)
        return 1
    # Best-effort defensive: never log the key, even on traceback.
    # GH Actions also auto-masks it via ::add-mask:: registered upstream.
    SECRET = api_key
    del api_key

    translator = deepl.Translator(SECRET)
    en = load(SOURCE_FILE)

    deepl_target_codes = {
        "es":    "ES",
        "fr":    "FR",
        "nl":    "NL",
        "it":    "IT",
        "pt-BR": "PT-BR",
        "pl":    "PL",
        # Remaining EU official languages
        "bg":    "BG",
        "hr":    "HR",
        "cs":    "CS",
        "da":    "DA",
        "et":    "ET",
        "fi":    "FI",
        "el":    "EL",
        "ga":    "GA",
        "hu":    "HU",
        "lv":    "LV",
        "lt":    "LT",
        "mt":    "MT",
        "ro":    "RO",
        "sk":    "SK",
        "sl":    "SL",
        "sv":    "SV",
        "pt-PT": "PT-PT",
        # European neighbours (non-EU)
        "nb":    "NB",
        "ru":    "RU",
        "uk":    "UK",
    }

    total_seeded = 0
    skipped_error = 0
    skipped_bad = 0

    for path in sorted(LOCALES_DIR.glob("*.json")):
        if path.name in OWNED:
            continue
        lang = path.stem
        target = deepl_target_codes.get(lang)
        if not target:
            print(f"skip {lang}: no DeepL target code mapped")
            continue

        # build or fetch glossary for this language
        glossary_id = None
        tsv = load_glossary_tsv(GLOSSARY_DIR / f"{lang}.tsv")
        if tsv:
            g = translator.create_glossary(
                name=f"kiekr-{lang}-{TODAY}",
                source_lang="EN",
                target_lang=target,
                entries={src: tr for src, tr in tsv},
            )
            glossary_id = g.glossary_id

        try:
            data = load(path)
            # Gather every (key, source) that still needs translating
            pending: list[tuple[str, str]] = []
            for k, v in en.items():
                if k == "_meta":
                    continue
                if k not in data:
                    continue
                if not needs_translation(data[k]):
                    continue
                src = en_value(v)
                if src is None:
                    continue
                pending.append((k, src))

            seeded = 0
            for i in range(0, len(pending), BATCH_SIZE):
                chunk = pending[i:i + BATCH_SIZE]
                keys = [k for k, _ in chunk]
                texts = [s for _, s in chunk]
                try:
                    translations = translate_batch(translator, texts, target, glossary_id)
                except Exception as e:
                    print(f"  batch {i}-{i + len(chunk)}: DeepL error: "
                          f"{_sanitize(str(e), SECRET)}", file=sys.stderr)
                    skipped_error += len(chunk)
                    continue
                for k, tr in zip(keys, translations):
                    src = en.get(k)
                    src_text = en_value(src) or ""
                    # Self-check: a translation that lost or invented a
                    # placeholder stays null (retried next run) instead of
                    # poisoning the catalog and failing validate later.
                    if not placeholders_ok(src_text, tr):
                        print(f"::warning file=locales/{path.name}::"
                              f"{k}: DeepL mangled placeholders "
                              f"({src_text!r} -> {tr!r}); left null")
                        skipped_bad += 1
                        continue
                    # Hard invariant: we only ever fill `null`. If the entry
                    # somehow holds a real value here, abort rather than
                    # overwrite human / already-reviewed text.
                    if data[k] is not None:
                        raise RuntimeError(
                            f"refusing to overwrite non-null entry {k!r} "
                            f"in {path.name} (value: {data[k]!r})"
                        )
                    data[k] = {"value": tr, "_ai": True, "_seeded": TODAY}
                    seeded += 1

            if seeded:
                data.setdefault("_meta", {"language": lang})["updated"] = TODAY
                dump(path, data)
                print(f"{lang}: seeded {seeded} keys (batched, {(seeded + BATCH_SIZE - 1) // BATCH_SIZE} requests)")
            else:
                print(f"{lang}: nothing to seed")
            total_seeded += seeded
        finally:
            # Always clean up the per-run glossary, even when a batch or the
            # overwrite guard raised — otherwise zombie glossaries pile up in
            # the DeepL account.
            if glossary_id:
                try:
                    translator.delete_glossary(glossary_id)
                except Exception as e:
                    print(f"  glossary cleanup failed for {lang}: "
                          f"{_sanitize(str(e), SECRET)}", file=sys.stderr)

    print(f"summary: seeded={total_seeded} "
          f"skipped_deepl_error={skipped_error} "
          f"skipped_bad_placeholders={skipped_bad}")
    if skipped_error or skipped_bad:
        # Not fatal: nulls are legal (app falls back to English) and the
        # next scheduled run retries them. Surface it, stay green.
        print(f"::warning::{skipped_error + skipped_bad} value(s) left null "
              f"this run — the nightly/next run will retry them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
