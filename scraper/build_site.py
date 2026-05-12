#!/usr/bin/env python3
"""Run the Amilia scraper and build everything the static site serves.

Usage:
    python3 scraper/build_site.py [program_url]

Outputs (under ``site/``):
  - ``data/sessions.json``      — the data the main page fetches
  - ``s/<segmentId>/index.html`` — one shareable, link-preview-ready page per
                                   session (regenerated each run; git-ignored)

The deployed base URL (used for absolute ``og:`` / canonical URLs) defaults to
the GitHub Pages URL and can be overridden with the ``SITE_BASE_URL`` env var.
Paths are resolved relative to this file, so it can be run from anywhere.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import pathlib
import re
import shutil
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import scrape_open_play as scraper  # noqa: E402

SITE = ROOT / "site"
DATA_OUT = SITE / "data" / "sessions.json"
SESSIONS_DIR = SITE / "s"
TEMPLATE = (HERE / "templates" / "session.html").read_text(encoding="utf-8")

SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "https://robertcorey.github.io/jcc-pickleball").rstrip("/")

WD_FULL = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
WD_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
MO_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MO_FULL = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
DAY_COLOR = {0: "#8b5fb0", 1: "#7c8a2e", 2: "#c6f23b", 3: "#2f8f73", 4: "#d99a2b", 5: "#3d6fb0", 6: "#b5562f"}


def esc(x) -> str:
    return html.escape("" if x is None else str(x), quote=True)


def short_name(n: str) -> str:
    s = re.sub(r"^\s*D/I\s*Pickleball\s*:\s*", "", n or "", flags=re.I)
    s = re.sub(r"^\s*D/I\s+", "", s, flags=re.I).strip()
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
def build_glance_lis(doc) -> str:
    """The shared 'Good to know' <li> list (HTML), same content for every page."""
    promos = []
    seen = set()
    for sc in doc.get("sub_categories", []):
        for a in sc.get("activities", []):
            for pr in a.get("promotions", []):
                key = (pr.get("title") or "") + "|" + (pr.get("discount") or "")
                if key in seen:
                    continue
                seen.add(key)
                detail = " · ".join(pr.get("details") or pr.get("notes") or ([pr["text"]] if pr.get("text") else []))
                promos.append((pr.get("title") or "Discount", pr.get("discount") or "", detail))
    notices = [n for n in (doc.get("notices") or []) if n]

    fac = None
    for s in doc.get("sessions", []):
        if s.get("facility"):
            fac = s["facility"]
            break
    if not fac:
        for sc in doc.get("sub_categories", []):
            for a in sc.get("activities", []):
                if a.get("facility"):
                    fac = a["facility"]
                    break
            if fac:
                break

    # price range across all sessions
    lo = hi = None
    for s in doc.get("sessions", []):
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
        items.append(("\U0001F4B5", f"<b>Drop-in</b> — {esc(pr)} per session. Pay on the JCC store, or use a Multipass."))
    for title, disc, detail in promos:
        pct = re.sub(r"^Discount of\s*", "", disc, flags=re.I).strip()
        t = re.sub(r"^Pickleball:\s*", "", title, flags=re.I).strip() or title
        items.append(("\U0001F3F7️", f"<b>{esc(t)}</b> — {esc(pct) + ' off' if pct else 'Discount'}" + (f" · {esc(detail)}" if detail else "")))
    for n in notices:
        items.append(("⚠️", esc(n)))
    if fac:
        addr = ", ".join(x for x in [fac.get("address1"), ", ".join(y for y in [fac.get("city"), fac.get("province")] if y) + (" " + fac["postal_code"] if fac.get("postal_code") else "")] if x)
        if fac.get("latitude") and fac.get("longitude"):
            map_href = f"https://maps.google.com/?q={fac['latitude']},{fac['longitude']}"
        else:
            map_href = "https://maps.google.com/?q=" + "+".join(x for x in [fac.get("address1"), fac.get("city"), fac.get("province"), fac.get("postal_code")] if x).replace(" ", "+")
        where = f"<b>Where</b> — {esc(fac.get('name') or 'JCC')}" + (f", {esc(addr)}" if addr else "")
        if fac.get("phone"):
            where += f" · {esc(fmt_phone(fac['phone']))}"
        where += f' · <a href="{esc(map_href)}" target="_blank" rel="noopener">Map ↗</a>'
        items.append(("\U0001F4CD", where))
    else:
        items.append(("\U0001F4CD", "<b>Where</b> — JCC Gymnasium, 401 Elmgrove Ave, Providence, RI 02906"))

    return "".join(f'<li><span class="ico" aria-hidden="true">{ico}</span><span>{html_}</span></li>' for ico, html_ in items)


def venue_line(doc) -> str:
    fac = None
    for s in doc.get("sessions", []):
        if s.get("facility"):
            fac = s["facility"]
            break
    if not fac:
        return "JCC Gymnasium · 401 Elmgrove Ave, Providence, RI 02906"
    addr = ", ".join(x for x in [fac.get("address1"), ", ".join(y for y in [fac.get("city"), fac.get("province")] if y) + (" " + fac["postal_code"] if fac.get("postal_code") else "")] if x)
    name = fac.get("name") or "JCC Gymnasium"
    return f"{name} · {addr}" if addr else name


def build_session_pages(doc) -> int:
    sessions = doc.get("sessions", [])
    if not sessions:
        return 0
    glance_lis = build_glance_lis(doc)
    venue = venue_line(doc)
    venue_short = venue.split("·")[0].strip()
    store_url = (doc.get("program") or {}).get("url") or scraper.DEFAULT_URL
    scraped_iso = doc.get("scraped_at_utc") or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    today = dt.date.today()

    # fresh dir
    if SESSIONS_DIR.exists():
        shutil.rmtree(SESSIONS_DIR)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    count = 0
    for s in sessions:
        sid = s.get("segment_id")
        if not sid:
            continue
        p = parse_local(s.get("start"))
        pe = parse_local(s.get("end"))
        act = short_name(s.get("activity_name"))
        cls, dot, label_html, label_plain = avail(s)
        cap, left, going = spots_info(s)
        pr = price_range(s.get("drop_in_best_price"), s.get("drop_in_price"))
        reg_url = s.get("registration_url") or s.get("details_url") or store_url

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
            cta = (f'<a class="btn btn-primary" href="{esc(reg_url)}" target="_blank" rel="noopener">'
                   + ("Join the waitlist" if s.get("wait_list_enabled") else "View on Amilia")
                   + ' <span class="arrow" aria-hidden="true">↗</span></a>')
        elif cls == "soon":
            cta = f'<a class="btn btn-primary" href="{esc(reg_url)}" target="_blank" rel="noopener">View on Amilia <span class="arrow" aria-hidden="true">↗</span></a>'
        else:
            cta = f'<a class="btn btn-primary" href="{esc(reg_url)}" target="_blank" rel="noopener">Register on Amilia <span class="arrow" aria-hidden="true">→</span></a>'

        # OG / meta text — keyed to this specific date, not the recurring slot name
        canonical = f"{SITE_BASE_URL}/s/{sid}/"
        date_brief = f"{WD_SHORT[p['wd']]}, {MO_SHORT[p['mo'] - 1]} {p['d']}" if p else ""
        date_long = f"{WD_FULL[p['wd']]}, {MO_FULL[p['mo'] - 1]} {p['d']}" if p else ""
        time_brief = fmt_time(p["h"], p["mi"]) if p else ""
        og_title = f"Drop-in pickleball · {date_brief}" + (f" at {time_brief}" if time_brief else "") + " · Providence JCC"
        if s.get("has_passed"):
            og_desc = f"Drop-in pickleball at the Providence JCC — {date_long}, {when_time}. This session has already happened; see the upcoming schedule."
        else:
            head = f"Drop-in pickleball at the Providence JCC — {date_long}" + (f", {when_time}" if when_time else "") + "."
            og_desc = f"{head} {venue_short}. {label_plain[:1].upper() + label_plain[1:]}"
            if pr:
                og_desc += f" · {pr} per drop-in"
            og_desc += ". Tap to register on the official JCC site."
        page_title = (f"Pickleball · {date_brief}" + (f" at {time_brief}" if time_brief else "") + " · Providence JCC") if date_brief else "Drop-in pickleball · Providence JCC"

        price_bit = f' · <span class="price">{esc(pr)}</span> / drop-in' if pr else ""

        fields = {
            "PAGE_TITLE": esc(page_title),
            "OG_TITLE": esc(og_title),
            "OG_DESC": esc(og_desc),
            "CANONICAL": esc(canonical),
            "OG_IMAGE": esc(f"{SITE_BASE_URL}/og.png"),
            "HOME_HREF": "../../",
            "STORE_URL": esc(store_url),
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
        }
        out = TEMPLATE
        for k, v in fields.items():
            out = out.replace("{{" + k + "}}", v)
        dest = SESSIONS_DIR / str(sid) / "index.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(out, encoding="utf-8")
        count += 1
    return count


# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    url = args[0] if args else scraper.DEFAULT_URL
    doc = scraper.build_document(url)

    DATA_OUT.parent.mkdir(parents=True, exist_ok=True)
    with DATA_OUT.open("w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    n_pages = build_session_pages(doc)

    t = doc.get("totals", {})
    print(
        f"wrote {DATA_OUT.relative_to(ROOT)} ({t.get('activities')} activities, "
        f"{t.get('sessions')} sessions, {t.get('upcoming_sessions')} upcoming) "
        f"+ {n_pages} session pages under site/s/  [base={SITE_BASE_URL}]",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
