# NEEDS-HUMAN — items requiring Rob's action / decision

Maintained by the orchestrator (Claude driving the aggregator build).

## ✅ Firebase + production-domain migration — DONE

Open Play RI is live on **Firebase Hosting** at **https://openplayri.com** (everything under Google).

- ✅ Firebase project `open-play-ri` (**Blaze** plan; usage ~$0). Hosting live; the hourly GitHub
  Action deploys via the `github-deployer@open-play-ri` service account (repo secret
  `FIREBASE_SERVICE_ACCOUNT_OPEN_PLAY_RI`). GitHub Pages is retired.
- ✅ **Off the JCC**: session/venue share pages are per-venue; the JCC is just one of 6 live sources.
- ✅ **GA4** analytics (`G-69SBHEGRY1`) site-wide; GoatCounter removed.
- ✅ Domain `openplayri.com` registered via **Google Cloud Domains** (~$12/yr, auto-renews ~Jun 26),
  **Cloud DNS** zone `openplayri-com`, Firebase-managed SSL. Canonical/OG/sitemap/feeds all on it.

### Optional follow-ups (non-blocking)
- [x] **Google Search Console** — `openplayri.com` added as a **Domain property**, ownership
      **auto-verified** (same Google account as Cloud Domains, no DNS step needed). Sitemap
      `https://openplayri.com/sitemap.xml` submitted and read — **Success, 673 pages discovered**
      (2026-06-26). If the old `robertcorey.github.io/jcc-pickleball` property was ever in Search
      Console, file a Change-of-Address from it; otherwise nothing to do.
- [x] **`www` redirect** — `www.openplayri.com` added in Firebase as a **301 redirect to the apex**;
      Cloud DNS zone `openplayri-com` now has a `www` **CNAME → open-play-ri.web.app** (the A record
      was swapped out — CNAME can't coexist with A). Firebase was still showing "records not yet
      detected" at setup time (propagation lag, same as the apex); it auto-connects in the background.
- [ ] **Old GitHub Pages** — `robertcorey.github.io/jcc-pickleball` is now stale (CI no longer
      deploys there). Disable it in repo settings, or leave it. Low stakes (barely indexed).
- [ ] **`gmail-cleanup-rc` billing** — I unlinked it to free a Cloud-billing slot for `openplayri.com`
      (the "Firebase Payment" account is at its 5-project cap). It had no paid resources, so it's fine
      on the free tier; re-link only if it ever needs billing (would require freeing another slot).

## Other open items (pre-existing, not migration-related)
- [ ] **Centerline Pickleball Club (Warwick) — CourtReserve org id** → one-line add to
      `COURTRESERVE_ORGS` in `scraper/sources.py` → instant 5th live club.
- [ ] **Bristol registration URL** → one-line swap in `scraper/bristol_ics.py` when you have the
      official link.
- [ ] **(Optional) Auto-refresh the venue directory** (`scraper/discover_places.py` → `directory.json`).

## Resolved
- [x] Firebase project + Hosting + custom domain (openplayri.com) + GA4 — this migration.
- [x] Firebase CLI auth (robertbcorey@gmail.com); Google Places API key on the Pi.
