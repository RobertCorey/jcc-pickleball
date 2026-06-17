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
import sys

import scrape_open_play
import bristol_ics


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


def _bristol() -> dict:
    return bristol_ics.build_source()


# Registry. Order here is the order venues appear on the site.
SOURCES = [
    ("jcc-ri", _jcc_amilia),
    ("bristol", _bristol),
]

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
