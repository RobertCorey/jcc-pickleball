#!/usr/bin/env python3
"""Scrape open-play (drop-in) pickleball sessions from an Amilia store program page.

Default target:
  https://app.amilia.com/store/en/jewishallianceofgreaterrhodeisland/shop/programs/128482?subCategoryIds=6876731

The pipeline:
  1. Parse the program URL into store / program / sub-category identifiers.
  2. Fetch the server-rendered program page (HTML) for per-activity display
     metadata: titles, schedule text, prices text, discount/promotion blurbs,
     "important information" notes, activity-detail links.
  3. Call Amilia's calendar feed (``api/Organization/EventsForProgram``) once per
     sub-category to get every individual session ("segment") with live capacity,
     pricing, location, facility address, tags and staff.
  4. Merge the two sources into a single JSON document and print it to stdout.

No authentication is used or required - every request here is anonymous. The only
non-obvious requirement is that the calendar feed needs *both* an
``X-Requested-With: XMLHttpRequest`` header and a ``Referer`` header pointing at
the store; without them the endpoint returns HTTP 500.

stdlib only - no third-party dependencies.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_URL = (
    "https://app.amilia.com/store/en/jewishallianceofgreaterrhodeisland"
    "/shop/programs/128482?subCategoryIds=6876731"
)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)

# Amilia activity "state" enum, mirrored from the store-page legend.
ACTIVITY_STATE = {
    0: "registration_available",
    1: "in_cart_or_previously_purchased",
    2: "available_soon",
    3: "full",
    4: "full_waitlist_available",
}


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
def _request(url: str, *, as_json: bool, referer: str | None = None, retries: int = 3, timeout: int = 30):
    accept = (
        "application/json, text/javascript, */*; q=0.01"
        if as_json
        else "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    )
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": accept,
        "Accept-Language": "en-US,en;q=0.9",
    }
    if as_json:
        # The calendar feed 500s without this header (and the Referer below).
        # Conversely, sending it on the program *page* makes Amilia return only
        # an AJAX HTML fragment instead of the full document - so JSON only.
        headers["X-Requested-With"] = "XMLHttpRequest"
    if referer:
        headers["Referer"] = referer
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if as_json else raw
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last_err = exc
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET {url} failed after {retries} attempts: {last_err}")


# --------------------------------------------------------------------------- #
# URL parsing
# --------------------------------------------------------------------------- #
def parse_program_url(url: str) -> dict:
    parsed = urllib.parse.urlparse(url)
    m = re.search(r"/store/([^/]+)/([^/]+)/shop/programs/(\d+)", parsed.path)
    if not m:
        raise ValueError(f"Not an Amilia program URL: {url!r}")
    language, org, program_id = m.group(1), m.group(2), int(m.group(3))
    query = urllib.parse.parse_qs(parsed.query)
    sub_ids: list[int] = []
    for key in ("subCategoryIds", "subCategoryId"):
        for value in query.get(key, []):
            sub_ids.extend(int(x) for x in re.split(r"[,\s]+", value) if x.strip())
    base = f"{parsed.scheme}://{parsed.netloc}/store/{language}/{org}"
    return {
        "language": language,
        "org": org,
        "program_id": program_id,
        "sub_category_ids": sub_ids,
        "store_base_url": base,
        "program_url": url,
    }


# --------------------------------------------------------------------------- #
# Tiny HTML utilities
# --------------------------------------------------------------------------- #
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def text_of(fragment: str) -> str:
    """Strip tags + entities, collapse whitespace."""
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", fragment))).strip()


def attr(fragment: str, name: str) -> str | None:
    m = re.search(rf'{name}\s*=\s*"([^"]*)"', fragment)
    return m.group(1) if m else None


def iter_tag_blocks(htmltext: str, tag: str, *, attr_filter: str | None = None):
    """Yield the full ``<tag ...>...</tag>`` blocks, handling nesting of *tag*."""
    open_re = re.compile(rf"<{tag}\b[^>]*>", re.I)
    close_tag = f"</{tag}>"
    pos = 0
    while True:
        m = open_re.search(htmltext, pos)
        if not m:
            return
        start = m.start()
        if attr_filter and attr_filter not in htmltext[m.start():m.end()]:
            pos = m.end()
            continue
        # walk forward balancing nested <tag ...> / </tag>
        depth = 1
        cursor = m.end()
        while depth:
            nxt_open = open_re.search(htmltext, cursor)
            nxt_close = htmltext.find(close_tag, cursor)
            if nxt_close == -1:
                # malformed; bail with what we have
                yield htmltext[start:]
                return
            if nxt_open and nxt_open.start() < nxt_close:
                depth += 1
                cursor = nxt_open.end()
            else:
                depth -= 1
                cursor = nxt_close + len(close_tag)
        yield htmltext[start:cursor]
        pos = cursor


# --------------------------------------------------------------------------- #
# Program-page HTML parsing
# --------------------------------------------------------------------------- #
def parse_program_page(htmltext: str, store_base_url: str) -> dict:
    """Extract program title + per-activity display metadata + page notices."""
    out: dict = {"program_title": None, "page_notices": [], "activities": {}}
    parts = urllib.parse.urlsplit(store_base_url)
    origin = f"{parts.scheme}://{parts.netloc}"

    def absolutize(href: str | None) -> str | None:
        return urllib.parse.urljoin(origin + "/", href.lstrip("/")) if href else None

    m = re.search(r"<title[^>]*>(.*?)</title>", htmltext, re.S | re.I)
    if m and text_of(m.group(1)):
        # "Pickleball | Register | Jewish Alliance of Greater Rhode Island Store"
        out["program_title"] = text_of(m.group(1)).split("|")[0].strip() or None
    if not out["program_title"]:
        m = re.search(r'property="og:title"\s+content="([^"]*)"', htmltext)
        if m:
            out["program_title"] = html.unescape(m.group(1)).split("|")[0].strip() or None

    # Page-level "Important information" custom messages.
    for block in iter_tag_blocks(htmltext, "div", attr_filter='class="row-fluid custom-message"'):
        note = text_of(block)
        if note:
            out["page_notices"].append(note)

    # Each activity is an <li id="activity-NNNN" class="activity-list-item" ...>.
    for li in iter_tag_blocks(htmltext, "li", attr_filter="activity-list-item"):
        m_id = re.search(r'id="activity-(\d+)"', li)
        if not m_id:
            continue
        activity_id = int(m_id.group(1))

        title = None
        m = re.search(r'activity-list-item-info-header-title"[^>]*>(.*?)</h\d>', li, re.S)
        if m:
            title = text_of(m.group(1))

        details_url = None
        for a in re.findall(r"<a\b[^>]*>", li):
            href = attr(a, "href")
            if href and "/shop/activities/" in href:
                details_url = absolutize(href)
                if "itemprop" in a:  # the canonical "View activity details" link
                    break
        if not details_url:
            m = re.search(r'data-href="([^"]*?/shop/activities/[^"]*)"', li)
            if m:
                details_url = absolutize(m.group(1))

        # Schedule lines (clock + calendar paragraphs inside .schedule-container).
        schedule_display: list[str] = []
        m = re.search(r'class="schedule-container"[^>]*>(.*?)</div>', li, re.S)
        if m:
            for p in re.findall(r"<p\b[^>]*>(.*?)</p>", m.group(1), re.S):
                t = text_of(p).rstrip(" ,").strip()
                if t:
                    schedule_display.append(t)

        # "Start date: ..." paragraph.
        start_date_display = None
        m = re.search(r"Start date:\s*</?[^>]*>?(.*?)</p>", li, re.S)
        if m:
            start_date_display = text_of(m.group(1)).lstrip(", ").strip() or None

        # Prices line.
        price_display = None
        m = re.search(r'activity-list-item-info-prices"[^>]*>(.*?)<div', li, re.S)
        if m:
            price_display = text_of(m.group(1)) or None

        # Promotion / discount blurbs.
        promotions: list[dict] = []
        m = re.search(
            r'activity-list-item-info-extras-details-content"[^>]*>(.*?)</div>\s*</details>',
            li,
            re.S,
        )
        if m:
            for p in re.findall(r"<p\b[^>]*>(.*?)</p>", m.group(1), re.S):
                promo = _parse_promotion(p)
                if promo:
                    promotions.append(promo)

        out["activities"][activity_id] = {
            "title": title,
            "details_url": details_url,
            "schedule_display": schedule_display,
            "start_date_display": start_date_display,
            "price_display": price_display,
            "promotions": promotions,
        }
    return out


def _parse_promotion(p_html: str) -> dict | None:
    def grab(cls: str) -> list[str]:
        return [text_of(x) for x in re.findall(rf"class='{cls}'[^>]*>(.*?)</span>", p_html, re.S) if text_of(x)]

    title = (grab("promotion-title") or [None])[0]
    discount = (grab("promotion-discount-item") or [None])[0]
    conditions = grab("promotion-application-text")
    extra = grab("promotion-listing-extra-info") + grab("promotion-has-required-memberships")
    if not any([title, discount, conditions, extra]):
        plain = text_of(p_html)
        return {"text": plain} if plain else None
    promo: dict = {}
    if title:
        promo["title"] = title
    if discount:
        promo["discount"] = discount
    if conditions:
        promo["details"] = conditions
    if extra:
        promo["notes"] = extra
    return promo


# --------------------------------------------------------------------------- #
# Calendar feed
# --------------------------------------------------------------------------- #
def fetch_sessions(
    store_base_url: str,
    program_id: int,
    *,
    sub_category_id: int | None = None,
    activity_id: int | None = None,
    window_years: int = 2,
    referer: str | None = None,
) -> list[dict]:
    """Return raw session ("segment") records from EventsForProgram.

    The feed is a FullCalendar event source; it accepts ``start`` / ``end``
    bounds and clamps results to whatever sessions actually exist.
    """
    today = dt.date.today()
    start = today.replace(month=1, day=1) - dt.timedelta(days=366 * (window_years - 1))
    end = today.replace(month=1, day=1) + dt.timedelta(days=366 * (window_years + 1))
    params = {
        "programId": program_id,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "_": int(time.time() * 1000),
    }
    if sub_category_id is not None:
        params["subCategoryId"] = sub_category_id
    if activity_id is not None:
        params["activityId"] = activity_id
    url = f"{store_base_url}/api/Organization/EventsForProgram?" + urllib.parse.urlencode(params)
    data = _request(url, as_json=True, referer=referer or store_base_url)
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected EventsForProgram payload: {type(data).__name__}")
    # Keep only real activity segments (the feed can also return "holiday" rows).
    return [e for e in data if e.get("Type") in (None, "activity-segment") and e.get("SegmentId")]


# --------------------------------------------------------------------------- #
# Shaping
# --------------------------------------------------------------------------- #
def _facility(raw: dict) -> dict | None:
    facs = raw.get("Facilities") or []
    if not facs:
        return None
    f = facs[0]
    addr = f.get("Address") or {}
    return {
        "name": f.get("ResourceName") or (f.get("Name") or {}).get("FirstAvailable"),
        "address1": addr.get("Address1") or None,
        "address2": addr.get("Address2") or None,
        "city": addr.get("City") or None,
        "province": addr.get("Province") or None,
        "postal_code": addr.get("PostalCode") or None,
        "country": addr.get("Country") or None,
        "phone": addr.get("Tel") or None,
        "phone_ext": addr.get("TelExt") or None,
        "latitude": addr.get("Latitude"),
        "longitude": addr.get("Longitude"),
    }


def _spots_remaining(raw: dict):
    if raw.get("HasUnlimitedSpots"):
        return None
    cap = raw.get("SpotsAvailable")
    taken = raw.get("SpotsReserved") or 0
    if isinstance(cap, (int, float)) and cap:
        return int(cap) - int(taken)
    return None


def shape_session(raw: dict, store_base_url: str = "") -> dict:
    state = raw.get("state", raw.get("ActivityState"))
    if raw.get("HasPassed"):
        status = "passed"
    else:
        status = ACTIVITY_STATE.get(state, f"state_{state}")
    reg_url = None
    if raw.get("ActivityId") and raw.get("SegmentId"):
        reg_url = f"{store_base_url}/shop/Activities/{raw['ActivityId']}/DropIns/{raw['SegmentId']}"
    return {
        "segment_id": raw.get("SegmentId"),
        "start": raw.get("start"),
        "end": raw.get("end"),
        "all_day": raw.get("allDay", False),
        "has_passed": bool(raw.get("HasPassed")),
        "status": status,
        "state_code": state,
        "capacity": None if raw.get("HasUnlimitedSpots") else raw.get("SpotsAvailable"),
        "has_unlimited_spots": bool(raw.get("HasUnlimitedSpots")),
        "spots_reserved": raw.get("SpotsReserved"),
        "spots_remaining": _spots_remaining(raw),
        "has_place_left": raw.get("HasPlaceLeft"),
        "max_attendance": raw.get("MaxAttendance"),
        "attendance_string": raw.get("AttendanceString"),
        "drop_in_price": raw.get("Price"),
        "drop_in_best_price": raw.get("BestPrice"),
        "fee": raw.get("Fee"),
        "wait_list_enabled": raw.get("WaitListEnabled"),
        "wait_list_spots_reserved": raw.get("WaitListSpotsReserved"),
        "can_register": raw.get("CanRegister"),
        "has_drop_ins": raw.get("HasDropIns"),
        "already_in_cart": raw.get("AlreadyInCart"),
        "description": raw.get("Description"),
        "extra_information": raw.get("ExtraInformation"),
        "registration_url": reg_url,
    }


def build_document(url: str, *, window_years: int = 2) -> dict:
    meta = parse_program_url(url)
    store_base = meta["store_base_url"]

    page_html = _request(meta["program_url"], as_json=False, referer=store_base)
    page = parse_program_page(page_html, store_base)

    # If the URL pins specific sub-categories, scrape exactly those; otherwise
    # fall back to a single program-wide pull.
    target_subs: list[int | None] = meta["sub_category_ids"] or [None]

    raw_sessions: list[dict] = []
    for sub_id in target_subs:
        raw_sessions.extend(
            fetch_sessions(
                store_base,
                meta["program_id"],
                sub_category_id=sub_id,
                window_years=window_years,
                referer=meta["program_url"],
            )
        )
    # de-dupe on (segment_id) in case sub-categories overlap
    seen: set = set()
    deduped: list[dict] = []
    for ev in raw_sessions:
        key = ev.get("SegmentId")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ev)
    raw_sessions = deduped

    # group sessions -> activities -> sub-categories
    subcats: dict[int, dict] = {}
    activities: dict[int, dict] = {}
    for ev in sorted(raw_sessions, key=lambda e: (e.get("SubCategoryId") or 0, e.get("ActivityId") or 0, e.get("start") or "")):
        sub_id = ev.get("SubCategoryId")
        act_id = ev.get("ActivityId")
        sub = subcats.setdefault(
            sub_id,
            {
                "id": sub_id,
                "name": ev.get("SubCategoryName"),
                "category": {"id": ev.get("CategoryId"), "name": ev.get("CategoryName")},
                "activities": [],
                "_activity_ids": set(),
            },
        )
        if act_id not in activities:
            page_meta = page["activities"].get(act_id, {})
            act = {
                "id": act_id,
                "name": page_meta.get("title") or ev.get("ActivityName"),
                "details_url": page_meta.get("details_url")
                or f"{store_base}/shop/activities/{act_id}",
                "category": {"id": ev.get("CategoryId"), "name": ev.get("CategoryName")},
                "sub_category": {"id": sub_id, "name": ev.get("SubCategoryName")},
                "schedule_display": page_meta.get("schedule_display", []),
                "start_date_display": page_meta.get("start_date_display"),
                "price_display": page_meta.get("price_display"),
                "drop_in_price": ev.get("Price"),
                "drop_in_best_price": ev.get("BestPrice"),
                "location": ev.get("Location"),
                "facility": _facility(ev),
                "tags": [t.get("Name") for t in (ev.get("Tags") or []) if t.get("Name")],
                "staff": list(ev.get("StaffNames") or []),
                "wait_list_enabled": ev.get("WaitListEnabled"),
                "promotions": page_meta.get("promotions", []),
                "session_count": 0,
                "sessions": [],
            }
            activities[act_id] = act
            sub["activities"].append(act)
            sub["_activity_ids"].add(act_id)
        activities[act_id]["sessions"].append(shape_session(ev, store_base))

    flat: list[dict] = []
    for act in activities.values():
        act["session_count"] = len(act["sessions"])
        for s in act["sessions"]:
            flat.append(
                {
                    "program_id": meta["program_id"],
                    "sub_category_id": act["sub_category"]["id"],
                    "sub_category_name": act["sub_category"]["name"],
                    "category": act["category"],
                    "activity_id": act["id"],
                    "activity_name": act["name"],
                    "location": act["location"],
                    **s,
                }
            )

    for sub in subcats.values():
        sub.pop("_activity_ids", None)

    return {
        "source_url": url,
        "scraped_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "store": {
            "organization": meta["org"],
            "language": meta["language"],
            "base_url": store_base,
        },
        "program": {
            "id": meta["program_id"],
            "title": page.get("program_title"),
            "url": meta["program_url"],
        },
        "notices": page.get("page_notices", []),
        "totals": {
            "sub_categories": len(subcats),
            "activities": len(activities),
            "sessions": len(flat),
            "upcoming_sessions": sum(1 for s in flat if not s["has_passed"]),
        },
        "sub_categories": list(subcats.values()),
        "sessions": flat,
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", nargs="?", default=DEFAULT_URL, help="Amilia program URL (default: JCC of Greater RI pickleball drop-in)")
    ap.add_argument("-o", "--output", help="Write JSON here instead of stdout")
    ap.add_argument("--indent", type=int, default=2, help="JSON indent (default: 2; use 0 for compact)")
    ap.add_argument("--window-years", type=int, default=2, help="How many years on either side of this year to query (default: 2)")
    args = ap.parse_args(argv)

    doc = build_document(args.url, window_years=args.window_years)
    text = json.dumps(doc, indent=args.indent or None, ensure_ascii=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"wrote {args.output}  ({doc['totals']})", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
