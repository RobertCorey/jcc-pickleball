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

- (iter 3, 2026-06-18) ✅ **Intent/collection guides** `/guide/<slug>/`: indoor-pickleball-rhode-island
  (20), free-public-pickleball-courts-rhode-island (46), pickleball-clubs-rhode-island (17). Curated
  venue lists grouped by town, CollectionPage/ItemList + Breadcrumb schema, cross-links. Homepage
  surfaces them (guide chips above directory + footer). Config-driven COLLECTIONS in build_site.py.
  Sitemap → 219 URLs. Used the streamlined commit (discard sessions.json → no merge conflict ✓).

- (iter 4, 2026-06-18) ✅ **Fixed blocked deploys (CI reliability).** Iter 3's guides wouldn't go
  live: the "Install Playwright + Chromium" step HUNG ~10min on Chromium download, stalling every
  deploy (and silently risking stale schedule data). `continue-on-error` doesn't catch a hang —
  added `timeout-minutes: 4` to that step + `12` to the scrape step. Redeployed clean; all 3 guides
  now live (200), sitemap 219. Re-submitted guides to IndexNow (HTTP 200). Lesson: best-effort
  steps need timeouts, not just continue-on-error.

- (iter 5, 2026-06-18) 🔨 **3rd live source — CourtReserve (in progress, delegated agent).** Found
  that 5 top RI clubs all use **CourtReserve**: Pickleball Citi (org 11577), Ocean State (7726),
  East Bay (16386), LIL Rhody (9068), Centerline (tbd). One adapter → up to 5 live venues. Public
  events endpoint confirmed (no auth wall): `GET app.courtreserve.com/Online/Calendar/ReadCalendarEvents/<orgId>`
  returns a valid Kendo JSON envelope `{"Data":[],"Total":..}`. Needs the right `jsonData`/date params
  (scrape `requestData` token + `CostTypeId` from `/Online/Calendar/Events/<orgId>/month`; see
  getCriteriaForRead result fields). Launched a background agent to crack the params + build
  `scraper/courtreserve.py` + integrate into sources.py (best-effort, stdlib-only, pickleball
  open-play only). Will review + merge its branch when it reports. THE high-value differentiator —
  more real session pages competitors don't have.

- (iter 6, 2026-06-18) ✅ **"Near me" geolocation sort** (index.html only, chosen to not collide with
  the in-flight CourtReserve agent's sources.py work). One-tap button → directory re-sorts by distance
  from the user (haversine, miles shown), toggles back to town grouping. Serves the core "pickleball
  near me" intent + tracks a `near-me` GoatCounter event. Verified in-browser with mocked geolocation.

- (iter 7, 2026-06-18) ✅✅ **BIG WIN — 4 new live-schedule venues via CourtReserve.** The delegated
  agent cracked CourtReserve's public events API (POST /Online/Calendar/ReadCalendarEvents with
  KendoStart/End as {Year,Month,Day} objects + a scraped requestData token; no auth). Built
  `scraper/courtreserve.py` (stdlib, best-effort, open-play-only filter) + registered 4 orgs in
  sources.py: Pickleball Citi, Ocean State, East Bay, LIL Rhody. **Live venues: 2 → 6.** Driver-verified:
  JSON-LD clean on all session pages (no injection), JCC/Bristol unchanged, all 4 venue pages show
  live schedules. Tuned volume to keep it sane: WINDOW_FWD_DAYS 45→21 (684 sessions vs 1248),
  OG_RENDER_CAP=220 (CI renders ≤220 cards, not 1248 → no build timeout), sitemap = upcoming sessions
  only (719 urls). Centerline (5th club) needs its org id — in NEEDS-HUMAN.
  ✅ Post-deploy VERIFIED: CI's runner fetched CourtReserve fine (no Cloudflare block) — prod
  sessions.json has all 6 sources with live data (citi 135, ocean 134, eastbay 152, lilrhody 161).
  4 club venue pages live (200) w/ schedule blocks; submitted to IndexNow. Hourly cron keeps it fresh.
  Watch item: if CourtReserve/Cloudflare tightens, those sources fail isolated (build emits
  ::warning::source failed) → site degrades to JCC+Bristol, not broken. Consider a post-deploy alert
  if live-source count drops (backlog).

- (iter 8, 2026-06-18) ✅ **Homepage session-list cap.** The 6-venue jump pushed the upcoming-session
  list to ~600 rows (overwhelming/slow). Now shows soonest 60 + "Show all N" button; venue/day filters
  reset the cap. index.html only. Verified in-browser (60→602 on expand, resets on filter).

- (iter 9, 2026-06-18) ✅ **Lighthouse audit + a11y fixes.** Ran Lighthouse (mobile) on the live site:
  SEO 100, Best Practices 96, Accessibility 96. Fixed the 2 contrast failures (--ink-faint + .avail
  status colors below 4.5:1 AA) → **Accessibility 100**. Sole remaining item is the ad-blockable
  analytics beacon (environmental). Baseline scores now: SEO 100 / A11y 100 / BP 96 / Agentic 100.

- (iter 10, 2026-06-18) ✅ **"State of Pickleball in RI" data report** (`/rhode-island-pickleball-report/`).
  Auto-updating insights page from aggregated data: 85 venues/28 towns/601 sessions, busiest-day +
  time-of-day + top-town + breakdown bar charts, Article+Breadcrumb schema. A distinctive, citable
  asset (the main link-earning lever without account access) that ranks for informational RI pickleball
  queries. Linked from homepage footer + sitemap. Stats refresh every build.

- (iter 11, 2026-06-18) ✅ **Calendar subscriptions (.ics).** Verified site still NOT indexed (Google
  `site:` empty — normal for a ~1-day-old site hrs after IndexNow; acquisition stays gated on
  Search Console). Built retention feature instead: an all-RI `open-play-rhode-island.ics` (599 events)
  + per-live-venue `/v/<slug>/open-play.ics` (6 feeds), proper VTIMEZONE/CRLF, escaped. "📅 Subscribe
  in your calendar" links (webcal://) on the homepage + each live venue page → users add RI open play
  to their phone/Google calendar and get auto-updates = reason to return. (Process fix adopted: batch
  growth-log into the feature commit, one push/iteration, to avoid concurrency deploy-cancels.)

- (iter 12, 2026-06-18) ✅ **GitHub-as-discovery + perf check.** (a) Verified the homepage payload is
  fine: sessions.json 1.2MB raw but **53KB gzipped** (Pages gzips) — no perf issue, no action. (b) Real
  autonomous Google-discovery lever: the repo is PUBLIC (Google crawls github.com), but its homepageUrl
  + description were EMPTY and the README was stale ("CourtTime/JCC"). Set repo homepageUrl → live site,
  added a keyworded description, and rewrote README to lead with the live link + "Open Play RI" + RI
  pickleball keywords. GitHub repo pages are indexed → this gives Google a crawlable path to the site
  without Search Console (still weak vs SC, but it's a real inbound link I control).

- (iter 13, 2026-06-18) ✅ **Health check + source-health guard.** Live system audit: build fresh
  (11 min), **all 6 sources OK** (84/18/134/134/152/161), no broken pages (sampled all page types →
  200). Bing index check inconclusive (CAPTCHA-blocked; still early). Shipped a guard so the core
  asset (live data) can't fail silently: build.json now advertises per-source health
  (`n_ok_sources` + `sources[]`) — pollable by an external monitor or by THIS loop each cycle — and
  any failed/empty/missing expected-live source emits a loud `::warning::` + step-summary on the
  Action. Going forward: poll build.json's source health each iteration (cheap asset protection).

- (iter 14, 2026-07-03) ✅ **Root-caused the indexing stall + fixed it; spun up a
  growth team.** A week after the openplayri.com migration, GA4/Search Console
  showed the real picture: ~0 real users (GA4 "traffic" was almost entirely
  bot/datacenter-city sessions — Council Bluffs, Boardman, Ashburn), 0 organic
  search clicks, and 672 of 676 sitemap URLs stuck "Discovered — currently not
  indexed." Ran a 4-agent workflow (SEO audit + real RI-community research, then
  outreach drafts + a concrete fix plan) — added 8 curated marketing/growth
  subagents to `.claude/agents/` (adapted from
  github.com/msitarzewski/agency-agents, scoped to this project's constraints:
  no ad budget, no social accounts, drafts only). The audit found and I shipped
  the actual root cause: **the homepage — the site's only high-authority page —
  had ZERO server-rendered links to any of the 36 venue or 21 town pages**
  (directory/session lists are 100% client-JS-injected from `fetch()`), so
  Google's HTML-only crawl of the domain's top page passed zero link equity
  downstream. Fixed: (1) homepage now server-renders real `<a href="v/…">` /
  `<a href="t/…">` links (a collapsed "every venue" disclosure + a footer towns
  column) — `site/index.html` is no longer hand-authored, it's now
  `scraper/templates/index.html` built by `build_homepage()`; (2) every session
  page (92% of the site's URLs) now links back to its own venue page + carries
  BreadcrumbList schema — previously a dead-end leaf pointing only at the
  homepage; (3) the sitemap no longer lists every date-instance of a recurring
  weekly slot (770 → 284 URLs) — only the soonest occurrence of each distinct
  (venue, weekday, time) slot is sitemapped/indexable, later dates stay live +
  linked but self-tag `noindex,follow` so ~575 near-duplicate pages stop
  diluting crawl trust. Also manually requested priority indexing (Search
  Console URL Inspection) for the homepage, all 3 guides, the data report, and
  the two highest-traffic town pages. Verified: exactly 36/21 SSR links on the
  homepage, 0 session pages missing a venue link or BreadcrumbList, sitemap
  count == non-noindexed page count (222 == 222) by construction. Outreach:
  real (verified) RI pickleball communities + drafted posts/emails saved to
  `OUTREACH.md` for Rob to personally send — no agent has or will post/send
  anything on his behalf. **Not shipped this iteration** (queued as backlog):
  per-page-type `lastmod` (currently identical across all URLs every build,
  which erodes Google's trust in the freshness signal) and cross-linking the
  data report / guides into the town/venue link graph.

## Ops notes
- **sessions.json merge conflicts**: the hourly bot commits `site/data/sessions.json` to main, so
  every feature push conflicts on it. The deploy job rebuilds it fresh from sources anyway, so the
  committed copy doesn't affect the live site. Future iterations: after `build_site.py`,
  `git checkout site/data/sessions.json` to drop the regenerated data file and commit only
  source/template/HTML — avoids the conflict entirely.
- IndexNow key: `76c5fcc110e2a861ce80e681690b95d2` (file at site root). ✅ 216 URLs submitted &
  accepted 2026-06-18. NOTE: `api.indexnow.org` returned `SiteVerificationNotCompleted` (403) on
  first try, but **`https://www.bing.com/indexnow`** accepted the same payload (HTTP 200). Use the
  Bing endpoint. Resubmit new/changed URLs after big content changes (payload at /tmp; or
  regenerate from the live sitemap).

## Backlog / ideas (pick the top item each iteration)
- [ ] **Per-page-type sitemap `lastmod`.** Currently every URL gets the same
      build-timestamp date every hour regardless of whether that page's content
      actually changed — Google discounts a freshness signal that never varies
      meaningfully. Venue/town/guide/report pages should carry a lastmod tied to
      when their rendered content last changed (hash directory fields, persist
      last-changed date). Session pages can keep the build timestamp (their
      availability genuinely changes hourly). ← flagged iter 14, not yet shipped.
- [ ] **Cross-link the data report + guides into the town/venue graph.**
      `/rhode-island-pickleball-report/` and the 3 `/guide/` pages don't link out
      to most `/t/` or `/v/` pages — they're currently link-equity dead ends
      despite being the most citable/linkable assets on the site. ← flagged iter 14.
- [ ] **Harden CI deploy (reliability = KPI).** The "Install Playwright + Chromium" step hung ~10min
      on a runner during iter 3 (Chromium download), stalling the deploy. OG-image rendering is
      best-effort (falls back to generic og.png), so it must never block a deploy. Add a `timeout-minutes`
      to that step (and/or the job) + `continue-on-error` so a flaky Chromium install can't stall
      publishing. Workflow: .github/workflows/scrape-and-deploy.yml.
- [ ] Town landing pages `/t/<town>/` — aggregate venues per town, ItemList schema. ← iter 1
- [ ] Intent pages: "indoor pickleball in RI", "free public pickleball courts RI", "beginner open play".
- [ ] Add more live-schedule sources (East Greenwich RecDesk, Centerline, Newport Pickleball Club,
      Pickleball Citi, RI YMCAs) — one adapter at a time.
- [ ] Homepage: link the town pages; add a "browse by town" jump nav.
- [ ] "Near me" geolocation sort on the directory.
- [ ] Per-venue OG cards for richer social shares (Playwright in CI already does session cards).
- [ ] WebSite + SearchAction (sitelinks search box) schema on home.
- [ ] Submit sitemap to Search Console (NEEDS-HUMAN — Rob's Google acct).
