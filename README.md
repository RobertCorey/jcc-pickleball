# Open Play RI — Pickleball Open Play across Rhode Island

**Live site → https://open-play-ri.web.app/**

Open Play RI is a statewide aggregator for **pickleball open play (drop-in) in Rhode Island**.
It combines two things no single venue site offers:

- **A directory of every place to play** — 85+ pickleball courts, clubs, YMCAs, racquet
  clubs, and public park courts across 28 RI towns, each with an address, map, hours, and
  its own page (e.g. "pickleball in Warwick, RI").
- **Live open-play schedules** — real, hourly-refreshed drop-in sessions for the venues we
  integrate (currently the JCC of Greater Rhode Island, the Bristol Pickleball Club, and four
  CourtReserve clubs: Pickleball Citi, Ocean State Pickleball, East Bay Pickleball Club, and
  LIL Rhody) — with times, prices, live sign-up counts, shareable per-session pages, and
  one-tap registration.

Plus: a **"Near me"** distance sort, town + intent landing pages, calendar subscriptions
(`.ics` / webcal), an auto-updating [data report](https://open-play-ri.web.app/rhode-island-pickleball-report/),
and full schema.org structured data. Privacy-friendly analytics (GoatCounter), no cookies.

## How it works

A scheduled GitHub Action rebuilds and republishes the static site every hour.

```
scraper/
  sources.py            # source registry + merge layer (JCC, Bristol, CourtReserve x4)
  scrape_open_play.py   # JCC Amilia scraper (stdlib)
  bristol_ics.py        # Bristol Pickleball Club Google-Calendar ICS adapter
  courtreserve.py       # CourtReserve public-events adapter (Pickleball Citi, Ocean State, ...)
  discover_places.py    # Google Places sweep -> site/data/directory.json (the venue directory)
  directory.py          # reads directory.json; geo-links live venues to their directory page
  build_site.py         # runs sources -> writes data + all pages, sitemap, feeds
  templates/            # session.html, venue.html
site/
  index.html            # the homepage UI (vanilla HTML/CSS/JS, no build step)
  data/sessions.json    # generated; merged live schedule the UI fetches
  data/directory.json   # committed; the Places-discovered venue directory
  v/<slug>/             # generated venue pages   (+ open-play.ics per live venue)
  t/<slug>/             # generated town pages
  guide/<slug>/         # generated intent guides
  s/<id>/               # generated per-session share pages
.github/workflows/
  scrape-and-deploy.yml # hourly cron: scrape -> build -> publish Pages
```

The hourly build only needs the committed `directory.json` — no API key. The directory is
refreshed separately by running `discover_places.py` on a host with a Google Places key.

## Run it locally

```bash
python3 scraper/build_site.py      # build site/ from the live sources
cd site && python3 -m http.server  # then open http://localhost:8000
```

(The page fetches `data/sessions.json`, so it must be *served*, not opened as `file://`.)

## Adding a venue with a live schedule

Most RI clubs use **CourtReserve** — add its org id to `COURTRESERVE_ORGS` in `sources.py`
(find the id in `app.courtreserve.com/Online/Calendar/Events/<ORGID>/month`). Other systems
get their own best-effort adapter following the `bristol_ics` / `courtreserve` pattern: a
`build_source()` returning the normalized source dict, registered in `sources.py`. Sources are
isolated — one failing source never breaks the build.

## Data sources

- **JCC (Amilia):** the program page HTML + Amilia's `EventsForProgram` calendar feed (live
  capacity, prices, facility address). The feed needs both `X-Requested-With: XMLHttpRequest`
  and a `Referer` header or it returns HTTP 500.
- **Bristol:** the club's public Google Calendar ICS feed.
- **CourtReserve clubs:** each club's public events API (no login) — a scraped per-org token
  plus a Kendo-style POST to `ReadCalendarEvents`.
- **Directory:** Google Places API sweep of RI, classified to pickleball-relevant venues.

---

*Independent and unofficial. Venue data comes from public sources; schedules and pricing can
change — always confirm with the venue. Not affiliated with any listed venue or booking system.*
