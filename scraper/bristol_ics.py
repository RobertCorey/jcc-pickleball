#!/usr/bin/env python3
"""Source adapter: Bristol Pickleball Club drop-in / open-play sessions.

Unlike the JCC (Amilia), Bristol publishes its schedule as a **public Google
Calendar ICS feed**. This module fetches that feed, expands the weekly
recurring rules into individual dated sessions, keeps only the open-play /
drop-in sessions at the Bristol Town Common courts, and normalizes them into
the same per-session shape the rest of the pipeline uses.

Best-effort and isolated: any failure here raises, and the merge layer
(``sources.py``) catches it, warns, and continues with the other sources.

stdlib only - urllib + re + datetime + zoneinfo. No third-party deps.

ROBOTS / ToS NOTE
-----------------
``calendar.google.com/robots.txt`` is a blanket ``Disallow: /`` - but that is
*Google's* crawler rule for its property, not a statement by the data owner.
The Bristol club deliberately published this as a **public ICS feed**, whose
entire purpose is to be consumed by calendar clients; an hourly single-file
fetch is exactly a calendar subscription, not crawling. This is flagged for
the human to confirm before the hourly Action goes live (see PR / report).
"""

from __future__ import annotations

import datetime as dt
import re
import urllib.request
from zoneinfo import ZoneInfo

ICS_URL = (
    "https://calendar.google.com/calendar/ical/"
    "bristolpickleballclubri%40gmail.com/public/basic.ics"
)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)

TZ = ZoneInfo("America/New_York")

# How far back / forward to materialize recurring sessions. Bounded so the feed's
# many open-ended weekly rules don't explode the output. The 30-day horizon
# matches the other sources' philosophy — open play further out is rarely
# actionable, and Bristol has no live spot counts to justify a longer window.
WINDOW_BACK_DAYS = 14
WINDOW_FWD_DAYS = 30

SOURCE_ID = "bristol"
DIRECTORY_SLUG = "bristol-town-common-pickleball-courts-bristol"

# Venue facts live ONLY in directory.json (the single source of truth); the
# caller (sources.py) hydrates them and passes the venue in. This module holds
# no venue literals so they can't drift.

# Friendly label for the registration CTA (Bristol isn't an Amilia store).
CTA_LABEL = "View schedule"

# Sessions whose SUMMARY matches any of these are NOT open drop-in play.
_EXCLUDE_RE = re.compile(
    r"\b(instruction|lesson|clinic|league|tournament|camp|private|class)\b", re.I
)
# Only courts at the Bristol Town Common (drops Newport / Barrington / etc.).
_BRISTOL_LOC_RE = re.compile(r"bristol town common", re.I)

_WD = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


# --------------------------------------------------------------------------- #
# Fetch + low-level ICS parsing
# --------------------------------------------------------------------------- #
def _fetch(url: str, *, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def _unfold(text: str) -> str:
    """RFC-5545 line unfolding: a CRLF followed by space/tab continues the line."""
    return re.sub(r"\r?\n[ \t]", "", text)


def _unescape(value: str) -> str:
    return (
        value.replace("\\n", "\n")
        .replace("\\N", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
        .strip()
    )


def _split_events(text: str) -> list[str]:
    return re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.S)


def _prop(block: str, name: str) -> tuple[dict, str] | None:
    """Return ({params}, value) for property *name*, or None if absent."""
    m = re.search(rf"^{name}([;:][^\r\n]*)", block, re.M)
    if not m:
        return None
    rest = m.group(1)
    # params end at the first unescaped ':'
    if rest.startswith(":"):
        return ({}, rest[1:])
    sep = rest.index(":")
    params_str, value = rest[1:sep], rest[sep + 1:]
    params = {}
    for piece in params_str.split(";"):
        if "=" in piece:
            k, v = piece.split("=", 1)
            params[k.upper()] = v
    return (params, value)


def _parse_dt(block: str, name: str) -> tuple[dt.datetime | None, bool]:
    """Parse a DTSTART/DTEND into a NAIVE America/New_York wall-clock datetime.

    Returns (datetime_or_None, is_all_day).
    """
    got = _prop(block, name)
    if not got:
        return (None, False)
    params, value = got
    value = value.strip()
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        return (None, True)  # all-day; open play always has a time
    m = re.match(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(Z)?", value)
    if not m:
        return (None, False)
    y, mo, d, h, mi, s, z = m.groups()
    naive = dt.datetime(int(y), int(mo), int(d), int(h), int(mi), int(s))
    if z == "Z":  # UTC -> convert to venue-local wall clock
        local = naive.replace(tzinfo=dt.timezone.utc).astimezone(TZ)
        return (local.replace(tzinfo=None), False)
    # TZID present (almost always America/New_York) or floating: digits are local.
    return (naive, False)


def _parse_until(rrule: dict) -> dt.date | None:
    raw = rrule.get("UNTIL")
    if not raw:
        return None
    m = re.match(r"(\d{4})(\d{2})(\d{2})", raw)
    return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def _parse_rrule(block: str) -> dict | None:
    got = _prop(block, "RRULE")
    if not got:
        return None
    out: dict = {}
    for piece in got[1].split(";"):
        if "=" in piece:
            k, v = piece.split("=", 1)
            out[k.upper()] = v
    return out


def _exdates(block: str) -> set[dt.date]:
    out: set[dt.date] = set()
    for m in re.finditer(r"^EXDATE[^:]*:([^\r\n]+)", block, re.M):
        for token in m.group(1).split(","):
            dm = re.match(r"(\d{4})(\d{2})(\d{2})", token.strip())
            if dm:
                out.add(dt.date(int(dm.group(1)), int(dm.group(2)), int(dm.group(3))))
    return out


# --------------------------------------------------------------------------- #
# Recurrence expansion (weekly only - the only FREQ this feed uses)
# --------------------------------------------------------------------------- #
def _expand_weekly(
    start: dt.datetime,
    rrule: dict,
    window_start: dt.date,
    window_end: dt.date,
):
    """Yield naive-local datetimes for a weekly RRULE within [window_start, end]."""
    interval = int(rrule.get("INTERVAL", 1) or 1)
    until = _parse_until(rrule)
    count = int(rrule["COUNT"]) if rrule.get("COUNT") else None
    byday = [_WD[d] for d in rrule.get("BYDAY", "").split(",") if d in _WD]
    if not byday:
        byday = [start.weekday()]
    byday.sort()
    h, mi, s = start.hour, start.minute, start.second
    base_date = start.date()
    base_monday = base_date - dt.timedelta(days=base_date.weekday())

    emitted = 0
    week = 0
    while True:
        wk_monday = base_monday + dt.timedelta(weeks=week * interval)
        if wk_monday > window_end:
            return
        for wd in byday:
            occ_date = wk_monday + dt.timedelta(days=wd)
            if occ_date < base_date:
                continue
            if until and occ_date > until:
                return
            if count is not None and emitted >= count:
                return
            emitted += 1
            if window_start <= occ_date <= window_end:
                yield dt.datetime(occ_date.year, occ_date.month, occ_date.day, h, mi, s)
        week += 1
        if week > 600:  # safety backstop (~11 years of weekly)
            return


# --------------------------------------------------------------------------- #
# Shaping
# --------------------------------------------------------------------------- #
def _clean_title(summary: str) -> str:
    """Map a noisy calendar SUMMARY to a tidy, canonical session name.

    The feed's summaries are full of admin noise ("PlayerLineUp app", "NOTE New
    Start Time", "~ 45 player Limit", "REGISTRATION REQUIRED"). Player caps are
    captured separately, so collapse to the play TYPE the title describes.
    """
    s = summary.lower()
    if "recreational" in s or "beginner" in s:
        return "Recreational & Beginner"
    if "challenge" in s:
        return "Challenge Play"
    if "open play" in s:
        return "Open Play"
    # Fall back to the summary with the obvious noise stripped.
    out = re.sub(r"^\s*Bristol Pickleball\s*~?\s*", "", summary, flags=re.I)
    out = re.sub(r"\b(PlayerLineUp app|REGISTRATION REQUIRED|NOTE[^~,:]*)\b", "", out, flags=re.I)
    out = re.sub(r"[~,-]?\s*\d{1,3}\s*player\s*(limit|max)\b", "", out, flags=re.I)
    out = re.sub(r"\s+", " ", out).strip(" ~:,-")
    return out or "Open Play"


def _capacity(text: str) -> int | None:
    m = re.search(r"limited to\s*(\d{1,3})", text, re.I)
    if not m:
        m = re.search(r"(\d{1,3})\s*player", text, re.I)
    return int(m.group(1)) if m else None


def _segment_id(uid: str, occ: dt.datetime) -> str:
    local = (uid.split("@", 1)[0] or "evt").strip()
    local = re.sub(r"[^A-Za-z0-9]", "", local)[:24] or "evt"
    return f"{local}-{occ:%Y%m%d}"


def _shape(occ: dt.datetime, dur: dt.timedelta, title: str, cap: int | None,
           uid: str, now_local: dt.datetime) -> dict:
    end = occ + dur
    passed = end < now_local
    return {
        "segment_id": _segment_id(uid, occ),
        "start": occ.isoformat(timespec="seconds"),
        "end": end.isoformat(timespec="seconds"),
        "all_day": False,
        "has_passed": passed,
        "status": "passed" if passed else "registration_available",
        "state_code": None,
        "capacity": cap,
        "has_unlimited_spots": cap is None,
        "spots_reserved": None,
        "spots_remaining": None,  # the feed has no live count
        "has_place_left": None if passed else True,
        "max_attendance": cap,
        "attendance_string": None,
        "drop_in_price": None,    # no court fees; donations accepted
        "drop_in_best_price": None,
        "fee": None,
        "wait_list_enabled": False,
        "wait_list_spots_reserved": None,
        "can_register": not passed,
        "has_drop_ins": True,
        "already_in_cart": False,
        "description": None,
        "extra_information": None,
        "activity_name": title,
        "registration_url": None,  # falls back to the venue registration_url
    }


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def build_source(venue: dict) -> dict:
    """Fetch + parse the Bristol feed into a source result. Raises on failure.

    ``venue`` is the normalized venue dict (facts from ``directory.json``,
    assembled by the caller in ``sources.py``).
    """
    text = _unfold(_fetch(ICS_URL))
    now_local = dt.datetime.now(TZ).replace(tzinfo=None)
    today = now_local.date()
    window_start = today - dt.timedelta(days=WINDOW_BACK_DAYS)
    window_end = today + dt.timedelta(days=WINDOW_FWD_DAYS)

    by_id: dict[str, dict] = {}
    for block in _split_events(text):
        loc = _prop(block, "LOCATION")
        summary = _prop(block, "SUMMARY")
        if not summary:
            continue
        summary_v = _unescape(summary[1])
        loc_v = _unescape(loc[1]) if loc else ""
        if not _BRISTOL_LOC_RE.search(loc_v):
            continue
        if _EXCLUDE_RE.search(summary_v):
            continue

        start, all_day = _parse_dt(block, "DTSTART")
        if not start or all_day:
            continue
        end, _ = _parse_dt(block, "DTEND")
        dur = (end - start) if (end and end > start) else dt.timedelta(hours=1, minutes=30)

        uid_got = _prop(block, "UID")
        uid = _unescape(uid_got[1]) if uid_got else summary_v
        desc_got = _prop(block, "DESCRIPTION")
        desc_v = _unescape(desc_got[1]) if desc_got else ""
        title = _clean_title(summary_v)
        cap = _capacity(summary_v + " " + desc_v)

        rrule = _parse_rrule(block)
        exdates = _exdates(block)
        if rrule and rrule.get("FREQ", "").upper() == "WEEKLY":
            occs = _expand_weekly(start, rrule, window_start, window_end)
        else:
            occs = [start] if window_start <= start.date() <= window_end else []

        for occ in occs:
            if occ.date() in exdates:
                continue
            s = _shape(occ, dur, title, cap, uid, now_local)
            # de-dupe overlapping rules that resolve to the same slot
            by_id[s["segment_id"]] = s

    sessions = sorted(by_id.values(), key=lambda s: s["start"])
    # attach the venue as a per-session facility too, so existing facility-based
    # site code renders Bristol identically to the JCC.
    facility = {k: venue.get(k) for k in (
        "name", "address1", "address2", "city", "province", "postal_code",
        "country", "phone", "phone_ext", "latitude", "longitude")}
    for s in sessions:
        s["facility"] = facility
        s["location"] = (
            f"{venue['name']} | {venue['address1']}, {venue['city']}, "
            f"{venue['province']}, {venue['postal_code']}"
        )

    return {
        "id": SOURCE_ID,
        "booking_system": "google-ics",
        "venue": venue,
        "cta_label": CTA_LABEL,
        "notices": [
            "Open play at the Bristol Town Common courts. Registration is required "
            "per session through the club; please don't register and skip.",
        ],
        "sub_categories": [],
        "sessions": sessions,
    }


if __name__ == "__main__":
    import json
    import sys

    import directory

    # Hydrate facts from directory.json — same single source of truth the
    # production path (sources._bristol) uses, so the standalone debug output
    # can't drift from what ships.
    entry = next((v for v in directory.load().get("venues", [])
                  if v.get("slug") == DIRECTORY_SLUG), None)
    if entry is None:
        sys.exit(f"directory.json has no entry for {DIRECTORY_SLUG!r}")
    venue = dict(entry, short_name="Bristol Pickleball",
                 registration_url="https://www.bristolpickleball.com")
    src = build_source(venue)
    print(f"bristol: {len(src['sessions'])} sessions", file=sys.stderr)
    print(json.dumps(src, ensure_ascii=False, indent=2))
