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
- [x] **Feedback form → GitHub issue bridge.** Live and verified end-to-end
      (2026-07-03): the "💬 Feedback" widget on every page posts to
      `/api/feedback` → Firebase Function `submitFeedback` → files a GitHub
      issue labeled `feedback`. Confirmed with a real test submission (issue
      #11, filed and closed). Secret `GITHUB_FEEDBACK_TOKEN` set by Rob
      directly (never entered by an agent — a first token pasted into chat was
      correctly refused and revoked; the working one was set straight into
      the `firebase functions:secrets:set` prompt). Artifact cleanup policy
      also set (1-day retention) so old container images don't accrue storage
      cost. The scheduled growth-loop agent checks
      `curl .../issues?labels=feedback&state=open` each run and treats open
      feedback as higher priority than the general backlog.

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

- [ ] **Sentry error monitoring — CDN edge issue, not a config bug, needs a later recheck.**
      Added the Sentry Loader Script (project `open-play-ri` under your existing
      `rob-corey-consulting` org) to all 3 page templates, error-monitoring only
      (Session Replay and Tracing explicitly disabled). Confirmed 0 events landed
      after checking https://rob-corey-consulting.sentry.io/issues/. Debugged: the
      loader script (`js.sentry-cdn.com/...min.js`) 503s consistently in the
      browser but returns 200 via curl every time — even with the browser's exact
      headers spoofed. This points to one specific Fastly edge PoP near Rob's
      network serving a stale cached 503 (likely from right after project
      creation), not a real config problem — DSN, script placement, and init are
      all verified correct. Should self-resolve as that edge's cache ages out.
      **Recheck later** (a different network/device, or just revisit in a day or
      two): https://rob-corey-consulting.sentry.io/issues/ after some real
      traffic, or trigger `myUndefinedFunction();` in the browser console on
      openplayri.com as a deliberate test error.
