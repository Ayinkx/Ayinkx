#!/usr/bin/env python3
"""Generate an accurate GitHub streak card as profile/streak.svg.

The popular third-party streak badge (streak-stats.demolab.com) can serve stale
numbers. This script computes the current and longest streaks directly from the
public contribution calendar and renders a small self-hosted SVG card, so the
figure is always correct and controlled by this repository.

Usage:
    python3 scripts/streak.py <username> [output_path]

Data source: https://github-contributions-api.jogruber.de/v4/<username>?y=last
Standard library only. On any failure it exits 0 without touching the existing
file, so it never breaks the profile workflow.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path

API = "https://github-contributions-api.jogruber.de/v4/{user}?y=last"

BG = "#0D1117"
BORDER = "#0E75B6"
TEXT = "#FFFFFF"
MUTED = "#8B949E"
ACCENT = "#00F7FF"


def fetch(user: str) -> dict:
    req = urllib.request.Request(
        API.format(user=user), headers={"User-Agent": "streak-card/1.0"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _compute(days: list[dict]) -> dict:
    counts = {d["date"]: int(d["count"]) for d in days}
    dates = sorted(counts)
    total = sum(counts.values())

    longest = 0
    longest_range = None
    run = 0
    start = None
    for date in dates:
        if counts[date] > 0:
            if run == 0:
                start = date
            run += 1
            if run > longest:
                longest = run
                longest_range = (start, date)
        else:
            run = 0

    order = list(reversed(dates))
    today = dt.date.today()
    idx = 0
    if (
        order
        and counts[order[0]] == 0
        and dt.date.fromisoformat(order[0]) == today
        and len(order) > 1
    ):
        idx = 1  # today has no contributions yet; streak may end yesterday

    current = 0
    current_end = None
    for date in order[idx:]:
        if counts[date] > 0:
            if current == 0:
                current_end = date
            current += 1
        else:
            break

    current_range = None
    if current and current_end:
        end = dt.date.fromisoformat(current_end)
        first = end - dt.timedelta(days=current - 1)
        if first.isoformat() in counts:
            current_range = (first.isoformat(), current_end)

    return {
        "total": total,
        "current": current,
        "longest": longest,
        "current_range": current_range,
        "longest_range": longest_range,
    }


def _label(rng: tuple[str, str] | None) -> str:
    if not rng:
        return ""
    a = dt.date.fromisoformat(rng[0]).strftime("%b %d")
    b = dt.date.fromisoformat(rng[1]).strftime("%b %d")
    return f"{a} - {b}"


def render(stats: dict) -> str:
    width, height = 495, 195
    cols = [
        (100, "Total Contributions", str(stats["total"]), ""),
        (247, "Current Streak", str(stats["current"]), _label(stats["current_range"])),
        (395, "Longest Streak", str(stats["longest"]), _label(stats["longest_range"])),
    ]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="GitHub streak">',
        "<style>text{font-family:Segoe UI,Helvetica,Arial,sans-serif}</style>",
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="8" '
        f'fill="{BG}" stroke="{BORDER}"/>',
    ]
    for x, title, value, sub in cols:
        parts.append(
            f'<text x="{x}" y="88" text-anchor="middle" font-size="36" '
            f'font-weight="700" fill="{ACCENT}">{value}</text>'
        )
        parts.append(
            f'<text x="{x}" y="118" text-anchor="middle" font-size="14" '
            f'fill="{TEXT}">{title}</text>'
        )
        if sub:
            parts.append(
                f'<text x="{x}" y="140" text-anchor="middle" font-size="12" '
                f'fill="{MUTED}">{sub}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


def main() -> int:
    user = sys.argv[1] if len(sys.argv) > 1 else "Ayinkx"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("profile/streak.svg")
    try:
        days = fetch(user).get("contributions") or []
        if not days:
            print("no contributions data; leaving existing file", file=sys.stderr)
            return 0
        stats = _compute(days)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render(stats), encoding="utf-8")
        print(
            f"wrote {out}: total={stats['total']} "
            f"current={stats['current']} longest={stats['longest']}"
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - never fail the profile workflow
        print(f"streak card generation skipped: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
