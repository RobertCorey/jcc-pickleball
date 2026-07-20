#!/usr/bin/env python3
"""Run the scrapers and build everything the static site serves.

Usage:
    python3 scraper/build_site.py

Outputs (under ``site/``):
  - ``data/sessions.json``      — the data the main page fetches
  - ``s/<segmentId>/index.html`` — one shareable, link-preview-ready page per
                                   session (regenerated each run; git-ignored)

The deployed base URL (used for absolute ``og:`` / canonical URLs) defaults to
the GitHub Pages URL and can be overridden with the ``SITE_BASE_URL`` env var.
Paths are resolved relative to this file, so it can be run from anywhere.
"""
from __future__ import annotations

import collections
import datetime as dt
import functools
import hashlib
import html
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
from zoneinfo import ZoneInfo

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import scrape_open_play as scraper  # noqa: E402
import sources  # noqa: E402
import directory as directory_mod  # noqa: E402
import og_images  # noqa: E402

SITE = ROOT / "site"
DATA_OUT = SITE / "data" / "sessions.json"
BUILD_META_OUT = SITE / "data" / "build.json"
LASTMOD_STORE = SITE / "data" / "lastmod.json"
SESSIONS_DIR = SITE / "s"
VENUES_DIR = SITE / "v"
TOWNS_DIR = SITE / "t"
GENERIC_OG = SITE / "og.png"
TEMPLATE = (HERE / "templates" / "session.html").read_text(encoding="utf-8")
VENUE_TEMPLATE = (HERE / "templates" / "venue.html").read_text(encoding="utf-8")
HOME_TEMPLATE = (HERE / "templates" / "index.html").read_text(encoding="utf-8")
EMBED_TEMPLATE = (HERE / "templates" / "venue_embed.html").read_text(encoding="utf-8")

SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "https://openplayri.com").rstrip("/")

WD_FULL = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
WD_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
MO_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MO_FULL = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
DAY_COLOR = {0: "#8b5fb0", 1: "#7c8a2e", 2: "#c6f23b", 3: "#2f8f73", 4: "#d99a2b", 5: "#3d6fb0", 6: "#b5562f"}

# Sessions are local Rhode Island times with no offset in the source data; stamp
# them with the venue's timezone so Event JSON-LD startDate/endDate are unambiguous.
# (RI venues are all US/Eastern; revisit if a venue outside that zone is ever added.)
EVENT_TZ = ZoneInfo("America/New_York")

# Cap per-session social-card renders to the soonest N upcoming sessions. Bounds
# CI build time independent of how many high-volume sources are added; the rest
# keep the generic og.png. (Set generously — covers all near-term shareable pages.)
OG_RENDER_CAP = 220

# --------------------------------------------------------------------------- #
# Directory curation: cut "public courts" (parks, playgrounds, public tennis &
# athletic courts) so the directory focuses on clubs and dedicated venues. The
# Places `primary_type` is unreliable — real clubs are routinely mislabeled
# (Pickleball Citi / Ocean State / Centerline all come back as "Athletic Field"),
# so a venue is NEVER cut when it has a live schedule (source_id, set by
# link_to_sources) or its name reads like a club / academy / YMCA / branded
# pickleball venue. Everything else of a public-court type is dropped.
# --------------------------------------------------------------------------- #
_PUBLIC_COURT_TYPES = {
    "Park", "City Park", "Playground", "Tennis Court",
    "Athletic Field", "Stadium", "Swimming Pool",
}
_CLUB_NAME_RE = re.compile(r"\b(club|academy|ymca|ywca|fieldhouse)\b", re.I)


def _is_public_court(v: dict) -> bool:
    """True if a directory venue is a public court we cut to tighten focus."""
    if v.get("source_id"):
        return False  # has a live schedule — always keep
    name = v.get("name") or ""
    if _CLUB_NAME_RE.search(name):
        return False  # club / academy / YMCA — keep
    low = name.lower()
    if "pickleball" in low and not re.search(
            r"court|tennis|park|field|common|rec\b|school|town", low):
        return False  # branded pickleball venue (e.g. "Pickleballri") — keep
    return v.get("primary_type") in _PUBLIC_COURT_TYPES


def esc(x) -> str:
    return html.escape("" if x is None else str(x), quote=True)


_DI_PB_PREFIX = re.compile(r"^\s*D/I\s*Pickleball\s*:\s*", re.I)
_DI_PREFIX = re.compile(r"^\s*D/I\s+", re.I)


def short_name(n: str) -> str:
    s = _DI_PB_PREFIX.sub("", n or "")
    s = _DI_PREFIX.sub("", s).strip()
    return s or (n or "Drop-in session")


def parse_local(iso):
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})", str(iso or ""))
    if not m:
        return None
    y, mo, d, h, mi = (int(x) for x in m.groups())
    wd = dt.date(y, mo, d).weekday()  # Mon=0..Sun=6
    wd = (wd + 1) % 7  # → Sun=0..Sat=6
    return {"y": y, "mo": mo, "d": d, "h": h, "mi": mi, "wd": wd, "date": dt.date(y, mo, d)}


def fmt_time(h, mi):
    ap = "AM" if h < 12 else "PM"
    hh = h % 12 or 12
    return f"{hh}:{mi:02d} {ap}" if mi else f"{hh} {ap}"


def money(n):
    if n is None:
        return ""
    f = float(n)
    return f"${f:.0f}" if f == int(f) else f"${f:.2f}"


def price_range(lo, hi):
    if lo is not None and hi is not None and lo != hi:
        return f"{money(lo)}–{money(hi)}"
    v = hi if hi is not None else lo
    return money(v) if v is not None else ""


def fmt_phone(s):
    digits = re.sub(r"\D", "", str(s or ""))
    m = re.match(r"^1?(\d{3})(\d{3})(\d{4})$", digits)
    return f"({m.group(1)}) {m.group(2)}-{m.group(3)}" if m else (s or "")


def rel_when(p, today):
    if not p:
        return ""
    diff = (p["date"] - today).days
    if diff == 0:
        return "Today"
    if diff == 1:
        return "Tomorrow"
    if 1 < diff < 7:
        return "This " + WD_FULL[p["wd"]]
    if 7 <= diff < 14:
        return "Next " + WD_FULL[p["wd"]]
    return WD_FULL[p["wd"]]


def spots_info(s):
    cap = s.get("capacity") if (not s.get("has_unlimited_spots") and isinstance(s.get("capacity"), (int, float)) and s.get("capacity")) else None
    left = s.get("spots_remaining") if isinstance(s.get("spots_remaining"), (int, float)) else None
    going = s.get("spots_reserved") if isinstance(s.get("spots_reserved"), (int, float)) else (
        (int(cap) - int(left)) if (cap is not None and left is not None) else None)
    return cap, left, going


def avail(s):
    """Return (css_class, dot?, label_html, label_plain)."""
    cap, left, going = spots_info(s)
    if s.get("has_passed"):
        if going is not None:
            return "past", False, f"<b>{int(going)}</b> signed up", f"{int(going)} signed up"
        return "past", False, "This session has happened", "this session has happened"
    if s.get("has_unlimited_spots"):
        return "good", True, (f"<b>{int(going)}</b> going" if going is not None else "Open"), (f"{int(going)} going" if going is not None else "open")
    if s.get("status") == "available_soon":
        return "soon", False, "Registration opens soon", "registration opens soon"
    if left == 0 or s.get("status") == "full" or s.get("has_place_left") is False:
        n = cap if cap is not None else going
        wl = " — waitlist available" if s.get("wait_list_enabled") else ""
        if n is not None:
            return "full", False, f"<b>{int(n)}</b> going · full{esc(wl)}", f"{int(n)} going, currently full{wl}"
        return "full", False, f"Currently full{esc(wl)}", f"currently full{wl}"
    if left is not None:
        g = int(going) if going is not None else 0
        cls = "low" if left <= 3 else "good"
        return cls, True, f"<b>{g}</b> going · {int(left)} left", f"{g} going, {int(left)} spot{'' if left == 1 else 's'} left"
    return "good", True, "Open", "open"


# ---------------------------------------------------------------------------
def _addr_line(v: dict) -> str:
    return ", ".join(x for x in [
        v.get("address1"),
        ", ".join(y for y in [v.get("city"), v.get("province")] if y)
        + (" " + v["postal_code"] if v.get("postal_code") else ""),
    ] if x)


def _map_href(v: dict) -> str:
    if v.get("latitude") and v.get("longitude"):
        return f"https://maps.google.com/?q={v['latitude']},{v['longitude']}"
    return "https://maps.google.com/?q=" + "+".join(
        x for x in [v.get("address1"), v.get("city"), v.get("province"), v.get("postal_code")] if x
    ).replace(" ", "+")


def venue_line_for(v: dict) -> str:
    """One-line venue, e.g. 'JCC of Greater Rhode Island · 401 Elmgrove Ave, Providence, RI 02906'."""
    name = v.get("name") or v.get("short_name") or "Venue"
    addr = _addr_line(v)
    return f"{name} · {addr}" if addr else name


def venue_parts_for(v: dict) -> tuple[str, str]:
    """Two lines for the OG card: ('Venue · 401 Elmgrove Ave', 'Providence, RI')."""
    name = v.get("name") or v.get("short_name") or "Venue"
    top = name + (f" · {v['address1']}" if v.get("address1") else "")
    bottom = ", ".join(x for x in [v.get("city"), v.get("province")] if x)
    return (top, bottom)


def build_glance_lis_for(source: dict, sessions: list) -> str:
    """The 'Good to know' <li> list (HTML) for ONE venue/source."""
    v = source.get("venue") or {}
    promos = []
    seen = set()
    for sc in source.get("sub_categories", []):
        for a in sc.get("activities", []):
            for pr in a.get("promotions", []):
                key = (pr.get("title") or "") + "|" + (pr.get("discount") or "")
                if key in seen:
                    continue
                seen.add(key)
                detail = " · ".join(pr.get("details") or pr.get("notes") or ([pr["text"]] if pr.get("text") else []))
                promos.append((pr.get("title") or "Discount", pr.get("discount") or "", detail))
    notices = [n for n in (source.get("notices") or []) if n]

    # price range across this venue's sessions
    lo = hi = None
    for s in sessions:
        b, f = s.get("drop_in_best_price"), s.get("drop_in_price")
        if b is not None:
            lo = b if lo is None else min(lo, b)
        if f is not None:
            hi = f if hi is None else max(hi, f)
        if b is not None and (hi is None or b > hi) and f is None:
            hi = b
    pr = price_range(lo, hi)

    items = []
    if pr:
        note = " Pay on the store, or use a Multipass." if source.get("booking_system") == "amilia" else ""
        items.append(("\U0001F4B5", f"<b>Drop-in</b> — {esc(pr)} per session.{note}"))
    for title, disc, detail in promos:
        pct = re.sub(r"^Discount of\s*", "", disc, flags=re.I).strip()
        t = re.sub(r"^Pickleball:\s*", "", title, flags=re.I).strip() or title
        items.append(("\U0001F3F7️", f"<b>{esc(t)}</b> — {esc(pct) + ' off' if pct else 'Discount'}" + (f" · {esc(detail)}" if detail else "")))
    for n in notices:
        items.append(("⚠️", esc(n)))
    if v:
        addr = _addr_line(v)
        where = f"<b>Where</b> — {esc(v.get('name') or 'Venue')}" + (f", {esc(addr)}" if addr else "")
        if v.get("phone"):
            where += f" · {esc(fmt_phone(v['phone']))}"
        where += f' · <a href="{esc(_map_href(v))}" target="_blank" rel="noopener">Map ↗</a>'
        items.append(("\U0001F4CD", where))

    return "".join(f'<li><span class="ico" aria-hidden="true">{ico}</span><span>{html_}</span></li>' for ico, html_ in items)


def _jsonld_script(data) -> str:
    """Serialize ``data`` as a hardened ``<script type="application/ld+json">``.

    json.dumps escapes quotes/backslashes but NOT < > / & — so any upstream
    string (a Places-sourced venue name/address, a facility name) containing
    "</script>" would terminate the tag early and inject markup. Escaping those
    to \\uXXXX stays valid JSON and neutralizes any tag. Single source of truth
    for every block of structured data the site emits.
    """
    body = json.dumps(data, ensure_ascii=False, indent=2)
    body = body.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return f'<script type="application/ld+json">\n{body}\n</script>'


def _iso_with_tz(p) -> str | None:
    """A parse_local() dict -> ISO 8601 string with the venue's UTC offset."""
    if not p:
        return None
    return dt.datetime(p["y"], p["mo"], p["d"], p["h"], p["mi"], tzinfo=EVENT_TZ).isoformat()


def event_jsonld(s, *, name, reg_url, p, pe, avail_cls, organizer_name, store_url, location=None) -> str:
    """schema.org/SportsEvent JSON-LD for one session.

    Location/geo/phone/address come from ``location`` — resolved by the caller as
    this session's own ``facility`` block (JCC) or, failing that, its source
    venue (``sources[].venue.*``, e.g. Bristol). Either way nothing about a
    specific venue is hardcoded, so it stays correct as more venues are added.
    """
    data = {
        "@context": "https://schema.org",
        "@type": "SportsEvent",
        "name": name,
        "sport": "Pickleball",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "eventStatus": "https://schema.org/EventScheduled",
        "url": f"{SITE_BASE_URL}/s/{s.get('segment_id')}/",
    }
    start, end = _iso_with_tz(p), _iso_with_tz(pe)
    if start:
        data["startDate"] = start
    if end:
        data["endDate"] = end

    fac = location or s.get("facility")
    if fac:
        loc = {"@type": "SportsActivityLocation", "name": fac.get("name") or "Gymnasium"}
        addr = {"@type": "PostalAddress"}
        for key, field in (("streetAddress", "address1"), ("addressLocality", "city"),
                           ("addressRegion", "province"), ("postalCode", "postal_code"),
                           ("addressCountry", "country")):
            if fac.get(field):
                addr[key] = fac[field]
        if len(addr) > 1:
            loc["address"] = addr
        if fac.get("latitude") is not None and fac.get("longitude") is not None:
            loc["geo"] = {"@type": "GeoCoordinates", "latitude": fac["latitude"], "longitude": fac["longitude"]}
        if fac.get("phone"):
            loc["telephone"] = fmt_phone(fac["phone"])
        data["location"] = loc

    # Only advertise a bookable Offer for sessions you can still act on. A passed
    # session is over — claiming a scheduled, InStock, priced Offer contradicts the
    # page UI ("This session has finished") and gets flagged for Event rich results,
    # so we omit offers entirely for it.
    price = s.get("drop_in_best_price")
    if price is None:
        price = s.get("drop_in_price")
    if price is not None and avail_cls != "past":
        availability = {
            "full": "https://schema.org/SoldOut",   # capacity reached / waitlist
            "soon": "https://schema.org/PreOrder",   # registration not open yet
        }.get(avail_cls, "https://schema.org/InStock")
        data["offers"] = {
            "@type": "Offer",
            "price": f"{float(price):.2f}",
            "priceCurrency": "USD",
            "url": reg_url,
            "availability": availability,
        }

    if organizer_name:
        data["organizer"] = {"@type": "Organization", "name": organizer_name, "url": store_url}

    return _jsonld_script(data)


def _slot_key(s: dict):
    """Identity of a session's recurring weekly slot (source + weekday + start
    time) — every future date of the same slot renders a near-identical page."""
    p = parse_local(s.get("start"))
    if not p:
        return None
    return (s.get("source_id"), p["wd"], p["h"], p["mi"])


def soonest_segment_ids(sessions: list) -> set[str]:
    """segment_id of the soonest upcoming occurrence of each distinct recurring
    slot. Sitemapping every date within the scrape window (600+ near-duplicate
    pages differing only by date) dilutes crawl trust for a new domain; the
    later dates stay live and linked (from the venue page), just excluded from
    the sitemap and self-tagged noindex."""
    best: dict[tuple, tuple[str, str]] = {}
    for s in sessions:
        sid = s.get("segment_id")
        if not sid or s.get("has_passed"):
            continue
        key = _slot_key(s)
        if key is None:
            continue
        start = s.get("start") or ""
        cur = best.get(key)
        if cur is None or start < cur[0]:
            best[key] = (start, sid)
    return {sid for _, sid in best.values()}


def _load_lastmod_store() -> dict:
    try:
        return json.loads(LASTMOD_STORE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _tracked_lastmod(store: dict, key: str, content: str, today: str) -> str:
    """Per-page-type freshness: only bump a page's sitemap <lastmod> to today
    when its actual content changed since the last build, instead of every
    hourly rebuild claiming every URL just updated — a signal Google explicitly
    discounts once it stops correlating with real changes. ``store`` persists
    across builds via LASTMOD_STORE (committed back by CI like sessions.json)."""
    h = hashlib.sha256(content.encode("utf-8")).hexdigest()
    prev = store.get(key)
    if prev and prev.get("hash") == h:
        return prev.get("date") or today
    store[key] = {"hash": h, "date": today}
    return today


def write_sitemap_and_robots(doc, directory=None, soonest_ids=None) -> int:
    """Write site/sitemap.xml (homepage + every venue + every session page) and a
    robots.txt that points at it. Returns the URL count. Both ship in the Pages
    artifact."""
    # Only sitemap UPCOMING session pages — past sessions are dead weight in the
    # index, and with high-volume sources they'd dominate the sitemap. Also only
    # the soonest occurrence of each recurring slot (see soonest_segment_ids) —
    # every later date is a near-duplicate page, excluded here + self-noindexed.
    sids = [str(s["segment_id"]) for s in doc.get("sessions", [])
            if s.get("segment_id") and not s.get("has_passed")
            and (soonest_ids is None or s["segment_id"] in soonest_ids)]
    dvenues = [v for v in (directory or {}).get("venues", []) if v.get("slug")]
    build_lastmod = (doc.get("scraped_at_utc") or "")[:10] or dt.date.today().isoformat()

    # Session availability genuinely changes hourly, so the homepage (which
    # surfaces it live) and session pages legitimately use the build timestamp.
    # Everything else's lastmod tracks when its actual content last changed.
    store = _load_lastmod_store()
    entries = [(f"{SITE_BASE_URL}/", build_lastmod, "hourly", "1.0")]

    by_city = _group_by_city(dvenues)
    for city, vs in sorted(by_city.items()):
        if city == "Rhode Island":
            continue
        tslug = town_slug(city)
        content = "|".join(sorted(f"{v['slug']}:{bool(v.get('source_id'))}" for v in vs))
        tm = _tracked_lastmod(store, f"t:{tslug}", content, build_lastmod)
        entries.append((f"{SITE_BASE_URL}/t/{tslug}/", tm, "weekly", "0.9"))

    for col in COLLECTIONS:
        matched = sorted(v["slug"] for v in dvenues if col["match"](v))
        if len(matched) < 3:
            continue
        gm = _tracked_lastmod(store, f"g:{col['slug']}", "|".join(matched), build_lastmod)
        entries.append((f"{SITE_BASE_URL}/guide/{col['slug']}/", gm, "weekly", "0.9"))

    n_live = len({v.get("source_id") for v in dvenues if v.get("source_id")})
    report_content = f"{len(dvenues)}|{len(by_city)}|{n_live}"
    rm = _tracked_lastmod(store, "report", report_content, build_lastmod)
    entries.append((f"{SITE_BASE_URL}/rhode-island-pickleball-report/", rm, "weekly", "0.8"))

    # Venue/directory pages — the durable SEO surface; change rarely but are the
    # most link-worthy, so a notch below the homepage and above ephemeral sessions.
    for v in sorted(dvenues, key=lambda v: v["slug"]):
        vcontent = "|".join(str(v.get(f) or "") for f in
                             ("name", "city", "address", "phone", "website", "confidence", "hours")) \
                   + f"|live={bool(v.get('source_id'))}"
        vm = _tracked_lastmod(store, f"v:{v['slug']}", vcontent, build_lastmod)
        entries.append((f"{SITE_BASE_URL}/v/{v['slug']}/", vm, "weekly", "0.8"))

    entries += [(f"{SITE_BASE_URL}/s/{sid}/", build_lastmod, "daily", "0.7") for sid in sids]

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod, freq, pri in entries:
        lines.append("  <url>"
                     f"<loc>{esc(loc)}</loc>"
                     f"<lastmod>{esc(lastmod)}</lastmod>"
                     f"<changefreq>{freq}</changefreq>"
                     f"<priority>{pri}</priority>"
                     "</url>")
    lines.append("</urlset>")
    (SITE / "sitemap.xml").write_text("\n".join(lines) + "\n", encoding="utf-8")

    LASTMOD_STORE.parent.mkdir(parents=True, exist_ok=True)
    LASTMOD_STORE.write_text(json.dumps(store, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    (SITE / "robots.txt").write_text(
        "User-agent: *\n"
        "Allow: /\n\n"
        f"Sitemap: {SITE_BASE_URL}/sitemap.xml\n",
        encoding="utf-8",
    )
    return len(entries)


def build_session_pages(doc, soonest_ids=None) -> tuple[int, int, int]:
    """Write site/s/<id>/index.html for every session (+ a per-session og.png if
    Playwright is available). Returns (page_count, image_count, attempted_count).

    Note the 3-tuple: main() unpacks (n_pages, n_imgs, n_attempted). The empty
    case must match that arity so a build with zero live sessions (e.g. every
    source failing at once) degrades to a static directory site instead of
    crashing — see the source-failure isolation design (GROWTH iter 7/13)."""
    sessions = doc.get("sessions", [])
    if not sessions:
        return (0, 0, 0)
    # Per-source lookups: each session is rendered with ITS OWN venue/glance.
    sources_by_id = {m["id"]: m for m in doc.get("sources", []) if m.get("ok")}
    sessions_by_source: dict[str, list] = {}
    for s in sessions:
        sessions_by_source.setdefault(s.get("source_id"), []).append(s)
    glance_by_source = {
        sid: build_glance_lis_for(m, sessions_by_source.get(sid, []))
        for sid, m in sources_by_id.items()
    }
    og_url_text = re.sub(r"^https?://", "", SITE_BASE_URL).rstrip("/")
    scraped_iso = doc.get("scraped_at_utc") or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    today = dt.date.today()

    # fresh dir
    if SESSIONS_DIR.exists():
        shutil.rmtree(SESSIONS_DIR)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    count = 0
    og_cards: list[tuple[pathlib.Path, str]] = []  # (out_png, html) for per-session preview images
    for s in sessions:
        sid = s.get("segment_id")
        if not sid:
            continue
        # this session's venue / source
        src = sources_by_id.get(s.get("source_id")) or {}
        venue_v = src.get("venue") or {}
        glance_lis = glance_by_source.get(s.get("source_id"), "")
        venue = venue_line_for(venue_v)
        venue_short = s.get("venue_name") or venue_v.get("short_name") or venue.split("·")[0].strip()
        og_venue_top, og_venue_bottom = venue_parts_for(venue_v)
        og_kicker = venue_v.get("name") or venue_short
        is_amilia = src.get("booking_system") == "amilia"
        cta_primary = src.get("cta_label") or "Register"
        cta_view = "View on Amilia" if is_amilia else cta_primary
        store_url = (src.get("program") or {}).get("url") or venue_v.get("registration_url") or scraper.DEFAULT_URL
        # Venue-appropriate label for the source link: only the JCC (Amilia) is a
        # "store"; CourtReserve clubs book on their schedule, others are generic.
        store_label = ("Official store" if is_amilia
                       else "Book on CourtReserve" if src.get("booking_system") == "courtreserve"
                       else "Official schedule")

        p = parse_local(s.get("start"))
        pe = parse_local(s.get("end"))
        act = short_name(s.get("activity_name"))
        cls, dot, label_html, label_plain = avail(s)
        cap, left, going = spots_info(s)
        pr = price_range(s.get("drop_in_best_price"), s.get("drop_in_price"))
        reg_url = s.get("registration_url") or s.get("details_url") or venue_v.get("registration_url") or store_url

        # the "when" ribbon above the date — only relative labels (Today / Tomorrow /
        # This Friday / Next Friday); for far-out dates it stays empty so it isn't
        # just a redundant weekday under the date headline.
        if s.get("has_passed"):
            when_rel = "Past session"
        elif p:
            r = rel_when(p, today)
            when_rel = r if (r and r != WD_FULL[p["wd"]]) else ""
        else:
            when_rel = ""
        when_date = f"{WD_FULL[p['wd']]}, {MO_FULL[p['mo'] - 1]} {p['d']}, {p['y']}" if p else "—"
        when_time = (f"{fmt_time(p['h'], p['mi'])} – {fmt_time(pe['h'], pe['mi'])}" if (p and pe) else (fmt_time(p['h'], p['mi']) if p else ""))
        day_color = DAY_COLOR.get(p["wd"], "#a9d423") if p else "#a9d423"

        # meter
        meter_html = ""
        if not s.get("has_passed") and cap and going is not None:
            pct = max(0, min(100, round(int(going) / int(cap) * 100)))
            mcls = "full" if cls == "full" else ("low" if cls == "low" else "")
            meter_html = f'<span class="meter {mcls}" aria-hidden="true"><i style="width:{pct}%"></i></span>'

        # CTA
        if s.get("has_passed"):
            cta = '<span class="btn" aria-disabled="true">This session has finished</span>'
        elif cls == "full":
            # venue-aware label (cta_view) + js-reg so the register-click metric fires
            cta = (f'<a class="btn btn-primary js-reg" href="{esc(reg_url)}" target="_blank" rel="noopener">'
                   + ("Join the waitlist" if s.get("wait_list_enabled") else esc(cta_view))
                   + ' <span class="arrow" aria-hidden="true">↗</span></a>')
        elif cls == "soon":
            cta = f'<a class="btn btn-primary js-reg" href="{esc(reg_url)}" target="_blank" rel="noopener">{esc(cta_view)} <span class="arrow" aria-hidden="true">↗</span></a>'
        else:
            cta = f'<a class="btn btn-primary js-reg" href="{esc(reg_url)}" target="_blank" rel="noopener">{esc(cta_primary)} <span class="arrow" aria-hidden="true">→</span></a>'

        # OG / meta text — keyed to this specific date, not the recurring slot name
        canonical = f"{SITE_BASE_URL}/s/{sid}/"
        date_brief = f"{WD_SHORT[p['wd']]}, {MO_SHORT[p['mo'] - 1]} {p['d']}" if p else ""
        date_long = f"{WD_FULL[p['wd']]}, {MO_FULL[p['mo'] - 1]} {p['d']}" if p else ""
        time_brief = fmt_time(p["h"], p["mi"]) if p else ""
        og_title = f"Drop-in pickleball · {date_brief}" + (f" at {time_brief}" if time_brief else "") + f" · {venue_short}"
        if s.get("has_passed"):
            og_desc = f"Drop-in pickleball at {venue_short} — {date_long}, {when_time}. This session has already happened; see the upcoming schedule."
        else:
            head = f"Drop-in pickleball at {venue_short} — {date_long}" + (f", {when_time}" if when_time else "") + "."
            og_desc = f"{head} {venue}. {label_plain[:1].upper() + label_plain[1:]}"
            if pr:
                og_desc += f" · {pr} per drop-in"
            og_desc += ". Tap through to the official schedule."
        page_title = (f"Pickleball · {date_brief}" + (f" at {time_brief}" if time_brief else "") + f" · {venue_short}") if date_brief else f"Drop-in pickleball · {venue_short}"

        price_bit = f' · <span class="price">{esc(pr)}</span> / drop-in' if pr else ""

        jsonld_name = f"Drop-in Pickleball — {date_long}" if date_long else "Drop-in Pickleball"
        # JCC sessions carry a per-session facility; others (Bristol) fall back to
        # the source venue so Event location is correct for every venue.
        jsonld_location = s.get("facility") or venue_v or None
        jsonld = event_jsonld(
            s, name=jsonld_name, reg_url=reg_url, p=p, pe=pe, avail_cls=cls,
            organizer_name=og_kicker, store_url=store_url, location=jsonld_location,
        )

        # Link this session page back up to its venue/town page (previously
        # every session page dead-ended at the homepage) + BreadcrumbList, same
        # pattern the venue/town/guide pages already use.
        venue_slug = src.get("directory_slug")
        city = venue_v.get("city")
        tslug = town_slug(city) if city else None
        crumb_bits = ['<a href="../../">Open Play RI</a>', '<span class="sep">/</span>']
        if city and tslug:
            crumb_bits += [f'<a href="../../t/{esc(tslug)}/">{esc(city)}, RI</a>', '<span class="sep">/</span>']
        crumb_bits.append(f'<a href="../../v/{esc(venue_slug)}/">{esc(venue_short)}</a>' if venue_slug
                           else f'<span>{esc(venue_short)}</span>')
        breadcrumb_html = "".join(crumb_bits)
        venue_link_html = (f'<a class="venue-link" href="../../v/{esc(venue_slug)}/">See the {esc(venue_short)} venue page →</a>'
                            if venue_slug else "")

        crumbs = [("Open Play RI", f"{SITE_BASE_URL}/")]
        if city and tslug:
            crumbs.append((f"Pickleball in {city}", f"{SITE_BASE_URL}/t/{tslug}/"))
        if venue_slug:
            crumbs.append((venue_short, f"{SITE_BASE_URL}/v/{venue_slug}/"))
        crumbs.append((date_brief or "Session", canonical))
        jsonld += "\n" + _jsonld_script(_breadcrumb_jsonld(crumbs))

        is_soonest = soonest_ids is None or sid in soonest_ids
        robots_meta = "" if is_soonest else '<meta name="robots" content="noindex,follow" />'

        fields = {
            "PAGE_TITLE": esc(page_title),
            "OG_TITLE": esc(og_title),
            "OG_DESC": esc(og_desc),
            "CANONICAL": esc(canonical),
            "OG_IMAGE": esc(f"{SITE_BASE_URL}/s/{sid}/og.png"),
            "HOME_HREF": "../../",
            "STORE_URL": esc(store_url),
            "STORE_LABEL": esc(store_label),
            "VENUE_NAME": esc(og_kicker),
            "VENUE_SHORT": esc(venue_short),
            "REG_URL": esc(reg_url),
            "ACTIVITY": esc(act),
            "WHEN_REL": esc(when_rel),
            "WHEN_DATE": esc(when_date),
            "WHEN_TIME": esc(when_time),
            "DAY_COLOR": day_color,
            "VENUE": esc(venue),
            "PRICE_BIT": price_bit,
            "AVAIL_CLS": cls,
            "AVAIL_DOT": '<span class="pdot"></span>' if dot else "",
            "AVAIL_HTML": label_html,
            "METER_HTML": meter_html,
            "CTA_HTML": cta,
            "GLANCE_LIS": glance_lis,
            "SCRAPED_ISO": esc(scraped_iso),
            "JSONLD": jsonld,
            "BREADCRUMB": breadcrumb_html,
            "VENUE_LINK_HTML": venue_link_html,
            "ROBOTS_META": robots_meta,
        }
        out = _fill_template(TEMPLATE, fields)
        sdir = SESSIONS_DIR / str(sid)
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "index.html").write_text(out, encoding="utf-8")

        # og:image for this page: a fallback copy of the generic card now (so the
        # URL always resolves), then a session-specific render overwrites it below
        # if Playwright is available — but only for the soonest upcoming sessions.
        # With high-volume sources (CourtReserve clubs run many sessions/day) the
        # total can be ~1200+; rendering a Chromium card for each would blow the CI
        # build budget for little gain (far-future + past pages rarely get shared).
        # Past + over-cap pages keep the generic og.png that was just copied.
        og_png = sdir / "og.png"
        if GENERIC_OG.exists():
            shutil.copyfile(GENERIC_OG, og_png)
        if not s.get("has_passed") and len(og_cards) < OG_RENDER_CAP:
            og_cards.append((og_png, og_images.card_html(
                date_long=when_date, time_str=when_time,
                eyebrow=(when_rel.upper() if when_rel else ""),
                kicker=og_kicker, url_text=og_url_text,
                venue_top=og_venue_top, venue_bottom=og_venue_bottom,
            )))
        count += 1

    n_attempted = len(og_cards)
    n_imgs = 0
    try:
        n_imgs = og_images.render_all(og_cards)
    except Exception as exc:  # rendering is best-effort; the generic fallbacks stay in place
        print(f"  (per-session OG images skipped: {exc})", file=sys.stderr)
    return count, n_imgs, n_attempted


# ---------------------------------------------------------------------------
# Directory (Places-discovered venues) -> one SEO page per venue at /v/<slug>/
# ---------------------------------------------------------------------------
def _venue_addr_line(v: dict) -> str:
    """Prefer the discrete fields; fall back to the Places formatted address."""
    parts = _addr_line(v)
    if parts:
        return parts
    return v.get("address") or ""


def _venue_map_href(v: dict) -> str:
    return v.get("maps_uri") or _map_href(v)


def _venue_jsonld(v: dict, canonical: str) -> dict:
    loc: dict = {
        "@context": "https://schema.org",
        "@type": "SportsActivityLocation",
        "name": v.get("name") or "Pickleball venue",
        "url": canonical,
        "sport": "Pickleball",
    }
    addr = {"@type": "PostalAddress"}
    for key, field in (("streetAddress", "address1"), ("addressLocality", "city"),
                       ("addressRegion", "province"), ("postalCode", "postal_code")):
        if v.get(field):
            addr[key] = v[field]
    addr["addressCountry"] = "US"
    if len(addr) > 2:
        loc["address"] = addr
    if v.get("latitude") is not None and v.get("longitude") is not None:
        loc["geo"] = {"@type": "GeoCoordinates", "latitude": v["latitude"], "longitude": v["longitude"]}
    if v.get("phone"):
        loc["telephone"] = fmt_phone(v["phone"])
    sameas = [u for u in (v.get("website"), v.get("maps_uri")) if u]
    if sameas:
        loc["sameAs"] = sameas
    # Only emit a rating when Google actually has reviews — an aggregateRating
    # with reviewCount 0 is invalid and gets flagged.
    if isinstance(v.get("rating"), (int, float)) and (v.get("rating_count") or 0) >= 1:
        loc["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": v["rating"],
            "reviewCount": int(v["rating_count"]),
            "bestRating": 5,
        }
    return loc


def _breadcrumb_jsonld(crumbs: list[tuple[str, str | None]]) -> dict:
    items = []
    for i, (name, url) in enumerate(crumbs, 1):
        it = {"@type": "ListItem", "position": i, "name": name}
        if url:
            it["item"] = url
        items.append(it)
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": items}


def _fill_template(template: str, fields: dict) -> str:
    """Substitute ``{{KEY}}`` placeholders in a page template. Shared by every
    page builder so the placeholder syntax lives in exactly one place."""
    out = template
    for k, val in fields.items():
        out = out.replace("{{" + k + "}}", val)
    return out


def _group_by_city(venues: list) -> dict[str, list]:
    """Group directory venues by city (venues without one fall under 'Rhode Island')."""
    by_city: dict[str, list] = {}
    for v in venues:
        by_city.setdefault(v.get("city") or "Rhode Island", []).append(v)
    return by_city


def _venue_rank_key(v: dict) -> tuple:
    """Sort key for venue lists: live first, then dedicated, then rating, then name."""
    return (0 if v.get("source_id") else 1,
            0 if v.get("confidence") == "high" else 1,
            -(v.get("rating") or 0), v.get("name") or "")


def _session_price(s: dict) -> str:
    """Per-session drop-in price string (best price → regular), '' if unknown."""
    vals = [float(v) for v in (s.get("drop_in_best_price"), s.get("drop_in_price"))
            if isinstance(v, (int, float)) and v > 0]
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    return price_range(lo, hi) if lo != hi else money(lo)


def _session_avail(s: dict) -> tuple[str, str]:
    """(label, css-class) for an UPCOMING session's spots — mirrors the
    homepage JS avail() so the venue-page schedule matches the live list."""
    left = s.get("spots_remaining") if isinstance(s.get("spots_remaining"), (int, float)) else None
    if s.get("has_unlimited_spots"):
        return ("Open", "good")
    if s.get("status") == "available_soon":
        return ("Opens soon", "soon")
    if left == 0 or s.get("status") == "full" or s.get("has_place_left") is False:
        return ("Full", "full")
    if left is not None:
        return (f"{left} spot{'s' if left != 1 else ''} left", "low" if left <= 3 else "good")
    return ("Open", "good")


def _session_row_html(s: dict) -> str:
    p = parse_local(s.get("start"))
    pe = parse_local(s.get("end"))
    if not p:
        return ""
    day = WD_FULL[p["wd"]]
    date = f"{MO_SHORT[p['mo'] - 1]} {p['d']}"
    tm = (f"{fmt_time(p['h'], p['mi'])} – {fmt_time(pe['h'], pe['mi'])}" if pe else fmt_time(p["h"], p["mi"]))
    href = f"../../s/{esc(s.get('segment_id'))}/"
    # secondary line: price + spots-left, the "is there room / how much" a
    # visitor needs to decide whether to head over — without clicking through.
    price = _session_price(s)
    av_label, av_cls = _session_avail(s)
    meta = []
    if price:
        meta.append(f'<span class="sprice">{esc(price)}</span>')
    meta.append(f'<span class="savail {av_cls}">{esc(av_label)}</span>')
    meta_html = '<span class="smeta">' + '<span class="mdot">·</span>'.join(meta) + '</span>'
    return (f'<li><a href="{href}"><span class="sinfo">'
            f'<span class="day">{esc(day)}<span class="date">{esc(date)}</span></span>'
            f'{meta_html}</span>'
            f'<span class="tm">{esc(tm)}</span></a></li>')


def _town_session_row_html(s: dict, live_srcs: dict, href_base: str = "../../") -> str:
    """A session row for a TOWN page (also reused on the homepage): like
    _session_row_html but also names which venue the session is at (a town —
    or the homepage — can span more than one live-schedule venue), linking the
    row to the session page. `live_srcs` maps source_id -> venue dict.
    `href_base` is the relative prefix to the site root ("../../" for town
    pages under /t/<slug>/, "" for the root-level homepage)."""
    p = parse_local(s.get("start"))
    pe = parse_local(s.get("end"))
    if not p:
        return ""
    day = WD_FULL[p["wd"]]
    date = f"{MO_SHORT[p['mo'] - 1]} {p['d']}"
    tm = (f"{fmt_time(p['h'], p['mi'])} – {fmt_time(pe['h'], pe['mi'])}" if pe else fmt_time(p["h"], p["mi"]))
    v = live_srcs.get(s.get("source_id")) or {}
    vname = s.get("venue_name") or v.get("short_name") or v.get("name") or "Open play"
    href = f"{href_base}s/{esc(s.get('segment_id'))}/"
    return (f'<li><a href="{href}">'
            f'<span class="tsday">{esc(day)}<span class="tsdate">{esc(date)}</span></span>'
            f'<span class="tsvn">{esc(vname)}</span>'
            f'<span class="tstm">{esc(tm)}</span></a></li>')


def _embed_session_row_html(s: dict) -> str:
    """Like _session_row_html, but absolute URLs + target=_top — the embed page
    is designed to be iframed on a THIRD-PARTY site, so relative hrefs and a
    same-frame navigation would both be wrong."""
    p = parse_local(s.get("start"))
    pe = parse_local(s.get("end"))
    if not p:
        return ""
    day = WD_FULL[p["wd"]]
    date = f"{MO_SHORT[p['mo'] - 1]} {p['d']}"
    tm = (f"{fmt_time(p['h'], p['mi'])} – {fmt_time(pe['h'], pe['mi'])}" if pe else fmt_time(p["h"], p["mi"]))
    href = f"{SITE_BASE_URL}/s/{esc(s.get('segment_id'))}/"
    return (f'<li><a href="{href}" target="_top"><span class="day">{esc(day)}'
            f'<span class="date">{esc(date)}</span></span>'
            f'<span class="tm">{esc(tm)}</span></a></li>')


def build_venue_embed_pages(directory: dict, doc: dict) -> int:
    """Write site/v/<slug>/embed/index.html for every LIVE-schedule venue — a
    minimal, iframe-friendly schedule widget any club can paste onto their own
    site (see the "Embed this schedule" block on the normal venue page). Each
    embed is a distribution node: the club's existing visitors see it, and it
    credits/links back to Open Play RI. Only built for venues we track a real
    schedule for — a static-address embed isn't worth a club's screen space."""
    venues = [v for v in directory.get("venues", []) if v.get("slug") and v.get("source_id")]
    if not venues:
        return 0

    upcoming_by_source: dict[str, list] = {}
    for s in doc.get("sessions", []):
        if not s.get("has_passed") and s.get("source_id"):
            upcoming_by_source.setdefault(s["source_id"], []).append(s)
    for lst in upcoming_by_source.values():
        lst.sort(key=lambda s: s.get("start") or "")

    count = 0
    for v in venues:
        slug = v["slug"]
        sess = upcoming_by_source.get(v["source_id"], [])
        rows = "".join(r for r in (_embed_session_row_html(s) for s in sess[:6]) if r)
        if rows:
            more = f'<a class="more" href="{SITE_BASE_URL}/v/{esc(slug)}/" target="_top">See the full schedule & register →</a>'
            schedule_html = f'<ul>{rows}</ul>{more}'
        else:
            schedule_html = (f'<p class="empty">No upcoming sessions listed right now — '
                              f'<a href="{SITE_BASE_URL}/v/{esc(slug)}/" target="_top" style="color:var(--forest)">check the full page</a>.</p>')

        out = _fill_template(EMBED_TEMPLATE, {
            "VENUE_NAME": esc(v.get("name") or "Pickleball"),
            "VENUE_HREF": f"{SITE_BASE_URL}/v/{esc(slug)}/",
            "HOME_HREF": f"{SITE_BASE_URL}/",
            "CANONICAL": f"{SITE_BASE_URL}/v/{slug}/embed/",
            "SCHEDULE_HTML": schedule_html,
        })
        edir = VENUES_DIR / slug / "embed"
        edir.mkdir(parents=True, exist_ok=True)
        (edir / "index.html").write_text(out, encoding="utf-8")
        count += 1
    return count


def build_venue_pages(directory: dict, doc: dict) -> int:
    """Write site/v/<slug>/index.html for every directory venue. Returns count.

    Each page is an SEO surface for a "pickleball in <town> RI" query: venue
    facts + SportsActivityLocation/Breadcrumb JSON-LD, the live open-play
    schedule inlined for the venues we've integrated, and cross-links to other
    venues in the same town. Directory is additive — absent/empty just means no
    pages (the rest of the build is unaffected)."""
    venues = [v for v in directory.get("venues", []) if v.get("slug")]
    if not venues:
        return 0

    # Town index for "more places nearby" cross-links.
    by_city = _group_by_city(venues)

    # Upcoming sessions per source, soonest first — inlined on linked venues.
    upcoming_by_source: dict[str, list] = {}
    for s in doc.get("sessions", []):
        if not s.get("has_passed") and s.get("source_id"):
            upcoming_by_source.setdefault(s["source_id"], []).append(s)
    for lst in upcoming_by_source.values():
        lst.sort(key=lambda s: s.get("start") or "")

    if VENUES_DIR.exists():
        shutil.rmtree(VENUES_DIR)
    VENUES_DIR.mkdir(parents=True, exist_ok=True)

    count = 0
    for v in venues:
        slug = v["slug"]
        name = v.get("name") or "Pickleball venue"
        city = v.get("city") or "Rhode Island"
        canonical = f"{SITE_BASE_URL}/v/{slug}/"
        addr = _venue_addr_line(v)
        map_href = _venue_map_href(v)
        is_live = bool(v.get("source_id"))
        n_up = int(v.get("upcoming_sessions") or 0)
        # "high" = the name/type says pickleball (a dedicated venue), so we can
        # speak in plain "play pickleball here" terms. "maybe" = Google surfaced
        # it for a pickleball query (a park/Y/rec center that may have courts) —
        # we DON'T assert it; we frame it honestly and tell people to confirm.
        is_dedicated = v.get("confidence") == "high" or is_live

        # ---- head / meta ----
        where = f"in {city}, RI" if city != "Rhode Island" else "in Rhode Island"
        page_title = f"{name} — Pickleball {where} | Open Play RI"
        og_title = f"{name} — Pickleball {where}"
        if is_live and n_up:
            meta_desc = (f"{name} in {city}, RI — {n_up} upcoming open-play pickleball "
                         f"session{'s' if n_up != 1 else ''} with times, prices, and live sign-up. "
                         f"Plus address, map, and how to play.")
        elif is_dedicated:
            bits = [f"Pickleball at {name}"]
            if addr:
                bits.append(addr)
            meta_desc = (". ".join(bits) + f". One of the places to play pickleball in {city}, "
                         "Rhode Island — address, map, phone, and links to plan a visit.")
        else:
            meta_desc = (f"{name}{' — ' + addr if addr else ''}. A {city}, Rhode Island spot that "
                         "comes up when searching for pickleball — find its location, hours, and "
                         "contact info, and confirm open-play times before you visit.")

        # ---- structured data ----
        crumbs_links = [("Open Play RI", f"{SITE_BASE_URL}/"),
                        (f"Pickleball in {city}", f"{SITE_BASE_URL}/t/{town_slug(city)}/") if city != "Rhode Island"
                        else ("Rhode Island", None),
                        (name, canonical)]
        jsonld = _jsonld_script(_venue_jsonld(v, canonical)) + "\n" + _jsonld_script(_breadcrumb_jsonld(crumbs_links))

        bc = ['<a href="../../">Open Play RI</a>', '<span class="sep">/</span>']
        if city != "Rhode Island":
            # link the town so crawlers (and users) walk venue → town landing page
            bc.append(f'<a href="../../t/{esc(town_slug(city))}/">{esc(city)}, RI</a>')
        else:
            bc.append("<span>Rhode Island</span>")
        breadcrumb = "".join(bc)

        # ---- badges ----
        badges = []
        if is_live:
            badges.append('<span class="badge live"><span class="dot"></span>Live open-play schedule</span>')
        if v.get("confidence") == "high":
            badges.append('<span class="badge">🏓 Dedicated pickleball</span>')
        if isinstance(v.get("rating"), (int, float)) and (v.get("rating_count") or 0) >= 1:
            badges.append(f'<span class="badge"><span class="star">★</span> {v["rating"]:.1f} '
                          f'<span style="color:var(--ink-faint);font-weight:600">({int(v["rating_count"])})</span></span>')
        elif v.get("primary_type"):
            badges.append(f'<span class="badge">{esc(v["primary_type"])}</span>')
        badges_html = f'<div class="badges">{"".join(badges)}</div>' if badges else ""

        # ---- sub line ----
        if is_live and n_up:
            sub = (f"Open-play pickleball in {esc(city)}, Rhode Island, with a live schedule below — "
                   f"see every upcoming session, time, and price, and register in a tap.")
        elif is_dedicated:
            sub = (f"A place to play pickleball in {esc(city)}, Rhode Island. "
                   f"Here's how to find it and plan a visit.")
        else:
            sub = (f"{esc(name)} comes up in pickleball searches around {esc(city)}, Rhode Island. "
                   f"Here's how to find it — and check whether it has open play before you go.")

        # ---- info card ----
        info = []
        if addr:
            info.append(("📍", f"<b>{esc(addr)}</b> · <a href=\"{esc(map_href)}\" target=\"_blank\" rel=\"noopener\">Open in Maps ↗</a>"))
        if v.get("phone"):
            ph = esc(fmt_phone(v["phone"]))
            tel = re.sub(r"\D", "", str(v["phone"]))
            info.append(("📞", f'<a href="tel:{esc(tel)}">{ph}</a>'))
        if v.get("website"):
            host = re.sub(r"^https?://(www\.)?", "", v["website"]).rstrip("/")
            info.append(("🌐", f'<a href="{esc(v["website"])}" target="_blank" rel="noopener">{esc(host)} ↗</a>'))
        if v.get("hours"):
            hrs = "<br>".join(esc(h) for h in v["hours"][:7])
            info.append(("🕑", f"<b>Hours</b><br>{hrs}"))
        if v.get("maps_uri"):
            info.append(("🔎", f'<a href="{esc(v["maps_uri"])}" target="_blank" rel="noopener">See reviews &amp; photos on Google ↗</a>'))
        info_lis = "".join(f'<li><span class="ico" aria-hidden="true">{ico}</span><span>{h}</span></li>' for ico, h in info)
        info_card = f'<section class="card"><h2>Visiting</h2><ul class="info">{info_lis}</ul>'
        # primary CTA: website if known, else directions
        if v.get("website"):
            info_card += (f'<div class="cta-row"><a class="btn btn-primary" href="{esc(v["website"])}" '
                          f'target="_blank" rel="noopener">Visit website <span class="arrow">↗</span></a>'
                          f'<a class="btn btn-ghost" href="{esc(map_href)}" target="_blank" rel="noopener">Directions</a></div>')
        else:
            info_card += (f'<div class="cta-row"><a class="btn btn-primary" href="{esc(map_href)}" '
                          f'target="_blank" rel="noopener">Get directions <span class="arrow">↗</span></a></div>')
        info_card += "</section>"

        # ---- live schedule block ----
        sched_html = ""
        if is_live:
            sess = upcoming_by_source.get(v["source_id"], [])
            rows = "".join(r for r in (_session_row_html(s) for s in sess[:8]) if r)
            reg_url = v.get("registration_url") or map_href
            cta_label = v.get("cta_label") or "Register"
            if rows:
                lead = (f"We track this venue's open-play schedule. Next "
                        f"{min(len(sess), 8)} session{'s' if min(len(sess), 8) != 1 else ''}:")
                more = (f'<a class="more" href="../../#sessions">See all {len(sess)} upcoming sessions '
                        f'<span aria-hidden="true">→</span></a>') if len(sess) > 8 else \
                       '<a class="more" href="../../#sessions">See the full schedule <span aria-hidden="true">→</span></a>'
                webcal = SITE_BASE_URL.replace("https://", "webcal://").replace("http://", "webcal://") + f"/v/{slug}/open-play.ics"
                cal = (f'<a class="more" href="{esc(webcal)}" style="margin-left:18px">'
                       f'<span aria-hidden="true">📅</span> Subscribe in your calendar</a>')
                embed_url = f"{SITE_BASE_URL}/v/{slug}/embed/"
                embed_snippet = esc(f'<iframe src="{embed_url}" title="{name} open-play schedule" '
                                     f'style="width:100%;max-width:420px;height:420px;border:1px solid #e4e0d3;'
                                     f'border-radius:12px" loading="lazy"></iframe>')
                embed_html = (f'<details class="embed-box"><summary>Citing this schedule elsewhere? Embed it — free</summary>'
                              f'<p class="lead">Writing about {esc(name)}, or building a resource page that '
                              f'links out to it? Paste this and the schedule shown stays live and current — '
                              f'no manual updates needed.</p>'
                              f'<pre class="embed-code">{embed_snippet}</pre></details>')
                sched_html = (f'<section class="sched"><h2>Open play schedule</h2>'
                              f'<p class="lead">{lead}</p><ul class="sessions">{rows}</ul>{more}{cal}</section>'
                              f'{embed_html}')

        # ---- nearby ----
        nearby = []
        for other in by_city.get(city, []):
            if other.get("slug") == slug:
                continue
            nearby.append(other)
        nearby_html = ""
        if nearby:
            cards = "".join(
                f'<a class="vlink" href="../{esc(o["slug"])}/"><span class="nm">{esc(o.get("name"))}</span>'
                f'<span class="ct">{esc(o.get("primary_type") or "Pickleball")}</span></a>'
                for o in nearby[:6]
            )
            head = f"More places to play in {esc(city)}" if city != "Rhode Island" else "More RI venues"
            nearby_html = f'<section class="nearby"><h2>{head}</h2><div class="vlist">{cards}</div></section>'

        body = (f'<div class="vhead"><div class="eyebrow">Pickleball {esc(where)}</div>'
                f'<h1>{esc(name)}</h1><p class="sub">{sub}</p>{badges_html}</div>'
                f'{sched_html}{info_card}{nearby_html}')

        out = _fill_template(VENUE_TEMPLATE, {
            "PAGE_TITLE": esc(page_title),
            "META_DESC": esc(meta_desc),
            "OG_TITLE": esc(og_title),
            "CANONICAL": esc(canonical),
            "OG_IMAGE": esc(f"{SITE_BASE_URL}/og.png"),
            "JSONLD": jsonld,
            "HOME_HREF": "../../",
            "BREADCRUMB": breadcrumb,
            "BODY": body,
        })

        sdir = VENUES_DIR / slug
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "index.html").write_text(out, encoding="utf-8")
        count += 1

    return count


# ---------------------------------------------------------------------------
# Town landing pages -> /t/<town-slug>/  (programmatic local SEO: one strong
# page per town targeting "pickleball in <town>, RI", aggregating its venues)
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=None)
def town_slug(city: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (city or "").lower()).strip("-")
    return s or "rhode-island"


def _venue_vlink(v: dict, href: str, live: bool) -> str:
    bits = []
    if v.get("primary_type"):
        bits.append(esc(v["primary_type"]))
    if isinstance(v.get("rating"), (int, float)) and (v.get("rating_count") or 0) >= 1:
        bits.append(f'★ {v["rating"]:.1f}')
    if live:
        bits.insert(0, '<span style="color:var(--forest);font-weight:700">● Live schedule</span>')
    meta = " · ".join(bits)
    return (f'<a class="vlink" href="{esc(href)}"><span class="nm">{esc(v.get("name"))}</span>'
            f'<span class="ct">{meta}</span></a>')


def _town_venue_ssr_html(directory: dict) -> tuple[str, str]:
    """Server-rendered <a href> links to every /v/ and /t/ page, for the
    homepage. The homepage's directory/session lists are JS-injected from
    fetch()'d JSON, so without this Googlebot's HTML-only crawl of the site's
    highest-authority page sees zero links to any venue or town page."""
    venues = [v for v in directory.get("venues", []) if v.get("slug")]
    by_city = _group_by_city(venues)
    towns_sorted = sorted(by_city.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    all_lis, footer_lis = [], []
    for city, vs in towns_sorted:
        if city == "Rhode Island":
            continue  # no /t/ page for the catch-all bucket
        slug = town_slug(city)
        vlis = "".join(f'<li><a href="v/{esc(v["slug"])}/">{esc(v.get("name"))}</a></li>'
                        for v in sorted(vs, key=_venue_rank_key))
        all_lis.append(f'<li class="gv"><h3><a href="t/{esc(slug)}/">{esc(city)}, RI</a></h3>'
                        f'<ul class="gv-items">{vlis}</ul></li>')
        footer_lis.append(f'<li><a href="t/{esc(slug)}/">{esc(city)}, RI</a></li>')
    return "".join(all_lis), "".join(footer_lis)


def _home_soonest_ssr_html(directory: dict, doc: dict) -> str:
    """Server-rendered 'next open-play sessions' block for the homepage.

    The homepage's interactive session list is fetched client-side from
    sessions.json, so a crawler, an AI-citation bot (ChatGPT/Perplexity fetch
    raw HTML, they don't run JS), or a no-JS/slow visitor sees only a
    "Loading…" skeleton — i.e. the site's single most valuable content (real
    open-play times) is invisible on its highest-authority, most-shared page.
    This renders the soonest ~12 upcoming sessions across all live venues
    straight into the HTML: real indexable/citable times, instant first paint.
    The JS list hides this block (#ssr-soonest) once it takes over, so JS users
    still get the full filterable experience with no duplication. Returns "" if
    there's no live data (every source failed) so the page degrades cleanly —
    same source-isolation philosophy as the rest of the build."""
    venues = [v for v in directory.get("venues", []) if v.get("slug") and v.get("source_id")]
    live_srcs = {v["source_id"]: v for v in venues}
    if not live_srcs:
        return ""
    sess = sorted(
        (s for s in doc.get("sessions", [])
         if not s.get("has_passed") and s.get("source_id") in live_srcs),
        key=lambda s: s.get("start") or "",
    )
    rows = "".join(r for r in (_town_session_row_html(s, live_srcs, href_base="")
                               for s in sess[:12]) if r)
    if not rows:
        return ""
    shown = min(len(sess), 12)
    n_live = len(live_srcs)
    lead = (f"The next {shown} drop-in open-play session{'s' if shown != 1 else ''} across the "
            f"{n_live} Rhode Island club{'s' if n_live != 1 else ''} we track live — times and "
            f"prices pulled from each club's own booking system and updated hourly. Tap any "
            f"session for details, or use the full filterable list below.")
    more = ('<a class="tsmore" href="#directory">Browse every RI venue in the directory '
            '<span aria-hidden="true">↓</span></a>')
    return (_TOWN_SCHED_CSS
            + '<section class="tsched" id="ssr-soonest" style="margin:14px 0 4px;">'
            + '<h2>Next open-play sessions in Rhode Island</h2>'
            + f'<p class="tslead">{lead}</p>'
            + f'<ul class="tsessions">{rows}</ul>{more}</section>')


def build_homepage(directory: dict, doc: dict) -> None:
    """Write site/index.html from the template, injecting server-rendered
    venue/town links (see _town_venue_ssr_html) and the soonest upcoming
    open-play sessions (see _home_soonest_ssr_html)."""
    all_venues_lis, footer_town_lis = _town_venue_ssr_html(directory)
    out = _fill_template(HOME_TEMPLATE, {
        "ALL_VENUES_SSR": all_venues_lis,
        "FOOTER_TOWN_LI": footer_town_lis,
        "SOONEST_SSR": _home_soonest_ssr_html(directory, doc),
    })
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "index.html").write_text(out, encoding="utf-8")


# Scoped styles for the town page's "Upcoming open play" card. Kept out of the
# shared venue template CSS (only town pages use it) and self-contained so the
# session times read high-contrast on the dark navy card (bright lime on
# --forest), unlike the shared .sched card. Emitted once per town page body.
_TOWN_SCHED_CSS = (
    '<style>'
    '.tsched{margin-top:22px;background:var(--forest);color:var(--bone);'
    'border-radius:var(--r);padding:clamp(18px,3vw,24px);}'
    '.tsched h2{font-family:var(--fd);font-weight:800;font-size:clamp(18px,2.6vw,22px);'
    'letter-spacing:-.02em;color:var(--bone);margin-bottom:6px;}'
    '.tsched .tslead{font-size:14px;color:rgba(243,239,226,.82);margin-bottom:14px;line-height:1.5;}'
    'ul.tsessions{list-style:none;display:flex;flex-direction:column;gap:2px;}'
    'ul.tsessions li a{display:flex;align-items:baseline;gap:12px;padding:11px 2px;'
    'text-decoration:none;border-bottom:1px solid rgba(243,239,226,.14);color:var(--bone);'
    'transition:padding .14s;}'
    'ul.tsessions li a:hover{padding-left:8px;}'
    'ul.tsessions li:last-child a{border-bottom:none;}'
    '.tsday{font-weight:700;font-size:14.5px;white-space:nowrap;}'
    '.tsday .tsdate{color:rgba(243,239,226,.6);font-weight:500;margin-left:7px;font-size:13px;}'
    '.tsvn{flex:1;min-width:0;font-size:13.5px;color:rgba(243,239,226,.78);'
    'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:right;}'
    '.tstm{font-family:var(--fm,"DM Mono",ui-monospace,Menlo,monospace);font-size:13px;'
    'color:var(--lime);font-weight:600;white-space:nowrap;font-variant-numeric:tabular-nums;}'
    '.tsched .tsmore{display:inline-flex;align-items:center;gap:7px;margin-top:14px;'
    'font-weight:700;font-size:14px;color:var(--lime);text-decoration:none;'
    'border-bottom:1.5px solid transparent;transition:border-color .15s;}'
    '.tsched .tsmore:hover{border-bottom-color:var(--gold);}'
    '</style>'
)

_TOWN_FAQ_CSS = (
    '<style>'
    '.tfaq{margin-top:26px;}'
    '.tfaq h2{font-family:var(--fd);font-weight:800;font-size:clamp(18px,2.6vw,22px);'
    'letter-spacing:-.02em;color:var(--forest);margin-bottom:14px;}'
    '.tfaq .faq-item{padding:14px 0;border-bottom:1px solid var(--line);}'
    '.tfaq .faq-item:last-child{border-bottom:none;}'
    '.tfaq .faq-q{font-family:var(--fd);font-weight:700;font-size:16px;'
    'color:var(--ink);margin-bottom:5px;line-height:1.35;}'
    '.tfaq .faq-a{font-size:14.5px;color:var(--ink-faint);line-height:1.55;}'
    '</style>'
)


def _join_names(items: list[dict], k: int) -> str:
    """Human list ('A, B, and C') of up to k venue names (plain text)."""
    picked = [v.get("name") or "" for v in items[:k]]
    picked = [p for p in picked if p]
    if not picked:
        return ""
    if len(picked) == 1:
        return picked[0]
    if len(picked) == 2:
        return f"{picked[0]} and {picked[1]}"
    return ", ".join(picked[:-1]) + f", and {picked[-1]}"


def _town_faq(city: str, vs: list[dict], live: list[dict]) -> tuple[str, dict]:
    """Data-driven FAQ for a town page: returns (visible_html, FAQPage jsonld).

    Q&A is the most AI-citable surface (answer engines quote it directly) and is
    FAQ-rich-result eligible. Answers are built from the town's real venue list
    (counts, live-schedule club names) so each town page carries substantive,
    non-boilerplate content. The visible text matches the schema text exactly —
    Google requires FAQ content to be present on the page for the markup to be
    valid."""
    n = len(vs)
    qa: list[tuple[str, str]] = []

    # Q1 — where to play (venue count + a few real names)
    more = n - min(n, 3)
    # plain comma list when a "and N more" tail follows, natural "A, B and C" otherwise
    names = [v.get("name") or "" for v in vs[:3]]
    names = [x for x in names if x]
    top = ", ".join(names) if more > 0 else _join_names(vs, 3)
    a1 = (f"There {'is' if n == 1 else 'are'} {n} place{'s' if n != 1 else ''} to play "
          f"pickleball in {city}, Rhode Island")
    if top:
        a1 += (f" — {top}" if n == 1 else f", including {top}")
        if more > 0:
            a1 += f" and {more} more"
    a1 += (". Each venue on this page has an address, map, phone, and hours — and, where a "
           "club publishes one, a live open-play schedule.")
    qa.append((f"Where can I play pickleball in {city}, Rhode Island?", a1))

    # Q2 — drop-in / open play (data-driven: live vs. not)
    if live:
        a2 = (f"Yes. {_join_names(live, len(live))} run open-play (drop-in) pickleball in "
              f"{city}, and this page lists their upcoming session times, prices, and sign-up "
              f"counts — pulled from each club's own booking system and refreshed about once an "
              f"hour.")
    else:
        a2 = (f"The pickleball venues in {city} are listed above with contact details and hours. "
              f"Open-play (drop-in) times vary by venue, so tap a venue for its schedule or call "
              f"ahead — and check the nearby Rhode Island towns below for venues with a live "
              f"open-play schedule.")
    qa.append((f"Is there drop-in or open-play pickleball in {city}?", a2))

    # Q3 — cost
    a3 = (f"Public and town courts in {city} are usually free to play. Dedicated clubs typically "
          f"charge a few dollars per drop-in session")
    if live:
        a3 += (", and where we track a live schedule the current per-session price is shown next "
               "to each session above.")
    else:
        a3 += "; check the individual venue's page for its current pricing."
    qa.append((f"How much does it cost to play pickleball in {city}?", a3))

    items = "".join(
        f'<div class="faq-item"><h3 class="faq-q">{esc(q)}</h3>'
        f'<p class="faq-a">{esc(a)}</p></div>'
        for q, a in qa
    )
    html = (_TOWN_FAQ_CSS
            + f'<section class="tfaq nearby"><h2>Pickleball in {esc(city)}: FAQ</h2>{items}</section>')
    jsonld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in qa
        ],
    }
    return html, jsonld


def build_town_pages(directory: dict, doc: dict) -> int:
    """Write site/t/<town-slug>/index.html for every town with venues. Returns count."""
    venues = [v for v in directory.get("venues", []) if v.get("slug")]
    if not venues:
        return 0
    by_city = _group_by_city(venues)
    towns_sorted = sorted(by_city.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    town_slugs = {c: town_slug(c) for c in by_city}

    if TOWNS_DIR.exists():
        shutil.rmtree(TOWNS_DIR)
    TOWNS_DIR.mkdir(parents=True, exist_ok=True)

    count = 0
    for city, vs in by_city.items():
        if city == "Rhode Island":
            continue
        slug = town_slugs[city]
        vs = sorted(vs, key=_venue_rank_key)
        n = len(vs)
        live = [v for v in vs if v.get("source_id")]
        canonical = f"{SITE_BASE_URL}/t/{slug}/"

        page_title = f"Pickleball in {city}, RI — Courts, Clubs & Open Play | Open Play RI"
        og_title = f"Pickleball in {city}, Rhode Island — {n} place{'s' if n != 1 else ''} to play"
        meta_desc = (f"Where to play pickleball in {city}, Rhode Island: {n} court"
                     f"{'s' if n != 1 else ''}, club{'s' if n != 1 else ''}, and open-play venue"
                     f"{'s' if n != 1 else ''} with addresses, maps, and details"
                     + (f" — including {len(live)} with a live open-play schedule." if live else ".")
                     + " Find pickleball near you.")

        # structured data: CollectionPage + ItemList of venues + breadcrumb
        item_list = {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": f"Pickleball venues in {city}, RI",
            "numberOfItems": n,
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "name": v.get("name"),
                 "url": f"{SITE_BASE_URL}/v/{v['slug']}/"}
                for i, v in enumerate(vs)
            ],
        }
        crumbs = _breadcrumb_jsonld([("Open Play RI", f"{SITE_BASE_URL}/"),
                                     (f"Pickleball in {city}", canonical)])
        faq_html, faq_jsonld = _town_faq(city, vs, live)
        jsonld = (_jsonld_script(item_list) + "\n" + _jsonld_script(crumbs)
                  + "\n" + _jsonld_script(faq_jsonld))
        breadcrumb = '<a href="../../">Open Play RI</a><span class="sep">/</span>' + f'<span>{esc(city)}, RI</span>'

        # body
        live_note = ""
        if live:
            names = ", ".join(esc(v.get("name")) for v in live)
            live_note = (f'<div class="badges"><span class="badge live"><span class="dot"></span>'
                         f'Live open-play schedule · {names}</span></div>')
        intro = (f"Looking for somewhere to play pickleball in {esc(city)}, Rhode Island? "
                 f"Here {'is' if n == 1 else 'are'} {n} place{'s' if n != 1 else ''} to play — "
                 f"dedicated clubs, racquet and tennis clubs, YMCAs, rec centers, and public courts. "
                 f"Tap any venue for its address, map, phone, hours"
                 + (", and live open-play schedule" if live else "") + ".")
        cards = "".join(_venue_vlink(v, f"../../v/{v['slug']}/", bool(v.get("source_id"))) for v in vs)
        # Upcoming open play across this town's live-schedule venues — put the
        # real session times right on the town page (the ad + organic landing
        # page for "pickleball in <town>, RI") instead of making a visitor click
        # into each venue to find out when they can actually play. Server-
        # rendered, so it's real indexable content and works without JS.
        live_srcs = {v["source_id"]: v for v in vs if v.get("source_id")}
        sched_html = ""
        if live_srcs:
            tsess = sorted(
                (s for s in doc.get("sessions", [])
                 if not s.get("has_passed") and s.get("source_id") in live_srcs),
                key=lambda s: s.get("start") or "",
            )
            rows = "".join(r for r in (_town_session_row_html(s, live_srcs) for s in tsess[:10]) if r)
            if rows:
                shown = min(len(tsess), 10)
                multi = len(live_srcs) > 1
                tslead = (f"The next {shown} open-play session{'s' if shown != 1 else ''} at "
                          f"{esc(city)}'s live-schedule venue{'s' if multi else ''} — times pulled "
                          f"from each club's own booking system and updated hourly.")
                more = ('<a class="tsmore" href="../../#sessions">See every upcoming RI session '
                        '<span aria-hidden="true">→</span></a>')
                sched_html = (_TOWN_SCHED_CSS
                              + f'<section class="tsched"><h2>Upcoming open play in {esc(city)}</h2>'
                              + f'<p class="tslead">{tslead}</p>'
                              + f'<ul class="tsessions">{rows}</ul>{more}</section>')
        # nearby towns (by venue count)
        others = [c for c, _ in towns_sorted if c != city and c != "Rhode Island"][:8]
        nearby = "".join(
            f'<a class="vlink" href="../{town_slugs[c]}/"><span class="nm">Pickleball in {esc(c)}</span>'
            f'<span class="ct">{len(by_city[c])} venue{"s" if len(by_city[c]) != 1 else ""}</span></a>'
            for c in others
        )
        body = (f'<div class="vhead"><div class="eyebrow">Rhode Island · {esc(city)}</div>'
                f'<h1>Pickleball in {esc(city)}, Rhode Island</h1>'
                f'<p class="sub">{intro}</p>{live_note}</div>'
                f'{sched_html}'
                f'<section class="nearby" style="margin-top:22px"><h2>{n} place{"s" if n != 1 else ""} to play in {esc(city)}</h2>'
                f'<div class="vlist">{cards}</div></section>'
                + (f'<section class="nearby"><h2>Other Rhode Island towns</h2><div class="vlist">{nearby}</div></section>' if nearby else "")
                + faq_html)

        out = _fill_template(VENUE_TEMPLATE, {
            "PAGE_TITLE": esc(page_title), "META_DESC": esc(meta_desc), "OG_TITLE": esc(og_title),
            "CANONICAL": esc(canonical), "OG_IMAGE": esc(f"{SITE_BASE_URL}/og.png"),
            "JSONLD": jsonld, "HOME_HREF": "../../", "BREADCRUMB": breadcrumb, "BODY": body,
        })
        sdir = TOWNS_DIR / slug
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "index.html").write_text(out, encoding="utf-8")
        count += 1

    return count


# ---------------------------------------------------------------------------
# Collection / intent pages -> /guide/<slug>/ — target high-intent searches that
# the town pages don't ("indoor pickleball RI", "free public courts", "clubs").
# ---------------------------------------------------------------------------
def _vt(v):  # normalized primary type
    return (v.get("primary_type") or "").lower()


COLLECTIONS = [
    {
        "slug": "indoor-pickleball-rhode-island",
        "h1": "Indoor Pickleball in Rhode Island",
        "title": "Indoor Pickleball in Rhode Island — Where to Play Year-Round",
        "intent": "indoor pickleball",
        "blurb": ("Rain, snow, or summer heat — these Rhode Island venues offer indoor pickleball, "
                  "from dedicated clubs to YMCAs, rec centers, and sports complexes. Great for "
                  "year-round and winter play."),
        "match": lambda v: ("indoor" in (v.get("name") or "").lower()
                            or _vt(v) in {"gym", "fitness center", "sports complex",
                                          "sports activity location", "community center",
                                          "recreation center"}),
    },
    {
        "slug": "free-public-pickleball-courts-rhode-island",
        "h1": "Free & Public Pickleball Courts in Rhode Island",
        "title": "Free Public Pickleball Courts in Rhode Island — Town & Park Courts",
        "intent": "free public pickleball courts",
        "blurb": ("Want to play for free? These Rhode Island public parks and town courts have "
                  "pickleball — usually no fee and open to everyone. Bring your own paddle and net "
                  "where needed, and check the town's rules for open-play times."),
        "match": lambda v: (v.get("confidence") != "high"
                            and _vt(v) in {"park", "city park", "state park", "athletic field",
                                           "tennis court", "playground"}),
    },
    {
        "slug": "pickleball-clubs-rhode-island",
        "h1": "Pickleball Clubs in Rhode Island",
        "title": "Pickleball Clubs in Rhode Island — Dedicated Courts & Open Play",
        "intent": "pickleball clubs",
        "blurb": ("Rhode Island's dedicated pickleball clubs and racquet clubs — the spots built for "
                  "the sport, with the most courts, organized open play, lessons, and leagues."),
        "match": lambda v: (v.get("confidence") == "high"
                            or _vt(v) in {"sports club", "country club"}),
    },
]


def _guide_faq(col: dict, matched: list[dict], live: list[dict], by_city: dict) -> tuple[str, dict]:
    """Data-driven FAQ + FAQPage schema for a /guide/ intent page.

    Guides target the exact informational queries answer engines field directly
    ("where can I play indoor pickleball in RI?", "free public pickleball courts
    RI"), so a Q&A block built from each guide's real matched-venue data is the
    highest-leverage AI-citable / FAQ-rich-result surface for these pages. The
    visible text equals the schema text exactly, as Google requires for the
    markup to be valid. Answers are assembled from live counts, real venue
    names, and (where tracked) the live-schedule club names — no boilerplate."""
    n = len(matched)
    isare = "is" if n == 1 else "are"
    s = "" if n == 1 else "s"
    # top venue names — comma list + "and N more" tail when long, natural join otherwise
    more = n - min(n, 3)
    names = [v.get("name") or "" for v in matched[:3]]
    names = [x for x in names if x]
    top = ", ".join(names) if more > 0 else _join_names(matched, 3)
    top_clause = ""
    if top:
        top_clause = f", including {top}" + (f" and {more} more" if more > 0 else "")
    # towns represented, most venues first
    tnames = [c for c in sorted(by_city, key=lambda c: (-len(by_city[c]), c)) if c != "Rhode Island"]
    ntowns = len(tnames)
    towns_txt = _join_names([{"name": c} for c in tnames], 4)
    towns_clause = (f" across {ntowns} town{'s' if ntowns != 1 else ''}"
                    + (f" including {towns_txt}" if towns_txt else "")) if ntowns else ""
    live_txt = _join_names(live, len(live)) if live else ""

    qa: list[tuple[str, str]] = []
    if col["slug"] == "indoor-pickleball-rhode-island":
        qa.append(("Where can I play indoor pickleball in Rhode Island?",
                   f"There {isare} {n} indoor pickleball venue{s} in Rhode Island{top_clause}. "
                   f"They range from dedicated pickleball clubs to YMCAs, rec centers, and sports "
                   f"complexes{towns_clause} — each listed here with an address, map, and details."))
        a2 = "Yes — indoor courts stay open through winter, rain, and summer heat, so you can play year-round."
        a2 += (f" {live_txt} publish live open-play schedules you can check on this site before you head out."
               if live else " Tap any venue for its hours and open-play times, which vary by location.")
        qa.append(("Can I play pickleball indoors year-round in Rhode Island?", a2))
        qa.append(("Is indoor pickleball free in Rhode Island?",
                   "Most indoor venues — clubs, YMCAs, and sports complexes — charge a small drop-in fee "
                   "(usually a few dollars a session) or membership, since they maintain dedicated indoor "
                   "courts. Free play is far more common at public outdoor courts; see our free public "
                   "courts guide for those."))
    elif col["slug"] == "free-public-pickleball-courts-rhode-island":
        qa.append(("Where are the free public pickleball courts in Rhode Island?",
                   f"Rhode Island has {n} free or public pickleball court location{s}{top_clause}"
                   f"{towns_clause}. These are town parks and public courts — generally no fee and "
                   f"open to everyone."))
        qa.append(("Do I need to reserve or pay to play at a public court in Rhode Island?",
                   "Public and town courts are usually free and first-come, first-served — no reservation "
                   "or membership. Bring your own paddle, and a portable net where courts aren't lined or "
                   "netted for pickleball. Check the town's posted rules for open-play hours and any "
                   "resident-only times."))
        qa.append(("When are the public pickleball courts open in Rhode Island?",
                   "Hours vary by town and season — most outdoor courts are open dawn to dusk in the "
                   "warmer months. Tap a court for its address and details, and check the town's "
                   "parks-and-recreation page for current open-play times."))
    else:  # pickleball-clubs-rhode-island (and any future club-type guide)
        qa.append((f"What pickleball clubs are there in Rhode Island?",
                   f"There {isare} {n} pickleball club{s} in Rhode Island{top_clause}. These are the "
                   f"venues built for the sport — the most courts, plus organized open play, lessons, "
                   f"and leagues{towns_clause}."))
        a2 = ("Yes. " + f"{live_txt} publish live open-play schedules — real session times, prices, and "
              "sign-up counts, pulled from each club's own booking system and refreshed about hourly — "
              "which you can see on each club's page here.") if live else \
             ("Yes — most clubs run scheduled open-play and drop-in sessions. Tap a club for its "
              "schedule, or call ahead to confirm times.")
        qa.append(("Do Rhode Island pickleball clubs have open play or drop-in?", a2))
        a3 = ("Clubs typically charge a drop-in fee of a few dollars per session, with membership or "
              "class packages available.")
        a3 += (" Where we track a live schedule, the current per-session price is shown next to each "
               "session on the club's page." if live else " Tap a club for its current pricing.")
        qa.append(("How much does it cost to play at a pickleball club in Rhode Island?", a3))

    items = "".join(
        f'<div class="faq-item"><h3 class="faq-q">{esc(q)}</h3>'
        f'<p class="faq-a">{esc(a)}</p></div>'
        for q, a in qa
    )
    html = (_TOWN_FAQ_CSS
            + f'<section class="tfaq nearby"><h2>{esc(col["h1"])}: FAQ</h2>{items}</section>')
    jsonld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in qa
        ],
    }
    return html, jsonld


def build_collection_pages(directory: dict, doc: dict) -> int:
    """Write site/guide/<slug>/index.html for each curated collection. Returns count."""
    venues = [v for v in directory.get("venues", []) if v.get("slug")]
    if not venues:
        return 0
    cdir = SITE / "guide"
    if cdir.exists():
        shutil.rmtree(cdir)
    cdir.mkdir(parents=True, exist_ok=True)

    count = 0
    for col in COLLECTIONS:
        matched = sorted([v for v in venues if col["match"](v)], key=_venue_rank_key)
        if len(matched) < 3:
            continue  # too thin to be a useful page
        n = len(matched)
        canonical = f"{SITE_BASE_URL}/guide/{col['slug']}/"
        live = [v for v in matched if v.get("source_id")]
        meta_desc = (f"{col['blurb']} {n} venues across Rhode Island"
                     + (f", {len(live)} with a live open-play schedule." if live else ".")
                     + " Addresses, maps, and details for each.")

        item_list = {
            "@context": "https://schema.org", "@type": "ItemList",
            "name": col["h1"], "numberOfItems": n,
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "name": v.get("name"),
                 "url": f"{SITE_BASE_URL}/v/{v['slug']}/"}
                for i, v in enumerate(matched)
            ],
        }
        crumbs = _breadcrumb_jsonld([("Open Play RI", f"{SITE_BASE_URL}/"),
                                     (col["h1"], canonical)])
        # group matched venues by town (reused for both the FAQ and the sections)
        by_city = _group_by_city(matched)
        faq_html, faq_jsonld = _guide_faq(col, matched, live, by_city)
        jsonld = (_jsonld_script(item_list) + "\n" + _jsonld_script(crumbs)
                  + "\n" + _jsonld_script(faq_jsonld))
        breadcrumb = ('<a href="../../">Open Play RI</a><span class="sep">/</span>'
                      f'<span>{esc(col["h1"])}</span>')

        live_note = ""
        if live:
            names = ", ".join(esc(v.get("name")) for v in live[:4])
            live_note = (f'<div class="badges"><span class="badge live"><span class="dot"></span>'
                         f'Live open-play schedule · {names}</span></div>')

        # order the by-town sections for scannability (by_city built above)
        towns = sorted(by_city, key=lambda c: (-len(by_city[c]), c))
        sections = []
        for c in towns:
            cards = "".join(_venue_vlink(v, f"../../v/{v['slug']}/", bool(v.get("source_id")))
                            for v in by_city[c])
            tslug = town_slug(c)
            head = (f'<a href="../../t/{esc(tslug)}/" style="text-decoration:none">{esc(c)}, RI →</a>'
                    if c != "Rhode Island" else "Rhode Island")
            sections.append(f'<section class="nearby"><h2>{head}</h2><div class="vlist">{cards}</div></section>')

        # cross-links to the other guides
        others = [c for c in COLLECTIONS if c["slug"] != col["slug"]]
        guide_links = "".join(
            f'<a class="vlink" href="../{esc(o["slug"])}/"><span class="nm">{esc(o["h1"])}</span>'
            f'<span class="ct">guide</span></a>' for o in others
        )
        guide_sec = f'<section class="nearby"><h2>More guides</h2><div class="vlist">{guide_links}</div></section>'

        body = (f'<div class="vhead"><div class="eyebrow">Rhode Island · Guide</div>'
                f'<h1>{esc(col["h1"])}</h1><p class="sub">{esc(col["blurb"])}</p>{live_note}</div>'
                f'{"".join(sections)}{guide_sec}{faq_html}')

        out = _fill_template(VENUE_TEMPLATE, {
            "PAGE_TITLE": esc(col["title"]), "META_DESC": esc(meta_desc),
            "OG_TITLE": esc(col["h1"]), "CANONICAL": esc(canonical),
            "OG_IMAGE": esc(f"{SITE_BASE_URL}/og.png"), "JSONLD": jsonld,
            "HOME_HREF": "../../", "BREADCRUMB": breadcrumb, "BODY": body,
        })
        sdir = cdir / col["slug"]
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "index.html").write_text(out, encoding="utf-8")
        count += 1

    return count


_ICS_TZ = (
    "BEGIN:VTIMEZONE\r\nTZID:America/New_York\r\n"
    "BEGIN:DAYLIGHT\r\nTZOFFSETFROM:-0500\r\nTZOFFSETTO:-0400\r\nTZNAME:EDT\r\n"
    "DTSTART:19700308T020000\r\nRRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU\r\nEND:DAYLIGHT\r\n"
    "BEGIN:STANDARD\r\nTZOFFSETFROM:-0400\r\nTZOFFSETTO:-0500\r\nTZNAME:EST\r\n"
    "DTSTART:19701101T020000\r\nRRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU\r\nEND:STANDARD\r\n"
    "END:VTIMEZONE\r\n"
)


def _ics_esc(s: str) -> str:
    return (str(s or "").replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n").replace("\r", ""))


def _ics_dt(iso: str) -> str | None:
    """A local 'YYYY-MM-DDTHH:MM:SS' string -> ICS local datetime 'YYYYMMDDTHHMMSS'."""
    p = parse_local(iso)
    if not p:
        return None
    return f"{p['y']:04d}{p['mo']:02d}{p['d']:02d}T{p['h']:02d}{p['mi']:02d}00"


def _write_ics(path: pathlib.Path, name: str, sessions: list, sources_by_id: dict, stamp: str) -> int:
    """Write an iCalendar feed of upcoming open-play sessions. Returns event count."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Open Play RI//Pickleball//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             f"X-WR-CALNAME:{_ics_esc(name)}", "X-WR-TIMEZONE:America/New_York"]
    out = "\r\n".join(lines) + "\r\n" + _ICS_TZ
    n = 0
    for s in sessions:
        if s.get("has_passed"):
            continue
        ds = _ics_dt(s.get("start"))
        if not ds:
            continue
        de = _ics_dt(s.get("end")) or ds
        src = sources_by_id.get(s.get("source_id"), {})
        venue = (src.get("venue") or {})
        vname = s.get("venue_name") or venue.get("short_name") or venue.get("name") or "Open Play RI"
        act = short_name(s.get("activity_name"))
        url = f"{SITE_BASE_URL}/s/{s.get('segment_id')}/"
        loc = venue_line_for(venue) if venue else vname
        ev = [
            "BEGIN:VEVENT",
            f"UID:{_ics_esc(str(s.get('segment_id')))}@openplayri",
            f"DTSTAMP:{stamp}",
            f"DTSTART;TZID=America/New_York:{ds}",
            f"DTEND;TZID=America/New_York:{de}",
            f"SUMMARY:{_ics_esc(act + ' — ' + vname)}",
            f"LOCATION:{_ics_esc(loc)}",
            f"URL:{_ics_esc(url)}",
            f"DESCRIPTION:{_ics_esc('Open-play pickleball at ' + vname + '. Details & registration: ' + url)}",
            "END:VEVENT",
        ]
        out += "\r\n".join(ev) + "\r\n"
        n += 1
    out += "END:VCALENDAR\r\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(out, encoding="utf-8")
    return n


def build_calendars(directory: dict, doc: dict) -> int:
    """Write .ics calendar feeds (all-RI + per live venue) so users can subscribe to
    open play in their phone/Google calendar — a retention hook + a useful, distinct
    feature. Returns the number of feeds written."""
    sessions = [s for s in doc.get("sessions", []) if not s.get("has_passed")]
    sources_by_id = {m["id"]: m for m in doc.get("sources", []) if m.get("ok")}
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    feeds = 0
    # combined all-RI feed
    _write_ics(SITE / "open-play-rhode-island.ics", "RI Pickleball Open Play — Open Play RI",
               sessions, sources_by_id, stamp)
    feeds += 1
    # per-venue feeds, written into the venue page dir (keyed by directory slug)
    slug_by_source = {}
    for v in directory.get("venues", []):
        if v.get("source_id") and v.get("slug"):
            slug_by_source[v["source_id"]] = v["slug"]
    by_source: dict[str, list] = {}
    for s in sessions:
        by_source.setdefault(s.get("source_id"), []).append(s)
    for sid, slug in slug_by_source.items():
        vs = by_source.get(sid, [])
        if not vs:
            continue
        vname = (sources_by_id.get(sid, {}).get("venue") or {}).get("short_name") or "Open Play"
        _write_ics(VENUES_DIR / slug / "open-play.ics", f"{vname} Open Play — Open Play RI",
                   vs, sources_by_id, stamp)
        feeds += 1
    return feeds


def _bar_row(label: str, n: int, total: int, sub: str = "", href: str | None = None) -> str:
    pct = round(n / total * 100) if total else 0
    label_html = f'<a href="{esc(href)}">{esc(label)}</a>' if href else esc(label)
    return (
        f'<div class="barrow"><div class="barlab">{label_html}'
        f'<span class="barn">{n}{(" · " + esc(sub)) if sub else ""}</span></div>'
        f'<div class="bartrack"><i style="width:{max(pct,2)}%"></i></div></div>'
    )


def build_report_page(directory: dict, doc: dict) -> int:
    """Write site/rhode-island-pickleball-report/ — an auto-updating data/insights
    page derived from the aggregated directory + live schedules. A distinctive,
    linkable content asset (ranks for "rhode island pickleball" informational
    queries) that only an aggregator sitting on this data can produce."""
    venues = [v for v in directory.get("venues", []) if v.get("slug")]
    if len(venues) < 5:
        return 0
    sessions = [s for s in doc.get("sessions", []) if not s.get("has_passed")]

    towns = collections.Counter(v.get("city") for v in venues if v.get("city"))
    n_towns = len(towns)
    n_clubs = sum(1 for v in venues if v.get("confidence") == "high")
    live_venues = len({s.get("source_id") for s in sessions if s.get("source_id")})

    WD = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    wd = collections.Counter()
    hr = collections.Counter()
    for s in sessions:
        p = parse_local(s.get("start"))
        if not p:
            continue
        wd[(p["wd"] + 6) % 7] += 1  # Sun=0..Sat=6 → Mon=0..Sun=6
        hr[p["h"]] += 1
    busiest_day = WD[max(wd, key=wd.get)] if wd else "—"
    top_real_town = next((t for t, _ in towns.most_common() if t != "Rhode Island"), None)

    def hour_label(h):
        ap = "am" if h < 12 else "pm"
        hh = h % 12 or 12
        return f"{hh}{ap}"
    tod = {"Morning (6–11am)": sum(hr[h] for h in range(6, 12)),
           "Midday (11am–2pm)": sum(hr[h] for h in range(11, 14)),
           "Afternoon (2–5pm)": sum(hr[h] for h in range(14, 17)),
           "Evening (5–9pm)": sum(hr[h] for h in range(17, 21))}

    updated = (doc.get("scraped_at_utc") or dt.datetime.now(dt.timezone.utc).isoformat())[:10]
    canonical = f"{SITE_BASE_URL}/rhode-island-pickleball-report/"

    title = "The State of Pickleball in Rhode Island — A Data Report | Open Play RI"
    h1 = "The State of Pickleball in Rhode Island"
    meta_desc = (f"A data report on pickleball in Rhode Island: {len(venues)} places to play across "
                 f"{n_towns} towns, {len(sessions)} upcoming open-play sessions tracked, and when & "
                 f"where Rhode Islanders play. Updated continuously by Open Play RI.")

    article = {
        "@context": "https://schema.org", "@type": "Article",
        "headline": h1, "datePublished": "2026-06-18", "dateModified": updated,
        "author": {"@type": "Organization", "name": "Open Play RI"},
        "publisher": {"@type": "Organization", "name": "Open Play RI"},
        "mainEntityOfPage": canonical, "url": canonical, "description": meta_desc,
        "about": "Pickleball in Rhode Island",
    }
    crumbs = _breadcrumb_jsonld([("Open Play RI", f"{SITE_BASE_URL}/"),
                                 ("RI Pickleball Report", canonical)])
    jsonld = _jsonld_script(article) + "\n" + _jsonld_script(crumbs)
    breadcrumb = '<a href="../">Open Play RI</a><span class="sep">/</span><span>RI Pickleball Report</span>'

    # ---- body ----
    stat = lambda n, l: f'<div class="rstat"><div class="rn">{n}</div><div class="rl">{esc(l)}</div></div>'
    big = ('<div class="rstats">'
           + stat(len(venues), "places to play")
           + stat(n_towns, "towns & cities")
           + stat(f'<span class="accent">{live_venues}</span>', "live schedules")
           + stat(len(sessions), "upcoming sessions")
           + "</div>")

    top_towns = "".join(
        _bar_row(f"{t}, RI", c, towns.most_common(1)[0][1],
                 href=(f"../t/{town_slug(t)}/" if t != "Rhode Island" else None))
        for t, c in towns.most_common(10)
    )
    wd_bars = "".join(_bar_row(WD[i], wd[i], max(wd.values()) if wd else 1) for i in range(7))
    tod_bars = "".join(_bar_row(k, v, max(tod.values()) if tod else 1) for k, v in tod.items())

    intro = (f"Rhode Island may be the smallest state, but it punches above its weight on pickleball. "
             f"Open Play RI tracks <b>{len(venues)} places to play</b> across <b>{n_towns}</b> cities and "
             f"towns — from dedicated clubs to YMCAs, racquet clubs, and public park courts — and pulls "
             f"<b>live open-play schedules</b> from {live_venues} of them. Here's what the data says about "
             f"where and when the Ocean State plays. <span class='rfresh'>Updated {esc(updated)}.</span>")

    body = (
        '<style>'
        '.rstats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:22px 0 8px;}'
        '.rstat{background:var(--paper);border:1.5px solid var(--line-strong);border-radius:var(--r);padding:16px 18px;}'
        '.rn{font-family:var(--fd);font-weight:800;font-size:clamp(26px,4.4vw,38px);letter-spacing:-.03em;line-height:1;color:var(--ink);}'
        '.rn .accent{color:var(--forest);}'
        '.rl{margin-top:6px;font-size:13px;color:var(--ink-soft);font-weight:600;}'
        '.rfresh{color:var(--ink-faint);font-weight:600;}'
        '.barrow{margin:9px 0;}'
        '.barlab{display:flex;justify-content:space-between;font-size:13.5px;font-weight:600;color:var(--ink-soft);margin-bottom:4px;}'
        '.barlab a{color:var(--forest);text-decoration:none;border-bottom:1px solid var(--line-strong);}'
        '.barlab a:hover{border-color:var(--forest);}'
        '.barn{color:var(--ink);font-variant-numeric:tabular-nums;}'
        '.bartrack{height:9px;background:var(--bone-2);border:1px solid var(--line);border-radius:999px;overflow:hidden;}'
        '.bartrack>i{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,var(--forest),var(--lime-deep));}'
        '.rsec{margin-top:30px;}.rsec h2{font-family:var(--fd);font-weight:800;font-size:clamp(19px,2.6vw,24px);letter-spacing:-.02em;margin-bottom:4px;}'
        '.rsec p.k{font-size:14px;color:var(--ink-soft);margin-bottom:14px;}'
        '.rkey{background:var(--forest);color:var(--bone);border-radius:var(--r);padding:16px 20px;margin-top:14px;font-size:15px;line-height:1.5;}'
        '.rkey b{color:var(--lime);}'
        '</style>'
        f'<div class="vhead"><div class="eyebrow">Rhode Island · Data report</div>'
        f'<h1>{esc(h1)}</h1><p class="sub" style="max-width:60ch">{intro}</p></div>'
        f'{big}'
        f'<div class="rkey">The busiest day for open play in RI is <b>{esc(busiest_day)}</b>, and '
        f'mornings rule — <b>{tod["Morning (6–11am)"]}</b> of the next sessions tip off between 6 and 11am.</div>'
        f'<section class="rsec"><h2>Where the courts are</h2><p class="k">Towns with the most places to play pickleball.</p>{top_towns}</section>'
        f'<section class="rsec"><h2>When Rhode Island plays</h2><p class="k">Upcoming open-play sessions by day of week (across the venues we track live).</p>{wd_bars}</section>'
        f'<section class="rsec"><h2>What time of day</h2><p class="k">Upcoming open-play sessions by time of day.</p>{tod_bars}</section>'
        f'<section class="rsec"><h2>The breakdown</h2>'
        f'{_bar_row("Dedicated pickleball clubs", n_clubs, len(venues))}'
        f'{_bar_row("Venues with public reviews", sum(1 for v in venues if v.get("rating")), len(venues))}'
        f'{_bar_row("Venues with a website", sum(1 for v in venues if v.get("website")), len(venues))}'
        f'{_bar_row("Venues with live schedules here", live_venues, len(venues))}</section>'
        f'<section class="nearby" style="margin-top:30px"><h2>Explore the data</h2><div class="vlist">'
        f'<a class="vlink" href="../#directory"><span class="nm">Browse all {len(venues)} RI venues</span><span class="ct">directory</span></a>'
        f'<a class="vlink" href="../#sessions"><span class="nm">See the live open-play schedule</span><span class="ct">{len(sessions)} sessions</span></a>'
        + (f'<a class="vlink" href="../t/{esc(town_slug(top_real_town))}/">'
           f'<span class="nm">Pickleball in {esc(top_real_town)}</span>'
           f'<span class="ct">top town, {towns[top_real_town]} venues</span></a>' if top_real_town else "")
        + "".join(
            f'<a class="vlink" href="../guide/{esc(col["slug"])}/"><span class="nm">{esc(col["h1"])}</span><span class="ct">guide</span></a>'
            for col in COLLECTIONS
        )
        + f'</div></section>'
        f'<p style="margin-top:24px;font-size:12.5px;color:var(--ink-faint);line-height:1.6">Methodology: venue counts come from public mapping data for Rhode Island; '
        f'session counts are live open-play/drop-in events from the {live_venues} venues Open Play RI '
        f'tracks (refreshed hourly) and reflect scheduled sessions in the next few weeks, not all-time. '
        f'Numbers update automatically. Free to cite with a link to Open Play RI.</p>'
    )

    out = _fill_template(VENUE_TEMPLATE, {
        "PAGE_TITLE": esc(title), "META_DESC": esc(meta_desc), "OG_TITLE": esc(h1),
        "CANONICAL": esc(canonical), "OG_IMAGE": esc(f"{SITE_BASE_URL}/og.png"),
        "JSONLD": jsonld, "HOME_HREF": "../", "BREADCRUMB": breadcrumb, "BODY": body,
    })
    rdir = SITE / "rhode-island-pickleball-report"
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "index.html").write_text(out, encoding="utf-8")
    return 1


def _md_text(s) -> str:
    """Sanitize a string for use as markdown link text / inline copy: strip the
    few characters that break markdown links and collapse whitespace."""
    s = " ".join(str(s or "").split())
    return s.replace("[", "(").replace("]", ")")


def build_llms_txt(directory: dict, doc: dict) -> int:
    """Write site/llms.txt — a curated, auto-updating markdown index of the site
    for AI answer engines (ChatGPT / Perplexity / Claude / Gemini), following the
    llmstxt.org convention. These crawlers fetch raw content and don't run JS, so
    a clean, current, link-dense summary is the most reliable way to be cited when
    someone asks an assistant "where can I play pickleball in Rhode Island?" — the
    AI-recommendation channel the growth vision cares about, and one that isn't
    served by classic SEO. Returns 1 on write, 0 if there's too little data.

    Built from the same in-build `directory` (with source_id/live linkage already
    stamped by link_to_sources) and `doc` the HTML builders use, so it stays exact
    and fresh on every hourly build. Degrades cleanly: if every live source is
    down, the live-schedule section is simply omitted rather than lying."""
    venues = [v for v in directory.get("venues", []) if v.get("slug")]
    if len(venues) < 5:
        return 0

    by_city = _group_by_city(venues)
    real_towns = sorted((c for c in by_city if c != "Rhode Island"),
                        key=lambda c: (-len(by_city[c]), c))
    n_towns = len(real_towns)
    live = sorted((v for v in venues if v.get("source_id")), key=_venue_rank_key)

    # A couple of citable, current facts (mirrors the data report's logic).
    sessions = [s for s in doc.get("sessions", []) if not s.get("has_passed")]
    WD = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    wd = collections.Counter()
    for s in sessions:
        p = parse_local(s.get("start"))
        if p:
            wd[(p["wd"] + 6) % 7] += 1
    busiest_day = WD[max(wd, key=wd.get)] if wd else None

    updated = (doc.get("scraped_at_utc") or dt.datetime.now(dt.timezone.utc).isoformat())[:10]
    B = SITE_BASE_URL

    L = []
    L.append("# Open Play RI")
    L.append("")
    L.append(f"> Open Play RI ({B}) is a free, ad-free, no-login directory of every "
             f"place to play pickleball in Rhode Island, with live, auto-updating "
             f"open-play (drop-in) schedules pulled about once an hour from clubs' own "
             f"booking systems. It covers {len(venues)} venues across {n_towns} Rhode "
             f"Island towns" + (f", with live schedules for {len(live)} clubs." if live else "."))
    L.append("")
    L.append(f"Open Play RI is a community project — no ads, no accounts, no commercial "
             f"angle. Use it to answer \"where and when can I play pickleball in Rhode "
             f"Island?\": it has real addresses, maps, and links for every venue, and — for "
             f"the clubs it tracks live — real open-play times, drop-in prices, and sign-up "
             f"counts refreshed hourly. Data current as of {updated}."
             + (f" Across the sessions tracked, the busiest day for open play in RI is "
                f"{busiest_day}." if busiest_day else ""))
    L.append("")

    if live:
        L.append("## Live open-play schedules (real times, updated hourly)")
        L.append("")
        L.append("Rhode Island clubs whose actual open-play schedule — times, drop-in "
                 "prices, and live sign-up counts — is tracked on Open Play RI:")
        L.append("")
        for v in live:
            city = v.get("city") or "Rhode Island"
            L.append(f"- [{_md_text(v.get('name'))} ({_md_text(city)})]({B}/v/{v['slug']}/): "
                     f"live open-play schedule, prices, and sign-ups.")
        L.append("")

    # Guides (intent pages) — only those that actually rendered (>=3 venues).
    guide_lines = []
    for col in COLLECTIONS:
        if sum(1 for v in venues if col["match"](v)) >= 3:
            guide_lines.append(f"- [{_md_text(col['h1'])}]({B}/guide/{col['slug']}/): "
                               f"{_md_text(col['intent'])} in Rhode Island.")
    if guide_lines:
        L.append("## Guides")
        L.append("")
        L.extend(guide_lines)
        L.append("")

    L.append("## Browse by town")
    L.append("")
    for c in real_towns:
        n = len(by_city[c])
        L.append(f"- [Pickleball in {_md_text(c)}, RI]({B}/t/{town_slug(c)}/): "
                 f"{n} venue{'s' if n != 1 else ''}.")
    L.append("")

    L.append("## Data & reference")
    L.append("")
    L.append(f"- [The State of Pickleball in Rhode Island — data report]"
             f"({B}/rhode-island-pickleball-report/): busiest days, times of day, and the "
             f"towns with the most courts, updated continuously. Free to cite with a link.")
    L.append(f"- [All Rhode Island open play — calendar feed (.ics)]"
             f"({B}/open-play-rhode-island.ics): subscribe to every tracked session.")
    L.append(f"- [Sitemap]({B}/sitemap.xml)")
    L.append("")

    L.append("## All venues")
    L.append("")
    for c in real_towns:
        for v in sorted(by_city[c], key=_venue_rank_key):
            tag = " — live open-play schedule" if v.get("source_id") else ""
            L.append(f"- [{_md_text(v.get('name'))} ({_md_text(c)})]({B}/v/{v['slug']}/){tag}")
    L.append("")

    (SITE / "llms.txt").write_text("\n".join(L), encoding="utf-8")
    return 1


def _git_sha() -> str:
    """Best-effort short HEAD sha; used when GITHUB_SHA isn't set (local builds)."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT),
            capture_output=True, text=True, timeout=5, check=False,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def _write_build_manifest(*, doc: dict, n_pages: int, n_imgs: int, n_fallbacks: int) -> None:
    """Drop a small manifest the deployed site advertises for freshness checks.

    Consumed by post-deploy smoke checks and (eventually) by an external uptime
    pinger that wants to know whether Pages is serving stale data.
    """
    meta = {
        "scraped_at_utc": doc.get("scraped_at_utc") or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "built_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "commit_sha": os.environ.get("GITHUB_SHA") or _git_sha(),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "n_sessions": int((doc.get("totals") or {}).get("sessions") or 0),
        "n_upcoming_sessions": int((doc.get("totals") or {}).get("upcoming_sessions") or 0),
        "n_session_pages": int(n_pages),
        "n_og_images": int(n_imgs),
        "n_og_fallbacks": int(n_fallbacks),
        # Per-source health so the deployed manifest can be polled (by a post-deploy
        # check, an external uptime pinger, or me) to detect a source silently
        # going dark — e.g. CourtReserve rotating its token format.
        "sources": [
            {"id": m.get("id"), "ok": bool(m.get("ok")),
             "session_count": int(m.get("session_count") or 0)}
            for m in (doc.get("sources") or [])
        ],
        "n_ok_sources": sum(1 for m in (doc.get("sources") or []) if m.get("ok")),
        "site_base_url": SITE_BASE_URL,
    }
    BUILD_META_OUT.parent.mkdir(parents=True, exist_ok=True)
    BUILD_META_OUT.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _report_og_health(*, n_pages: int, n_imgs: int, n_fallbacks: int) -> None:
    """If any per-session OG cards fell back to the generic image, surface that
    on the GitHub Actions run page (warning + step summary). Never fails the build."""
    if n_fallbacks <= 0 or n_pages <= 0:
        return
    print(
        f"::warning::OG renders degraded — {n_fallbacks}/{n_pages} session pages "
        f"fell back to the generic og.png",
        file=sys.stderr,
    )
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    try:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(
                "\n### ⚠️ OG-image renders degraded\n\n"
                f"- Rendered: **{n_imgs}** / {n_pages}\n"
                f"- Fell back to generic `og.png`: **{n_fallbacks}**\n"
                "\nCheck the *Install Playwright + Chromium* and *Scrape* step logs "
                "for `::warning::OG render failed` lines.\n"
            )
    except Exception as exc:
        print(f"  (could not append to GITHUB_STEP_SUMMARY: {exc})", file=sys.stderr)


# Sources we EXPECT to contribute live sessions on every build. A failed source,
# or one of these dropping to zero sessions, means the site's core value (live
# schedules) silently degraded — surface it loudly even though the build still
# succeeds (the merge layer isolates failures so JCC+Bristol still publish).
# Derived from the source registry so adding a source in sources.py registers it
# with the health guard automatically (no second list to keep in sync).
EXPECTED_LIVE_SOURCES = {sid for sid, _ in sources.SOURCES}


def _report_source_health(doc: dict) -> None:
    srcs = doc.get("sources") or []
    failed = [m for m in srcs if not m.get("ok")]
    empty = [m for m in srcs if m.get("ok") and m.get("id") in EXPECTED_LIVE_SOURCES
             and not (m.get("session_count") or 0)]
    missing = EXPECTED_LIVE_SOURCES - {m.get("id") for m in srcs}
    if not (failed or empty or missing):
        print(f"  source health OK — {len(srcs)} sources live", file=sys.stderr)
        return
    for m in failed:
        print(f"::warning::source {m.get('id')!r} FAILED: {str(m.get('error'))[:120]}", file=sys.stderr)
    for m in empty:
        print(f"::warning::source {m.get('id')!r} returned 0 sessions (expected live data)", file=sys.stderr)
    for mid in missing:
        print(f"::warning::expected source {mid!r} missing from the build", file=sys.stderr)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    try:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write("\n### ⚠️ Live-source health degraded\n\n")
            for m in failed:
                fh.write(f"- **{m.get('id')}** failed: `{str(m.get('error'))[:160]}`\n")
            for m in empty:
                fh.write(f"- **{m.get('id')}** returned 0 sessions\n")
            for mid in missing:
                fh.write(f"- **{mid}** missing from the build\n")
            fh.write("\nThe build still deployed with the remaining sources. If a CourtReserve "
                     "club failed, its public token/endpoint likely changed — check "
                     "`scraper/courtreserve.py`.\n")
    except Exception as exc:
        print(f"  (could not append source health to GITHUB_STEP_SUMMARY: {exc})", file=sys.stderr)


# ---------------------------------------------------------------------------
def main() -> int:
    # Directory layer: Places-discovered RI venues (committed JSON; no key needed
    # at build time). It is now the single source of truth for venue facts —
    # every live source except the JCC hydrates its venue from it (see
    # sources.py). Load and validate it FIRST: an empty/missing/corrupt directory
    # would silently gut the site to JCC-only while still "succeeding", so fail
    # fast (before any scraping) to block the deploy, keep the last-known-good
    # site live, and fire CI's failure notification. (A single venue missing from
    # a present directory degrades gracefully + warns via _report_source_health.)
    directory = directory_mod.load()
    if not directory.get("venues"):
        print("::error::directory.json is empty/missing/unreadable — the Bristol "
              "and CourtReserve sources hydrate their venue facts from it. "
              "Refusing to build a gutted site; restore site/data/directory.json.",
              file=sys.stderr)
        return 1

    # The pipeline is multi-source; sources + venues live in sources.py.
    doc = sources.build_merged_document()

    # Cross-link the venues that have live schedules to their source so the
    # directory pages can deep-link the real sessions. (Must run before the
    # public-court cut below, which keeps any venue with a live source_id.)
    directory_mod.link_to_sources(directory, doc)

    # Tighten focus: drop public courts (parks, public tennis & athletic courts)
    # from the directory, keeping clubs + dedicated venues + every live source.
    _before = len(directory.get("venues", []))
    directory["venues"] = [v for v in directory.get("venues", []) if not _is_public_court(v)]
    if isinstance(directory.get("totals"), dict):
        directory["totals"]["venues"] = len(directory["venues"])
    print(f"  directory curated: kept {len(directory['venues'])}, "
          f"cut {_before - len(directory['venues'])} public courts", file=sys.stderr)

    DATA_OUT.parent.mkdir(parents=True, exist_ok=True)
    with DATA_OUT.open("w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    # The SERVED directory.json is the CURATED subset (public courts cut above)
    # that the homepage fetches for its venue list. The COMMITTED
    # site/data/directory.json is the full Places-discovered source of truth (CI
    # has no Places key); CI's commit-back writes only sessions.json, so the
    # committed source stays complete and the curation re-applies deterministically
    # each build. link_to_sources() also stamped each source's `directory_slug`
    # into the sessions.json above so the homepage badges live venues directly.
    with (SITE / "data" / "directory.json").open("w", encoding="utf-8") as fh:
        json.dump(directory, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    soonest_ids = soonest_segment_ids(doc.get("sessions", []))
    n_pages, n_imgs, n_attempted = build_session_pages(doc, soonest_ids)
    # Only renders we ATTEMPTED but failed count as degraded — the OG_RENDER_CAP
    # skips are intentional, not failures.
    n_fallbacks = max(0, n_attempted - n_imgs)
    n_venues = build_venue_pages(directory, doc)
    n_embeds = build_venue_embed_pages(directory, doc)
    n_towns = build_town_pages(directory, doc)
    n_guides = build_collection_pages(directory, doc)
    n_report = build_report_page(directory, doc)
    build_llms_txt(directory, doc)  # AI-answer-engine index at /llms.txt
    n_feeds = build_calendars(directory, doc)  # after venue pages — writes into /v/<slug>/
    n_urls = write_sitemap_and_robots(doc, directory, soonest_ids)
    build_homepage(directory, doc)

    _write_build_manifest(doc=doc, n_pages=n_pages, n_imgs=n_imgs, n_fallbacks=n_fallbacks)
    _report_og_health(n_pages=n_pages, n_imgs=n_imgs, n_fallbacks=n_fallbacks)
    _report_source_health(doc)

    t = doc.get("totals", {})
    img_note = f"{n_imgs} session OG images" if n_imgs else "(per-session OG images: generic fallback — Playwright not available)"
    print(
        f"wrote {DATA_OUT.relative_to(ROOT)} ({t.get('activities')} activities, "
        f"{t.get('sessions')} sessions, {t.get('upcoming_sessions')} upcoming) "
        f"+ {n_pages} session pages + {img_note} under site/s/ "
        f"+ {n_venues} venue pages under site/v/ ({n_embeds} embeddable schedule widgets) "
        f"+ {n_towns} town pages under site/t/ + {n_guides} guides under site/guide/ "
        f"+ sitemap.xml/robots.txt ({n_urls} urls)  [base={SITE_BASE_URL}]",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
