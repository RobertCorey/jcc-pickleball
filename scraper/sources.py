#!/usr/bin/env python3
"""Source registry + merge layer for the CourtTime aggregator.

A *source* is a callable that returns a normalized "source result" dict, or
raises. Each source is BEST-EFFORT and ISOLATED: if one raises (network down,
HTML/feed changed), the merge layer warns and continues with the others - one
broken source never blanks the site or drops the rest. This mirrors the
existing Playwright best-effort/fallback pattern in ``build_site.py``.

A source result looks like::

    {
        "id": "jcc-ri",                 # stable slug; namespaces segment ids
        "booking_system": "amilia",
        "venue": { name, short_name, address1, city, province, postal_code,
                   country, phone, latitude, longitude, registration_url, ... },
        "cta_label": "Register on Amilia",   # optional; CTA verb for this venue
        "notices": [...],
        "sub_categories": [...],        # optional (Amilia promotions live here)
        "store": {...}, "program": {...},    # optional, source-specific detail
        "sessions": [ <per-session dict>, ... ],
    }

The merged document this module produces (written to ``site/data/sessions.json``)::

    {
        "scraped_at_utc": "...",
        "totals": { sources, venues, sessions, upcoming_sessions, activities },
        "sources": [ { id, ok, booking_system, venue, cta_label, notices,
                       sub_categories, store, program } ],
        "sessions": [ <session> + { source_id, venue_name } ; segment_id namespaced ],
    }

Every session's ``segment_id`` is namespaced ``"<source_id>:<local_id>"`` so
ids never collide across sources and per-session share pages stay unique.
"""

from __future__ import annotations

import datetime as dt
import functools
import sys

import scrape_open_play
import bristol_ics
import courtreserve
import directory


# --------------------------------------------------------------------------- #
# Source adapters - each returns a source result or raises.
# --------------------------------------------------------------------------- #
def _jcc_amilia() -> dict:
    """Source #1: the JCC of Greater Rhode Island (Amilia store).

    Thin wrapper around the unchanged ``scrape_open_play`` pipeline - its
    per-session data is produced exactly as before; we only lift the venue,
    notices and promotions up to the source level.
    """
    doc = scrape_open_play.build_document(scrape_open_play.DEFAULT_URL)
    return {
        "id": "jcc-ri",
        "booking_system": "amilia",
        "venue": _jcc_venue(doc),
        "cta_label": "Register on Amilia",
        "notices": doc.get("notices", []),
        "sub_categories": doc.get("sub_categories", []),
        "store": doc.get("store"),
        "program": doc.get("program"),
        "sessions": doc.get("sessions", []),
    }


def _jcc_venue(doc: dict) -> dict:
    """Build the JCC venue from the scraped facility, with known-good fallbacks."""
    fac = None
    for s in doc.get("sessions", []):
        if s.get("facility"):
            fac = s["facility"]
            break
    fac = fac or {}
    program = doc.get("program") or {}
    store = doc.get("store") or {}
    return {
        "name": "JCC of Greater Rhode Island",
        "short_name": "Providence JCC",
        "address1": fac.get("address1") or "401 Elmgrove Avenue",
        "address2": fac.get("address2"),
        "city": fac.get("city") or "Providence",
        "province": fac.get("province") or "RI",
        "postal_code": fac.get("postal_code") or "02906",
        "country": fac.get("country") or "US",
        "phone": fac.get("phone") or "4014214111",
        "phone_ext": fac.get("phone_ext"),
        "latitude": fac.get("latitude"),
        "longitude": fac.get("longitude"),
        "registration_url": program.get("url") or scrape_open_play.DEFAULT_URL,
        "homepage_url": store.get("base_url"),
    }


# Bristol's per-session registration link is source-owned — the directory can't
# know it. The club's official site (bristolpickleballri.org) states registration
# "is managed via Playerlineup" and its "Register to Play" button points here;
# unlike the old read-only Google Calendar embed, this is where players actually
# mark themselves IN/OUT for a session. Facts come from the directory.
_BRISTOL_REG_URL = "https://bristolpickleball.playerlineup.com/"


def _bristol() -> dict:
    venue = _venue_from_directory(
        "bristol-town-common-pickleball-courts-bristol",
        short_name="Bristol Pickleball", registration_url=_BRISTOL_REG_URL,
    )
    return bristol_ics.build_source(venue)


# --------------------------------------------------------------------------- #
# Venue facts: single source of truth.
#
# ``directory.json`` (Places-discovered, committed) is the ONE home for a venue's
# geographic/contact facts. A source only references its directory entry by slug
# and supplies what the directory can't know: the booking ``registration_url``
# and a short display name. The venue facts are hydrated from the directory at
# build time, so the facts never live in two places that can drift apart.
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=1)
def _directory_index() -> dict:
    """slug -> directory venue (loaded once from the committed directory.json)."""
    return {v.get("slug"): v for v in directory.load().get("venues", [])}


def _venue_from_directory(slug: str, *, short_name: str,
                          registration_url: str) -> dict:
    """Assemble a normalized source venue from its directory entry.

    The directory supplies the facts (name/address/geo/phone/website); the source
    supplies only booking + presentation fields. Raises if the slug is absent so
    a fact-less venue can never ship silently — the merge layer isolates the
    failure and the source-health guard surfaces it.
    """
    d = _directory_index().get(slug)
    if d is None:
        raise RuntimeError(f"venue {slug!r} not found in directory.json")
    return {
        "name": d.get("name"),
        "short_name": short_name,
        "address1": d.get("address1"),
        "address2": None,
        "city": d.get("city"),
        "province": d.get("province"),
        "postal_code": d.get("postal_code"),
        "country": "US",
        "phone": d.get("phone"),
        "phone_ext": None,
        "latitude": d.get("latitude"),
        "longitude": d.get("longitude"),
        "registration_url": registration_url,
        "homepage_url": d.get("website"),
    }


# --------------------------------------------------------------------------- #
# CourtReserve sources — RI clubs that publish a public CourtReserve calendar.
#
# Each entry is one organization whose public calendar we VERIFIED returns real
# upcoming open-play / drop-in events with no login. Venue facts come from the
# matching ``directory.json`` entry (named by ``directory_slug``); only the
# CourtReserve org id and a short display name live here.
# (Centerline's org id, 12220, was recovered from its CourtReserve embed widget /
# Portal/Index page — the live Wix site only exposes a generic, org-less signup
# link, so it isn't visible in the page source.)
# --------------------------------------------------------------------------- #
_COURTRESERVE_REG_URL = "https://app.courtreserve.com/Online/Calendar/Events/{org_id}/month"

COURTRESERVE_ORGS = [
    {"source_id": "pickleball-citi", "org_id": 11577,
     "directory_slug": "pickleball-citi-cranston", "short_name": "Pickleball Citi"},
    {"source_id": "ocean-state-pickleball", "org_id": 7726,
     "directory_slug": "ocean-state-pickleball-narragansett", "short_name": "Ocean State Pickleball"},
    {"source_id": "east-bay-pickleball", "org_id": 16386,
     "directory_slug": "east-bay-pickleball-club-warren", "short_name": "East Bay Pickleball"},
    {"source_id": "lil-rhody-pickleball", "org_id": 9068,
     "directory_slug": "lil-rhody-pickleball-north-kingstown", "short_name": "Lil Rhody Pickleball"},
    {"source_id": "centerline-pickleball", "org_id": 12220,
     "directory_slug": "centerline-pickleball-club-warwick", "short_name": "Centerline Pickleball"},
]


def _make_courtreserve_source(org: dict):
    """Bind one COURTRESERVE_ORGS entry into a zero-arg source callable."""
    def _fn() -> dict:
        venue = _venue_from_directory(
            org["directory_slug"], short_name=org["short_name"],
            registration_url=_COURTRESERVE_REG_URL.format(org_id=org["org_id"]),
        )
        return courtreserve.build_source(
            org["org_id"], venue, source_id=org["source_id"],
            cta_label="Reserve on CourtReserve",
        )
    return _fn


# Registry. Order here is the order venues appear on the site.
SOURCES = [
    ("jcc-ri", _jcc_amilia),
    ("bristol", _bristol),
]
SOURCES += [(o["source_id"], _make_courtreserve_source(o)) for o in COURTRESERVE_ORGS]

# Keys copied verbatim from each source result into the per-source metadata.
_SOURCE_META_KEYS = (
    "booking_system", "venue", "cta_label", "notices",
    "sub_categories", "store", "program",
)


# --------------------------------------------------------------------------- #
# Merge
# --------------------------------------------------------------------------- #
def build_merged_document() -> dict:
    """Run every source (isolated) and merge into one document."""
    scraped_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    sources_meta: list[dict] = []
    all_sessions: list[dict] = []

    for sid, fn in SOURCES:
        try:
            res = fn()
        except Exception as exc:  # best-effort: one source must not break the build
            print(f"::warning::source {sid!r} failed; skipping: {exc}", file=sys.stderr)
            sources_meta.append({"id": sid, "ok": False, "error": str(exc)})
            continue

        venue = res.get("venue") or {}
        venue_name = venue.get("short_name") or venue.get("name") or sid
        meta = {"id": sid, "ok": True}
        for k in _SOURCE_META_KEYS:
            if k in res:
                meta[k] = res[k]
        n = 0
        for raw in res.get("sessions", []):
            s = dict(raw)
            s["source_id"] = sid
            s["venue_name"] = venue_name
            s["segment_id"] = f"{sid}:{raw.get('segment_id')}"
            all_sessions.append(s)
            n += 1
        meta["session_count"] = n
        sources_meta.append(meta)
        print(f"  source {sid!r}: {n} sessions", file=sys.stderr)

    all_sessions.sort(key=lambda s: (s.get("start") or "", s.get("venue_name") or ""))

    ok_sources = [m for m in sources_meta if m.get("ok")]
    activities = {
        (s.get("source_id"), s.get("activity_id") or s.get("activity_name"))
        for s in all_sessions
    }
    totals = {
        "sources": len(ok_sources),
        "venues": len({m["venue"].get("name") for m in ok_sources if m.get("venue")}),
        "activities": len(activities),
        "sessions": len(all_sessions),
        "upcoming_sessions": sum(1 for s in all_sessions if not s.get("has_passed")),
    }

    return {
        "scraped_at_utc": scraped_at,
        "totals": totals,
        "sources": sources_meta,
        "sessions": all_sessions,
    }


if __name__ == "__main__":
    import json

    doc = build_merged_document()
    print(json.dumps(doc["totals"], indent=2))
    print(f"sources: {[(m['id'], m.get('ok'), m.get('session_count')) for m in doc['sources']]}",
          file=sys.stderr)
