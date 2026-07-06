#!/usr/bin/env python3
"""Second pass: download remaining Squarespace-hosted assets referenced by
dist/ pages (lazy JS rollups on assets.squarespace.com, component visitor JS
on definitions.sqspcdn.com) and localize the refs. Also neutralize internal
squarespace.com domain references."""
import os, re, sys, urllib.parse, urllib.request

DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")

def walk_files(exts):
    for dp, _, fs in os.walk(DIST):
        for f in fs:
            if f.endswith(exts):
                yield os.path.join(dp, f)

# 1. collect targets
need = set()
for p in walk_files((".html", ".css")):
    s = open(p, encoding="utf-8", errors="replace").read()
    # local asset refs that don't exist on disk yet -> re-fetch from origin
    for m in re.findall(r'/(?:assets\.squarespace|static1\.squarespace)\.com/[^\s"\'()<>\\&]+', s):
        path = urllib.parse.unquote(m.split("?")[0].split("#")[0])
        if not os.path.exists(DIST + path):
            need.add("https:/" + m)
    # still-external definitions js
    for m in re.findall(r'https://definitions\.sqspcdn\.com/[^\s"\'<>\\&]+', s):
        need.add(m)

print(f"{len(need)} files to fetch")
fail = []
for url in sorted(need):
    local = urllib.parse.unquote(url.replace("https://", ""))
    dest = os.path.join(DIST, local)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as fh:
            fh.write(r.read())
    except Exception as e:
        fail.append((url, str(e)))
        print(f"FAIL {url}: {e}", file=sys.stderr)

# 2. rewrite refs in html (definitions urls -> local; internal sqsp domain -> own domain)
for p in walk_files((".html",)):
    s = open(p, encoding="utf-8", errors="replace").read()
    orig = s
    s = s.replace("https://definitions.sqspcdn.com/", "/definitions.sqspcdn.com/")
    s = s.replace("https:\\/\\/definitions.sqspcdn.com\\/", "\\/definitions.sqspcdn.com\\/")
    s = s.replace("https://tuna-tuatara-ygy5.squarespace.com", "")
    s = s.replace("https:\\/\\/tuna-tuatara-ygy5.squarespace.com", "")
    if s != orig:
        open(p, "w", encoding="utf-8").write(s)

print(f"done, {len(fail)} failures")
