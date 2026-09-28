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


def _icon(kind: str, cx: float, cy: float) -> str:
    """A small vector icon centred on (cx, cy)."""
    if kind == "total":
        return (
            f'<g transform="translate({cx - 12},{cy - 12})" fill="none" '
            f'stroke="url(#gNum)" stroke-width="2.4" stroke-linecap="round">'
            f'<line x1="5" y1="20" x2="5" y2="13"/>'
            f'<line x1="12" y1="20" x2="12" y2="7"/>'
            f'<line x1="19" y1="20" x2="19" y2="3"/></g>'
        )
    if kind == "current":
        return (
            f'<g transform="translate({cx - 12},{cy - 12})">'
            f'<path d="M12 2c1.6 4.2-4.2 5.8-4.2 10.4a4.2 4.2 0 0 0 8.4 0c0-1.7-1-2.5-1-3.6 '
            f'2.3 1.3 3.1 3.4 3.1 5.6a6.3 6.3 0 0 1-12.6 0C5.7 8.2 9.4 6 12 2z" '
            f'fill="url(#gNum)"/></g>'
        )
    # longest -> trophy
    return (
        f'<g transform="translate({cx - 12},{cy - 12})" fill="url(#gNum)">'
        f'<path d="M7 3h10v4a5 5 0 0 1-10 0V3z"/>'
        f'<path d="M5 4H3v1.5A3.5 3.5 0 0 0 6.5 9H7V7H5.5A1.5 1.5 0 0 1 4 5.5V5H5z" opacity=".85"/>'
        f'<path d="M19 4h2v1.5A3.5 3.5 0 0 1 17.5 9H17V7h1.5A1.5 1.5 0 0 0 20 5.5V5h-1z" opacity=".85"/>'
        f'<rect x="11" y="11.5" width="2" height="3.5"/>'
        f'<rect x="8" y="15" width="8" height="2" rx="1"/></g>'
    )


def render(stats: dict) -> str:
    width, height = 495, 210
    cols = [
        (82.5, "total", "Total Contributions", str(stats["total"]), ""),
        (247.5, "current", "Current Streak", str(stats["current"]), _label(stats["current_range"])),
        (412.5, "longest", "Longest Streak", str(stats["longest"]), _label(stats["longest_range"])),
    ]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="GitHub streak">',
        '<defs>'
        f'<linearGradient id="gBg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="#161B22"/><stop offset="1" stop-color="#0D1117"/>'
        f'</linearGradient>'
        f'<linearGradient id="gNum" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{ACCENT}"/><stop offset="1" stop-color="#7C3AED"/>'
        f'</linearGradient>'
        f'<linearGradient id="gTop" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="#0E75B6"/><stop offset="0.5" stop-color="{ACCENT}"/>'
        f'<stop offset="1" stop-color="#7C3AED"/></linearGradient>'
        f'<filter id="glow" x="-30%" y="-30%" width="160%" height="160%">'
        f'<feGaussianBlur stdDeviation="6" result="b"/>'
        f'<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
        '</defs>',
        '<style>text{font-family:Segoe UI,-apple-system,Helvetica,Arial,sans-serif}'
        '.lbl{font-size:11px;letter-spacing:1.5px;fill:#8B949E}'
        '.sub{font-size:12px;fill:#79C0FF}.num{font-size:40px;font-weight:800}'
        '.title{font-size:13px;letter-spacing:3px;fill:#C9D1D9}</style>',
        f'<rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="14" '
        f'fill="url(#gBg)" stroke="#30363D"/>',
        f'<rect x="1" y="1" width="{width - 2}" height="4" rx="2" fill="url(#gTop)"/>',
        # faint radial glow behind the numbers
        f'<ellipse cx="{width / 2}" cy="120" rx="230" ry="70" fill="{ACCENT}" opacity="0.05"/>',
        f'<text x="{width / 2}" y="34" text-anchor="middle" class="title">GITHUB STREAK</text>',
    ]
    # vertical dividers
    for dx in (165, 330):
        parts.append(
            f'<line x1="{dx}" y1="52" x2="{dx}" y2="180" stroke="#21262D" stroke-width="1"/>'
        )
    for cx, kind, title, value, sub in cols:
        parts.append(_icon(kind, cx, 74))
        parts.append(
            f'<text x="{cx}" y="132" text-anchor="middle" class="num" '
            f'fill="url(#gNum)" filter="url(#glow)">{value}</text>'
        )
        parts.append(
            f'<text x="{cx}" y="158" text-anchor="middle" class="lbl">{title}</text>'
        )
        if sub:
            parts.append(
                f'<text x="{cx}" y="178" text-anchor="middle" class="sub">{sub}</text>'
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
