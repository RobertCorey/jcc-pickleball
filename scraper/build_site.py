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
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import scrape_open_play as scraper  # noqa: E402
import sources  # noqa: E402
import og_images  # noqa: E402

SITE = ROOT / "site"
DATA_OUT = SITE / "data" / "sessions.json"
BUILD_META_OUT = SITE / "data" / "build.json"
SESSIONS_DIR = SITE / "s"
GENERIC_OG = SITE / "og.png"
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


def build_session_pages(doc) -> tuple[int, int]:
    """Write site/s/<id>/index.html for every session (+ a per-session og.png if
    Playwright is available). Returns (page_count, image_count)."""
    sessions = doc.get("sessions", [])
    if not sessions:
        return (0, 0)
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
            cta = (f'<a class="btn btn-primary" href="{esc(reg_url)}" target="_blank" rel="noopener">'
                   + ("Join the waitlist" if s.get("wait_list_enabled") else esc(cta_view))
                   + ' <span class="arrow" aria-hidden="true">↗</span></a>')
        elif cls == "soon":
            cta = f'<a class="btn btn-primary" href="{esc(reg_url)}" target="_blank" rel="noopener">{esc(cta_view)} <span class="arrow" aria-hidden="true">↗</span></a>'
        else:
            cta = f'<a class="btn btn-primary" href="{esc(reg_url)}" target="_blank" rel="noopener">{esc(cta_primary)} <span class="arrow" aria-hidden="true">→</span></a>'

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

        fields = {
            "PAGE_TITLE": esc(page_title),
            "OG_TITLE": esc(og_title),
            "OG_DESC": esc(og_desc),
            "CANONICAL": esc(canonical),
            "OG_IMAGE": esc(f"{SITE_BASE_URL}/s/{sid}/og.png"),
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
        sdir = SESSIONS_DIR / str(sid)
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "index.html").write_text(out, encoding="utf-8")

        # og:image for this page: a fallback copy of the generic card now (so the
        # URL always resolves), then a session-specific render overwrites it below
        # if Playwright is available.
        og_png = sdir / "og.png"
        if GENERIC_OG.exists():
            shutil.copyfile(GENERIC_OG, og_png)
        og_cards.append((og_png, og_images.card_html(
            date_long=when_date, time_str=when_time,
            eyebrow=(when_rel.upper() if when_rel else ""),
            kicker=og_kicker, url_text=og_url_text,
            venue_top=og_venue_top, venue_bottom=og_venue_bottom,
        )))
        count += 1

    n_imgs = 0
    try:
        n_imgs = og_images.render_all(og_cards)
    except Exception as exc:  # rendering is best-effort; the generic fallbacks stay in place
        print(f"  (per-session OG images skipped: {exc})", file=sys.stderr)
    return count, n_imgs


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


# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    # The pipeline is now multi-source; sources + venues live in sources.py.
    # (A CLI arg is still accepted for back-compat but ignored — the JCC URL is
    # the default source in the registry.)
    doc = sources.build_merged_document()

    DATA_OUT.parent.mkdir(parents=True, exist_ok=True)
    with DATA_OUT.open("w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    n_pages, n_imgs = build_session_pages(doc)
    n_fallbacks = max(0, n_pages - n_imgs)

    _write_build_manifest(doc=doc, n_pages=n_pages, n_imgs=n_imgs, n_fallbacks=n_fallbacks)
    _report_og_health(n_pages=n_pages, n_imgs=n_imgs, n_fallbacks=n_fallbacks)

    t = doc.get("totals", {})
    img_note = f"{n_imgs} session OG images" if n_imgs else "(per-session OG images: generic fallback — Playwright not available)"
    print(
        f"wrote {DATA_OUT.relative_to(ROOT)} ({t.get('activities')} activities, "
        f"{t.get('sessions')} sessions, {t.get('upcoming_sessions')} upcoming) "
        f"+ {n_pages} session pages + {img_note} under site/s/  [base={SITE_BASE_URL}]",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
