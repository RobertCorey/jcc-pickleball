# NEEDS-HUMAN — items requiring Rob's action / decision

Maintained by the orchestrator (Claude driving the aggregator build).
Nothing here blocks ongoing code work — these are decisions / credentials / DNS only you can supply.

---

## 🔥 Firebase + production-domain migration (front-loaded — these unblock launch)

Moving off GitHub Pages (`robertcorey.github.io/jcc-pickleball`) → **Firebase Hosting** on the production
domain **openplayri.com**. Already done by me: Firebase project `open-play-ri` created (Spark), web app +
SDK config pulled, `firebase.json`/`.firebaserc` committed, smoke deploy live at
**https://openplayri.com**, and custom domain `openplayri.com` added (status: *Needs setup*).

### 1. ⬛ DNS for openplayri.com  ← the biggest blocker
Confirm you own **openplayri.com** (register it if not). Then in Cloudflare DNS add:

| Type | Name | Value | Notes |
|------|------|-------|-------|
| A    | `@` (openplayri.com) | `199.36.158.100` | **DNS-only / grey cloud — NOT proxied**, so Firebase can verify + provision SSL |
| TXT  | `@` (openplayri.com) | `hosting-site=open-play-ri` | ownership verification |

Then tell me — I'll click **Verify** in the console; managed SSL provisions in minutes–24h.
(Optional `www` → apex redirect: say the word and I'll wire it + give you its record.)

### 2. ⬛ (Recommended) Upgrade to Blaze + a $5 budget alert
The recommended stack is **$0/month**, but Spark has one hard cliff: exceed 10 GB/mo CDN transfer and the
**public site goes dark** until the next month. Blaze removes that cliff and at this traffic still bills
~$0. Upgrade in the console (needs your billing account — I can't set up billing) and add a $5 budget
alert. Not blocking; Spark is fine for launch day.

### 3. ⬛ Analytics decision (GA4 vs GoatCounter)
Research recommendation: **keep GoatCounter** (cookieless, no consent banner) and **defer GA4** — GA4 sets
`_ga` cookies, which trigger a GDPR/ePrivacy consent banner, the exact friction the cookieless setup
avoids. If you still want GA4 ("analytics everything"), say so and I'll wire it **plus** a consent banner.

### 4. ⬛ CI deploy credential (or let me do it)
The hourly GitHub Action needs a Firebase deploy credential. I can create the service account + add the
`FIREBASE_SERVICE_ACCOUNT_OPEN_PLAY_RI` repo secret myself (gcloud + gh are both authed) — just say "go".
Otherwise run `firebase init hosting:github` yourself. (Avoid `firebase login:ci` / `FIREBASE_TOKEN` —
deprecated.)

### 5. ⬛ Google Search Console (after the domain resolves)
Add **openplayri.com** as a property + submit `https://openplayri.com/sitemap.xml`, and file a **Change of
Address** from the old `robertcorey.github.io/jcc-pickleball` property. Needs your Google account; I'll drop
an HTML verification file if you use that method.

### 6. ⬛ Old GitHub Pages tail (SEO)
Decide: disable the old Pages site, or let me leave per-page `meta-refresh` + `rel=canonical` stubs on it
pointing to the new domain (cleaner hand-off for the few already-indexed URLs). Low stakes — barely indexed.

---

## Other open items (pre-existing, not migration-related)

- [ ] **Centerline Pickleball Club (Warwick) — CourtReserve org id.** One-line add to `COURTRESERVE_ORGS`
      in `scraper/sources.py` once you have the org id → instant 5th live club.
- [ ] **Bristol registration URL** — the CTA still points at the club's public Google Calendar; one-line
      swap in `scraper/bristol_ics.py` `VENUE["registration_url"]` when you have the official link.
- [ ] **(Optional) Auto-refresh the venue directory.** `scraper/discover_places.py` → `directory.json`.
      Today it's a manual run on the Pi. Weekly Pi cron or a `GOOGLE_PLACES_API_KEY` GitHub secret would
      keep it fresh (~$1 Places quota/run).

## Resolved
- [x] **Firebase project + Hosting** — `open-play-ri` created; live at https://openplayri.com.
- [x] **Firebase CLI auth** — already logged in as robertbcorey@gmail.com (CLI + gcloud).
- [x] **Google Places API key** — on the Pi (`~/.env`), verified.
- [x] **GoatCounter blocked by Pi-hole** — allowlisted goatcounter.com / www / gc.zgo.at.
