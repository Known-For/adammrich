# adammrich.com — static clone

Self-contained static copy of the Squarespace site at www.adammrich.com,
captured 2026-07-06 so the Squarespace subscription can be cancelled and the
site self-hosted on Render (free static hosting).

## What's here

- `dist/` — the deployable site. All 13 pages as clean URLs
  (`/`, `/thought-leadership/`, `/content-strategy/`, 10 article pages, `/cart/`),
  plus every asset localized: Squarespace CDN images (largest variant of each),
  CSS/JS bundles, 110 lazy-loaded webpack chunks (`dist/scripts/`), component
  CSS/JS from definitions.sqspcdn.com, and self-hosted fonts in `dist/fonts/`
  (the Typekit "interface" family ×7 weights — downloaded while the
  Squarespace/Adobe license was active — and Archivo Black).
- `render.yaml` — Render blueprint: static site publishing `dist/`, with
  `/home` → `/` redirects (the old Squarespace homepage alias).
- `build_dist.py`, `fetch_missing.py` — the scripts that transformed the raw
  `wget` mirror (`site/`, not committed) into `dist/`. Only needed if you ever
  re-scrape.
- `optimize_images.py`, `image_shim.js` — the image right-sizing pass, run
  automatically as the last step of `build_dist.py`. See "Bandwidth" below.

## Deploy to Render

1. Push this repo to GitHub.
2. In Render: **New → Static Site**, connect the repo. The `render.yaml` is
   picked up automatically (or set Publish Directory = `dist`, no build command).
3. Add custom domains `adammrich.com` and `www.adammrich.com`; follow Render's
   DNS instructions at your registrar.

## Before cancelling Squarespace

- **Check where the domain is registered.** If adammrich.com is registered
  through Squarespace, keep the domain registration (Squarespace bills it
  separately from the website plan) or transfer it out first. Cancelling only
  the website plan is safe; letting the domain lapse is not.
- Update DNS to point at Render *before* the plan ends to avoid downtime.

## Bandwidth

Two things were quietly costing a lot of Render egress:

**Nothing was cached.** Render's default for static sites is
`Cache-Control: public, max-age=0, s-maxage=300` — browsers re-validate every
asset on every visit, and the CDN edge drops everything after five minutes, so
almost all traffic fell through to the origin. `render.yaml` now sets explicit
headers: one year `immutable` for the content-hashed bundles under
`/assets…`, `/static1…`, `/definitions…`, `/scripts` and `/fonts`, 30 days for
images, and a short browser TTL with a long edge TTL for HTML. Render purges
the edge on deploy, so the long values are safe.

**Every thumbnail was served as a full-resolution original.** `build_dist.py`
keeps only the largest `?format=<N>w` variant of each image, but Squarespace's
image loader still requests sized ones at runtime — and static hosting ignores
query strings, so a request for a 300 px thumbnail returned the 2500 px
master. `optimize_images.py` fixes this by emitting the sized variants as real
files (`name__300w.png`), inlining `image_shim.js` to map the loader's
`?format=` requests onto them, capping every stored image at 1000 px wide, and
resampling the few that only ever existed at full size. Homepage image
payload went from 2.97 MB to ~0.3 MB with the rendered layout unchanged.

If you re-scrape, just run `build_dist.py` — it calls the optimizer for you.
`site/` must be present, since that is where the sized variants come from.

### The Klarna GIF

`Klarna+Feed+PoC.gif` is deliberately exempt from all of the above and ships
byte-for-byte untouched at 4.04 MB. It is already only 230x498 — its weight is
314 frames of animation, not resolution — so there is nothing to reclaim
without making it smaller or choppier. It is lazy-loaded, so only visitors who
scroll to it pay for it.

The one option that would shrink it *without* touching resolution or
smoothness is re-encoding to video, which also drops GIF's 256-colour limit:

| format | size | vs GIF |
| --- | --- | --- |
| GIF (current) | 4.24 MB | — |
| H.264 MP4, CRF 20 | 0.91 MB | -79% |
| VP9 WebM, CRF 28 | 0.68 MB | -84% |

That needs the `<img>` swapped for `<video autoplay muted loop playsinline>`,
so it is left as a deliberate decision rather than done automatically.

## Known limitations

- Contact/newsletter forms and cart/commerce no longer have a backend —
  form posts to `/api/...` will silently fail. (The site's analytics beacons
  also 404 harmlessly.) If a working contact form is needed, swap in a
  Formspree/Basin endpoint.
- This is a frozen snapshot; content edits mean editing `dist/` HTML directly.
