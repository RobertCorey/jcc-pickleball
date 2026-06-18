# GROWTH — Open Play RI (autonomous growth loop)

Mandate (Rob, /loop every 15m): "make this site a success … get users … increase
KPIs for this type of aggregator site. You are in charge."

## North-star + KPIs
A local-discovery aggregator wins on **organic search traffic → engaged sessions →
register-clicks** (no ad budget). Tracked KPIs:
- **Indexable surface** — # of locally-targeted pages Google can rank (home, /v/ venue,
  /t/ town). More high-quality local pages = more long-tail "pickleball in <town> RI" hits.
- **Organic visits** — GoatCounter (jcc-pickleball.goatcounter.com). Baseline below.
- **Register-clicks** — the conversion event already tracked (`register-click`).
- **Coverage** — # venues (85) + # with LIVE schedules (2). Live schedules are the
  differentiator vs a plain Google search.
- **Freshness/accuracy** — hourly schedule refresh; weekly directory refresh.

## Strategy (highest leverage first)
1. **Programmatic local SEO** — one strong landing page per town ("pickleball in <town>, RI"),
   per venue, and per intent (indoor, free public courts, beginners). [in progress]
2. **More live schedules** — each new integrated source adds real value + indexable session
   pages competitors don't have. Backlog of RI sources below.
3. **Internal linking + schema** — ItemList/Breadcrumb/FAQ; town↔venue↔session graph so crawlers
   find everything and rich results trigger.
4. **Engagement** — "near me" / map, "this week" view, shareable pages (already have OG cards).
5. **Distribution Rob can do** — Search Console submit, RI pickleball FB groups, the Cloudflare
   domain. (Logged in NEEDS-HUMAN, not blocking.)

## KPI log
- 2026-06-18 — baseline: 85 venues, 2 live, 189 sitemap URLs (1 home + 85 venue + 103 session).
  GoatCounter: 3 visits / 7 days, ALL self-test (unknown referrer, my Chrome/macOS) → ~0 real
  users. Site is new + not yet indexed. Implication: invest in rankable surface + indexing now;
  conversions lag indexing by days/weeks.

## Iteration log
- (iter 1, 2026-06-18) ✅ Shipped **28 town landing pages** `/t/<town>/` ("pickleball in <town>, RI")
  with CollectionPage/ItemList + Breadcrumb schema, venue lists, nearby-town cross-links. Wired
  internal links: homepage town headers → /t/, venue breadcrumb city → /t/, venue↔town↔venue.
  Sitemap 189 → 216 URLs. Checked GoatCounter baseline (≈0 real users yet).

- (iter 2, 2026-06-18) ✅ **Indexing push** — root robots.txt is 404 (no crawl restrictions),
  so the site is crawlable; it's just undiscovered. Added (a) **IndexNow** key file
  (`site/76c5fcc110e2a861ce80e681690b95d2.txt`) → submit URLs to Bing/Yandex/DuckDuckGo without
  a Google account; (b) homepage **Organization + WebSite** JSON-LD with a SearchAction; (c) the
  directory search is now URL-addressable (`?q=`) → shareable searches + valid SearchAction.
  Real unlock still = Search Console (Rob's Google acct, in NEEDS-HUMAN).

## Ops notes
- **sessions.json merge conflicts**: the hourly bot commits `site/data/sessions.json` to main, so
  every feature push conflicts on it. The deploy job rebuilds it fresh from sources anyway, so the
  committed copy doesn't affect the live site. Future iterations: after `build_site.py`,
  `git checkout site/data/sessions.json` to drop the regenerated data file and commit only
  source/template/HTML — avoids the conflict entirely.
- IndexNow key: `76c5fcc110e2a861ce80e681690b95d2` (file at site root). Resubmit new/changed URLs
  on big content changes: POST to `https://api.indexnow.org/indexnow`.

## Backlog / ideas (pick the top item each iteration)
- [ ] Town landing pages `/t/<town>/` — aggregate venues per town, ItemList schema. ← iter 1
- [ ] Intent pages: "indoor pickleball in RI", "free public pickleball courts RI", "beginner open play".
- [ ] Add more live-schedule sources (East Greenwich RecDesk, Centerline, Newport Pickleball Club,
      Pickleball Citi, RI YMCAs) — one adapter at a time.
- [ ] Homepage: link the town pages; add a "browse by town" jump nav.
- [ ] "Near me" geolocation sort on the directory.
- [ ] Per-venue OG cards for richer social shares (Playwright in CI already does session cards).
- [ ] WebSite + SearchAction (sitelinks search box) schema on home.
- [ ] Submit sitemap to Search Console (NEEDS-HUMAN — Rob's Google acct).
