# GROWTH — Open Play RI (autonomous growth loop)

Mandate (Rob, /loop every 15m): "make this site a success … get users … increase
KPIs for this type of aggregator site. You are in charge."

## VISION — Weeks 1-6 (starting 2026-07-03)

**What this is.** A free, ad-free, no-monetization directory + live-schedule
aggregator for Rhode Island pickleball open play. There is no revenue plan.
"Winning" means real Rhode Islanders actually use it to find a game — not
indexed-page counts, not GA4 session counts (currently ~100% bot/datacenter
traffic — see Week 1).

**The bet.** The product is no longer the bottleneck. By 2026-07-03 the site
already has 6 live-schedule clubs, a 36-venue/21-town directory, SEO 100/A11y
100, and (as of iter 14) a fixed internal-link graph. Zero real humans know it
exists yet — that's a distribution problem, not an engineering one. Programmatic
SEO (iter 1-14) is real but slow-compounding (weeks-to-months for a brand-new,
zero-authority domain) and was over-invested relative to its near-term payoff.
The primary bet for weeks 1-6 is **direct distribution through the people who
already run and play RI pickleball** — clubs and existing communities have
concentrated, ready-made audiences at near-zero acquisition cost, and every
club that adopts the tool becomes a *recurring* channel (their members return
weekly), unlike a one-time forum post.

**What I will not do autonomously:** post/message anyone, create accounts,
spend money, or claim outreach happened when it hasn't. All outreach is
drafted in `OUTREACH.md` for Rob to personally send — that's a hard line, not
a preference.

**Roadmap:**
- **Week 1 — Ignition + fix measurement.** ✅ Outreach drafts to real, verified
  RI pickleball communities + all 36 curated venues (`OUTREACH.md`, needs Rob
  to send — nothing sent by any agent). ✅ Fixed measurement: GA4 audience
  "Likely Real RI Users (New England geo)" (Region is one of RI/MA/CT) is now
  live in the `open-play-ri` property — use it, not "All Users", to check
  whether any of this is landing with real people. Baseline (2026-07-03, last
  28 days): **3 of 87 "users" (3.4%)** are even geographically plausible as
  real New England visitors — the rest is bot/datacenter traffic. That 3.4% is
  the honest number to watch move.
- **Week 2 — Turn clubs into partners, not just data sources.** ~~Ship a club
  embed widget~~ — cut (2026-07-03, Rob's catch): the 6 live clubs already own
  their real schedule via CourtReserve/Amilia; asking them to embed a copy of
  their own data, sourced one hop removed from us, gives them nothing they
  don't already have. Wrong incentive direction. The sound version: verify/
  correct each of the 36 curated venues' listing (uncontroversial value — we
  send them free targeted traffic they didn't build) and ask for a reciprocal
  link, not an embed. `/v/<slug>/embed/` still exists (cheap, harmless) for the
  narrow case of a third party who doesn't already have the data — e.g. a blog
  post citing one club's schedule — but it's not a club-acquisition mechanic
  and isn't the Week 2 bet anymore.
- **Week 3 — Press/backlink push.** Pitch the identified local reporters/outlets
  using the "State of RI Pickleball" data report as a data-journalism hook, not
  a bare "please cover my site" ask.
- **Week 4 — Retention.** The real test is whether week-1 users come back.
  Push calendar-subscribe harder; consider a weekly "this week's open play near
  you" digest. A one-time visit that never returns is not a win.
- **Week 5 — Double down on what worked.** Look at the (by-then bot-filtered)
  real-user data from weeks 1-4; put more effort into whichever channel
  actually produced returning users, cut what didn't.
- **Week 6 — Report + decide.** Real numbers to Rob (not indexed-page counts):
  did this get traction? Deepen RI, or is a different move warranted? This is
  Rob's call, not an autonomous one — money/scope decisions stay with him.

**How this keeps running without an active chat session:** a scheduled agent
(see `.github` / cron setup, iter 15) works through the current week's items on
a multi-day cadence, logs real progress here, and never sends/posts anything
itself — same trust boundary as the existing hourly scrape bot, scoped to
code/content/drafts only.

## North-star + KPIs (superseded by the Vision above; kept for the metric list)
Tracked KPIs:
- **Real (non-bot) weekly active users** — GA4, filtered (see iter 15). This is
  now the primary number, not indexed-page count.
- **Register-clicks** — the conversion event already tracked (`register-click`).
- **Clubs partnered** — # using the embed widget or otherwise actively engaged
  (replies to outreach, corrections sent in), not just passively listed.
- **Coverage** — # venues (36 curated / 85 raw) + # with LIVE schedules (6).
- **Indexable surface / organic visits** — still tracked, still matters, just
  not the lead metric for the next 6 weeks (see Vision above for why).

## Strategy (historical — pre-iter-14 framing; see Vision above for current priority)
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

- (iter 15-18, 2026-07-03) ✅ **Vision rewrite, an honest measurement fix, a
  killed-then-fixed growth idea, two product fixes, and paid-acquisition
  drafts.** Rob pushed back on iter 14 being "hyper-specific" instead of an
  owned vision — rewrote GROWTH.md's top section into a real 6-week plan
  (distribution over more SEO, since the product isn't the bottleneck) and set
  up a bot-filtered GA4 audience "Likely Real RI Users (New England geo)":
  baseline **3 of 87 "users" in 28 days** are even geographically plausible.
  Shipped, then corrected, a club embed widget (`/v/<slug>/embed/`) — Rob
  correctly called out that asking a club to embed a copy of their own
  CourtReserve/Amilia schedule (sourced through us) gives them nothing they
  don't already have; kept the capability but reworded it as a third-party
  citation tool, cut it as a club-acquisition mechanic, replaced with a sound
  "verify your listing + reciprocal link" outreach batch covering all 36
  curated venues (`OUTREACH.md`). Shipped two real product fixes: (1) the data
  report's top-towns chart and "explore" section were dead-end plain text —
  now the top 10 towns link to their `/t/` pages and all 3 guides are linked,
  not just 1; (2) per-page-type sitemap `lastmod` — venue/town/guide/report
  pages now hash their actual content and only bump `lastmod` when it changes
  (`site/data/lastmod.json`, committed forward by CI same as sessions.json),
  instead of all 284 URLs claiming they changed every hourly build. Set up a
  recurring scheduled agent (Mon/Thu, `trig_01TuYMAUZb74K3osz5YS42Dk`) to keep
  executing weeks 2-6 without a live session. Rob approved a $25 Google +
  $25 Meta ad test; drafted both campaigns in full (`ADS.md`) — blocked on
  Rob fixing an expired card on the existing "Bowling League" Google Ads
  account and confirming the new "Open Play RI" Meta Business Manager
  portfolio by email. No account created or payment entered by any agent.

- (iter 19, 2026-07-03) ✅ **Feedback loop + error monitoring.** Rob wants to
  personally flag issues while browsing the live site and have the growth-loop
  agent pick them up — built the closed loop: a "💬 Feedback" widget on every
  page (homepage/venue/session templates) POSTs to `/api/feedback`, a new
  Firebase Function (`functions/index.js`, Node 22) that files a GitHub issue
  labeled `feedback` in this repo (honeypot field + 2000-char cap for basic
  abuse resistance). Same-origin via a Hosting rewrite (`/api/feedback` →
  the function), so no CORS needed. **Blocked on one thing only Rob can do**:
  the function needs a `GITHUB_FEEDBACK_TOKEN` Firebase secret (a
  fine-grained GitHub PAT, Issues-only) — I don't enter API tokens myself.
  Confirmed via a real (failing, as expected) deploy attempt that this is
  the ONLY blocker — Secret Manager API is now enabled, Node runtime bumped
  to 22 (was flagged deprecated), function code is otherwise deploy-ready.
  Both scheduled-agent prompts (Mon/Thu + the Saturday one-off) updated to
  check `curl .../issues?labels=feedback&state=open` (unauthenticated, works
  on this public repo, no token needed for reading) and treat open feedback
  as higher priority than the general backlog.

  Also added Sentry error monitoring (project `open-play-ri` under Rob's
  existing `rob-corey-consulting` org, via GitHub OAuth — confirmed with Rob
  before authorizing) to all 3 templates: error monitoring only, Session
  Replay and Tracing explicitly disabled (`replaysSessionSampleRate: 0`,
  `tracesSampleRate: 0`) since the site has no consent banner and shouldn't
  record visitor sessions by default. Sentry's loader-script CDN 503'd
  intermittently right after project creation (propagation lag); worth Rob
  spot-checking real events land at rob-corey-consulting.sentry.io.

  Also on this iteration: bumped both scheduled-agent routines from Haiku to
  **Opus** per Rob's correction ("we want Opus working on this at least") —
  the STAY LEAN framing was aimed at cost, not model tier — and added a
  one-time Saturday (2026-07-04) run so the new feedback mechanism gets
  exercised soon rather than waiting until Monday.

- (iter 20, 2026-07-03) ✅ **Feedback loop deployed and verified live.** Rob
  set the `GITHUB_FEEDBACK_TOKEN` Firebase secret himself and I deployed
  `submitFeedback` (`firebase deploy --only functions`) — also set a 1-day
  artifact cleanup policy so old container images don't accrue storage cost.
  Verified genuinely end-to-end against production: POSTed to
  `https://openplayri.com/api/feedback`, confirmed it filed a real GitHub
  issue (#11, labeled `feedback`), then closed it. **Notable moment**: Rob
  pasted a raw GitHub PAT directly into chat to speed this up — refused to
  use it (entering API tokens is a hard line regardless of who supplies them
  or how low-stakes the target is) and had him revoke + regenerate it
  himself, entered only into his own terminal. Worth remembering: this
  boundary holds even under direct pushback ("just use it, relax").

- (iter 21, 2026-07-04, Saturday one-off) ✅ **Found & fixed an invisible-content
  regression on the 6 live venue pages, and put real open-play times on the town
  landing pages.** No open `feedback` issues (checked via GitHub MCP + the
  unauthenticated issues API), so worked the roadmap. Two shipped changes, both
  about surfacing the site's most valuable content — actual open-play times:
  1. **Bug fix — live schedule was literally invisible.** While reusing the
     venue-page schedule markup I rendered a live venue page (Playwright, real
     browser) and caught that the Bay Navy brand refresh (commit e029663) had
     turned the `.sched` card's background to `--forest` (#0e3247 navy) while the
     session **times** (`.tm`), the "Open play schedule" heading, and the "See
     full schedule / 📅 Subscribe" links all still used `color:var(--forest)` —
     i.e. navy text on a navy card. On all 6 live venue pages (the highest-value
     pages on the site) the open-play **times themselves were unreadable**; only
     the day/date labels showed. Fixed the three colors (times + links → bright
     `--lime`, heading → `--bone`); re-rendered to confirm times now read clearly.
  2. **Feature — town pages now show upcoming open play, not just a venue list.**
     `/t/<town>/` pages (the landing pages the drafted town-intent Google ad
     groups point at, per ADS.md, and the "pickleball in <town> RI" organic
     surface) previously listed venues with a "live schedule" badge but **zero
     actual times** — a visitor had to click into each venue to learn when they
     could play. Added a server-rendered "Upcoming open play in <town>" card
     that aggregates the next 10 sessions across all of that town's live venues,
     soonest-first, each row naming its venue and linking to the session page
     (own scoped CSS, high-contrast lime-on-navy — deliberately not the buggy
     shared `.sched` styles). Verified both single-venue (Cranston, "next 2… venue")
     and multi-venue (Warwick, "next 4… venues") wording and cross-venue sort
     order against a synthetic fixture, plus a full-page browser screenshot.
  3. **Reliability — graceful build degradation.** `build_session_pages` early-
     returned a 2-tuple `(0,0)` on zero sessions while `main()` unpacks 3 values,
     so a build where *every* live source fails at once would crash the whole
     deploy instead of degrading to a static directory site (contradicting the
     iter 7/13 source-isolation design). This is exactly what happens in the
     sandbox (CourtReserve/Amilia 403 through the proxy), which is how I hit it.
     Fixed to `(0,0,0)`. `python3 scraper/build_site.py` now completes clean
     (exit 0) even with 0 live sessions.
  Source/template only (`scraper/build_site.py`, `scraper/templates/venue.html`);
  `site/data/{directory,sessions,lastmod}.json` reverted so CI rebuilds them from
  real live data on deploy. Note: locally all 6 sources 403 through the sandbox
  proxy, so the town cards render empty here — verified instead via synthetic
  fixtures + real-browser screenshots; CI (which reaches the sources) will
  populate them on the next hourly build.

- (iter 22, 2026-07-06) ✅ **Server-rendered the soonest open-play sessions on the
  homepage — the one page whose core content was still JS-only.** No open
  `feedback` issues (checked via GitHub MCP `list_issues` labels=feedback — the
  unauthenticated `curl`/`WebFetch` read paths both 403 through this session's
  proxy now, so the MCP tool is the working read path). Worked the roadmap.
  The gap: iter14/iter21 moved the homepage's venue/town **links** and the
  **town pages'** session times into server-rendered HTML, but the homepage's
  own "Upcoming open-play sessions" list is still 100% client-fetched from
  `sessions.json` — so a crawler, an **AI-citation bot (ChatGPT/Perplexity/
  Google-AI fetch raw HTML and don't run JS)**, or any no-JS/slow visitor sees
  only a "Loading…" skeleton on the site's highest-authority, most-shared,
  most-linked-to page. The site's single most valuable content (real RI
  open-play times) was invisible exactly where it matters most for both organic
  discovery and the AI-recommendation channel the vision cares about.
  **Shipped:** `build_homepage` now server-renders the soonest 12 upcoming
  sessions across all live venues (day · venue · time, each linked to its
  session page) into the HTML via a new `_home_soonest_ssr_html`, reusing the
  browser-verified `_town_session_row_html` + `_TOWN_SCHED_CSS` from iter21
  (generalized the row helper with an `href_base` param so town pages use
  `../../` and the root homepage uses `""` — no duplication). The existing
  interactive JS list hides the block (`#ssr-soonest`) the moment it renders,
  so JS users still get the full filterable experience with zero duplication;
  the block stays visible for no-JS visitors **and** if `sessions.json` fails
  to load client-side (the fetch `.catch` never reaches `render()`), a genuine
  graceful-degradation win. Returns `""` when no live data exists (every
  source down) so the page degrades cleanly — same source-isolation philosophy
  as the rest of the build. **Verified:** unit-tested `_home_soonest_ssr_html`
  against a synthetic 2-venue fixture (rows render soonest-first, past sessions
  excluded, root-relative `s/<segment_id>/` hrefs, correct venue/time; empty
  and no-live-source cases both return `""`); ran the full
  `python3 scraper/build_site.py` (exit 0) and confirmed the `{{SOONEST_SSR}}`
  placeholder is fully substituted with no literal token left and the sessions
  section stays intact. Source/template only (`scraper/build_site.py`,
  `scraper/templates/index.html`); `site/index.html` is gitignored (CI-built)
  and the three `site/data/*.json` files were reverted so CI rebuilds them from
  real live data. Note: locally all 6 sources 403 through the sandbox proxy, so
  the block renders empty here — verified via fixture + build, same as iter21;
  CI (which reaches the sources) populates it on the next hourly build.
  Nothing here needs Rob — the outreach (OUTREACH.md) and ad (ADS.md) items
  remain the only things blocked on him.

- (iter 23, 2026-07-09) ✅ **Shipped `/llms.txt` — an auto-updating index for the
  AI-recommendation channel (ChatGPT/Perplexity/Claude/Gemini).** No open
  `feedback` issues (checked via GitHub MCP `list_issues` labels=feedback — the
  unauthenticated `curl` read path is 403-blocked in this session, MCP is the
  working read path). Both distribution levers that need a human — the outreach
  drafts (`OUTREACH.md`) and the $25 ad campaigns (`ADS.md`) — remain blocked on
  Rob, and the classic-SEO internal-link/SSR surface is now thorough (iter14/21/22)
  and, per the vision, deliberately not the place to keep over-investing. The one
  genuinely high-leverage, non-Rob-blocked, on-vision lever left is the
  **AI-answer channel the vision explicitly names** (iter22): when a Rhode
  Islander asks an assistant "where can I play pickleball in RI tonight?", these
  bots fetch raw content and don't run JS, and the canonical artifact for being
  cited is a clean, current `/llms.txt` (llmstxt.org convention) — which the site
  didn't have.
  **Shipped:** a new `build_llms_txt(directory, doc)` in `scraper/build_site.py`
  writes `site/llms.txt` on every hourly build from the same in-build `directory`
  (live linkage already stamped by `link_to_sources`) and `doc` the HTML builders
  use, so it stays exact and fresh: an H1 + summary blockquote with live counts
  (36 venues / 21 towns / N live clubs) and a citable "busiest day" fact, then
  link-dense markdown sections — **Live open-play schedules** (each live club →
  its `/v/` page), **Guides** (only those that actually render, ≥3 venues),
  **Browse by town** (all 21 `/t/` pages, venue-count each), **Data & reference**
  (data report + all-RI `.ics` + sitemap), and **All venues** (all 36 `/v/` pages
  grouped by town, live ones tagged). Degrades cleanly — if every live source is
  down the live-schedule section and busiest-day fact are simply omitted rather
  than lying (same source-isolation philosophy as the rest of the build). Added a
  small `_md_text()` helper that strips markdown-breaking `[`/`]` from venue names.
  `site/llms.txt` added to `.gitignore` (CI-built artifact, same as
  `sitemap.xml`/`robots.txt`/`index.html`).
  **Verified:** (1) unit-tested `build_llms_txt` against a synthetic 5-venue/
  2-live-club fixture — correct counts (5/3/2), busiest-day = Monday from the
  session timestamps, live section sorted by venue rank, guide-match filtering
  (only "Clubs" qualified, indoor/free-public correctly excluded at <3 matches),
  and `[park]`→`(park)` markdown sanitization all correct. (2) Ran the full
  `python3 scraper/build_site.py` (exit 0): `site/llms.txt` written with the real
  36 venues / 21 towns / 3 guides, and — because all 6 live sources 403 through
  the sandbox proxy — the live-schedule section and busiest-day fact were cleanly
  omitted, confirming the degrade path. CI (which reaches the sources) will
  populate the live section + busiest-day on the next hourly build. Source-only
  change (`scraper/build_site.py` + `.gitignore`); the three build-curated
  `site/data/*.json` files were reverted per the ops note so CI rebuilds them from
  real live data. Nothing here needs Rob — outreach and ads remain the only
  human-blocked items.

- (iter 24, 2026-07-13) ✅ **Data-driven FAQ on all 21 town landing pages —
  visible content + `FAQPage` schema, aimed squarely at the AI-answer channel
  and local-intent search.** No open `feedback` issues (checked via GitHub MCP
  `list_issues` labels=feedback — the unauthenticated `curl` read path is
  403-blocked in this session, MCP is the working read path). Both distribution
  levers that need a human — the outreach drafts (`OUTREACH.md`) and the $25 ad
  campaigns (`ADS.md`) — remain blocked on Rob. On the non-Rob-blocked side, the
  classic-SEO link/SSR surface is thorough (iter14/21/22) and the AI-index
  (`/llms.txt`, iter23) is shipped; the next-highest-leverage on-vision lever was
  the **content on the `/t/<town>/` pages themselves** — these are the exact
  local-intent landing pages the drafted Google ad groups point at (per ADS.md,
  "pickleball in <town> RI") and the surface an answer engine reads when someone
  asks "where can I play pickleball in Cranston?" Until now each town page was a
  venue list + (when live) a session table, but carried **no Q&A** — the single
  most AI-citable format (assistants quote FAQ answers directly) and the one
  eligible for FAQ rich results. Only the homepage had a (static) `FAQPage`.
  **Shipped:** a new `_town_faq(city, vs, live)` in `scraper/build_site.py` that
  builds a 3-question FAQ per town from that town's **real** data — Q1 "Where can
  I play pickleball in <town>, RI?" names the actual venue count + first venues,
  Q2 "Is there drop-in/open-play pickleball in <town>?" branches on whether the
  town has live-schedule venues (names them + points at the on-page session
  table) vs. not (points at nearby towns), Q3 "How much does it cost?" is
  town-anchored. Each page now renders the FAQ as **visible HTML** (`section.tfaq`,
  scoped `_TOWN_FAQ_CSS`, high-contrast on the light page) **and** a matching
  `FAQPage` JSON-LD block — the visible text equals the schema text exactly, as
  Google requires for the markup to be valid. Added a small `_join_names()`
  helper for natural "A, B and C" venue lists. `build_town_pages` now emits three
  JSON-LD blocks (ItemList + BreadcrumbList + FAQPage). **Verified:** (1)
  unit-tested `_town_faq` for the live case (2 live venues → Q2 "Yes. …" naming
  both, Q3 mentions the live per-session price), the no-live case (Q2 → "vary by
  venue", Q3 → "check the individual venue's page"), and 1/2/3/4-venue grammar
  (singular "There is 1 place … — <name>", "A, B and C", comma-list + "and N
  more"); asserted every question and answer string appears in the visible HTML
  (escaped) so schema==on-page text. (2) Ran the full
  `python3 scraper/build_site.py` (exit 0) and machine-checked all **21** town
  pages: every one parses to valid JSON in all 3 LD blocks and contains a
  `FAQPage`, 0 malformed blocks; spot-read Bristol/Cranston/Warwick answers for
  correct counts and phrasing. Source-only change (`scraper/build_site.py`); the
  three build-curated `site/data/*.json` files were reverted per the ops note so
  CI rebuilds them from real live data, and the `site/t/` HTML is CI-built
  (gitignored). Note: locally all 6 live sources 403 through the sandbox proxy,
  so the live/no-live FAQ branch is driven by each venue's `source_id` in
  `directory.json` (static), not by scrape success — same as the existing "Live
  open-play schedule" badge; CI (which reaches the sources) renders the session
  tables the live-branch answers reference. Nothing here needs Rob — outreach and
  ads remain the only human-blocked items.

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
