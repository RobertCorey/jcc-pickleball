#!/usr/bin/env python3
"""Source adapter: CourtReserve public event calendars (RI pickleball clubs).

Several Rhode Island clubs publish their open-play / drop-in pickleball schedule
through CourtReserve's **public** member-portal calendar (no login required to
*view* events). This module reads that calendar for a given organization and
normalizes the open-play / drop-in sessions into the same per-session shape the
rest of the pipeline uses (mirroring ``bristol_ics``).

How the public calendar works (reverse-engineered, stdlib only)
---------------------------------------------------------------
1. ``GET /Online/Calendar/Events/<orgId>/month`` returns an HTML page that
   embeds, per org, a short-lived ``requestData`` token and a ``CostTypeId``.
   Both are scraped fresh on every run (the token is tied to the org/session).
2. The calendar grid then POSTs to
   ``/Online/Calendar/ReadCalendarEvents/<orgId>`` (a Kendo ``aspnetmvc-ajax``
   DataSource read) with a form body of
   ``sort=&group=&filter=&jsonData=<JSON>``. The ``jsonData`` payload carries
   the date window (``startDate``/``end`` ISO + ``KendoStart``/``KendoEnd`` as
   ``{Year,Month,Day}`` objects), the org id, the ``CostTypeId``, and a handful
   of flags. The response is a JSON envelope
   ``{"Data":[...events...],"Total":N,...}`` requiring **no authentication**.

Each event object carries everything we need: ``EventName``, ``EventType``,
``Start``/``End`` (epoch-ms; these match the human ``TimeDisplay``, whereas the
sibling ``EventStart``/``EventEnd`` are offset and NOT used), capacity
(``MaxMembersOnEvent``/``SignedMembers``/``IsFull``), sign-up state
(``CanSignUp``/``InPast``/``AllowWaitList``), a stable ``Number`` (used to build
a public event-details URL) and an ``IsLeague`` flag.

Best-effort and isolated: any failure here raises, and the merge layer
(``sources.py``) catches it, warns, and continues with the other sources.

stdlib only - urllib + json + re + datetime + zoneinfo. No third-party deps.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/New_York")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)

BASE = "https://app.courtreserve.com"

# How far forward to pull events. A small look-back keeps "today, earlier"
# sessions present (they render as passed) without bloating the payload.
WINDOW_BACK_DAYS = 1
WINDOW_FWD_DAYS = 45

# --------------------------------------------------------------------------- #
# Open-play / drop-in classification
# --------------------------------------------------------------------------- #
# We ONLY want open / drop-in play. CourtReserve clubs tag events with an
# ``EventType`` (and ``EventName``); these clubs use a sprawling, free-text set
# of types, so we include on positive open-play signals and exclude on the
# usual non-open-play formats (leagues, lessons/clinics, tournaments, training,
# private rentals, round-robin ladder events, etc.).
_INCLUDE_RE = re.compile(r"\b(open\s*play|drop[\s-]*in)\b", re.I)

_EXCLUDE_RE = re.compile(
    r"\b(league|lesson|clinic|tournament|class|classes|training|camp|academy"
    r"|private|rental|rent|round\s*robin|ladder|dupr\s*event|team\b|mahjong"
    r"|coached|mlp|skills)\b",
    re.I,
)


def _is_open_play(event: dict) -> bool:
    """True only for open-play / drop-in pickleball events."""
    if event.get("IsLeague"):
        return False
    name = (event.get("EventName") or event.get("Title") or "").strip()
    etype = (event.get("EventType") or "").strip()
    blob = f"{name} {etype}"
    if _EXCLUDE_RE.search(blob):
        return False
    return bool(_INCLUDE_RE.search(blob))


# --------------------------------------------------------------------------- #
# Fetch helpers
# --------------------------------------------------------------------------- #
def _fetch(url: str, *, data: bytes | None = None, headers: dict | None = None,
           timeout: int = 30) -> str:
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def _scrape_tokens(org_id: int | str) -> tuple[str, str]:
    """Scrape a fresh (requestData, CostTypeId) from the org's calendar page."""
    html = _fetch(f"{BASE}/Online/Calendar/Events/{org_id}/month")
    m = re.search(r"requestData=([^'\"&\s]+)", html)
    if not m:
        raise RuntimeError(f"courtreserve {org_id}: no requestData token on calendar page")
    token = urllib.parse.unquote(m.group(1))
    cm = re.search(r"CostTypeId:\s*'(\d+)'", html)
    cost = cm.group(1) if cm else ""
    return token, cost


def _read_events(org_id: int | str, token: str, cost: str,
                 start: dt.datetime, end: dt.datetime) -> list[dict]:
    """POST the Kendo read and return the raw event list (``Data``)."""
    org = str(org_id)
    result = {
        "startDate": start.strftime("%Y-%m-%dT04:00:00.000Z"),
        "end": end.strftime("%Y-%m-%dT04:00:00.000Z"),
        "Date": start.strftime("%a, %d %b %Y 04:00:00 GMT"),
        "orgId": org,
        "TimeZone": "America/New_York",
        "KendoStart": {"Year": start.year, "Month": start.month, "Day": start.day},
        "KendoEnd": {"Year": end.year, "Month": end.month, "Day": end.day},
        "Categories": [],
        "EventTagIds": [],
        "CostTypeId": cost,
        "MemberId": "",
        "FamilyId": "",
        "FamilyMemberIds": "",
        "EventSessionIds": [],
        "ViewType": "Month",
        "MonthlySelectedDate": start.strftime("%Y-%m-%dT16:00:00.000Z"),
        "IsLeagueCalendar": "False",
        "IncludeLeagues": "False",
        "IncludeRoundRobins": "False",
    }
    body = urllib.parse.urlencode(
        {"sort": "", "group": "", "filter": "", "jsonData": json.dumps(result)}
    ).encode("utf-8")
    url = (
        f"{BASE}/Online/Calendar/ReadCalendarEvents/{org}"
        f"?id={org}&uiCulture=en-US&requestData={urllib.parse.quote(token)}"
    )
    raw = _fetch(url, data=body, headers={
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "*/*",
        "Origin": BASE,
        "Referer": f"{BASE}/Online/Calendar/Events/{org}/Month",
    })
    doc = json.loads(raw)
    return doc.get("Data") or []


# --------------------------------------------------------------------------- #
# Parsing / shaping
# --------------------------------------------------------------------------- #
_DATE_RE = re.compile(r"/Date\((-?\d+)\)/")


def _epoch_ms(value) -> int | None:
    """Parse a Kendo ``/Date(ms)/`` string to integer epoch milliseconds."""
    if not isinstance(value, str):
        return None
    m = _DATE_RE.search(value)
    return int(m.group(1)) if m else None


def _to_local(ms: int) -> dt.datetime:
    """Epoch-ms -> naive America/New_York wall-clock datetime."""
    return dt.datetime.fromtimestamp(ms / 1000, TZ).replace(tzinfo=None)


def _clean_name(event: dict) -> str:
    name = (event.get("EventName") or event.get("Title") or "").strip()
    # Collapse the noisy ALL-CAPS / trailing-space names to something tidy while
    # preserving the level info players care about (Beginner / Intermediate / ...).
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        name = (event.get("EventType") or "Open Play").strip()
    # Title-case fully-uppercase names; leave mixed-case names as authored.
    if name and name == name.upper():
        name = name.title()
    return name or "Open Play"


def _details_url(org_id: int | str, event: dict) -> str | None:
    """Public event-details page, e.g. /Online/Events/Details/<org>/<Number>."""
    number = event.get("Number")
    if not number:
        return None
    eid = event.get("EventId")
    url = f"{BASE}/Online/Events/Details/{org_id}/{number}"
    if eid:
        url += f"?eventId={eid}"
    return url


def _shape(org_id: int | str, event: dict, facility: dict,
           portal_url: str, now_local: dt.datetime) -> dict | None:
    sm = _epoch_ms(event.get("Start"))
    em = _epoch_ms(event.get("End"))
    if sm is None:
        return None
    start = _to_local(sm)
    end = _to_local(em) if em is not None else (start + dt.timedelta(hours=1, minutes=30))

    cap = event.get("MaxMembersOnEvent")
    cap = int(cap) if isinstance(cap, (int, float)) and cap else None
    signed = event.get("SignedMembers")
    signed = int(signed) if isinstance(signed, (int, float)) else None
    remaining = (cap - signed) if (cap is not None and signed is not None) else None

    passed = end < now_local or bool(event.get("InPast"))
    is_full = bool(event.get("IsFull")) or (remaining is not None and remaining <= 0)
    can_sign_up = bool(event.get("CanSignUp")) and not passed
    wait_list = bool(event.get("AllowWaitList"))

    if passed:
        status = "passed"
    elif is_full:
        status = "full"
    elif can_sign_up:
        status = "registration_available"
    else:
        status = "registration_closed"

    eid = event.get("EventId")
    seg = f"{eid}-{start:%Y%m%d}" if eid else f"{event.get('Number', 'evt')}"
    details = _details_url(org_id, event)

    return {
        "segment_id": seg,
        "start": start.isoformat(timespec="seconds"),
        "end": end.isoformat(timespec="seconds"),
        "all_day": bool(event.get("IsAllDay")),
        "has_passed": passed,
        "status": status,
        "state_code": None,
        "capacity": cap,
        "has_unlimited_spots": cap is None,
        "spots_reserved": signed,
        "spots_remaining": remaining,
        "has_place_left": (None if passed else (remaining is None or remaining > 0)),
        "max_attendance": cap,
        "attendance_string": event.get("SlotsInfo"),
        "drop_in_price": None,        # not exposed on the public calendar feed
        "drop_in_best_price": None,
        "fee": None,
        "wait_list_enabled": wait_list,
        "wait_list_spots_reserved": event.get("WaitListCount"),
        "can_register": can_sign_up,
        "has_drop_ins": True,
        "already_in_cart": False,
        "description": event.get("EventNote") or None,
        "extra_information": (event.get("EventType") or None),
        "activity_name": _clean_name(event),
        "details_url": details,
        "registration_url": details or portal_url,
        "facility": facility,
        "location": (
            f"{facility['name']} | {facility['address1']}, {facility['city']}, "
            f"{facility['province']}, {facility['postal_code']}"
            if facility.get("address1") else facility.get("name")
        ),
    }


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def build_source(org_id: int | str, venue: dict, *, source_id: str,
                 cta_label: str = "Reserve on CourtReserve",
                 notices: list[str] | None = None) -> dict:
    """Fetch + parse one org's public CourtReserve calendar into a source result.

    ``venue`` is the normalized venue dict (name/address/geo/registration_url),
    typically built from ``directory.json``. Raises on network/parse failure so
    the merge layer can isolate it.
    """
    token, cost = _scrape_tokens(org_id)
    now_local = dt.datetime.now(TZ).replace(tzinfo=None)
    start = now_local - dt.timedelta(days=WINDOW_BACK_DAYS)
    end = now_local + dt.timedelta(days=WINDOW_FWD_DAYS)

    events = _read_events(org_id, token, cost, start, end)

    portal_url = venue.get("registration_url") or f"{BASE}/Online/Calendar/Events/{org_id}/month"
    facility = {k: venue.get(k) for k in (
        "name", "address1", "address2", "city", "province", "postal_code",
        "country", "phone", "phone_ext", "latitude", "longitude")}

    by_id: dict[str, dict] = {}
    window_end_date = end.date()
    for ev in events:
        if not _is_open_play(ev):
            continue
        s = _shape(org_id, ev, facility, portal_url, now_local)
        if not s:
            continue
        # keep the window tidy: the feed can return a wider span than requested
        sd = s["start"][:10]
        if sd > window_end_date.isoformat():
            continue
        by_id[s["segment_id"]] = s

    sessions = sorted(by_id.values(), key=lambda s: s["start"])

    return {
        "id": source_id,
        "booking_system": "courtreserve",
        "venue": venue,
        "cta_label": cta_label,
        "notices": notices or [
            "Open-play and drop-in sessions are booked per session through "
            "CourtReserve. Spots and times can change; confirm on CourtReserve "
            "before heading over.",
        ],
        "sub_categories": [],
        "sessions": sessions,
    }


if __name__ == "__main__":
    import sys

    org = sys.argv[1] if len(sys.argv) > 1 else "11577"
    v = {
        "name": "Test Club", "address1": "1 Main St", "city": "Cranston",
        "province": "RI", "postal_code": "02920", "country": "US",
        "latitude": 41.78, "longitude": -71.47,
        "registration_url": f"{BASE}/Online/Calendar/Events/{org}/month",
    }
    src = build_source(org, v, source_id=f"courtreserve-{org}")
    up = [s for s in src["sessions"] if not s["has_passed"]]
    print(f"org {org}: {len(src['sessions'])} open-play sessions "
          f"({len(up)} upcoming)", file=sys.stderr)
    for s in up[:8]:
        print(f"  {s['start']}  {s['activity_name']!r}  "
              f"cap={s['capacity']} left={s['spots_remaining']} "
              f"status={s['status']}", file=sys.stderr)
