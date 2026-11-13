#!/usr/bin/env python3
"""Generate the animated GitHub stats and "Spent My Time" cards.

Both cards are self-hosted SVGs (profile/github-stats.svg and
profile/spent-my-time.svg) so the numbers come from live data and the
look stays under this repository's control.

Usage:
    python3 scripts/animated_cards.py <username> [profile_dir]

Data sources:
    - https://github-contributions-api.jogruber.de/v4/<user>?y=last (no auth)
    - GitHub REST API for owned repositories and language bytes
      (uses GITHUB_TOKEN when present; falls back to unauthenticated)

Standard library only. On failure it exits 0 without touching the cards,
so it can never break the profile workflow.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import sys
import urllib.request
from collections import Counter
from pathlib import Path

CALENDAR_API = "https://github-contributions-api.jogruber.de/v4/{user}?y=last"
GH_API = "https://api.github.com"

BG0, BG1 = "#0A0F1F", "#0F1530"
TEXT, MUTED = "#E8ECF8", "#8B94B3"
BLUE, CYAN, VIOLET = "#0E75B6", "#00F7FF", "#7C3AED"

LANG_COLORS = {
    "Python": "#3572A5",
    "TypeScript": "#3178C6",
    "JavaScript": "#F1E05A",
    "Rust": "#DEA584",
    "HTML": "#E34C26",
    "CSS": "#563D7C",
    "Shell": "#89E051",
    "Solidity": "#AA6746",
    "Go": "#00ADD8",
    "C++": "#F34B7D",
    "C": "#555555",
    "Vue": "#41B883",
    "Dockerfile": "#384D54",
    "Makefile": "#427819",
    "Jupyter Notebook": "#DA5B0B",
}
FALLBACK_LANG = "#8B94B3"


def _get(url: str, token: str | None = None) -> object:
    headers = {"User-Agent": "ayinkx-profile-cards/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["Accept"] = "application/vnd.github+json"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_calendar(user: str) -> list[dict]:
    data = _get(CALENDAR_API.format(user=user))
    return data.get("contributions") or []


def fetch_repos(user: str, token: str | None) -> list[dict]:
    repos: list[dict] = []
    page = 1
    while True:
        batch = _get(
            f"{GH_API}/users/{user}/repos?per_page=100&type=owner&page={page}",
            token,
        )
        if not isinstance(batch, list):
            break
        repos += batch
        if len(batch) < 100:
            break
        page += 1
    return repos


def language_bytes(repos: list[dict], token: str | None) -> Counter:
    totals: Counter = Counter()
    for repo in repos:
        if repo.get("fork") or not repo.get("size"):
            continue
        try:
            langs = _get(f"{GH_API}/repos/{repo['full_name']}/languages", token)
        except Exception:  # noqa: BLE001 - one bad repo must not stop the card
            continue
        if isinstance(langs, dict):
            totals.update({k: int(v) for k, v in langs.items()})
    return totals


def streaks(days: list[dict]) -> dict:
    counts = {d["date"]: int(d["count"]) for d in days}
    dates = sorted(counts)
    total = sum(counts.values())
    longest = run = 0
    longest_range = None
    start = None
    for date in dates:
        if counts[date] > 0:
            if run == 0:
                start = date
            run += 1
            if run > longest:
                longest, longest_range = run, (start, date)
        else:
            run = 0

    order = list(reversed(dates))
    idx = 0
    today = dt.date.today().isoformat()
    if order and counts[order[0]] == 0 and order[0] == today and len(order) > 1:
        idx = 1
    current = 0
    current_end = None
    for date in order[idx:]:
        if counts[date] > 0:
            current_end = current_end or date
            current += 1
        else:
            break
    current_range = None
    if current and current_end:
        first = dt.date.fromisoformat(current_end) - dt.timedelta(days=current - 1)
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


def _defs() -> str:
    return f"""<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BG0}"/><stop offset="1" stop-color="{BG1}"/></linearGradient>
<radialGradient id="glowA" cx="0.12" cy="0.05" r="0.55"><stop offset="0" stop-color="{BLUE}" stop-opacity="0.34"/><stop offset="1" stop-color="{BLUE}" stop-opacity="0"/></radialGradient>
<radialGradient id="glowB" cx="0.92" cy="0.98" r="0.5"><stop offset="0" stop-color="{VIOLET}" stop-opacity="0.28"/><stop offset="1" stop-color="{VIOLET}" stop-opacity="0"/></radialGradient>
<pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="#FFFFFF" fill-opacity="0.055"/></pattern>
<linearGradient id="numfill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#C9D2F5"/></linearGradient>
<linearGradient id="ring" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BLUE}"/><stop offset="0.5" stop-color="{CYAN}"/><stop offset="1" stop-color="{VIOLET}"/></linearGradient>
<linearGradient id="bar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{CYAN}"/><stop offset="1" stop-color="{BLUE}" stop-opacity="0.7"/></linearGradient>
<linearGradient id="barPeak" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{CYAN}"/><stop offset="1" stop-color="{VIOLET}"/></linearGradient>
<linearGradient id="tileEdge" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BLUE}" stop-opacity="0.7"/><stop offset="0.5" stop-color="{CYAN}" stop-opacity="0.5"/><stop offset="1" stop-color="{VIOLET}" stop-opacity="0.7"/></linearGradient>
<filter id="glow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
<clipPath id="frame"><rect width="1200" height="800" rx="28"/></clipPath>
</defs>"""


def _roll(x: float, baseline: float, value: int, size: float, name: str, delay: float) -> str:
    """One digit column that scrolls from 0 to `value`."""
    step = round(size * 1.4, 2)
    top = baseline - size
    height = round(size * 1.28, 2)
    chars = "".join(
        f'<text x="{x}" y="{round(baseline + i * step, 2)}" text-anchor="middle" '
        f'font-size="{size}" font-weight="800" fill="url(#numfill)">{digit}</text>'
        for i, digit in enumerate([*range(10), value])
    )
    return (
        f'<clipPath id="c_{name}"><rect x="{round(x - size * 0.42, 2)}" y="{round(top, 2)}" '
        f'width="{round(size * 0.84, 2)}" height="{height}"/></clipPath>'
        f'<g clip-path="url(#c_{name})"><g style="animation:{name} 1.4s cubic-bezier(.2,.8,.2,1) '
        f'{delay}s both">{chars}</g></g>'
    )


def _number(cx: float, baseline: float, value: int, size: float, css: list[str]) -> str:
    text = str(value)
    adv = size * 0.62
    left = cx - (len(text) * adv) / 2 + adv / 2
    step = round(size * 1.4, 2)
    parts = []
    for i, ch in enumerate(text):
        name = f"n{int(cx)}_{i}"
        css.append(
            f"@keyframes {name}{{from{{transform:translateY(0)}}to{{transform:translateY({-10 * step}px)}}}}"
        )
        parts.append(_roll(round(left + i * adv, 2), baseline, int(ch), size, name, 0.15 + i * 0.08))
    return "".join(parts)


def render_stats(stats: dict, weekday: list[tuple[str, int]], langs: list[tuple[str, int]], repos: list[dict]) -> str:
    peak_day = max(weekday, key=lambda kv: kv[1])[0] if weekday else ""
    peak_max = max((v for _, v in weekday), default=0) or 1
    lang_total = sum(v for _, v in langs) or 1
    top_langs = langs[:5]
    top_repos = sorted(repos, key=lambda r: (-r.get("stargazers_count", 0), r.get("name", "")))[:5]

    css = [
        "text{font-family:'Segoe UI Variable Display','Segoe UI',Inter,system-ui,-apple-system,Roboto,Arial,sans-serif;font-variant-numeric:tabular-nums}",
        "#content{animation:fadein .7s ease-out both}",
        "@keyframes fadein{from{opacity:0}to{opacity:1}}",
        "@media (prefers-reduced-motion:reduce){*{animation:none!important}.dot{display:none}}",
        ".b{transform-box:fill-box;transform-origin:50% 100%}",
    ]
    # ring + bars
    radius = 62
    circ = round(2 * 3.14159265 * radius, 2)
    pct = min(stats["current"] / 100, 1.0)
    css.append(
        f"@keyframes ring{{from{{stroke-dasharray:{circ} {circ};stroke-dashoffset:{circ}}}"
        f"to{{stroke-dasharray:{circ} {circ};stroke-dashoffset:{round(circ * (1 - pct), 2)}}}}}"
    )
    for i in range(len(weekday)):
        css.append(
            f"@keyframes bar{i}{{from{{transform:scaleY(0)}}to{{transform:scaleY(1)}}}}"
        )
    for i, (_, value) in enumerate(top_langs):
        length = 427.26 * (value / lang_total)
        css.append(
            f"@keyframes slice{i}{{from{{stroke-dasharray:0 427.26;stroke-dashoffset:0}}"
            f"to{{stroke-dasharray:{length:.2f} 427.26;stroke-dashoffset:0}}}}"
        )

    # built before the style tag so their keyframes land in `css`
    total_num = _number(190, 218, stats["total"], 72, css)
    streak_num = _number(472, 207, stats["current"], 46, css)
    longest_num = _number(960, 218, stats["longest"], 72, css)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 800" width="1200" height="800" role="img" aria-label="GitHub stats for Ayinkx">',
        f"<title>GitHub stats for Lawal Olayinka Awal (Ayinkx)</title>",
        _defs(),
        "<style>" + "".join(css) + "</style>",
        '<g clip-path="url(#frame)"><rect width="1200" height="800" fill="url(#bg)"/>'
        '<rect width="1200" height="800" fill="url(#dots)"/>'
        '<rect width="1200" height="800" fill="url(#glowA)"/>'
        '<rect width="1200" height="800" fill="url(#glowB)"/></g>',
        '<rect x="0.5" y="0.5" width="1199" height="799" rx="28" fill="none" stroke="#FFFFFF" stroke-opacity="0.08"/>',
        '<g id="content">',
        f'<text x="40" y="54" font-size="27" font-weight="800" fill="{TEXT}" letter-spacing="-0.4">GitHub stats</text>',
        f'<text x="40" y="78" font-size="14" fill="{MUTED}">Lawal Olayinka Awal (Ayinkx), Backend Engineer</text>',
        # tile 1 total
        '<rect x="40" y="96" width="300" height="190" rx="20" fill="#FFFFFF" fill-opacity="0.04" stroke="#FFFFFF" stroke-opacity="0.09"/>',
        f'<text x="68" y="138" font-size="15" font-weight="600" fill="{MUTED}">Total contributions</text>',
        total_num,
        f'<text x="68" y="260" font-size="13" font-weight="600" fill="{CYAN}">last 12 months</text>',
        # tile 2 streak ring
        '<rect x="360" y="96" width="480" height="190" rx="20" fill="#FFFFFF" fill-opacity="0.04" stroke="url(#tileEdge)" stroke-width="1.4"/>',
        f'<circle cx="472" cy="191" r="{radius}" fill="none" stroke="#FFFFFF" stroke-opacity="0.1" stroke-width="10"/>',
        f'<circle cx="472" cy="191" r="{radius}" fill="none" stroke="url(#ring)" stroke-width="10" stroke-linecap="round" transform="rotate(-90 472 191)" filter="url(#glow)" style="animation:ring 1.6s cubic-bezier(.2,.8,.2,1) .4s both"/>',
        '<circle class="dot" r="3.5" fill="#FFFFFF" opacity=".9"><animateMotion dur="6s" repeatCount="indefinite" path="M 472,129 A 62,62 0 1,1 471.99,129"/></circle>',
        streak_num,
        f'<text x="472" y="229" text-anchor="middle" font-size="12" font-weight="600" fill="{MUTED}">days</text>',
        f'<text x="574" y="174" font-size="19" font-weight="700" fill="{TEXT}">Current streak</text>',
        f'<text x="574" y="200" font-size="14" fill="{CYAN}" font-weight="600">{html.escape(_label(stats["current_range"]))}</text>',
        f'<text x="574" y="228" font-size="13" fill="{MUTED}">Goal: 100 consecutive days</text>',
        # tile 3 longest
        '<rect x="860" y="96" width="300" height="190" rx="20" fill="#FFFFFF" fill-opacity="0.04" stroke="#FFFFFF" stroke-opacity="0.09"/>',
        f'<text x="888" y="138" font-size="15" font-weight="600" fill="{MUTED}">Longest streak</text>',
        longest_num,
        f'<text x="{960 + len(str(stats["longest"])) * 22 + 10}" y="218" font-size="20" font-weight="600" fill="{MUTED}">days</text>',
        f'<text x="888" y="260" font-size="13" font-weight="600" fill="{CYAN}">{html.escape(_label(stats["longest_range"]))}</text>',
        # weekday chart
        '<rect x="40" y="306" width="1120" height="200" rx="20" fill="#FFFFFF" fill-opacity="0.04" stroke="#FFFFFF" stroke-opacity="0.09"/>',
        f'<text x="68" y="344" font-size="17" font-weight="700" fill="{TEXT}">Contributions by weekday</text>',
        f'<text x="1132" y="344" text-anchor="end" font-size="13" fill="{MUTED}">last 12 months</text>',
    ]
    # baseline and grid
    base_y, top_y = 472.0, 380.0
    for frac, label in ((1.0, peak_max), (0.5, peak_max // 2), (0.0, 0)):
        y = base_y - frac * (base_y - top_y)
        parts.append(f'<line x1="100" y1="{y:.1f}" x2="1132" y2="{y:.1f}" stroke="#FFFFFF" stroke-opacity="{0.16 if frac == 0 else 0.06}"/>')
        parts.append(f'<text x="90" y="{y + 4:.1f}" text-anchor="end" font-size="11" fill="{MUTED}">{label}</text>')
    slot = (1132 - 100) / 7
    for i, (day, count) in enumerate(weekday):
        h = (count / peak_max) * (base_y - top_y) if count else 2
        x = 100 + i * slot + slot / 2 - 20
        is_peak = day == peak_day
        parts.append(
            f'<rect class="b" x="{x:.1f}" y="{base_y - h:.1f}" width="40" height="{h:.1f}" rx="6" '
            f'fill="url(#{"barPeak" if is_peak else "bar"})" style="animation:bar{i} 1s cubic-bezier(.2,.8,.2,1) {0.4 + i * 0.07:.2f}s both"/>'
        )
        parts.append(f'<text x="{x + 20:.1f}" y="492" text-anchor="middle" font-size="12" fill="{MUTED}">{day}</text>')
        if is_peak:
            parts.append(
                f'<text x="{x + 20:.1f}" y="{base_y - h - 10:.1f}" text-anchor="middle" font-size="12" font-weight="600" fill="{CYAN}">{count}</text>'
            )
    # languages panel
    parts += [
        '<rect x="40" y="526" width="550" height="250" rx="20" fill="#FFFFFF" fill-opacity="0.04" stroke="#FFFFFF" stroke-opacity="0.09"/>',
        f'<text x="68" y="566" font-size="17" font-weight="700" fill="{TEXT}">Top languages by code</text>',
    ]
    for i, (name, value) in enumerate(top_langs):
        y = 604 + i * 31
        share = round(value / lang_total * 100)
        parts.append(f'<circle cx="74" cy="{y}" r="5" fill="{LANG_COLORS.get(name, FALLBACK_LANG)}"/>')
        parts.append(f'<text x="92" y="{y + 5}" font-size="14" fill="{TEXT}">{html.escape(name)}</text>')
        parts.append(f'<text x="302" y="{y + 5}" text-anchor="end" font-size="14" font-weight="600" fill="{MUTED}">{share}%</text>')
    # donut (reuse ring geometry)
    r2, c2 = 68, 427.26
    parts.append(f'<circle cx="450" cy="668" r="{r2}" fill="none" stroke="#FFFFFF" stroke-opacity="0.06" stroke-width="26"/>')
    offset = 0.0
    for i, (name, value) in enumerate(top_langs):
        share = value / lang_total
        length = c2 * share
        parts.append(
            f'<circle cx="450" cy="668" r="{r2}" fill="none" stroke="{LANG_COLORS.get(name, FALLBACK_LANG)}" '
            f'stroke-width="26" stroke-dasharray="{length:.2f} {c2}" stroke-dashoffset="{-offset:.2f}" '
            f'transform="rotate(-90 450 668)" style="animation:slice{i} 1.2s ease-out {0.5 + i * 0.15:.2f}s both"/>'
        )
        offset += length
    if top_langs:
        name, value = top_langs[0]
        parts.append(f'<text x="450" y="672" text-anchor="middle" font-size="24" font-weight="800" fill="url(#numfill)">{round(value / lang_total * 100)}%</text>')
        parts.append(f'<text x="450" y="690" text-anchor="middle" font-size="12" fill="{MUTED}">{html.escape(name)}</text>')
    # repos panel
    parts += [
        '<rect x="610" y="526" width="550" height="250" rx="20" fill="#FFFFFF" fill-opacity="0.04" stroke="#FFFFFF" stroke-opacity="0.09"/>',
        f'<text x="638" y="566" font-size="17" font-weight="700" fill="{TEXT}">Top repositories</text>',
    ]
    for i, repo in enumerate(top_repos):
        y = 604 + i * 31
        name = repo.get("name", "")
        lang = repo.get("language") or ""
        stars = repo.get("stargazers_count", 0)
        parts.append(f'<circle cx="644" cy="{y}" r="5" fill="{LANG_COLORS.get(lang, FALLBACK_LANG)}"/>')
        parts.append(f'<text x="662" y="{y + 5}" font-size="14" fill="{TEXT}">{html.escape(name)}</text>')
        parts.append(f'<text x="872" y="{y + 5}" text-anchor="end" font-size="14" font-weight="600" fill="{MUTED}">★ {stars}</text>')
    parts += ["</g>", "</svg>"]
    return "".join(parts)


# ---------------------------------------------------------------- spent my time

EDITOR_CODE = [
    (
        "app.py",
        [
            [("", "@router.post"), ("", '("/posts")')],
            [("", "async def "), ("f", "publish"), ("", "(body: Post):")],
            [("", "    await "), ("f", "queue.enqueue"), ("", "(body)")],
            [("", "    return "), ("", '{"status": "queued"}')],
        ],
        "Route live, 360 tests passing",
        CYAN,
    ),
    (
        "repo.py",
        [
            [("", "rows = await "), ("f", "db.fetch"), ("", "(")],
            [("s", '    "SELECT id FROM posts'), ("s", '"')],
            [("s", '    " WHERE due < $1", '), ("n", "now()")],
            [("", ")")],
        ],
        "Due posts picked up",
        VIOLET,
    ),
    (
        "soroban.py",
        [
            [("", "info = await "), ("f", "rpc.inspect"), ("", "(cid)")],
            [("k", "assert"), ("", " info.upgrade_safe")],
            [("", "print(info."), ("f", "interface"), ("", ")")],
            [("", "# XDR decoded")],
        ],
        "Contract verified",
        BLUE,
    ),
]


def render_time(days: list[dict]) -> str:
    width, height = 1600, 640
    # last 26 weeks of real contributions
    by_date = {d["date"]: int(d["count"]) for d in days}
    today = dt.date.today()
    end = today
    cells: list[list[tuple[str, int]]] = []
    for w in range(25, -1, -1):
        col = []
        for weekday in range(7):
            date = end - dt.timedelta(days=w * 7 + (6 - weekday))
            col.append((date.isoformat(), by_date.get(date.isoformat(), 0)))
        cells.append(col)
    flat = [c for col in cells for _, c in col]
    hi = max(flat) or 1

    months: list[tuple[int, str]] = []
    seen = set()
    for i, col in enumerate(cells):
        m = dt.date.fromisoformat(col[0][0]).strftime("%b")
        if m not in seen:
            seen.add(m)
            months.append((i, m))

    css = [
        ".sans{font-family:Inter,'Segoe UI','Helvetica Neue',Arial,sans-serif}",
        ".mono{font-family:'JetBrains Mono','SFMono-Regular',Consolas,Menlo,monospace}",
        ".code{font-size:21px;fill:#D6DEEB}",
        ".k{fill:#FF7AC6}.s{fill:#8FE3A1}.f{fill:#7CC4FF}.n{fill:#FFB84D}.c{fill:#8A97B5}",
        "@keyframes wave{0%{opacity:.8;transform:scale(1)}4%{opacity:1;transform:scale(1.14)}12%{opacity:.9;transform:scale(1)}30%,100%{opacity:.8;transform:scale(1)}}",
        ".cell{transform-box:fill-box;transform-origin:center;animation:wave 12s ease-in-out infinite;opacity:.8}",
        "@keyframes rise{0%{opacity:0;transform:translateY(0)}20%{opacity:.85}75%{opacity:.5}100%{opacity:0;transform:translateY(-150px)}}",
        ".bit{animation:rise 8s ease-in infinite;opacity:0}",
        "@media (prefers-reduced-motion:reduce){.cell,.bit{animation:none}}",
        "@keyframes blink{0%,49%{opacity:.9}50%,100%{opacity:0}}",
    ]
    css.append("@keyframes phase{0%{opacity:0}.5%{opacity:1}31.5%{opacity:1}33.33%{opacity:0}100%{opacity:0}}")
    css.append(".phase{animation:phase 12s linear infinite both}")
    css.append("@keyframes note{0%{opacity:0}15%{opacity:0}18%{opacity:1}31.5%{opacity:1}33.33%{opacity:0}100%{opacity:0}}")
    css.append(".note{animation:note 12s linear infinite both}")
    for p, (_, lines, _, _) in enumerate(EDITOR_CODE):
        for li, segs in enumerate(lines):
            w = sum(len(text) for _, text in segs) * 13.2
            start = round(p * 100 / 3 + 2 + li * 2, 2)
            css.append(
                f"@keyframes t{p}_{li}{{0%{{width:0}}{start}%{{width:0}}"
                f"{round(start + 3, 2)}%{{width:{w:.1f}px}}100%{{width:{w:.1f}px}}}}"
            )

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Spent My Time">',
        "<title>Spent My Time</title>",
        "<desc>An animated view of building APIs, working with data and inspecting Stellar contracts.</desc>",
        "<defs>",
        "<style>" + "".join(css) + "</style>",
        f'<pattern id="dots" width="32" height="32" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1.2" fill="#1A2542"/></pattern>',
        f'<radialGradient id="gA" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="{CYAN}" stop-opacity=".16"/><stop offset="1" stop-color="{CYAN}" stop-opacity="0"/></radialGradient>',
        f'<radialGradient id="gB" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="{VIOLET}" stop-opacity=".16"/><stop offset="1" stop-color="{VIOLET}" stop-opacity="0"/></radialGradient>',
        f'<linearGradient id="gBase" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2A3958"/><stop offset="1" stop-color="#172238"/></linearGradient>',
        '<filter id="blur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="28"/></filter>',
        '<filter id="soft" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="7"/></filter>',
        '<clipPath id="frame"><rect width="1600" height="640" rx="28"/></clipPath>',
        '<clipPath id="screen"><rect x="108" y="226" width="416" height="272" rx="10"/></clipPath>',
        "</defs>",
        '<g clip-path="url(#frame)"><rect width="1600" height="640" fill="#0A0F1E"/>'
        '<rect width="1600" height="640" fill="url(#dots)"/>'
        '<ellipse cx="180" cy="120" rx="560" ry="360" fill="url(#gA)"/>'
        '<ellipse cx="1480" cy="860" rx="620" ry="380" fill="url(#gB)"/></g>',
        '<rect x=".5" y=".5" width="1599" height="639" rx="28" fill="none" stroke="#1F2B47"/>',
        f'<text class="sans" x="56" y="112" font-size="56" font-weight="700" fill="{TEXT}" letter-spacing="-1">Spent My Time</text>',
        f'<text class="sans" x="56" y="154" font-size="26" fill="#8A97B5">Building APIs, shaping data and inspecting Stellar contracts.</text>',
    ]
    legend = [("API", CYAN, 1008), ("Data", VIOLET, 1180), ("Soroban", BLUE, 1360)]
    for label, color, x in legend:
        parts.append(f'<circle cx="{x}" cy="98" r="8" fill="{color}"/>')
        parts.append(f'<text class="sans" x="{x + 18}" y="106" font-size="24" fill="{TEXT}">{label}</text>')

    # floating bits
    for i, (x, y, color) in enumerate(
        [(64, 430, CYAN), (84, 300, VIOLET), (554, 470, BLUE), (566, 360, CYAN), (72, 520, VIOLET), (548, 250, CYAN)]
    ):
        parts.append(
            f'<rect class="bit" x="{x}" y="{y}" width="8" height="8" rx="2" fill="{color}" style="animation-delay:-{i * 1.2:.1f}s"/>'
        )

    # monitor
    parts += [
        '<g transform="translate(0,30)">',
        f'<ellipse cx="316" cy="370" rx="250" ry="170" fill="{CYAN}" opacity="0" filter="url(#blur)"><animate attributeName="opacity" values="0;0.3;0.3;0;0" keyTimes="0;0.012;0.3213;0.3333;1" dur="12s" repeatCount="indefinite"/></ellipse>',
        f'<ellipse cx="316" cy="370" rx="250" ry="170" fill="{VIOLET}" opacity="0" filter="url(#blur)"><animate attributeName="opacity" values="0;0;0.3;0.3;0;0" keyTimes="0;0.3333;0.3453;0.6547;0.6667;1" dur="12s" repeatCount="indefinite"/></ellipse>',
        f'<ellipse cx="316" cy="370" rx="250" ry="170" fill="{BLUE}" opacity="0" filter="url(#blur)"><animate attributeName="opacity" values="0;0;0.3;0.3;0" keyTimes="0;0.6667;0.6787;0.988;1" dur="12s" repeatCount="indefinite"/></ellipse>',
        '<ellipse cx="316" cy="556" rx="260" ry="12" fill="#000" opacity=".45" filter="url(#soft)"/>',
        '<rect x="96" y="214" width="440" height="296" rx="20" fill="#182338" stroke="#2C3D62" stroke-width="2"/>',
        '<rect x="108" y="226" width="416" height="272" rx="10" fill="#0B1222"/>',
        '<g clip-path="url(#screen)">',
        '<rect x="108" y="226" width="416" height="36" fill="#101A2F"/>',
        '<rect x="108" y="261" width="416" height="1" fill="#1F2B47"/>',
        f'<circle cx="128" cy="244" r="5" fill="{CYAN}"/><circle cx="146" cy="244" r="5" fill="{VIOLET}"/><circle cx="164" cy="244" r="5" fill="{BLUE}"/>',
        '<rect x="108" y="462" width="416" height="36" fill="#101A2F"/>',
        '<rect x="108" y="462" width="416" height="1" fill="#1F2B47"/>',
    ]

    # three 4s phases inside a 12s loop (CSS so every renderer agrees)
    char_w = 13.2
    for p, (tab, lines, note, color) in enumerate(EDITOR_CODE):
        parts.append(f'<g class="phase" opacity="{1 if p == 0 else 0}" style="animation-delay:-{p * 4}s">')
        parts.append(
            f'<rect x="184" y="259" width="{18 + len(tab) * 11}" height="3" fill="{color}"/>'
        )
        parts.append(
            f'<text class="mono" x="190" y="251" font-size="18" fill="{TEXT}">{tab}</text>'
        )
        for li, segs in enumerate(lines):
            y = 304 + li * 36
            line_y = y - 24
            width_px = sum(len(text) for _, text in segs) * char_w
            parts.append(
                f'<clipPath id="cl{p}{li}"><rect x="126" y="{line_y}" width="{width_px:.1f}" height="32" '
                f'style="animation:t{p}_{li} 12s linear infinite both"/></clipPath>'
            )
            body = "".join(
                f'<tspan class="{cls}">{html.escape(text)}</tspan>' if cls else f"<tspan>{html.escape(text)}</tspan>"
                for cls, text in segs
            )
            parts.append(
                f'<text class="mono code" x="128" y="{y}" clip-path="url(#cl{p}{li})" xml:space="preserve">{body}</text>'
            )
        last_y = 304 + (len(lines) - 1) * 36
        caret_x = 128 + sum(len(t) for _, t in lines[-1]) * char_w
        parts.append(
            f'<rect x="{caret_x:.1f}" y="{last_y - 19}" width="9" height="24" fill="{color}" '
            f'opacity="0" style="animation:blink 1s step-end infinite;animation-delay:{p * 4 + 1.2:.1f}s"/>'
        )
        parts.append(
            f'<g class="note" style="animation-delay:-{p * 4}s">'
            f'<text class="sans" x="150" y="486" font-size="19" fill="{TEXT}">{note}</text>'
            f'<path d="M127.5 480.5l3.2 3.2 6-6.6" fill="none" stroke="{color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<circle cx="132" cy="480" r="9" fill="{color}" opacity=".18"/></g>'
        )
        parts.append("</g>")
    parts += [
        "</g>",
        '<path d="M74 510 H558 L586 536 Q588 540 583 540 H49 Q44 540 46 536 Z" fill="url(#gBase)" stroke="#2C3D62" stroke-width="1.5" stroke-linejoin="round"/>',
        '<rect x="266" y="510" width="100" height="9" rx="4.5" fill="#0E1729"/>',
        "</g>",
    ]

    # heatmap
    parts += [
        f'<text class="sans" x="620" y="224" font-size="28" font-weight="600" fill="{TEXT}">Daily contributions</text>',
        '<text class="sans" x="1544" y="222" font-size="20" fill="#8A97B5" text-anchor="end">More</text>',
        '<text class="sans" x="1352" y="222" font-size="20" fill="#8A97B5" text-anchor="end">Less</text>',
        '<rect x="1362" y="207" width="18" height="18" rx="4" fill="#17213A"/>',
    ]
    for i, opacity in enumerate((0.29, 0.45, 0.61, 0.75)):
        parts.append(f'<rect x="{1386 + i * 24}" y="207" width="18" height="18" rx="4" fill="{CYAN}" fill-opacity="{opacity}"/>')
    for i, month in months:
        parts.append(f'<text class="sans" x="{698 + i * 34}" y="266" font-size="20" fill="#8A97B5">{month}</text>')
    for row, label in ((0, "Mon"), (2, "Wed"), (4, "Fri")):
        parts.append(f'<text class="sans" x="620" y="{337 + row * 34}" font-size="20" fill="#8A97B5">{label}</text>')

    for i, col in enumerate(cells):
        for j, (_, count) in enumerate(col):
            if count == 0:
                parts.append(f'<rect x="{698 + i * 34}" y="{282 + j * 34}" width="28" height="28" rx="6" fill="#17213A"/>')
                continue
            level = min(1.0, 0.35 + 0.65 * (count / hi))
            parts.append(
                f'<rect class="cell" x="{698 + i * 34}" y="{282 + j * 34}" width="28" height="28" rx="6" '
                f'fill="{CYAN}" fill-opacity="{level:.2f}" style="animation-delay:{i * 0.48:.2f}s"/>'
            )
    parts.append("</svg>")
    return "".join(parts)


def main() -> int:
    user = sys.argv[1] if len(sys.argv) > 1 else "Ayinkx"
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("profile")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    try:
        days = fetch_calendar(user)
        if not days:
            raise RuntimeError("no contribution data")
        stats = streaks(days)

        weekday_totals = Counter()
        for d in days:
            weekday_totals[dt.date.fromisoformat(d["date"]).strftime("%a")] += int(d["count"])
        order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        weekday = [(day, weekday_totals[day]) for day in order]

        langs: list[tuple[str, int]] = []
        repos: list[dict] = []
        try:
            repos = fetch_repos(user, token)
            totals = language_bytes(repos, token)
            langs = totals.most_common(6)
        except Exception as exc:  # noqa: BLE001 - language panel is optional
            print(f"language data skipped: {exc}", file=sys.stderr)

        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "github-stats.svg").write_text(
            render_stats(stats, weekday, langs, [r for r in repos if not r.get("fork")]),
            encoding="utf-8",
        )
        (out_dir / "spent-my-time.svg").write_text(render_time(days), encoding="utf-8")
        print(
            f"wrote stats + time cards: total={stats['total']} "
            f"current={stats['current']} longest={stats['longest']} langs={len(langs)}"
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - never fail the profile workflow
        print(f"animated cards skipped: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
