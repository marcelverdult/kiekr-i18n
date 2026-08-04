#!/usr/bin/env python3
"""One-off DeepL diagnostic: why does translate return 456 while usage is 0?

Prints library version, the deepl-library usage + translate results, AND raw
HTTP calls to /v2/usage and /v2/translate so we see the TRUE status code and
response body. Never logs the key (masks it). Delete after use.
"""
import os, sys, json, urllib.request, urllib.parse, urllib.error

KEY = os.environ.get("DEEPL_API_KEY", "")
if not KEY:
    print("no DEEPL_API_KEY"); sys.exit(1)
def mask(s): return s.replace(KEY, "***") if KEY else s

# :fx suffix -> free endpoint, else pro
BASE = "https://api-free.deepl.com" if KEY.endswith(":fx") else "https://api.deepl.com"
print(f"key suffix :fx = {KEY.endswith(':fx')}  -> endpoint {BASE}")

def raw(path, data=None):
    url = BASE + path
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers={"Authorization": f"DeepL-Auth-Key {KEY}"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode()[:600]
    except urllib.error.HTTPError as e:
        return e.code, mask(e.read().decode()[:600])
    except Exception as e:
        return "ERR", mask(str(e))

print("\n=== RAW GET /v2/usage ===")
print(raw("/v2/usage"))

print("\n=== RAW POST /v2/translate (text=Hello, EN->ES, no glossary) ===")
print(raw("/v2/translate", {"text": "Hello world", "source_lang": "EN", "target_lang": "ES"}))

print("\n=== deepl library ===")
try:
    import deepl
    print("deepl version:", getattr(deepl, "__version__", "?"))
    t = deepl.Translator(KEY)
    u = t.get_usage()
    print("lib usage:", u.character.count, "/", u.character.limit,
          "valid=", u.character.valid, "limit_reached=", u.character.limit_reached)
    try:
        r = t.translate_text("Hello world", source_lang="EN", target_lang="ES")
        print("lib translate OK:", r.text)
    except Exception as e:
        print("lib translate EXC:", type(e).__name__,
              "http_status=", getattr(e, "http_status_code", None),
              "should_retry=", getattr(e, "should_retry", None),
              "msg=", mask(str(e)))
except Exception as e:
    print("lib import/setup EXC:", mask(str(e)))
