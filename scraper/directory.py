#!/usr/bin/env python3
"""The *directory* layer: load the Places-discovered RI venue list and link the
handful with live schedules back to their source.

``discover_places.py`` writes ``site/data/directory.json`` (every RI pickleball
venue Google knows about). This module is the read side used at build time:

  * ``load()``            -> the directory doc (or an empty one if absent).
  * ``link_to_sources()`` -> stamp each directory venue that matches a live
                             source (JCC, Bristol) with ``source_id`` + an
                             upcoming-session count, and conversely give each
                             source its ``directory_slug``. Matching is by
                             geographic proximity (no brittle name matching).

Keeping this separate from ``sources.py`` preserves the rule that the hourly
build never needs the Places key: it just reads the committed JSON.
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
DIRECTORY_JSON = ROOT / "site" / "data" / "directory.json"

# Two venues count as "the same place" within this many meters. The Places point
# and a source's self-reported facility geo can differ by a building's width, so
# allow a generous radius — RI pickleball venues are never this close together.
MATCH_RADIUS_M = 400.0


def load(path: pathlib.Path | None = None) -> dict:
    """Load the directory doc. Missing/corrupt file -> an empty directory so the
    build still succeeds (directory is additive; live sessions are the core)."""
    p = path or DIRECTORY_JSON
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"venues": [], "totals": {}, "by_city": {}}
    except json.JSONDecodeError as exc:
        # A present-but-unparseable file is alarming (a truncated/bad write), not
        # a benign absence — surface it so it isn't read as a silent empty doc.
        print(f"::warning::directory.json is present but unparseable ({exc}); "
              f"treating as empty", file=sys.stderr)
        return {"venues": [], "totals": {}, "by_city": {}}
    doc.setdefault("venues", [])
    return doc


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance in meters between two lat/lng points."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _coords(v: dict) -> tuple[float, float] | None:
    lat, lng = v.get("latitude"), v.get("longitude")
    if lat is None or lng is None:
        return None
    try:
        return float(lat), float(lng)
    except (TypeError, ValueError):
        return None


def link_to_sources(directory: dict, doc: dict) -> dict:
    """Cross-link the directory with the live-schedule sources, in place.

    For each ``ok`` source, find the nearest directory venue within
    ``MATCH_RADIUS_M`` and:
      * set ``venue["source_id"]`` and ``venue["upcoming_sessions"]`` on it,
      * set ``source["directory_slug"]`` on the matching source meta.
    A source that matches no directory venue (or has no geo) is simply left
    unlinked — its sessions still render; it just isn't deep-linked from a
    directory page. Returns the (mutated) directory for convenience.
    """
    venues = directory.get("venues", [])
    sessions = doc.get("sessions", [])
    upcoming_by_source: dict[str, int] = {}
    for s in sessions:
        if not s.get("has_passed"):
            sid = s.get("source_id")
            if sid:
                upcoming_by_source[sid] = upcoming_by_source.get(sid, 0) + 1

    for src in doc.get("sources", []):
        if not src.get("ok"):
            continue
        sv = src.get("venue") or {}
        sc = _coords(sv)
        if not sc:
            continue
        best = None
        best_d = MATCH_RADIUS_M
        for v in venues:
            vc = _coords(v)
            if not vc:
                continue
            d = haversine_m(sc[0], sc[1], vc[0], vc[1])
            if d <= best_d:
                best, best_d = v, d
        if best is not None:
            sid = src.get("id")
            best["source_id"] = sid
            best["upcoming_sessions"] = upcoming_by_source.get(sid, 0)
            best["cta_label"] = src.get("cta_label")
            best["registration_url"] = sv.get("registration_url")
            src["directory_slug"] = best.get("slug")
    return directory


if __name__ == "__main__":
    d = load()
    t = d.get("totals", {})
    print(f"{t.get('venues', len(d.get('venues', [])))} venues, "
          f"{t.get('high_confidence', '?')} high-confidence, "
          f"{t.get('cities', '?')} cities")
