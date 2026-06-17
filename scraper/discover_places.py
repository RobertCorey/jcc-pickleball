#!/usr/bin/env python3
"""Discover every pickleball venue in Rhode Island via the Google Places API.

This is the *directory* layer of the aggregator. Where ``sources.py`` produces
live, session-level schedules for the handful of venues we've integrated, this
script sweeps the Places API for **every** place in RI where you can play
pickleball — the comprehensive "where can I play" map that anchors the site's
statewide framing and its local-SEO surface (one page per venue / town).

It is deliberately decoupled from the hourly schedule build:

  * It needs ``GOOGLE_PLACES_API_KEY`` (lives in the Pi's ``~/.env``) and costs a
    few cents of Places quota per run, so it is NOT run hourly. It runs
    on-demand (or weekly) on the Pi and commits its output, ``site/data/directory.json``.
  * The hourly Pages build just reads that committed JSON — no key, no quota.

stdlib only (urllib/json), so it runs on the Pi's stock Python 3.11 with no pip.

Usage::

    GOOGLE_PLACES_API_KEY=... python3 scraper/discover_places.py        # write file
    GOOGLE_PLACES_API_KEY=... python3 scraper/discover_places.py --stdout  # print JSON

Pi run (key never leaves the Pi)::

    ssh pi 'set -a; . ~/.env; set +a; python3 - --stdout' < scraper/discover_places.py > site/data/directory.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "site" / "data" / "directory.json"

PLACES_ENDPOINT = "https://places.googleapis.com/v1/places:searchText"

# Bounding box around Rhode Island (a little padding; we filter to RI by address
# afterward, so a few MA/CT edge hits getting pulled in is fine — they're dropped).
RI_RECT = {
    "low": {"latitude": 41.10, "longitude": -71.95},
    "high": {"latitude": 42.05, "longitude": -71.08},
}

# Text queries — all pickleball-INTENT. The RI rectangle restriction + a
# pickleball verb makes Google rank by actual pickleball relevance, so every
# result is a place Google associates with the sport. We deliberately do NOT
# seed per-town queries ("pickleball <town> RI"): when a town has no real
# pickleball venue, Places falls back to returning every park/lodge in it as a
# weak match, and dedup destroys the relevance ranking that would let us drop
# them — so town seeds inject pure noise. Pagination depth covers the long tail
# instead.
QUERIES = [
    "pickleball",
    "pickleball courts",
    "pickleball club",
    "pickleball open play",
    "indoor pickleball",
    "public pickleball courts",
    "pickleball lessons",
    "where to play pickleball",
]

# Fields we ask for (mask keeps the bill down vs. requesting everything).
FIELD_MASK = ",".join(
    "places." + f for f in (
        "id", "displayName", "formattedAddress", "shortFormattedAddress",
        "location", "nationalPhoneNumber", "internationalPhoneNumber",
        "websiteUri", "googleMapsUri", "regularOpeningHours", "rating",
        "userRatingCount", "primaryType", "primaryTypeDisplayName", "types",
        "businessStatus", "addressComponents",
    )
) + ",nextPageToken"

MAX_PAGES = 3  # up to 60 results per query (Places caps text search at 60)


def _post(api_key: str, body: dict) -> dict:
    req = urllib.request.Request(
        PLACES_ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _search(api_key: str, text_query: str) -> list[dict]:
    """One text query, paginated, RI-rectangle-restricted."""
    out: list[dict] = []
    page_token = None
    for _ in range(MAX_PAGES):
        body: dict = {
            "textQuery": text_query,
            "locationRestriction": {"rectangle": RI_RECT},
            "maxResultCount": 20,
        }
        if page_token:
            body["pageToken"] = page_token
        try:
            data = _post(api_key, body)
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:300]
            print(f"::warning::query {text_query!r} HTTP {e.code}: {msg}", file=sys.stderr)
            break
        except Exception as e:  # noqa: BLE001 - best effort per query
            print(f"::warning::query {text_query!r} failed: {e}", file=sys.stderr)
            break
        out.extend(data.get("places", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
        time.sleep(2.0)  # nextPageToken needs a moment to activate
    return out


# --------------------------------------------------------------------------- #
# Normalization
# --------------------------------------------------------------------------- #
def _component(place: dict, want_type: str) -> str | None:
    for c in place.get("addressComponents", []):
        if want_type in c.get("types", []):
            return c.get("shortText") or c.get("longText")
    return None


def _province(place: dict) -> str | None:
    return _component(place, "administrative_area_level_1")


def _slugify(name: str, city: str | None) -> str:
    base = f"{name} {city}" if city else name
    s = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
    return s[:60] or "venue"


# Classification. Every result already came from a pickleball-intent query, but
# Google still drags in weak matches. We remove the clear non-pickleball noise by
# the *sport in the name* (basketball/bocce/skate/golf courts are not ours) and
# tier the rest by signal strength into "high" (dedicated pickleball) vs "maybe"
# (a park/Y/rec center Google associates with pickleball). We deliberately do NOT
# gate parks on Places relevance rank: rank carries a geographic bias (a real but
# peripheral destination like Ninigret Park in Charlestown ranks low in statewide
# queries), so it drops genuine venues. Instead, "maybe" venues get honest,
# non-asserting copy on their pages ("comes up in pickleball searches — confirm
# open play"), so a borderline park is never a false claim.
_PB = re.compile(r"pickle\s*-?\s*ball", re.I)
# Racquet-sport signal in a NAME — tennis/racquet courts commonly add pickleball
# lines, so these are plausible play venues.
_RACQUET = re.compile(r"\b(pickle\s*-?\s*ball|tennis|racquet|racket)\b", re.I)
# Other-sport signal: a name that's about basketball/bocce/skate/etc. (and NOT
# also racquet) is the wrong kind of court — drop it.
_OTHER_SPORT = re.compile(r"\b(basketball|bocce|skate|skatepark|playground|bowling|baseball|soccer|hockey|golf|swim|aquatic|pool)\b", re.I)
# Indoor / programmed venues that realistically host pickleball when a pickleball
# query surfaces them (YMCAs, rec centers, sports clubs/complexes).
_PLAY_TYPES = {"sports_complex", "sports_activity_location", "athletic_field",
               "gym", "fitness_center", "recreation_center", "sports_club",
               "community_center", "country_club"}
# Open-space / outdoor-court types that plausibly host pickleball when a
# pickleball query surfaces them.
_PARK_TYPES = {"park", "city_park", "state_park", "national_park",
               "tourist_attraction", "playground", "stadium"}


def _pickleball_confidence(place: dict, best_rank: int = 999) -> str | None:
    name = (place.get("displayName") or {}).get("text") or ""
    types = set(place.get("types") or []) | {place.get("primaryType") or ""}
    type_blob = " ".join(types).lower()

    if _PB.search(name) or "pickleball" in type_blob:
        return "high"                       # explicitly pickleball
    if _OTHER_SPORT.search(name) and not _RACQUET.search(name):
        return None                         # basketball/bocce/skate/golf court → not ours
    if _RACQUET.search(name):
        return "maybe"                      # tennis/racquet venue → likely pickleball lines
    if types & (_PLAY_TYPES | _PARK_TYPES):
        return "maybe"                       # rec center / YMCA / sports complex / park
    return None                              # unrelated business; drop


# Place types that are never public open-play venues even when "pickleball" is in
# the name (private vacation rentals with a backyard court, etc.).
_EXCLUDE_TYPES = {
    "lodging", "bed_and_breakfast", "resort_hotel", "guest_house", "hotel",
    "motel", "cottage", "campground", "real_estate_agency",
}


def _normalize(place: dict, best_rank: int = 999) -> dict | None:
    if place.get("businessStatus") == "CLOSED_PERMANENTLY":
        return None
    raw_types = set(place.get("types") or []) | {place.get("primaryType") or ""}
    if raw_types & _EXCLUDE_TYPES:
        return None
    province = _province(place)
    if province not in ("RI", "Rhode Island"):
        return None
    conf = _pickleball_confidence(place, best_rank)
    if conf is None:
        return None

    name = (place.get("displayName") or {}).get("text") or "Pickleball venue"
    city = _component(place, "locality") or _component(place, "postal_town") \
        or _component(place, "administrative_area_level_2")
    loc = place.get("location") or {}
    hours = (place.get("regularOpeningHours") or {}).get("weekdayDescriptions") or []
    return {
        "place_id": place.get("id"),
        "name": name,
        "slug": _slugify(name, city),
        "address": place.get("formattedAddress") or place.get("shortFormattedAddress"),
        "address1": _component(place, "route") and (
            (_component(place, "street_number") or "") + " " + _component(place, "route")
        ).strip() or None,
        "city": city,
        "province": "RI",
        "postal_code": _component(place, "postal_code"),
        "latitude": loc.get("latitude"),
        "longitude": loc.get("longitude"),
        "phone": place.get("nationalPhoneNumber"),
        "website": place.get("websiteUri"),
        "maps_uri": place.get("googleMapsUri"),
        "rating": place.get("rating"),
        "rating_count": place.get("userRatingCount"),
        "primary_type": place.get("primaryTypeDisplayName", {}).get("text")
        if isinstance(place.get("primaryTypeDisplayName"), dict) else place.get("primaryType"),
        "hours": hours,
        "confidence": conf,
        "rank": best_rank,
    }


def discover(api_key: str) -> dict:
    raw: dict[str, dict] = {}             # place_id -> richest raw place
    best_rank: dict[str, int] = {}        # place_id -> best (lowest) relevance rank seen
    queries = list(QUERIES)
    for q in queries:
        for rank, place in enumerate(_search(api_key, q)):
            pid = place.get("id")
            if not pid:
                continue
            best_rank[pid] = min(best_rank.get(pid, 999), rank)
            # keep the richest copy (one with more fields populated)
            if pid not in raw or len(place) > len(raw[pid]):
                raw[pid] = place
        print(f"  query {q!r}: cumulative {len(raw)} unique places", file=sys.stderr)

    venues = [v for v in (_normalize(p, best_rank.get(p.get("id"), 999)) for p in raw.values()) if v]
    # Dedupe on (name, city) in case Places returns two ids for one spot. Sort key
    # has a deterministic tiebreak (most-reviewed, then place_id) so re-runs are
    # reproducible and the richest of any duplicate pair survives.
    seen: set[tuple] = set()
    deduped: list[dict] = []
    for v in sorted(venues, key=lambda x: (x["confidence"] != "high", x.get("city") or "",
                                           x["name"], -(x.get("rating_count") or 0), x.get("place_id") or "")):
        key = (v["name"].lower().strip(), (v.get("city") or "").lower().strip())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(v)

    # Guarantee slug uniqueness — distinct venues whose names share a 60-char
    # prefix would otherwise collide and overwrite each other's /v/<slug>/ page.
    slug_seen: dict[str, int] = {}
    for v in deduped:
        base = v["slug"]
        if base in slug_seen:
            slug_seen[base] += 1
            tail = (v.get("place_id") or str(slug_seen[base]))[-6:].lower()
            tail = re.sub(r"[^a-z0-9]", "", tail) or str(slug_seen[base])
            v["slug"] = f"{base[:53]}-{tail}"
        else:
            slug_seen[base] = 0

    by_city: dict[str, int] = {}
    for v in deduped:
        by_city[v.get("city") or "Unknown"] = by_city.get(v.get("city") or "Unknown", 0) + 1

    return {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": "google-places-api",
        "totals": {
            "venues": len(deduped),
            "high_confidence": sum(1 for v in deduped if v["confidence"] == "high"),
            "cities": len(by_city),
            "queries_run": len(queries),
        },
        "by_city": dict(sorted(by_city.items(), key=lambda kv: (-kv[1], kv[0]))),
        "venues": deduped,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stdout", action="store_true", help="print JSON to stdout instead of writing the file")
    args = ap.parse_args(argv)

    api_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        print("error: GOOGLE_PLACES_API_KEY not set in env", file=sys.stderr)
        return 2

    doc = discover(api_key)
    payload = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    if args.stdout:
        sys.stdout.write(payload)
    else:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(payload, encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)} — {doc['totals']['venues']} RI venues "
              f"({doc['totals']['high_confidence']} high-confidence) across "
              f"{doc['totals']['cities']} cities", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
