# NEEDS-HUMAN — items requiring Rob's action / decision

Maintained by the orchestrator (Claude driving the aggregator build).

## ✅ Clear — nothing is currently blocking

As of 2026-06-26 the migration follow-ups **and** the standing data-gap items are
all resolved. Open Play RI is live at **https://openplayri.com** (Firebase Hosting,
all-Google) with **7 live schedule sources**.

### Recently cleared
- [x] **Firebase + production-domain migration** — live on Firebase Hosting; the
      hourly GitHub Action deploys via the `github-deployer@open-play-ri` service
      account. GitHub Pages retired as the host.
- [x] **www → apex redirect** — `www.openplayri.com` 301-redirects to the apex
      (Firebase custom domain + Cloud DNS `www` CNAME), path-preserving, valid SSL.
- [x] **Google Search Console** — `openplayri.com` Domain property auto-verified;
      `sitemap.xml` submitted and read (Success, 673 pages).
- [x] **Old GitHub Pages → redirect** — `robertcorey.github.io/jcc-pickleball`
      now serves path-preserving redirect stubs (`index.html` + `404.html`) that
      forward every old bookmark / deep link to the matching openplayri.com page.
      Verified end-to-end in a real browser.
- [x] **Centerline Pickleball Club (Warwick)** — added as the 5th live CourtReserve
      club (org id `12220`, recovered from its embed widget + Wayback; 147 upcoming
      sessions verified, build health green at 7 sources).
- [x] **Bristol registration URL** — swapped the read-only Google Calendar embed
      for the real Playerlineup signup (`https://bristolpickleball.playerlineup.com/`),
      the surface the club's official site routes registration through.

### By design (not a task)
- **Venue directory refresh** (`discover_places.py` → `directory.json`) stays an
  on-demand / weekly **Pi** run, not hourly — it needs the Places API key and costs
  quota, and RI's venue list changes slowly. (Automating it is folded into the
  maintenance-agent idea below.)
- **`gmail-cleanup-rc` billing** — left on the free tier (it was unlinked to free a
  Cloud-billing slot for `openplayri.com`). No paid resources; nothing to do unless
  it ever needs Blaze again.

## ⏳ Pending your call
- [ ] **Autonomous maintenance agent** (your "agent in Firebase/GitHub" request) —
      proposed: a **scheduled GitHub Action** that runs an agent to hunt new RI
      venues / missing CourtReserve org ids / dead source endpoints and opens a PR
      (or issue) for your review. Would also cover the directory refresh above.
      **Needs you to add an `ANTHROPIC_API_KEY` repo secret.** Awaiting design sign-off.

- [ ] **Feedback form → GitHub issue bridge — needs a GitHub token.** The site now
      has a "💬 Feedback" widget (bottom-right, every page) that POSTs to
      `/api/feedback`, a Firebase Function (`functions/index.js`) that files a
      GitHub issue labeled `feedback` in this repo. The function code is written
      and deployable, but it's blocked on a secret only you can set (I can't enter
      API tokens into anything myself — hard line):
      1. Create a **fine-grained GitHub PAT**: github.com → Settings → Developer
         settings → Personal access tokens → Fine-grained tokens → New token.
         Repository access: only `RobertCorey/jcc-pickleball`. Permissions:
         **Issues: Read and write** (nothing else needed).
      2. Run: `firebase functions:secrets:set GITHUB_FEEDBACK_TOKEN --project open-play-ri`
         and paste the token when prompted.
      3. Tell me it's set — I'll run `firebase deploy --only functions --project open-play-ri`
         myself (already authenticated locally, and everything else about the
         function deploys clean — confirmed via a dry run that the ONLY thing
         missing is this secret value).
      Once live, the scheduled growth-loop agent checks
      `gh issue list --label feedback --state open` / the public issues API each
      run and treats open feedback as higher priority than the general backlog.

- [ ] **Sentry error monitoring — verify it's actually receiving events.** Added
      the Sentry Loader Script (project `open-play-ri` under your existing
      `rob-corey-consulting` org) to all 3 page templates, error-monitoring only
      (Session Replay and Tracing explicitly disabled — no consent banner on the
      site, so no session recording by default). The CDN script returned a 503
      intermittently right after project creation (likely propagation lag) —
      should have resolved on its own within a few minutes, but worth a spot
      check: visit https://rob-corey-consulting.sentry.io/issues/ after some
      real traffic (or trigger a test error) and confirm events are landing.
