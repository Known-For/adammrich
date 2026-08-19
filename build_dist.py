#!/usr/bin/env python3
"""Build dist/ (self-contained static site) from site/ (raw wget mirror of
www.adammrich.com). Rewrites Squarespace CDN references to local paths,
dedupes ?format= image variants, converts pages to clean-URL directories,
and replaces the Typekit loader with self-hosted fonts."""
import os, re, shutil, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(ROOT, "site")
DIST = os.path.join(ROOT, "dist")

CDN_HOSTS = ["images.squarespace-cdn.com", "static1.squarespace.com", "assets.squarespace.com"]

if os.path.exists(DIST):
    shutil.rmtree(DIST)
os.makedirs(DIST)

# ---------- 1. Copy CDN assets, deduping query-string variants ----------
def fmt_width(name):
    m = re.search(r"\?format=(\d+)w", name)
    return int(m.group(1)) if m else -1

for host in CDN_HOSTS:
    src_root = os.path.join(SITE, host)
    if not os.path.isdir(src_root):
        continue
    groups = {}  # base path (query stripped) -> list of full paths
    for dirpath, _, files in os.walk(src_root):
        for f in files:
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, SITE)
            if f == "index.html" and dirpath == src_root:
                continue  # preconnect artifact
            base = rel.split("?", 1)[0]
            groups.setdefault(base, []).append(full)
    for base, variants in groups.items():
        # prefer the plain (no-query) file = original; else largest format width; else largest size
        plain = [v for v in variants if "?" not in os.path.basename(v)]
        if plain:
            pick = plain[0]
        else:
            variants.sort(key=lambda v: (fmt_width(os.path.basename(v)), os.path.getsize(v)))
            pick = variants[-1]
        dest = os.path.join(DIST, base)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(pick, dest)

# ---------- 2. Fonts ----------
shutil.copytree(os.path.join(SITE, "fonts"), os.path.join(DIST, "fonts"))

# ---------- 3. Page mapping ----------
PAGES_ROOT = os.path.join(SITE, "www.adammrich.com")

def clean_url_for(site_rel):
    """Map a path under site/ to its clean URL, or None if not a page."""
    site_rel = site_rel.replace("\\", "/")
    if site_rel.startswith("adammrich.com/"):
        return "/"
    for host in CDN_HOSTS + ["use.typekit.net"]:
        if site_rel.startswith(host + "/"):
            return "/"  # preconnect index.html artifacts
    if not site_rel.startswith("www.adammrich.com/"):
        return None
    p = site_rel[len("www.adammrich.com/"):]
    p = p.split("?", 1)[0]
    if p.endswith(".html"):
        p = p[:-5]
    if p in ("index", ""):
        return "/"
    return "/" + p + "/"

PAGE_FILES = []  # (src_path, clean_url)
for dirpath, _, files in os.walk(PAGES_ROOT):
    for f in files:
        if not f.endswith(".html"):
            continue
        if "?" in f:  # ?author= / ?format=rss duplicates
            continue
        full = os.path.join(dirpath, f)
        rel = os.path.relpath(full, SITE)
        PAGE_FILES.append((full, clean_url_for(rel)))

# ---------- 4. HTML rewriting ----------
CDN_ALT = "|".join(re.escape(h) for h in CDN_HOSTS)

def rewrite_html(src_path, html):
    src_dir = os.path.dirname(src_path)

    # a. absolute CDN urls (plain and JSON-escaped) -> root-absolute local
    for host in CDN_HOSTS:
        html = html.replace(f"https://{host}/", f"/{host}/")
        html = html.replace(f"http://{host}/", f"/{host}/")
        html = html.replace(f"https:\\/\\/{host}\\/", f"\\/{host}\\/")

    # b. wget-converted relative CDN refs -> root-absolute
    html = re.sub(r"(?:\.\./)+((?:%s)/)" % CDN_ALT, r"/\1", html)

    # c. strip query suffixes (?/%3F...) on local CDN paths
    html = re.sub(r"(/(?:%s)/[^\s\"'()<>\\]*?)(?:%%3F|\?)[^\s\"'()<>\\]*" % CDN_ALT, r"\1", html)

    # d. typekit loader script tag -> self-hosted fonts stylesheet
    html = re.sub(r'<script[^>]*use\.typekit\.net[^>]*>\s*</script>',
                  '<link rel="stylesheet" href="/fonts/fonts.css">', html)
    html = re.sub(r'<link[^>]*use\.typekit\.net[^>]*>', '', html)
    # google fonts css -> covered by fonts.css
    html = re.sub(r'<link[^>]*fonts\.googleapis\.com[^>]*>', '', html)
    html = re.sub(r'<link[^>]*href="https://fonts\.gstatic\.com"[^>]*>', '', html)

    # e. internal page links (wget-converted relative .html refs) -> clean URLs
    def repl_link(m):
        attr, ref, suffix = m.group(1), m.group(2), m.group(3) or ""
        if ref.startswith(("http://", "https://", "//", "/")):
            return m.group(0)
        target = os.path.normpath(os.path.join(src_dir, ref.replace("%3F", "?")))
        rel = os.path.relpath(target, SITE)
        url = clean_url_for(rel)
        if url is None:
            return m.group(0)
        return f'{attr}"{url}{suffix}"'

    html = re.sub(r'(href=)"([^":#]*?\.html)(#[^"]*)?"', repl_link, html)
    # rss-style links without .html
    html = re.sub(r'(href=)"((?:\.\./)*[^":#]*?%3Fformat=rss)()"', repl_link, html)

    # f. remaining absolute self-links -> root-relative (survives any domain setup)
    html = html.replace('https://www.adammrich.com/', '/')
    html = html.replace('href="https://www.adammrich.com"', 'href="/"')

    return html

for src, url in PAGE_FILES:
    with open(src, encoding="utf-8", errors="replace") as fh:
        html = fh.read()
    html = rewrite_html(src, html)
    out_dir = os.path.join(DIST, url.lstrip("/"))
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"page: {url}")

# ---------- 5. CSS: strip %3F query suffixes so refs match deduped filenames ----------
for dirpath, _, files in os.walk(DIST):
    for f in files:
        if not f.endswith(".css"):
            continue
        p = os.path.join(dirpath, f)
        with open(p, encoding="utf-8", errors="replace") as fh:
            css = fh.read()
        new = re.sub(r"(%3F|\?)[^'\")\s]*", "", css)
        if new != css:
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(new)

# ---------- 6. Download any still-external stylesheet deps (definitions.sqspcdn.com) ----------
import urllib.request
ext_css = set()
for dirpath, _, files in os.walk(DIST):
    for f in files:
        if not f.endswith(".html"):
            continue
        with open(os.path.join(dirpath, f), encoding="utf-8", errors="replace") as fh:
            ext_css.update(re.findall(r'https://definitions\.sqspcdn\.com/[^\s"\']+\.css', fh.read()))
for url in sorted(ext_css):
    local = url.replace("https://", "")
    dest = os.path.join(DIST, local)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        urllib.request.urlretrieve(url, dest)
        print(f"fetched: {local}")
    except Exception as e:
        print(f"FAILED to fetch {url}: {e}", file=sys.stderr)
        continue
    for dirpath, _, files in os.walk(DIST):
        for f in files:
            if not f.endswith(".html"):
                continue
            p = os.path.join(dirpath, f)
            with open(p, encoding="utf-8", errors="replace") as fh:
                html = fh.read()
            if url in html:
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(html.replace(url, "/" + local))

# 404 page = homepage copy so Render serves something sane
shutil.copy2(os.path.join(DIST, "index.html"), os.path.join(DIST, "404.html"))

# ---------- 7. Right-size images ----------
# Step 1 above keeps only the largest ?format= variant of each image, but the
# Squarespace loader still requests sized ones at runtime — and static hosting
# ignores query strings, so every thumbnail would be answered with the
# full-resolution original. optimize_images.py restores the sized variants and
# teaches the loader to ask for them. Without it the site ships ~10x more
# image data than it needs to.
import optimize_images
optimize_images.main()

print("done")
