#!/usr/bin/env python3
"""Post-process dist/ so images are served at a sane resolution.

The problem
-----------
build_dist.py collapses every Squarespace `?format=<N>w` variant of an image
down to one file — the largest. Squarespace's runtime image loader still asks
for a sized variant (`img.src = <path>?format=300w`), but static hosting
ignores query strings, so *every* thumbnail request is answered with the
full-resolution original. On the homepage that turns ~0.3 MB of genuinely
needed image data into ~3 MB, on every single visit.

The fix, in three parts
-----------------------
1. Emit each `?format=<N>w` variant as a real file (`<stem>__<N>w<ext>`), so
   there is something correctly-sized to point at. Identical variants share
   one file.

2. Inline a small shim (image_shim.js) that maps the loader's
   `?format=<N>w` requests onto those files. This is done at the loader
   level rather than by rewriting `<img>` markup, because Squarespace's
   loader also drives the *layout* of summary and gallery thumbnails —
   detaching it collapses them to zero height.

3. Cap everything at CANON_MAX_WIDTH — both the emitted variants and the
   canonical file itself. Many images — the summary
   block thumbnails especially — are injected client-side by Squarespace's JS,
   so no amount of HTML rewriting reaches them; they will always request
   `<canonical>?format=Nw`. Whatever sits at the canonical path is what they
   get, so that file needs to be a sensible size rather than a 2500px master.
   Measured render sizes on this site top out around 530 CSS px, so 1000w
   still covers a 2x display with headroom.

Anything still over the cap afterwards — images the mirror only ever held at
full size — is resampled directly with `sips`.

The Klarna GIF is deliberately exempt. Its `?format=` variants at 300w and
above are byte-identical to the original, so there is nothing to win, and the
100w variant would visibly degrade it. It keeps the loader path and ships
untouched at full resolution.
"""
import json, os, re, shutil, subprocess, sys, hashlib

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(ROOT, "site")
DIST = os.path.join(ROOT, "dist")

# Filenames that must ship exactly as-is, at full resolution.
PRESERVE = ("Klarna+Feed+PoC.gif",)

# Largest variant allowed to sit at the canonical path (see docstring).
CANON_MAX_WIDTH = 1000

# Quality for re-encoding WebP content that is over the cap. Only content
# photographs exceed 1000w here — logos, icons and UI sprites are all smaller
# and are never touched — so lossy at this quality is visually equivalent.
# (Squarespace stored several of these as *lossless* WebP, which is why a
# single film still weighed 932 KB.)
WEBP_QUALITY = 90

# Per-image overrides for things displayed far smaller than the general cap.
# The author avatar is a 2500x3750 master used as a ~50 px byline thumbnail.
RESAMPLE_OVERRIDES = {
    "images.squarespace-cdn.com/content/v2/namespaces/memberAccountAvatars/libraries/"
    "62b9b66797bef35d3985ef88/0bc4af89009e492e9e28f50a697be321/"
    "0bc4af89009e492e9e28f50a697be321.jpeg": 300,
}

VARIANT_RE = re.compile(r"^(?P<stem>.+?)\?format=(?P<w>\d+)w$")


def digest(p):
    return hashlib.sha1(open(p, "rb").read()).hexdigest()


def preserved(name):
    return any(name.endswith(p) for p in PRESERVE)


def build_variants():
    """canonical dist-rel path -> {width: dist-rel variant path}"""
    if not os.path.isdir(SITE):
        sys.exit("site/ (raw wget mirror) not found — needed to recover the "
                 "sized image variants. Re-scrape, or skip this step.")
    index, emitted = {}, 0
    for dirpath, _, files in os.walk(SITE):
        groups = {}
        for f in files:
            m = VARIANT_RE.match(f)
            if m:
                groups.setdefault(m.group("stem"), []).append((int(m.group("w")), f))
        for stem, variants in groups.items():
            canon_rel = os.path.relpath(os.path.join(dirpath, stem), SITE)
            if preserved(stem) or not os.path.exists(os.path.join(DIST, canon_rel)):
                continue
            root, ext = os.path.splitext(canon_rel)
            by_hash, widths = {}, {}
            for w, fname in sorted(variants):
                # Nothing above the cap ships: the canonical file is capped at
                # CANON_MAX_WIDTH too, so emitting larger variants would let the
                # shim serve bigger images than the no-JS path ever could.
                # Requests above the cap fall back to the largest kept width.
                if w > CANON_MAX_WIDTH:
                    continue
                src = os.path.join(dirpath, fname)
                h = digest(src)
                if h in by_hash:                    # identical to a smaller width
                    widths[w] = by_hash[h]
                    continue
                out_rel = f"{root}__{w}w{ext}"
                out_abs = os.path.join(DIST, out_rel)
                os.makedirs(os.path.dirname(out_abs), exist_ok=True)
                shutil.copy2(src, out_abs)
                by_hash[h] = out_rel
                widths[w] = out_rel
                emitted += 1
            if widths:
                index[canon_rel] = widths
    return index, emitted


def cap_canonicals(index):
    """Replace each oversized canonical with its largest variant <= CANON_MAX_WIDTH."""
    saved = 0
    for canon_rel, widths in index.items():
        eligible = [w for w in widths if w <= CANON_MAX_WIDTH]
        if not eligible:
            continue
        pick = os.path.join(DIST, widths[max(eligible)])
        canon = os.path.join(DIST, canon_rel)
        before = os.path.getsize(canon)
        if os.path.getsize(pick) >= before:
            continue                                # already at or below target
        shutil.copy2(pick, canon)
        saved += before - os.path.getsize(canon)
    return saved


def image_kind(path):
    with open(path, "rb") as fh:
        head = fh.read(16)
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if head[:2] == b"\xff\xd8":
        return "jpeg"
    return None


def pixel_width(path):
    r = subprocess.run(["sips", "-g", "pixelWidth", path],
                       capture_output=True, text=True)
    m = re.search(r"pixelWidth:\s*(\d+)", r.stdout)
    return int(m.group(1)) if m else None


def resample_oversized():
    """Bring any remaining image down to the cap.

    cap_canonicals() only helps where the mirror kept a smaller `?format=`
    variant. Some images — the article hero copies under static1, the author
    avatar — only ever existed at full size and need resampling instead.

    Several are WebP served under a .png/.jpg name (Squarespace content-
    negotiated, and wget saved the body under the requested URL), so they are
    re-encoded with cwebp rather than sips, which cannot write WebP.
    """
    saved, count = 0, 0
    for dirpath, _, files in os.walk(DIST):
        for f in files:
            if not f.lower().endswith((".png", ".jpg", ".jpeg")) or preserved(f):
                continue
            path = os.path.join(dirpath, f)
            rel = os.path.relpath(path, DIST)
            target = RESAMPLE_OVERRIDES.get(rel, CANON_MAX_WIDTH)

            width = pixel_width(path)
            if not width or width <= target:
                continue

            kind = image_kind(path)
            before = os.path.getsize(path)
            tmp = path + ".tmp"
            if kind == "webp":
                cmd = ["cwebp", "-quiet", "-q", str(WEBP_QUALITY),
                       "-resize", str(target), "0", path, "-o", tmp]
            else:
                cmd = ["sips", "--resampleWidth", str(target), path, "--out", tmp]

            if subprocess.run(cmd, capture_output=True).returncode != 0 \
                    or not os.path.exists(tmp):
                print(f"  WARN: could not resample {rel}", file=sys.stderr)
                if os.path.exists(tmp):
                    os.remove(tmp)
                continue

            # Never let a "resize" make a file bigger.
            if os.path.getsize(tmp) >= before:
                os.remove(tmp)
                continue
            os.replace(tmp, path)
            saved += before - os.path.getsize(path)
            count += 1
    return saved, count


def inject_shim(index):
    """Inline image_shim.js so the runtime loader requests real sized files.

    The summary and gallery blocks rebuild their <img> elements client-side,
    so the static-HTML rewrite above never reaches them; they always request
    `<canonical>?format=Nw`. The shim maps those onto the `__<N>w` files.
    It is inlined rather than linked so it runs before Squarespace's bundles
    without costing an extra blocking round trip.
    """
    template = open(os.path.join(ROOT, "image_shim.js"), encoding="utf-8").read()

    manifest = {}
    for canon_rel, widths in index.items():
        avail = sorted({int(re.search(r"__(\d+)w", v).group(1))
                        for v in widths.values() if "__" in v})
        if avail:
            manifest["/" + canon_rel.replace(os.sep, "/")] = avail
    if not manifest:
        return 0

    js = template.replace("__MANIFEST__", json.dumps(manifest, separators=(",", ":")))
    tag = "<script>" + js + "</script>"

    n = 0
    for dirpath, _, files in os.walk(DIST):
        for f in files:
            if not f.endswith(".html"):
                continue
            path = os.path.join(dirpath, f)
            html = open(path, encoding="utf-8", errors="replace").read()
            if "sized-variant shim" in html:
                continue
            new, cnt = re.subn(r"(<head[^>]*>)", lambda m: m.group(1) + tag,
                               html, count=1)
            if cnt:
                open(path, "w", encoding="utf-8").write(new)
                n += 1
    return n


def main():
    index, emitted = build_variants()
    print(f"variants: {emitted} files emitted for {len(index)} images")

    capped = cap_canonicals(index)
    print(f"canonical: capped at {CANON_MAX_WIDTH}w, {capped/1048576:.2f} MB reclaimed")

    resampled, n_res = resample_oversized()
    print(f"resampled: {n_res} images over the cap, {resampled/1048576:.2f} MB reclaimed")

    n = inject_shim(index)
    print(f"shim:      inlined into {n} pages")


if __name__ == "__main__":
    main()
