# CourtTime — JCC of Greater Rhode Island drop-in pickleball

A friendlier front end for the [JCC's open drop-in pickleball schedule](https://app.amilia.com/store/en/jewishallianceofgreaterrhodeisland/shop/programs/128482?subCategoryIds=6876731).
It scrapes the JCC's Amilia store, publishes the sessions as JSON, and renders
them on a static site with search/filter, live availability bars, and one-tap
"register on Amilia" buttons. A scheduled GitHub Action re-scrapes hourly and
redeploys.

```
scraper/
  scrape_open_play.py   # the scraper (stdlib only) — emits the full session document
  build_site.py         # runs the scraper → writes site/data/sessions.json
site/
  index.html            # the UI (vanilla HTML/CSS/JS, no build step)
  data/sessions.json     # generated; what the UI fetches
.github/workflows/
  scrape-and-deploy.yml # hourly cron: scrape → commit data → publish Pages
```

## Run it locally

```bash
python3 scraper/build_site.py     # refresh site/data/sessions.json
cd site && python3 -m http.server # then open http://localhost:8000
```

(The page fetches `data/sessions.json`, so it needs to be *served*, not opened
as a `file://` URL.)

## How the data is obtained

Everything is anonymous — no login, no credentials. Two sources, merged:

1. The program page HTML → per-activity display text (schedule blurbs, price
   labels, member-discount promotions, "important information" notices,
   activity-detail links).
2. Amilia's calendar feed, `api/Organization/EventsForProgram` → every
   individual session ("segment") with live capacity, attendance string, drop-in
   prices, location, facility address (incl. lat/long + phone), tags, staff,
   wait-list state, and the per-session registration URL.

> Quirk: the calendar feed returns **HTTP 500** unless the request carries *both*
> an `X-Requested-With: XMLHttpRequest` header and a `Referer` header. The
> scraper sets both. (Conversely that header on the *page* request makes Amilia
> return a partial HTML fragment, so it's only sent for the feed.)

See `scraper/scrape_open_play.py`'s module docstring for the full output schema.

## Deployment

GitHub Pages, published by the `scrape-and-deploy.yml` workflow (Pages source =
"GitHub Actions"). The workflow runs on push to `main`, on an hourly cron, and on
manual dispatch; each run re-scrapes, commits `site/data/sessions.json` if it
changed, uploads `site/` as the Pages artifact, and deploys it.

## Not affiliated

This is an unofficial convenience mirror of a public schedule. Registration,
payment, pricing and the schedule itself all live on the official JCC / Amilia
site; the buttons here just link there.
