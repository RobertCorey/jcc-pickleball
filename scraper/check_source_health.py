#!/usr/bin/env python3
"""Deploy guard: refuse to ship sessions.json when live sources have gone dark.

Failure mode this exists for (seen 2026-06-26): individual sources fail or parse
to zero sessions, build_merged_document logs a ::warning:: and the deploy ships
a mostly-empty site while CI stays green. One quiet source is tolerable (a club
can have a gap or a transient outage); two or more dark sources — or a collapsed
session count — means the data is not fit to publish, and yesterday's deploy is
better than today's empty one.

Exit 0 = healthy enough to deploy. Exit 1 = block the deploy.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scraper"))
from sources import SOURCES  # registry is the ground truth for what "all" means

MAX_DARK_SOURCES = 1      # >1 dark source blocks the deploy
MIN_UPCOMING = 100        # healthy baseline is ~700; a collapse below this blocks


def main() -> int:
    doc = json.loads((REPO / "site" / "data" / "sessions.json").read_text())
    meta = {m.get("id"): m for m in doc.get("sources", [])}
    expected = [sid for sid, _ in SOURCES]

    dark = []
    print(f"{'source':<28}{'ok':<6}sessions")
    for sid in expected:
        m = meta.get(sid)
        ok = bool(m and m.get("ok"))
        count = int(m.get("session_count", 0)) if m else 0
        print(f"{sid:<28}{str(ok):<6}{count}")
        if not ok or count == 0:
            reason = "missing from build" if m is None else (m.get("error", "ok but 0 sessions") if not ok else "0 sessions")
            dark.append((sid, reason))

    upcoming = int(doc.get("totals", {}).get("upcoming_sessions", 0))
    print(f"upcoming sessions: {upcoming} (floor {MIN_UPCOMING})")

    failed = False
    for sid, reason in dark:
        print(f"::warning::source {sid} is dark: {reason}")
    if len(dark) > MAX_DARK_SOURCES:
        print(f"::error::{len(dark)} of {len(expected)} live sources are dark "
              f"({', '.join(s for s, _ in dark)}) — refusing to deploy degraded data")
        failed = True
    if upcoming < MIN_UPCOMING:
        print(f"::error::only {upcoming} upcoming sessions (< {MIN_UPCOMING}) — refusing to deploy")
        failed = True

    if not failed:
        print(f"source health OK: {len(expected) - len(dark)}/{len(expected)} sources live")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
