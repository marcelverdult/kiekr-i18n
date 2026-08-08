#!/usr/bin/env python3
"""LLM-based seeder: translate locales via a local OpenAI-compatible
endpoint (LM Studio / MLX / Ollama). Prompt-steered — glossary + UI
conventions + placeholder rules, i.e. exactly the levers that DeepL-Free
and raw NMT (NLLB) lack.

Same catalog invariants as seed_local.py:
  - default fills only `null`; never touches en/de or `_human`
  - writes {value, _ai:true, _seeded}
  - placeholder self-check: a translation that drops/invents a
    placeholder is skipped (stays null), never poisons the catalog

Config (env):
  LLM_ENDPOINT  OpenAI-compatible base URL (default http://localhost:1234/v1)
  LLM_MODEL     model id as the server lists it (REQUIRED)
  LLM_TEMP      sampling temperature (default 0.2)

Modes:
  --probe            translate a fixed hard-set (keys x langs), print, WRITE NOTHING
  --langs a,b,c      restrict to these locale codes
  --reseed-ai        also overwrite existing _ai values (mass re-verify)
  --limit N          cap pending strings per locale (debug)

Exit 0 = ran; 1 = endpoint/model error or a FLORES/arg problem.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES_DIR = ROOT / "locales"
GLOSSARY_DIR = ROOT / "glossary"
SOURCE_FILE = LOCALES_DIR / "en.json"
OWNED = {"en", "de"}
TODAY = date.today().isoformat()

ENDPOINT = os.environ.get("LLM_ENDPOINT", "http://localhost:1234/v1").rstrip("/")
MODEL = os.environ.get("LLM_MODEL", "")
TEMP = float(os.environ.get("LLM_TEMP", "0.2"))
WORKERS = int(os.environ.get("LLM_WORKERS", "4"))

PLACEHOLDER_RE = re.compile(r"%\d+\$[sd]|%[sd@]|%(?:\.\d+)?[fld]+")

# our locale code -> human language name for the prompt (LLMs steer far
# better on "Maltese" than on a FLORES code). pt-BR/pt-PT distinguished.
LANG_NAMES = {
    "es": "Spanish", "fr": "French", "nl": "Dutch", "it": "Italian",
    "pt-BR": "Brazilian Portuguese", "pt-PT": "European Portuguese",
    "pl": "Polish", "bg": "Bulgarian", "hr": "Croatian", "cs": "Czech",
    "da": "Danish", "et": "Estonian", "fi": "Finnish", "el": "Greek",
    "ga": "Irish", "hu": "Hungarian", "lv": "Latvian", "lt": "Lithuanian",
    "mt": "Maltese", "ro": "Romanian", "sk": "Slovak", "sl": "Slovenian",
    "sv": "Swedish", "nb": "Norwegian Bokmål", "ru": "Russian", "uk": "Ukrainian",
}

SYSTEM = (
    "You are a professional UI-string translator for KiekR, a mesh-radio "
    "companion app (MeshCore protocol). You translate short English UI "
    "strings — titles, labels, buttons, short hints — into the target "
    "language. Rules:\n"
    "- Keep it as concise as a real UI element: a title/label/button, NOT a "
    "full sentence. Match the register of the English (imperative for "
    "actions/buttons).\n"
    "- Preserve placeholders EXACTLY as written: %1$d, %2$s, %@, etc.\n"
    "- Never translate the brand name 'KiekR', the protocol 'MeshCore', or "
    "technical tokens like 'GPS'. Keep channel names (e.g. '#zephyr') as-is.\n"
    "- Output ONLY the translation. No quotes, no explanation, no alternatives."
)


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


def placeholders_ok(src: str, tr: str) -> bool:
    return sorted(PLACEHOLDER_RE.findall(src)) == sorted(PLACEHOLDER_RE.findall(tr))


def load_glossary(lang: str) -> str:
    """Return a prompt glossary block for this language, or '' if none."""
    path = GLOSSARY_DIR / f"{lang}.tsv"
    if not path.exists():
        return ""
    pairs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if "\t" in line:
            en, tr = line.split("\t", 1)
            pairs.append(f"{en.strip()}={tr.strip()}")
    if not pairs:
        return ""
    return "Glossary (use these exact term translations): " + "; ".join(pairs) + "\n"


def clean(text: str) -> str:
    t = text.strip()
    # strip a single pair of wrapping quotes the model sometimes adds
    if len(t) >= 2 and t[0] in "\"'" and t[-1] == t[0]:
        t = t[1:-1].strip()
    return t


def translate(src: str, lang: str, glossary: str) -> str:
    user = (
        f"Target language: {LANG_NAMES[lang]}\n"
        f"{glossary}"
        f"English: {src}\n"
        f"Translation:"
    )
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ],
        "temperature": TEMP,
        "max_tokens": 200,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read())
    return clean(d["choices"][0]["message"]["content"])


def needs(entry, reseed_ai: bool, resume: bool) -> bool:
    if entry is None:
        return True
    if isinstance(entry, dict):
        # resume: skip what THIS run already wrote today (idempotent restart)
        if resume and entry.get("_ai") and entry.get("_seeded") == TODAY:
            return False
        if reseed_ai and entry.get("_ai") and not entry.get("_human") and "plural" not in entry:
            return True
    return False


PROBE_KEYS = [
    "settings_catalog_update_title", "settings_catalog_update_button",
    "settings_catalog_update_checking", "settings_catalog_update_up_to_date",
    "settings_catalog_update_added", "settings_catalog_update_never",
    "settings_catalog_update_available", "settings_community_coverage_bg_allow",
]
PROBE_LANGS = ["es", "fr", "el", "mt", "ga", "pl", "ru"]


def main() -> int:
    argv = sys.argv[1:]
    if not MODEL:
        print("ERROR: set LLM_MODEL (the model id the server lists)", file=sys.stderr)
        return 1
    probe = "--probe" in argv
    reseed = "--reseed-ai" in argv
    resume = "--resume" in argv
    langs = None
    if "--langs" in argv:
        langs = set(argv[argv.index("--langs") + 1].split(","))
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None

    en = load(SOURCE_FILE)
    print(f"endpoint={ENDPOINT} model={MODEL} temp={TEMP}")

    if probe:
        probe_langs = sorted(langs) if langs else list(LANG_NAMES)
        # heuristics to auto-flag broken output (meta-commentary, english
        # leakage, run-on) so the clean/broken boundary is obvious.
        META = re.compile(
            r"\b(translation|context|English|Irish|Maltese|would be|"
            r"up to date|meaning|correct|concise|doesn't|isn't|phrase|"
            r"note:|sorry)\b", re.I)
        print(f"=== PROBE (no writes) — {len(probe_langs)} langs x {len(PROBE_KEYS)} keys ===")
        summary = {}
        for lang in probe_langs:
            gl = load_glossary(lang)
            issues = 0
            print(f"\n[{lang}] {LANG_NAMES[lang]}{'  (+gloss)' if gl else ''}")
            for k in PROBE_KEYS:
                src = en_value(en.get(k))
                if not src:
                    continue
                try:
                    tr = translate(src, lang, gl)
                except Exception as e:
                    print(f"  {k}: ERROR {e}")
                    issues += 1
                    continue
                iss = []
                if not placeholders_ok(src, tr):
                    iss.append("PH")
                if len(tr) > 3 * len(src) + 25:
                    iss.append("LONG")
                if META.search(tr):
                    iss.append("EN")
                issues += len(iss)
                mark = ("  <-- " + ",".join(iss)) if iss else ""
                print(f"  {src!r} -> {tr!r}{mark}")
            summary[lang] = issues
            print(f"  [{lang}] {'CLEAN' if issues == 0 else f'ISSUES={issues}'}")
        print("\n=== SUMMARY (issues per lang; 0 = clean) ===")
        for lang in probe_langs:
            print(f"  {lang:6} {summary[lang]}")
        clean = [l for l in probe_langs if summary[l] == 0]
        print(f"\nCLEAN ({len(clean)}): {', '.join(clean)}")
        print(f"FLAGGED ({len(probe_langs)-len(clean)}): "
              f"{', '.join(l for l in probe_langs if summary[l] > 0)}")
        return 0

    total_written = total_skipped = 0
    for lang in LANG_NAMES:
        if langs and lang not in langs:
            continue
        path = LOCALES_DIR / f"{lang}.json"
        if not path.exists():
            continue
        data = load(path)
        gl = load_glossary(lang)
        pending = [(k, en_value(v)) for k, v in en.items()
                   if k != "_meta" and k in data and needs(data.get(k), reseed, resume)
                   and en_value(v)]
        if limit:
            pending = pending[:limit]
        if not pending:
            print(f"{lang}: nothing to do", flush=True)
            continue
        print(f"{lang}: {len(pending)} to translate ({WORKERS} concurrent)", flush=True)
        written = skipped = done = 0

        def _do(item, _lang=lang, _gl=gl):
            k, src = item
            try:
                return (k, src, translate(src, _lang, _gl), None)
            except Exception as e:
                return (k, src, None, str(e))

        # 4 parallel requests (LM Studio serves them concurrently); ex.map
        # preserves input order so periodic saves stay coherent.
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for k, src, tr, err in ex.map(_do, pending):
                done += 1
                if err:
                    print(f"  {lang}/{k}: endpoint error {err}; skipped", flush=True)
                    skipped += 1
                    continue
                if not placeholders_ok(src, tr):
                    skipped += 1
                    continue
                data[k] = {"value": tr, "_ai": True, "_seeded": TODAY}
                written += 1
                if written % 50 == 0:
                    data.setdefault("_meta", {"language": lang})["updated"] = TODAY
                    dump(path, data)
                    print(f"  {lang}: {done}/{len(pending)} (saved)", flush=True)
        if written:
            data.setdefault("_meta", {"language": lang})["updated"] = TODAY
            dump(path, data)
        print(f"{lang}: wrote {written}, skipped {skipped}", flush=True)
        total_written += written
        total_skipped += skipped
    print(f"\nsummary: wrote={total_written} skipped={total_skipped}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
