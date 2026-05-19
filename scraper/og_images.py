#!/usr/bin/env python3
"""Render a per-session social-preview card (1200x630 PNG) for each session.

Used by ``build_site.py``. Rendering needs Playwright + a Chromium build; if
neither is importable the functions degrade gracefully (the caller falls back to
the generic ``og.png``).

Each card shows only *non-volatile* facts about the session — the date, time,
"open drop-in pickleball", and the venue — so a generated image never needs
re-rendering for an existing session (its content can't go stale).
"""
from __future__ import annotations

import html as _html
import pathlib
import sys


def available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except Exception:
        return False


_MARK_SVG = (
    '<svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="32" fill="none" stroke="#c6f23b" stroke-width="9"/>'
    '<circle cx="39" cy="37" r="5" fill="#c6f23b"/><circle cx="61" cy="37" r="5" fill="#c6f23b"/>'
    '<circle cx="39" cy="63" r="5" fill="#c6f23b"/><circle cx="61" cy="63" r="5" fill="#c6f23b"/>'
    '<circle cx="50" cy="50" r="5" fill="#c6f23b"/></svg>'
)

_GRAIN = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E"
    "%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E"
    "%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.05'/%3E%3C/svg%3E"
)

_TEMPLATE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700;12..96,800&family=Hanken+Grotesque:wght@500;600;700&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
html,body{{width:1200px;height:630px;overflow:hidden;}}
body{{font-family:"Hanken Grotesque",sans-serif;color:#1a1b13;background:#f3efe2;
  background-image:radial-gradient(115% 78% at 94% -12%,rgba(198,242,59,.36),transparent 54%),radial-gradient(80% 60% at -8% 6%,rgba(20,72,58,.15),transparent 50%);position:relative;}}
body::after{{content:"";position:absolute;inset:0;opacity:.5;mix-blend-mode:multiply;background-image:url("{grain}");}}
.frame{{position:absolute;inset:0;padding:62px 80px;display:flex;flex-direction:column;}}
.top{{display:flex;align-items:center;gap:18px;}}
.mark{{width:66px;height:66px;border-radius:16px;background:#1a1b13;display:grid;place-items:center;flex:none;}}
.mark svg{{width:42px;height:42px;}}
.kick{{font-family:"Bricolage Grotesque",sans-serif;font-weight:700;font-size:21px;letter-spacing:.16em;text-transform:uppercase;color:#14483a;}}
.mid{{margin-top:auto;margin-bottom:auto;}}
.eyebrow{{display:inline-block;font-family:"Bricolage Grotesque",sans-serif;font-weight:700;font-size:21px;letter-spacing:.14em;text-transform:uppercase;color:#0c3328;background:#c6f23b;padding:7px 16px;border-radius:999px;margin-bottom:22px;}}
h1{{font-family:"Bricolage Grotesque",sans-serif;font-weight:800;font-size:{date_size}px;line-height:1.0;letter-spacing:-0.035em;}}
.line{{margin-top:24px;font-size:34px;font-weight:600;color:#1a1b13;}}
.line .acc{{position:relative;white-space:nowrap;}}
.line .acc::after{{content:"";position:absolute;left:-3px;right:-3px;bottom:.06em;height:.34em;background:#c6f23b;z-index:-1;transform:rotate(-1deg);border-radius:3px;}}
.line .sep{{color:#84846f;font-weight:400;margin:0 10px;}}
.bottom{{display:flex;align-items:center;justify-content:space-between;gap:20px;}}
.url{{display:inline-flex;align-items:center;gap:12px;background:#1a1b13;color:#f3efe2;padding:13px 21px;border-radius:12px;font-family:"Bricolage Grotesque",sans-serif;font-weight:700;font-size:22px;letter-spacing:-.01em;flex:none;}}
.url .dot{{width:10px;height:10px;border-radius:50%;background:#c6f23b;flex:none;}}
.place{{font-size:21px;font-weight:600;color:#84846f;text-align:right;line-height:1.35;}}
.place b{{color:#1a1b13;}}
</style></head><body><div class="frame">
<div class="top"><span class="mark">{mark}</span><span class="kick">{kicker}</span></div>
<div class="mid">{eyebrow_html}<h1>{date_long}</h1><div class="line">{time_str}<span class="sep">·</span>open drop-in <span class="acc">pickleball</span></div></div>
<div class="bottom"><span class="url"><span class="dot"></span>{url}</span><span class="place">{venue_top}<br><b>{venue_bottom}</b></span></div>
</div></body></html>"""


def _esc(x) -> str:
    return _html.escape("" if x is None else str(x))


def card_html(*, date_long: str, time_str: str, eyebrow: str, kicker: str,
              url_text: str, venue_top: str, venue_bottom: str) -> str:
    # shrink the date if it's a long one ("Wednesday, September 30, 2026")
    n = len(date_long)
    date_size = 84 if n <= 22 else (74 if n <= 26 else 64)
    eyebrow_html = f'<span class="eyebrow">{_esc(eyebrow)}</span>' if eyebrow else ""
    return _TEMPLATE.format(
        grain=_GRAIN, mark=_MARK_SVG, date_size=date_size,
        kicker=_esc(kicker), eyebrow_html=eyebrow_html, date_long=_esc(date_long),
        time_str=_esc(time_str), url=_esc(url_text), venue_top=_esc(venue_top), venue_bottom=_esc(venue_bottom),
    )


def render_all(cards: list[tuple[pathlib.Path, str]]) -> int:
    """cards: list of (output_png_path, html_string). Returns number rendered.

    Each card is rendered in its own try/except so one bad card can't take
    down the rest. Failures emit GitHub Actions ``::warning::`` lines so they
    show up on the run summary instead of being silently swallowed into the
    generic ``og.png`` fallback that the caller drops in beforehand.
    """
    if not cards:
        return 0
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        print(f"::warning::OG image render skipped — Playwright not importable ({exc})", file=sys.stderr)
        return 0
    n = 0
    failures = 0
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=1)
            for i, (out_path, html) in enumerate(cards):
                try:
                    page.set_content(html, wait_until="load")
                    try:
                        page.evaluate("() => document.fonts.ready.then(() => true)")
                    except Exception:
                        pass
                    page.wait_for_timeout(500 if i == 0 else 90)  # let webfonts paint (cold-cache on the first one)
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(out_path), clip={"x": 0, "y": 0, "width": 1200, "height": 630})
                    n += 1
                except Exception as exc:
                    failures += 1
                    print(f"::warning::OG render failed for session {out_path.parent.name}: {exc}", file=sys.stderr)
            browser.close()
    except Exception as exc:
        # browser launch / context-manager exit / etc. — partial counts are fine; caller's
        # pre-copied generic og.png stays in place for the missing ones.
        print(f"::warning::OG image renderer aborted after {n}/{len(cards)} ({exc})", file=sys.stderr)
    if failures:
        print(f"::warning::OG image render: {failures} of {len(cards)} cards failed", file=sys.stderr)
    return n
