#!/usr/bin/env python3
"""Seed translations in non-source locales with a LOCAL NLLB-200 model.

Offline drop-in replacement for the DeepL-based seed.py: no API key, no
quota. Runs on the maintainer's machine before a publish.

Same invariants as seed.py / fill_from_json.py:
  - by default only fills `null` entries
  - never touches en/de, never touches `_human` entries
  - writes { "value": "...", "_ai": true, "_seeded": "<today>" }
  - placeholder self-check: a translation that lost/invented a
    placeholder is skipped (left null) instead of poisoning the catalog

Modes:
  --check-codes     only verify every FLORES code resolves in the
                    tokenizer, then exit (no model download / no writes)
  --reseed-ai       ALSO replace existing machine (`_ai`) values — the
                    mass re-verify. Backs every touched file up to
                    locales/.reseed-backup/<lang>.json first. `_human`
                    stays untouched.
  --langs a,b,c     restrict to these locale codes
  --limit N         (debug) cap pending strings per locale

Model: env NLLB_MODEL (default facebook/nllb-200-distilled-1.3B).

Exit 0 = ran clean. Exit 1 = a FLORES code is missing / a hard error.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES_DIR = ROOT / "locales"
BACKUP_DIR = LOCALES_DIR / ".reseed-backup"
SOURCE_FILE = LOCALES_DIR / "en.json"
OWNED = {"en", "de"}
TODAY = date.today().isoformat()
MODEL = os.environ.get("NLLB_MODEL", "facebook/nllb-200-distilled-1.3B")
BATCH = int(os.environ.get("NLLB_BATCH", "16"))

# Same pattern validate.py enforces.
PLACEHOLDER_RE = re.compile(r"%\d+\$[sd]|%[sd@]|%(?:\.\d+)?[fld]+")

# our locale code -> NLLB FLORS-200 code. pt-BR and pt-PT both map to
# por_Latn (NLLB does not distinguish the two Portuguese variants).
FLORES = {
    "es": "spa_Latn", "fr": "fra_Latn", "nl": "nld_Latn", "it": "ita_Latn",
    "pt-BR": "por_Latn", "pt-PT": "por_Latn", "pl": "pol_Latn",
    "bg": "bul_Cyrl", "hr": "hrv_Latn", "cs": "ces_Latn", "da": "dan_Latn",
    "et": "est_Latn", "fi": "fin_Latn", "el": "ell_Grek", "ga": "gle_Latn",
    "hu": "hun_Latn", "lv": "lvs_Latn", "lt": "lit_Latn", "mt": "mlt_Latn",
    "ro": "ron_Latn", "sk": "slk_Latn", "sl": "slv_Latn", "sv": "swe_Latn",
    "nb": "nob_Latn", "ru": "rus_Cyrl", "uk": "ukr_Cyrl",
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def en_value(entry):
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return entry.get("value")
    return None


def placeholders_ok(source: str, translated: str) -> bool:
    return sorted(PLACEHOLDER_RE.findall(source)) == sorted(
        PLACEHOLDER_RE.findall(translated)
    )


def needs(entry, reseed_ai: bool) -> bool:
    """Which entries this run should (re)translate."""
    if entry is None:
        return True
    if reseed_ai and isinstance(entry, dict):
        # replace machine seeds, never human, never plurals (separate pass)
        if entry.get("_ai") and not entry.get("_human") and "plural" not in entry:
            return True
    return False


def parse_args(argv):
    opts = {"check_codes": "--check-codes" in argv, "reseed_ai": "--reseed-ai" in argv,
            "langs": None, "limit": None, "keys": None}
    if "--langs" in argv:
        opts["langs"] = set(argv[argv.index("--langs") + 1].split(","))
    if "--limit" in argv:
        opts["limit"] = int(argv[argv.index("--limit") + 1])
    # --keys k1,k2,... — seed ONLY these keys. Lets a feature tranche fill
    # its own handful of strings in minutes without dragging the whole
    # null backlog (thousands of values, hours of CPU) into the run, and
    # without touching keys another branch is still working on.
    if "--keys" in argv:
        opts["keys"] = set(argv[argv.index("--keys") + 1].split(","))
    return opts


def main() -> int:
    opts = parse_args(sys.argv[1:])

    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
    print(f"tokenizer: {MODEL}", flush=True)
    tok = AutoTokenizer.from_pretrained(MODEL)

    # --- verify every FLORES code resolves (fail-fast) ---
    unk = tok.unk_token_id
    missing = []
    print("=== FLORES code check ===")
    for lang, code in sorted(FLORES.items()):
        tid = tok.convert_tokens_to_ids(code)
        ok = tid != unk
        print(f"  {lang:6} {code:9} id={tid} {'OK' if ok else 'MISSING!'}")
        if not ok:
            missing.append((lang, code))
    if missing:
        print(f"\nERROR: {len(missing)} FLORES code(s) missing: {missing}", file=sys.stderr)
        return 1
    if opts["check_codes"]:
        print("\nall codes OK (--check-codes: no model load, no writes)")
        return 0

    print(f"loading model {MODEL} ...", flush=True)
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL)
    model.eval()

    def translate_batch(texts, tgt_code):
        tok.src_lang = "eng_Latn"
        enc = tok(texts, return_tensors="pt", padding=True, truncation=True, max_length=256)
        import torch
        with torch.no_grad():
            gen = model.generate(
                **enc,
                forced_bos_token_id=tok.convert_tokens_to_ids(tgt_code),
                max_length=256,
                num_beams=4,
            )
        return tok.batch_decode(gen, skip_special_tokens=True)

    en = load(SOURCE_FILE)
    total_written = total_skipped = 0

    for lang, code in FLORES.items():
        if opts["langs"] and lang not in opts["langs"]:
            continue
        path = LOCALES_DIR / f"{lang}.json"
        if not path.exists():
            print(f"{lang}: no locale file, skip")
            continue
        data = load(path)

        pending = []  # (key, en_source)
        for k, v in en.items():
            if k == "_meta" or k not in data:
                continue
            if opts["keys"] and k not in opts["keys"]:
                continue
            if not needs(data.get(k), opts["reseed_ai"]):
                continue
            src = en_value(v)
            if src:
                pending.append((k, src))
        if opts["limit"]:
            pending = pending[: opts["limit"]]
        if not pending:
            print(f"{lang}: nothing to do")
            continue

        # backup before any overwrite of existing values
        if opts["reseed_ai"]:
            BACKUP_DIR.mkdir(exist_ok=True)
            dump(BACKUP_DIR / f"{lang}.json", data)

        written = skipped = 0
        for i in range(0, len(pending), BATCH):
            chunk = pending[i : i + BATCH]
            outs = translate_batch([s for _, s in chunk], code)
            for (k, src), tr in zip(chunk, outs):
                if not placeholders_ok(src, tr):
                    print(f"  {lang}/{k}: placeholder mismatch ({src!r} -> {tr!r}); skipped")
                    skipped += 1
                    continue
                data[k] = {"value": tr, "_ai": True, "_seeded": TODAY}
                written += 1
            print(f"  {lang}: {min(i + BATCH, len(pending))}/{len(pending)}", flush=True)

        if written:
            data.setdefault("_meta", {"language": lang})["updated"] = TODAY
            dump(path, data)
        print(f"{lang}: wrote {written}, skipped {skipped}")
        total_written += written
        total_skipped += skipped

    print(f"\nsummary: wrote={total_written} skipped_placeholder={total_skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
