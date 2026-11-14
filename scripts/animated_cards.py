"""Render the animated GitHub stats and Spent My Time cards.

Layout mirrors the shahidazam2020-oss cards pixel for pixel; every number,
label and language comes from the live GitHub API for the given user.

    python scripts/animated_cards.py <user> <out_dir>

Standard library only. Any failure exits 0 so the workflow never breaks.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

BLUE = "#0E75B6"
CYAN = "#00F7FF"
VIOLET = "#7C3AED"
TEXT = "#E8ECF8"
MUTED = "#8B94B3"
BG = "#0A0F1E"
STAGE = (CYAN, BLUE, VIOLET)
STAGE_NAMES = ("APIs", "Data", "Soroban")
PALETTE = (BLUE, CYAN, VIOLET, "#2DD4BF", "#FFB84D")
FONT = "'Segoe UI Variable Display','Segoe UI','SF Pro Display',Inter,system-ui,-apple-system,Roboto,'Helvetica Neue',Arial,sans-serif"
MONO = "'JetBrains Mono','SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace"
UA = {"User-Agent": "ayinkx-profile-cards", "Accept": "application/vnd.github+json"}
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def get_json(url):
    headers = dict(UA)
    if TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def paged(url):
    out, page = [], 1
    while True:
        chunk = get_json(url + ("&" if "?" in url else "?") + "per_page=100&page=%d" % page)
        if not isinstance(chunk, list) or not chunk:
            return out
        out += chunk
        if len(chunk) < 100:
            return out
        page += 1


def daily_counts(user):
    data = get_json("https://github-contributions-api.jogruber.de/v4/%s?y=last" % user)
    days = data.get("contributions") or []
    return {d["date"]: int(d["count"]) for d in days}


def streaks(days):
    total = sum(days.values())
    cur, longest, run, prev = 0, 0, 0, None
    for iso in sorted(days):
        d = date.fromisoformat(iso)
        c = days[iso]
        if c > 0:
            run = run + 1 if prev == d - timedelta(days=1) else 1
            longest = max(longest, run)
        else:
            run = 0
        prev = d
    # A streak stays alive until a full day is missed, so an empty today
    # continues the run ending yesterday (and covers API lag).
    cur = 0
    if days:
        d = date.fromisoformat(max(days))
        if days[d.isoformat()] == 0:
            d -= timedelta(days=1)
        while days.get(d.isoformat(), 0) > 0:
            cur += 1
            d -= timedelta(days=1)
    return total, cur, longest


_demo = {"2026-11-12": 1, "2026-11-13": 2, "2026-11-14": 0}
assert streaks(_demo)[1] == 2, "an empty today must keep yesterday's streak alive"


def area_of(lang):
    low = lang.lower()
    if "rust" in low or "soroban" in low:
        return 2
    if any(t in low for t in ("typescript", "javascript", "html", "css", "jupyter")):
        return 1
    return 0


def gathering(user, days):
    """Commits, languages and the repo list backing both cards."""
    repos = [r for r in paged("https://api.github.com/users/%s/repos?type=owner&sort=pushed" % user)
             if not r.get("fork")]
    since = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
    langs, page = {}, {}
    for r in repos:
        try:
            page[r["full_name"]] = get_json(r["url"] + "/languages")
        except Exception:
            page[r["full_name"]] = {}
    byte_totals = {}
    for r in repos:
        for name, n in page[r["full_name"]].items():
            byte_totals[name] = byte_totals.get(name, 0) + n
    order = sorted(byte_totals, key=byte_totals.get, reverse=True)
    repo_top = [(name, byte_totals[name]) for name in order[:5]]

    hours = [0] * 24
    by_day = {}
    commit_langs = {}
    commit_repos = []
    for r in repos[:20]:
        lang = max(page[r["full_name"]], key=page[r["full_name"]].get) if page[r["full_name"]] else "Other"
        try:
            commits = get_json("%s/commits?author=%s&per_page=100&since=%s"
                               % (r["url"], user, since))
        except Exception:
            commits = []
        if not commits:
            continue
        commit_repos.append((r["name"], len(commits), r.get("stargazers_count", 0), lang))
        commit_langs[lang] = commit_langs.get(lang, 0) + len(commits)
        for c in commits:
            stamp = ((c.get("commit") or {}).get("committer") or {}).get("date", "")
            if not stamp:
                continue
            dt = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
            hours[dt.hour] += 1
            iso = dt.date().isoformat()
            by_day.setdefault(iso, {})[lang] = by_day.setdefault(iso, {}).get(lang, 0) + 1

    if not commit_langs:
        commit_langs = dict(byte_totals)
    commit_top = sorted(commit_langs.items(), key=lambda kv: kv[1], reverse=True)[:5]
    return dict(repo_top=repo_top, commit_top=commit_top, hours=hours,
                by_day=by_day, commits=commit_repos, days=days)


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def short_date(d):
    return "%s %d" % (d.strftime("%b"), d.day)


def pct_list(items, key):
    total = sum(v for _, v in items) or 1
    out, acc = [], 0
    for i, (name, v) in enumerate(items):
        p = int(round(v * 100.0 / total))
        acc += p
        out.append((name, max(p, 0), PALETTE[i % len(PALETTE)]))
    if out:
        name, p, col = out[0]
        out[0] = (name, p + (100 - min(acc, 100)), col)
    return out


def digits(value, cx0, base, size, xstep, ystep, cls, css, clip_y, clip_h):
    clip_x = cx0 - xstep / 2.0 - 4
    clip_w = len(str(value)) * xstep + 8
    s = str(value)
    parts = ['<clipPath id="%s"><rect x="%.1f" y="%.1f" width="%.1f" height="%.1f"/></clipPath>'
             % (cls, clip_x, clip_y, clip_w, clip_h)]
    parts.append('<g clip-path="url(#%s)">' % cls)
    for i, ch in enumerate(s):
        d = int(ch)
        name = "%s_%d" % (cls, i)
        start = round(3.571 + i * 0.857, 3)
        end = round(start + 12.143, 3)
        css.append("@keyframes %s{0%%,%.3f%%{transform:translateY(0px);animation-timing-function:cubic-bezier(.2,.8,.2,1)}%.3f%%,100%%{transform:translateY(-%.1fpx)}}"
                   % (name, start, end, ystep * (10 + d)))
        parts.append('<g style="animation:%s 14.0s infinite;transform:translateY(-%.1fpx)">' % (name, ystep * (10 + d)))
        for n in range(20):
            parts.append('<text x="%.1f" y="%.1f" text-anchor="middle" font-size="%d" font-weight="800" '
                         'fill="url(#numfill)">%d</text>' % (cx0 + i * xstep, base + ystep * n, size, n % 10))
        parts.append("</g>")
    parts.append("</g>")
    return "\n".join(parts)


def donut(cx, cy, rows, kf_id, css):
    circ = 427.26
    out = ['<circle cx="%d" cy="%d" r="68" fill="none" stroke="#FFFFFF" stroke-opacity="0.06" stroke-width="26"/>' % (cx, cy)]
    offset = 0.0
    for i, (name, pct, col) in enumerate(rows):
        length = max(pct / 100.0 * circ - 3, 0.5)
        name_k = "%s_%d" % (kf_id, i)
        css.append("@keyframes %s{0%%,%.3f%%{stroke-dasharray:0 427.26;animation-timing-function:cubic-bezier(.2,.8,.2,1)}%.3f%%,100%%{stroke-dasharray:%.2f 427.26}}"
                   % (name_k, 17.143 + i * 1.2, 20.0 + i * 1.2, length))
        out.append('<circle cx="%d" cy="%d" r="68" fill="none" stroke="%s" stroke-width="26" '
                   'stroke-dasharray="%.2f 427.26" stroke-dashoffset="-%.2f" transform="rotate(-90 %d %d)" '
                   'style="animation:%s 14.0s infinite"/>'
                   % (cx, cy, col, length, offset + 1.5, cx, cy, name_k))
        offset += pct / 100.0 * circ
    top = rows[0] if rows else ("", 0, MUTED)
    css_name = kf_id + "_c"
    css.append("@keyframes %s{0%%,17.143%%{opacity:0;animation-timing-function:ease}20.0%%,100%%{opacity:1}}" % css_name)
    out.append('<g style="animation:%s 14.0s infinite"><text x="%d" y="672" text-anchor="middle" font-size="24" '
               'font-weight="800" fill="url(#numfill)">%d%%</text><text x="%d" y="690" text-anchor="middle" '
               'font-size="12" fill="%s">%s</text></g>'
               % (css_name, cx, top[1], cx, MUTED, esc(top[0])))
    return "\n".join(out)


def render_stats(user, data):
    days = data["days"]
    total, cur, longest = streaks(days)
    iso = sorted(days)
    first = iso[0] if iso else date.today().isoformat()
    today = date.today()
    fd = date.fromisoformat(first)
    window = "%s %d, %d to present" % (fd.strftime("%b"), fd.day, fd.year)
    cur_start = None
    if cur:
        last = date.fromisoformat(max(days))
        if days[last.isoformat()] == 0:
            last -= timedelta(days=1)
        cur_start = last - timedelta(days=cur - 1)
    cur_txt = ("%s to %s" % (short_date(cur_start), short_date(last))) if cur_start else "No active streak"
    css = []
    body = []
    body.append('<text x="40" y="54" font-size="27" font-weight="800" fill="%s" letter-spacing="-0.4">GitHub stats</text>' % TEXT)
    body.append('<text x="40" y="78" font-size="14" fill="%s">Lawal Olayinka Awal (Ayinkx), Backend Engineer</text>' % MUTED)

    # total contributions tile
    body.append('<rect x="40" y="96" width="300" height="190" rx="20" fill="#FFFFFF" fill-opacity="0.04" stroke="#FFFFFF" stroke-opacity="0.09"/>')
    body.append('<text x="68" y="138" font-size="15" font-weight="600" fill="%s">Total contributions</text>' % MUTED)
    body.append(digits(total, 90.5, 218.0, 72, 45, 100.8, "c1", css, 156.1, 80.6))
    body.append('<text x="68" y="260" font-size="13" font-weight="600" fill="%s">%s</text>' % (CYAN, window))

    # current streak tile
    body.append('<rect x="360" y="96" width="480" height="190" rx="20" fill="#FFFFFF" fill-opacity="0.04" stroke="url(#tileEdge)" stroke-width="1.4"/>')
    circ = 389.56
    pct = min(cur / 100.0, 1.0)
    css.append("@keyframes ring{0%%,4.643%%{stroke-dashoffset:389.56;animation-timing-function:cubic-bezier(.2,.8,.2,1)}16.786%%,100%%{stroke-dashoffset:%.2f}}" % (circ * (1 - pct)))
    body.append('<circle cx="472" cy="191" r="62" fill="none" stroke="#FFFFFF" stroke-opacity="0.1" stroke-width="10"/>')
    body.append('<circle cx="472" cy="191" r="62" fill="none" stroke="url(#ring)" stroke-width="10" stroke-linecap="round" stroke-dasharray="389.56" stroke-dashoffset="%.2f" transform="rotate(-90 472 191)" filter="url(#glow)" style="animation:ring 14.0s infinite"/>' % (circ * (1 - pct)))
    css.append("@keyframes orbit{0%,17.143%{opacity:0;animation-timing-function:ease}20.0%,100%{opacity:1}}")
    body.append('<circle class="dot" r="3.5" fill="#FFFFFF" style="animation:orbit 14.0s infinite;opacity:1"><animateMotion dur="6s" repeatCount="indefinite" path="M 472,129 A 62,62 0 1,1 471.99,129"/></circle>')
    small = digits(cur, 457.5, 207.0, 46, 29, 64.4, "c6", css, 167.4, 51.5)
    body.append(small)
    body.append('<text x="472" y="229" text-anchor="middle" font-size="12" font-weight="600" fill="%s">days</text>' % MUTED)
    body.append('<text x="574" y="174" font-size="19" font-weight="700" fill="%s">Current streak</text>' % TEXT)
    body.append('<text x="574" y="200" font-size="14" fill="%s" font-weight="600">%s</text>' % (CYAN, cur_txt))
    note = "Matches the longest streak" if cur >= longest else "%d days to match the longest" % max(longest - cur, 0)
    body.append('<text x="574" y="228" font-size="13" fill="%s">%s</text>' % (MUTED, note))

    # longest streak tile
    body.append('<rect x="860" y="96" width="300" height="190" rx="20" fill="#FFFFFF" fill-opacity="0.04" stroke="#FFFFFF" stroke-opacity="0.09"/>')
    body.append('<text x="888" y="138" font-size="15" font-weight="600" fill="%s">Longest streak</text>' % MUTED)
    ln = len(str(longest))
    body.append(digits(longest, 910.5, 218.0, 72, 45, 100.8, "c8", css, 156.1, 80.6))
    body.append('<text x="988" y="218" font-size="20" font-weight="600" fill="%s">days</text>' % MUTED)
    body.append('<text x="888" y="260" font-size="13" font-weight="600" fill="%s">%s</text>' % (CYAN, cur_txt if longest == cur else "%d day best" % longest))

    # commits by hour
    hours = data["hours"]
    peak = max(range(24), key=lambda h: hours[h]) if any(hours) else 0
    top_h = max(hours) or 1
    tick = max(1, -(-top_h // 5) * 5)
    body.append('<rect x="40" y="306" width="1120" height="200" rx="20" fill="#FFFFFF" fill-opacity="0.04" stroke="#FFFFFF" stroke-opacity="0.09"/>')
    body.append('<text x="68" y="344" font-size="17" font-weight="700" fill="%s">Commits by hour</text>' % TEXT)
    body.append('<text x="1132" y="344" text-anchor="end" font-size="13" fill="%s">UTC</text>' % MUTED)
    for i, y in enumerate((472.0, 446.0, 420.0, 394.0)):
        body.append('<line x1="100" y1="%.1f" x2="1132" y2="%.1f" stroke="#FFFFFF" stroke-opacity="%s"/>' % (y, y, "0.16" if i == 0 else "0.06"))
        body.append('<text x="90" y="%.1f" text-anchor="end" font-size="11" fill="%s">%d</text>' % (y + 4, MUTED, tick * i // 3))
    for i in range(24):
        h = hours[i]
        height = max(2.6, 78.0 * h / tick)
        x = 112.4 + i * 42.85
        col = "barPeak" if abs(i - peak) <= 1 else "bar"
        name = "bar%d" % i
        start = 10.714 + i * 0.286
        css.append("@keyframes %s{0%%,%.3f%%{transform:scaleY(0);animation-timing-function:cubic-bezier(.2,.8,.2,1)}%.3f%%,100%%{transform:scaleY(1)}}" % (name, start, start + 5.0))
        body.append('<rect class="b" x="%.1f" y="%.1f" width="26" height="%.1f" rx="5" fill="url(#%s)" style="animation:%s 14.0s infinite"/>'
                    % (x, 472.0 - height, height, col, name))
    peak_x = 112.4 + peak * 42.85
    box_x = min(max(peak_x - 48, 100), 1132 - 122.5)
    css.append("@keyframes peak{0%,18.571%{opacity:0;animation-timing-function:ease}22.857%,100%{opacity:1}}")
    body.append('<g style="animation:peak 14.0s infinite"><rect x="%.1f" y="358" width="122.5" height="118.0" rx="10" fill="%s" fill-opacity="0.08"/>'
                '<text x="%.1f" y="374" text-anchor="middle" font-size="12" font-weight="600" fill="%s">Peak hours</text></g>'
                % (box_x, CYAN, box_x + 61.25, CYAN))
    for i in range(0, 24, 3):
        body.append('<text x="%.1f" y="492" text-anchor="middle" font-size="11" fill="%s">%02d</text>' % (125.4 + i * 42.85, MUTED, i))
    body.append('<text x="%.1f" y="492" text-anchor="middle" font-size="11" fill="%s">23</text>' % (125.4 + 23 * 42.85, MUTED))

    # language panels
    repo_rows = pct_list(data["repo_top"], 1)
    commit_rows = pct_list(data["commit_top"], 1)
    for side, title, rows, kx in (
        (0, "Top languages by repository", repo_rows, 40),
        (1, "Top languages by commit", commit_rows, 610),
    ):
        body.append('<rect x="%d" y="526" width="550" height="250" rx="20" fill="#FFFFFF" fill-opacity="0.04" stroke="#FFFFFF" stroke-opacity="0.09"/>' % kx)
        body.append('<text x="%d" y="566" font-size="17" font-weight="700" fill="%s">%s</text>' % (kx + 28, TEXT, title))
        for i, (name, p, col) in enumerate(rows[:5]):
            y = 611 + i * 31
            body.append('<circle cx="%d" cy="%d" r="5" fill="%s"/>' % (kx + 34, y, col))
            body.append('<text x="%d" y="%d" font-size="14" fill="%s">%s</text>' % (kx + 52, y + 5, TEXT, esc(name)))
            body.append('<text x="%d" y="%d" text-anchor="end" font-size="14" font-weight="600" fill="%s">%d%%</text>' % (kx + 262, y + 5, MUTED, p))
        body.append(donut(kx + 410, 668, rows[:5], "d%d" % side, css))

    aria = "GitHub stats for %s: %d contributions, current streak %d days, longest streak %d days." % (user, total, cur, longest)
    return page(1200, 800, aria,
                'Total contributions, current and longest streak, commits by hour, and top languages by repository and by commit.',
                css, body)


def page(w, h, title, desc, css, body):
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" role="img" aria-labelledby="t d">
<title id="t">%s</title>
<desc id="d">%s</desc>
<style>
text{font-family:%s;font-variant-numeric:tabular-nums}
.b{transform-box:fill-box;transform-origin:50%% 100%%}
#content{animation:master 14.0s infinite}
@keyframes master{0%%{opacity:0}3%%{opacity:1}93%%{opacity:1}97%%{opacity:0}100%%{opacity:0}}
%s
@media (prefers-reduced-motion:reduce){*{animation:none!important}.dot{display:none}}
</style>
%s
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0A0F1F"/><stop offset="1" stop-color="#0F1530"/></linearGradient>
  <radialGradient id="glowA" cx="0.12" cy="0.05" r="0.55"><stop offset="0" stop-color="%s" stop-opacity="0.26"/><stop offset="1" stop-color="%s" stop-opacity="0"/></radialGradient>
  <radialGradient id="glowB" cx="0.92" cy="0.98" r="0.5"><stop offset="0" stop-color="%s" stop-opacity="0.2"/><stop offset="1" stop-color="%s" stop-opacity="0"/></radialGradient>
  <pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="#FFFFFF" fill-opacity="0.055"/></pattern>
  <linearGradient id="numfill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#C9D2F5"/></linearGradient>
  <linearGradient id="ring" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="%s"/><stop offset="0.55" stop-color="%s"/><stop offset="1" stop-color="%s"/></linearGradient>
  <linearGradient id="bar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="%s"/><stop offset="1" stop-color="%s" stop-opacity="0.75"/></linearGradient>
  <linearGradient id="barPeak" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="%s"/><stop offset="1" stop-color="%s"/></linearGradient>
  <linearGradient id="tileEdge" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="%s" stop-opacity="0.55"/><stop offset="0.5" stop-color="%s" stop-opacity="0.35"/><stop offset="1" stop-color="%s" stop-opacity="0.55"/></linearGradient>
  <filter id="glow" x="-30%%" y="-30%%" width="160%%" height="160%%"><feGaussianBlur stdDeviation="5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <clipPath id="frame"><rect width="%d" height="%d" rx="28"/></clipPath>
</defs>
<g clip-path="url(#frame)">
  <rect width="%d" height="%d" fill="url(#bg)"/>
  <rect width="%d" height="%d" fill="url(#dots)"/>
  <rect width="%d" height="%d" fill="url(#glowA)"/>
  <rect width="%d" height="%d" fill="url(#glowB)"/>
</g>
<rect x="0.5" y="0.5" width="%d" height="%d" rx="28" fill="none" stroke="#FFFFFF" stroke-opacity="0.08"/>
<g id="content">
%s
</g>
</svg>
""" % (w, h, w, h, esc(title), esc(desc), FONT, "\n".join(css), "", VIOLET, VIOLET, CYAN, CYAN,
       CYAN, BLUE, VIOLET, CYAN, BLUE, CYAN, VIOLET, CYAN, BLUE, VIOLET,
       w, h, w, h, w, h, w, h, w, h, w - 1, h - 1, "\n".join(body))


# ---------------------------------------------------------------- spent my time

PHASES = [
    dict(tab="app.py", accent=CYAN, note="Routes published", board="Backend APIs",
         desc=("FastAPI routes, auth, validation", "and Postgres queries"),
         lines=[
             [(" ", ""), ("@router", "f"), (".", ""), ("post", "f"), ('("/publish")', "s")],
             [(" ", ""), ("async", "k"), (" ", ""), ("def", "k"), (" publish", ""), ("(post, db):", "")],
             [("    ", ""), ("await", "k"), (" db.", ""), ("execute", "f"), ("(stmt)", "")],
             [("    ", ""), ("await", "k"), (" db.", ""), ("commit", "f"), ("()", "")],
             [("    ", ""), ("return", "k"), (' {"ok": ', ""), ('"queued"', "s"), ("}", "")],
         ]),
    dict(tab="repo.py", accent=BLUE, note="Posts queued", board="Data pipelines",
         desc=("Queue workers, migrations and", "scheduled reporting"),
         lines=[
             [(" ", ""), ("async", "k"), (" ", ""), ("def", "k"), (" due_posts", ""), ("(db):", "")],
             [("    ", ""), ("q", ""), (" = ", ""), ("select", "f"), ("(Post).", ""), ("where", "f"), ("(due)", "")],
             [("    ", ""), ("rows", ""), (" = ", ""), ("await", "k"), (" scalars(q)", "")],
             [("    ", ""), ("return", "k"), (" [r ", ""), ("for", "k"), (" r ", ""), ("in", "k"), (" rows]", "")],
             [("    ", ""), ("# ", "c"), ("batch of 100 per tick", "c")],
         ]),
    dict(tab="soroban.py", accent=VIOLET, note="Contract call safe", board="Stellar & Soroban",
         desc=("Contract calls, RPC events and", "safety checks"),
         lines=[
             [(" ", ""), ("rpc", ""), (" = ", ""), ("SorobanServer", "f"), ("(RPC_URL)", "")],
             [(" ", ""), ("tx", ""), (" = rpc.", ""), ("get_tx", "f"), ("(tx_hash)", "")],
             [(" ", ""), ("assert", "k"), (" tx.status == ", ""), ('"SUCCESS"', "s")],
             [(" ", ""), ("events", ""), (" = tx.", ""), ("events", "f"), ('("contract")', "s")],
             [("    ", ""), ("# ", "c"), ("wasm hash checked", "c")],
         ]),
]
CHAR_W = 12.8


def code_line(segments, pid, idx, accent, css):
    text = "".join(t for t, _ in segments)
    width = min(len(text) * CHAR_W, 388)
    t0 = 0.0375 + 0.05 * idx + pid / 3.0
    t1 = t0 + 0.0417
    clip = "cl%d%d" % (pid, idx)
    spans = "".join('<tspan class="%s">%s</tspan>' % (c, esc(t).replace(" ", "\u00a0")) if c else "<tspan>%s</tspan>" % esc(t).replace(" ", "\u00a0")
                    for t, c in segments)
    y = 304 + 36 * idx
    out = ['<clipPath id="%s"><rect x="126" y="%d" width="0" height="32"><animate attributeName="width" values="0;0;%.1f;%.1f" keyTimes="0;%.4f;%.4f;1" dur="12.0s" repeatCount="indefinite"/></rect></clipPath>'
           % (clip, y - 24, width, width, t0, t1),
           '<text class="mono code" x="128" y="%d" clip-path="url(#%s)" xml:space="preserve">%s</text>' % (y, clip, spans),
           '<rect x="128" y="%d" width="9" height="24" fill="%s" opacity="0"><animate attributeName="x" values="128;128;%.1f;%.1f" keyTimes="0;%.4f;%.4f;1" dur="12.0s" repeatCount="indefinite"/>'
           '<animate attributeName="opacity" values="0;0;.9;.9;0;0" keyTimes="0;%.4f;%.4f;%.4f;%.4f;1" dur="12.0s" repeatCount="indefinite"/></rect>'
           % (y - 19, accent, 128 + width, 128 + width, t0, t1, t0, t0 + 0.0017, t1, t1 + 0.0016)]
    return out


def render_time(user, data):
    days = data["days"]
    by_day = data["by_day"]
    areas = [0, 0, 0]
    for iso, langs in by_day.items():
        for lang, c in langs.items():
            areas[area_of(lang)] += c
    total = sum(areas) or 1
    shares = [int(round(a * 100.0 / total)) for a in areas]
    shares[0] += 100 - sum(shares)
    shares = [max(s, 1) for s in shares]
    shares[2] += 100 - sum(shares)

    # 26-week heatmap ending this week
    today = date.today()
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=24)
    weeks = 25
    cells = []
    month_x = {}
    for col in range(weeks):
        for row in range(7):
            d = start + timedelta(days=col * 7 + row)
            if d > today:
                cells.append((col, row, None))
                continue
            iso = d.isoformat()
            if d.day <= 7:
                month_x.setdefault(d.strftime("%b"), 698 + col * 34)
            cells.append((col, row, (iso, days.get(iso, 0), by_day.get(iso))))

    body = []
    body.append('<text class="sans" x="56" y="112" font-size="56" font-weight="700" fill="#E8EEF9" letter-spacing="-1">Spent My Time</text>')
    body.append('<text class="sans" x="56" y="154" font-size="26" fill="%s">Building APIs, moving data and shipping contracts, every day I code.</text>' % MUTED)
    for i, (name, col) in enumerate(zip(STAGE_NAMES, STAGE)):
        body.append('<circle cx="%d" cy="98" r="8" fill="%s"/>' % ((1008, 1172, 1400)[i], col))
        body.append('<text class="sans" x="%d" y="106" font-size="24" fill="#E8EEF9">%s</text>' % ((1026, 1190, 1418)[i], name))

    body.append('<g transform="translate(0,30)">')
    for i, phase in enumerate(PHASES):
        body.append('<ellipse cx="316" cy="370" rx="250" ry="170" fill="%s" opacity="0" filter="url(#blur)"><animate attributeName="opacity" values="%s" keyTimes="%s" dur="12.0s" repeatCount="indefinite"/></ellipse>'
                    % (phase["accent"],
                       ("0;0.34;0.34;0;0", "0;0;0.34;0.34;0;0", "0;0;0.34;0.34;0")[i],
                       ("0;0.012;0.3213;0.3333;1", "0;0.3333;0.3453;0.6547;0.6667;1", "0;0.6667;0.6787;0.988;1")[i]))
    bits = ((64, 430, CYAN, "0"), (84, 300, BLUE, "2.4"), (554, 470, VIOLET, "1.1"),
            (566, 360, CYAN, "4.2"), (72, 520, VIOLET, "5.1"), (548, 250, BLUE, "3.3"),
            (92, 210, VIOLET, "6.3"), (536, 540, BLUE, "7.2"))
    for x, y, col, delay in bits:
        body.append('<rect class="bit" x="%d" y="%d" width="8" height="8" rx="2" fill="%s" style="animation-delay:-%ss"/>' % (x, y, col, delay))
    body.append('<ellipse cx="316" cy="556" rx="260" ry="12" fill="#000" opacity=".45" filter="url(#soft)"/>')
    body.append('<rect x="96" y="214" width="440" height="296" rx="20" fill="#182338" stroke="#2C3D62" stroke-width="2"/>')
    body.append('<rect x="108" y="226" width="416" height="272" rx="10" fill="#0B1222"/>')
    body.append('<g clip-path="url(#screen)">')
    body.append('<rect x="108" y="226" width="416" height="36" fill="#101A2F"/>')
    body.append('<rect x="108" y="261" width="416" height="1" fill="#1F2B47"/>')
    for i, col in enumerate(STAGE):
        body.append('<circle cx="%d" cy="244" r="5" fill="%s"/>' % (128 + i * 18, col))
    keytimes = ("0;0.012;0.3213;0.3333;1", "0;0.3333;0.3453;0.6547;0.6667;1", "0;0.6667;0.6787;0.988;1")
    opac = ("0;1;1;0;0", "0;0;1;1;0;0", "0;0;1;1;0")
    for i, phase in enumerate(PHASES):
        body.append('<g opacity="0"><animate attributeName="opacity" values="%s" keyTimes="%s" dur="12.0s" repeatCount="indefinite"/>'
                    '<text class="mono" x="190" y="251" font-size="18" fill="#E8EEF9">%s</text>'
                    '<rect x="184" y="259" width="%d" height="3" fill="%s"/></g>'
                    % (opac[i], keytimes[i], phase["tab"], len(phase["tab"]) * 9, phase["accent"]))
        body.append('<g opacity="0"><animate attributeName="opacity" values="%s" keyTimes="%s" dur="12.0s" repeatCount="indefinite"/>'
                    % (opac[i], keytimes[i]))
        for j, line in enumerate(phase["lines"]):
            body += code_line(line, i, j, phase["accent"], None)
        note_at = 0.2917 + i / 3.0
        end_at = 0.3167 + i / 3.0
        body.append('<g><animate attributeName="opacity" values="0;0;1;1;0;0" keyTimes="0;%.4f;%.4f;%.4f;%.4f;1" dur="12.0s" repeatCount="indefinite"/>'
                    '<rect x="108" y="462" width="416" height="36" fill="#101A2F"/><rect x="108" y="462" width="416" height="1" fill="#1F2B47"/>'
                    '<circle cx="132" cy="480" r="9" fill="%s" opacity=".18"/>'
                    '<path d="M127.5 480.5l3.2 3.2 6-6.6" fill="none" stroke="%s" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'
                    '<text class="sans" x="150" y="486" font-size="19" fill="#E8EEF9">%s</text></g>'
                    % (note_at, end_at, end_at + 0.0046, 0.3333 + i / 3.0 if i < 2 else 0.988, phase["accent"], phase["accent"], phase["note"]))
        body.append("</g>")
    body.append("</g>")
    body.append('<path d="M74 510 H558 L586 536 Q588 540 583 540 H49 Q44 540 46 536 Z" fill="url(#gBase)" stroke="#2C3D62" stroke-width="1.5" stroke-linejoin="round"/>')
    body.append('<rect x="266" y="510" width="100" height="9" rx="4.5" fill="#0E1729"/>')
    body.append("</g>")

    body.append('<text class="sans" x="620" y="224" font-size="28" font-weight="600" fill="#E8EEF9">Daily contributions</text>')
    body.append('<text class="sans" x="1544" y="222" font-size="20" fill="%s" text-anchor="end">More</text>' % MUTED)
    body.append('<text class="sans" x="1352" y="222" font-size="20" fill="%s" text-anchor="end">Less</text>' % MUTED)
    body.append('<rect x="1362" y="207" width="18" height="18" rx="4" fill="#17213A"/>')
    for i, o in enumerate((0.29, 0.45, 0.61, 0.75)):
        body.append('<rect x="%d" y="207" width="18" height="18" rx="4" fill="#E8EEF9" fill-opacity="%s"/>' % (1386 + i * 24, o))
    for month, x in list(month_x.items())[:6]:
        body.append('<text class="sans" x="%d" y="266" font-size="20" fill="%s">%s</text>' % (x, MUTED, month))
    for label, y in (("Mon", 337), ("Wed", 405), ("Fri", 473)):
        body.append('<text class="sans" x="620" y="%d" font-size="20" fill="%s">%s</text>' % (y, MUTED, label))
    body.append("<g>")
    max_day = max(days.values()) if days else 1
    for col, row, cell in cells:
        x, y = 698 + col * 34, 282 + row * 34
        if not cell:
            body.append('<rect x="%d" y="%d" width="28" height="28" rx="6" fill="#17213A"/>' % (x, y))
            continue
        iso, count, langs = cell
        if count <= 0:
            body.append('<rect x="%d" y="%d" width="28" height="28" rx="6" fill="#17213A"/>' % (x, y))
            continue
        idx = 0
        if langs:
            buckets = [0, 0, 0]
            for lang, c in langs.items():
                buckets[area_of(lang)] += c
            idx = max(range(3), key=lambda k: buckets[k])
        ratio = min(count / max(max_day, 1), 1.0)
        opacity = (0.38, 0.6, 0.82, 1.0)[min(3, int(ratio * 3.999))]
        body.append('<rect class="cell" x="%d" y="%d" width="28" height="28" rx="6" fill="%s" fill-opacity="%s" style="animation-delay:%.2fs"/>'
                    % (x, y, STAGE[idx], opacity, col * 0.48))
    body.append("</g>")
    body.append('<g clip-path="url(#heat)"><rect x="618" y="270" width="80" height="240" fill="url(#gScan)"><animate attributeName="x" values="638;1522" dur="12.0s" repeatCount="indefinite"/></rect></g>')

    body.append('<text class="sans" x="620" y="556" font-size="28" font-weight="600" fill="#E8EEF9">Commits by project area</text>')
    body.append('<rect x="620" y="574" width="924" height="30" rx="15" fill="#17213A"/>')
    body.append('<g clip-path="url(#barclip)">')
    x = 620.0
    for i, share in enumerate(shares):
        w = 924.0 * share / 100.0
        body.append('<rect x="%.1f" y="574" width="0" height="30" fill="%s"><animate attributeName="width" values="0;0;%.1f;%.1f" keyTimes="0;%.4f;%.4f;1" dur="12.0s" repeatCount="indefinite"/></rect>'
                    % (x, STAGE[i], w, w, 0.0333 + i * 0.0584, 0.1 + i * 0.0584))
        if share > 0:
            lx, anchor = (x, "start") if x < 1424 else (1544.0, "end")
            body.append('<g opacity="0"><animate attributeName="opacity" values="0;0;1;1;0;0" keyTimes="0;%.4f;%.4f;0.988;0.994;1" dur="12.0s" repeatCount="indefinite"/>'
                        '<text class="sans" x="%.1f" y="644" text-anchor="%s" font-size="23" fill="%s">%s <tspan font-weight="700" fill="%s">%d%%</tspan></text></g>'
                        % (0.075 + i * 0.0584, 0.095 + i * 0.0584, lx, anchor, MUTED, STAGE_NAMES[i], STAGE[i], share))
        x += w
    body.append("</g>")
    body.append('<rect x="56" y="688" width="1488" height="4" rx="2" fill="#1B2846"/>')
    body.append('<rect x="56" y="688" width="0" height="4" rx="2" fill="url(#gProg)"><animate attributeName="width" values="0;1488" dur="12.0s" repeatCount="indefinite"/></rect>')
    marker_x = (293.0, 800.0, 1307.0)
    icons = (
        '<g transform="translate(88,746)"><path d="M0 2 H38 L23 20 V36 L15 32 V20 Z" fill="none" stroke="%s" stroke-width="3.4" stroke-linejoin="round"/></g>',
        '<g transform="translate(595,746)"><line x1="0" y1="5" x2="38" y2="5" stroke="%s" stroke-width="3.4" stroke-linecap="round"/><line x1="0" y1="19" x2="38" y2="19" stroke="%s" stroke-width="3.4" stroke-linecap="round"/><line x1="0" y1="33" x2="38" y2="33" stroke="%s" stroke-width="3.4" stroke-linecap="round"/><circle cx="11" cy="5" r="5.5" fill="#111A30" stroke="%s" stroke-width="3.4"/><circle cx="27" cy="19" r="5.5" fill="#111A30" stroke="%s" stroke-width="3.4"/><circle cx="15" cy="33" r="5.5" fill="#111A30" stroke="%s" stroke-width="3.4"/></g>',
        '<g transform="translate(1102,746)"><rect x="1" y="20" width="9" height="16" rx="2" fill="%s"/><rect x="15" y="8" width="9" height="28" rx="2" fill="%s" opacity=".8"/><rect x="29" y="0" width="9" height="36" rx="2" fill="%s" opacity=".6"/></g>',
    )
    for i, phase in enumerate(PHASES):
        bx = (56, 563, 1070)[i]
        body.append('<line x1="%.1f" y1="692" x2="%.1f" y2="716" stroke="#1F2B47" stroke-width="2"/>' % (marker_x[i], marker_x[i]))
        body.append('<circle cx="%.1f" cy="690" r="9" fill="#0A0F1E" stroke="%s" stroke-width="3"/>' % (marker_x[i], STAGE[i]))
        body.append('<rect x="%d" y="716" width="474" height="188" rx="18" fill="#111A30" stroke="#1F2B47" stroke-width="1.5"/>' % bx)
        body.append('<g opacity="0"><animate attributeName="opacity" values="%s" keyTimes="%s" dur="12.0s" repeatCount="indefinite"/>'
                    '<rect x="%d" y="716" width="474" height="188" rx="18" fill="%s" fill-opacity=".07" stroke="%s" stroke-width="2.5"/>'
                    '<circle cx="%.1f" cy="690" r="14" fill="%s" opacity=".25"/></g>'
                    % (opac[i], keytimes[i], bx, STAGE[i], STAGE[i], marker_x[i], STAGE[i]))
        body.append(icons[i].replace("%s", STAGE[i]))
        body.append('<text class="sans" x="%d" y="778" font-size="32" font-weight="700" fill="#E8EEF9">%s</text>' % (bx + 96, esc(phase["board"])))
        for j, line in enumerate(phase["desc"]):
            body.append('<text class="sans" x="%d" y="%d" font-size="23" fill="%s">%s</text>' % (bx + 32, 838 + j * 32, MUTED, esc(line)))
    body.append('<circle r="20" cy="690" fill="%s" opacity=".28" filter="url(#soft)"><animate attributeName="cx" values="56;1544" dur="12.0s" repeatCount="indefinite"/>'
                '<animate attributeName="fill" values="%s;%s;%s" keyTimes="0;.3333;.6667" calcMode="discrete" dur="12.0s" repeatCount="indefinite"/></circle>'
                % (STAGE[0], STAGE[0], STAGE[1], STAGE[2]))
    body.append('<circle r="9" cy="690" fill="%s" stroke="#0A0F1E" stroke-width="3"><animate attributeName="cx" values="56;1544" dur="12.0s" repeatCount="indefinite"/>'
                '<animate attributeName="fill" values="%s;%s;%s" keyTimes="0;.3333;.6667" calcMode="discrete" dur="12.0s" repeatCount="indefinite"/></circle>'
                % (STAGE[0], STAGE[0], STAGE[1], STAGE[2]))

    css = """
.sans{font-family:%s}
.mono{font-family:%s}
.code{font-size:21px;fill:#D6DEEB}
.k{fill:#FF7AC6} .s{fill:#8FE3A1} .f{fill:#7CC4FF} .n{fill:#FFB84D} .c{fill:#8A97B5}
.cell{transform-box:fill-box;transform-origin:center;animation:wave 12.0s ease-in-out infinite;opacity:.8}
@keyframes wave{0%%{opacity:.8;transform:scale(1)}4%%{opacity:1;transform:scale(1.14)}12%%{opacity:.9;transform:scale(1)}30%%,100%%{opacity:.8;transform:scale(1)}}
.bit{animation:rise 8s ease-in infinite;opacity:0}
@keyframes rise{0%%{opacity:0;transform:translateY(0)}20%%{opacity:.85}75%%{opacity:.5}100%%{opacity:0;transform:translateY(-150px)}}
@media (prefers-reduced-motion:reduce){.cell,.bit{animation:none}}
""" % (FONT, MONO)

    return time_page(css, body)


def time_page(css, body):
    return """<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="960" viewBox="0 0 1600 960" role="img" aria-labelledby="t d">
<title id="t">Spent My Time</title>
<desc id="d">Editor animation, daily contribution heatmap and commit area split.</desc>
<defs>
<style>%s</style>
<pattern id="dots" width="32" height="32" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1.2" fill="#1A2542"/></pattern>
<radialGradient id="gA" cx="50%%" cy="50%%" r="50%%"><stop offset="0" stop-color="%s" stop-opacity=".13"/><stop offset="1" stop-color="%s" stop-opacity="0"/></radialGradient>
<radialGradient id="gB" cx="50%%" cy="50%%" r="50%%"><stop offset="0" stop-color="%s" stop-opacity=".16"/><stop offset="1" stop-color="%s" stop-opacity="0"/></radialGradient>
<linearGradient id="gProg" gradientUnits="userSpaceOnUse" x1="56" y1="0" x2="1544" y2="0"><stop offset="0" stop-color="%s"/><stop offset=".5" stop-color="%s"/><stop offset="1" stop-color="%s"/></linearGradient>
<linearGradient id="gBase" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2A3958"/><stop offset="1" stop-color="#172238"/></linearGradient>
<linearGradient id="gScan" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".14"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
<filter id="blur" x="-50%%" y="-50%%" width="200%%" height="200%%"><feGaussianBlur stdDeviation="28"/></filter>
<filter id="soft" x="-100%%" y="-100%%" width="300%%" height="300%%"><feGaussianBlur stdDeviation="7"/></filter>
<clipPath id="frame"><rect width="1600" height="960" rx="28"/></clipPath>
<clipPath id="screen"><rect x="108" y="226" width="416" height="272" rx="10"/></clipPath>
<clipPath id="barclip"><rect x="620" y="574" width="924" height="30" rx="15"/></clipPath>
<clipPath id="heat"><rect x="698" y="270" width="844" height="246"/></clipPath>
</defs>
<g clip-path="url(#frame)">
<rect width="1600" height="960" fill="%s"/>
<rect width="1600" height="960" fill="url(#dots)"/>
<ellipse cx="180" cy="120" rx="560" ry="360" fill="url(#gA)"/>
<ellipse cx="1480" cy="860" rx="620" ry="380" fill="url(#gB)"/>
</g><rect x=".5" y=".5" width="1599" height="959" rx="28" fill="none" stroke="#1F2B47"/>
%s
</svg>
""" % (css, CYAN, CYAN, VIOLET, VIOLET, CYAN, BLUE, VIOLET, BG, "\n".join(body))


def main():
    user = sys.argv[1] if len(sys.argv) > 1 else "Ayinkx"
    out = sys.argv[2] if len(sys.argv) > 2 else "profile"
    os.makedirs(out, exist_ok=True)
    days = daily_counts(user)
    data = gathering(user, days)
    for name, svg in (("github-stats.svg", render_stats(user, data)),
                      ("spent-my-time.svg", render_time(user, data))):
        with open(os.path.join(out, name), "w", encoding="utf-8") as fh:
            fh.write(svg)
    total, cur, longest = streaks(days)
    print("wrote stats + time cards: total=%d current=%d longest=%d langs=%d"
          % (total, cur, longest, len(data["repo_top"])))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # never fail the workflow
        print("animated cards skipped: %s" % exc)
