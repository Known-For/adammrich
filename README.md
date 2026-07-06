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

## Known limitations

- Contact/newsletter forms and cart/commerce no longer have a backend —
  form posts to `/api/...` will silently fail. (The site's analytics beacons
  also 404 harmlessly.) If a working contact form is needed, swap in a
  Formspree/Basin endpoint.
- This is a frozen snapshot; content edits mean editing `dist/` HTML directly.
