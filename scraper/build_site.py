#!/usr/bin/env python3
"""Run the Amilia scraper and write the data file the static site reads.

Usage:
    python3 scraper/build_site.py [program_url]

Writes ``site/data/sessions.json``. Run from the repo root (or anywhere — paths
are resolved relative to this file).
"""
from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import scrape_open_play as scraper  # noqa: E402

OUT = ROOT / "site" / "data" / "sessions.json"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    url = args[0] if args else scraper.DEFAULT_URL
    doc = scraper.build_document(url)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    t = doc.get("totals", {})
    print(
        f"wrote {OUT.relative_to(ROOT)} — "
        f"{t.get('activities')} activities, {t.get('sessions')} sessions, "
        f"{t.get('upcoming_sessions')} upcoming",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
