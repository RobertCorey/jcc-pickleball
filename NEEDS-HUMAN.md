# NEEDS-HUMAN — items requiring Rob's action / decision

Maintained by the orchestrator (Claude driving the aggregator build).
Nothing below blocks ongoing work — these are decisions/credentials only you can supply.

## Open
- [ ] **★ TOP GROWTH ACTION — submit to Google Search Console.** This is the single biggest lever
      for traffic and the one thing I can't do (needs your Google account). The site is fully
      crawlable and now has 216 pages incl. 28 town landing pages, full schema, and a sitemap —
      but Google won't rank what it hasn't discovered. Steps (~5 min): go to
      search.google.com/search-console → add property `https://robertcorey.github.io/jcc-pickleball/`
      (URL-prefix) → it'll ask you to verify; the **HTML-file** method works on GitHub Pages (give me
      the verification filename and I'll drop it in `site/`). Then submit the sitemap
      `https://robertcorey.github.io/jcc-pickleball/sitemap.xml`. (I've already pushed all URLs to
      Bing/Yandex/DuckDuckGo via IndexNow — Google needs Search Console.)

- [ ] **Brand / domain for the aggregator.** The site is now branded **"Open Play RI"**
      (statewide pickleball directory), but the repo + URL are still
      `robertcorey.github.io/jcc-pickleball`. A real domain (you have an unused Cloudflare
      one) would fit the statewide brand and help SEO. Decide: point the Cloudflare domain
      at it, or pick/buy a new one. Not blocking — everything runs on the github.io URL until
      you decide. If you do move it, update `SITE_BASE_URL` in the build + the canonical/OG
      URLs.

- [ ] **(Optional) Auto-refresh the venue directory.** `scraper/discover_places.py` sweeps
      the Google Places API for RI pickleball venues and writes `site/data/directory.json`
      (committed; the hourly site build just reads it — no key needed in CI). Today it's a
      **manual run on the Pi** (the key lives in the Pi's `~/.env`):
      `ssh pi 'set -a; . ~/.env; set +a; python3 /tmp/discover_places.py --stdout' > site/data/directory.json`
      then commit. New venues open often, so a **weekly** refresh keeps the directory fresh.
      Options: (a) a weekly Pi cron that runs it + commits/pushes, or (b) add
      `GOOGLE_PLACES_API_KEY` as a GitHub Actions secret and a weekly workflow. Tell me which
      and I'll wire it up. (Costs ~$1 of Places quota per run.)

- [ ] **Submit the sitemap to Google Search Console** — `https://robertcorey.github.io/jcc-pickleball/sitemap.xml`
      (now 192 URLs: homepage + 88 venue pages + session pages). Crawlers only auto-read
      robots.txt from the domain root, which is shared across your GitHub Pages projects, so
      Search Console submission is the reliable indexing path. Needs your Google account.

- [ ] **Centerline Pickleball Club (Warwick) — CourtReserve org id.** We now pull LIVE open-play
      schedules from 4 RI clubs via CourtReserve (Pickleball Citi, Ocean State, East Bay, LIL Rhody).
      Centerline uses CourtReserve too but their Wix site never exposes the org id (only a generic
      register link). If you can get it (ask the club, or grab it from a logged-in member's calendar
      URL `app.courtreserve.com/Online/Calendar/Events/<ORGID>/month`), it's a one-line add to
      `COURTRESERVE_ORGS` in `scraper/sources.py` → instant 5th live club.

- [ ] **Bristol registration URL** — the Bristol CTA still points at the club's public Google
      Calendar; couldn't verify the official PlayerLineUp link. One-line swap in
      `scraper/bristol_ics.py:VENUE["registration_url"]` when you have it.

## Resolved
- [x] **Google Places API key** — already present on the Pi (`~/.env GOOGLE_PLACES_API_KEY`),
      verified working (returns RI pickleball venues). No new account/billing needed.
- [x] **Namespaced `:` share URLs on GitHub Pages** — verified live (`/s/jcc-ri:130888277/` → 200).
- [x] **GoatCounter blocked by Pi-hole** — allowlisted goatcounter.com / www / gc.zgo.at.
- [x] **Bristol directory linkage** — added Town Common geo so it links to its `/v/` page.

## Notes (non-blocking)
- The directory includes ~73 "maybe"-confidence venues (YMCAs, rec centers, racquet clubs,
  public town courts/parks that Google associates with pickleball) alongside 15 dedicated
  pickleball clubs. Town parks are real RI pickleball spots, but a few may be courts-by-listing
  only — acceptable for a discovery directory; the dedicated clubs are foregrounded.
- GoatCounter: still worth purging the early `/shell-verify` test hits + setting ignore-IP.
