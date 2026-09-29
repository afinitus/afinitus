#!/usr/bin/env python3
"""Draw the auto-updating "detector readout" stats card (and frame the contribution snake).

Runs daily in .github/workflows/profile-assets.yml on ubuntu-latest with the Python standard
library only. Text is set as outlined glyphs from scripts/glyphs.json (built by
scripts/art/build_glyphs.py from JetBrains Mono + Space Grotesk), because README images are served
with a CSP that blocks every kind of font.

    GITHUB_TOKEN=$(gh auth token) python3 scripts/profile_stats.py --out dist \
        [--user afinitus] [--exclude-lang "Jupyter Notebook"] [--exclude-repo OpenBot] \
        [--snake-dir dist/raw]

Writes <out>/stats-dark.svg and <out>/stats-light.svg. With --snake-dir, also wraps the raw
Platane/snk output (<snake-dir>/snake-{dark,light}.svg) in a matching card and writes
<out>/snake-{dark,light}.svg. Offline: --save-json keeps the API data, --from-json replays it.
"""
import argparse
import datetime as dt
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://api.github.com/graphql"

# design tokens, shared with scripts/art/banner.py and components.py
TOKENS = {
    "dark": dict(bg0="#0b0f14", bg1="#12171e", line="#21262d", text="#e6edf3", muted="#8b949e",
                 green="#3fb950", violet="#a78bfa", amber="#fbbf24", rose="#fb7185"),
    "light": dict(bg0="#fbfcfe", bg1="#f3f5f7", line="#d8dee4", text="#1f2328", muted="#59636e",
                  green="#1a7f37", violet="#7c3aed", amber="#d97706", rose="#e11d48"),
}
# language bar: two accent hues at two strengths, then neutrals (amber/rose stay reserved)
LANG_COLORS = [("green", 1), ("violet", 1), ("green", .5), ("violet", .5), ("muted", 1)]
OTHER_COLOR = ("muted", .35)
MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
WEEKDAYS = "Monday Tuesday Wednesday Thursday Friday Saturday Sunday".split()

QUERY = """
query($login: String!, $cursor: String, $withCalendar: Boolean!) {
  user(login: $login) {
    login
    contributionsCollection @include(if: $withCalendar) {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(first: 100, after: $cursor, privacy: PUBLIC, ownerAffiliations: [OWNER], isFork: false) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        languages(first: 50, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name } } }
      }
    }
  }
}
"""


# --------------------------------------------------------------------------- data

def graphql(token, variables, attempts=4):
    body = json.dumps({"query": QUERY, "variables": variables}).encode()
    req = urllib.request.Request(API, data=body, method="POST", headers={
        "Authorization": f"bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "profile-stats (github.com/afinitus/afinitus)",
    })
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
            if data.get("errors"):
                raise RuntimeError("GraphQL: " + "; ".join(e.get("message", "?") for e in data["errors"]))
            return data["data"]
        except urllib.error.HTTPError as e:
            if e.code < 500 and e.code != 429 or i == attempts - 1:
                raise RuntimeError(f"GitHub API HTTP {e.code}: {e.read()[:300]!r}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if i == attempts - 1:
                raise RuntimeError(f"GitHub API unreachable: {e}") from None
        time.sleep(2 ** i * 3)
    raise RuntimeError("unreachable")


def fetch(token, login):
    calendar, repos, cursor = None, [], None
    while True:
        data = graphql(token, {"login": login, "cursor": cursor, "withCalendar": calendar is None})
        user = data.get("user")
        if user is None:
            raise RuntimeError(f"user {login!r} not found")
        if calendar is None:
            calendar = user["contributionsCollection"]["contributionCalendar"]
        page = user["repositories"]
        repos += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return {"login": user["login"], "calendar": calendar, "repos": repos}


def analyse(raw, exclude_langs=(), exclude_repos=()):
    cal = raw.get("calendar") or {}
    days = sorted(
        ((dt.date.fromisoformat(d["date"]), int(d["contributionCount"]))
         for w in cal.get("weeks") or [] for d in w.get("contributionDays") or []),
        key=lambda x: x[0])
    total = int(cal.get("totalContributions") or sum(c for _, c in days))
    counts = [c for _, c in days]

    # current streak: today may still be empty without breaking it
    cur, cur_start = 0, None
    idx = len(days) - 1
    if idx >= 0 and counts[idx] == 0:
        idx -= 1
    while idx >= 0 and counts[idx] > 0:
        cur, cur_start, idx = cur + 1, days[idx][0], idx - 1
    last_active = next((d for d, c in reversed(days) if c > 0), None)

    best, best_span, run, run_start = 0, None, 0, None
    for d, c in days:
        if c > 0:
            run, run_start = run + 1, run_start if run else d
            if run >= best:  # ties go to the most recent run
                best, best_span = run, (run_start, d)
        else:
            run = 0

    by_wd = [0] * 7
    for d, c in days:
        by_wd[d.weekday()] += c
    wd_total = sum(by_wd)
    top_wd = max(range(7), key=lambda i: by_wd[i]) if wd_total else None

    # calendar weeks (Sunday first); keep the last 52 (the last one is the current, partial week)
    weeks = []
    for w in (cal.get("weeks") or [])[-52:]:
        ds = [dt.date.fromisoformat(d["date"]) for d in w["contributionDays"]]
        weeks.append((min(ds) if ds else None, sum(int(d["contributionCount"]) for d in w["contributionDays"])))

    ex_l = {x.lower() for x in exclude_langs}
    ex_r = {x.lower() for x in exclude_repos}
    sizes = {}
    for repo in raw.get("repos") or []:
        if repo["name"].lower() in ex_r:
            continue
        for e in (repo.get("languages") or {}).get("edges") or []:
            name = e["node"]["name"]
            if name.lower() not in ex_l:
                sizes[name] = sizes.get(name, 0) + int(e["size"])
    lang_total = sum(sizes.values())
    ranked = sorted(sizes.items(), key=lambda kv: (-kv[1], kv[0]))
    langs = [(n, s / lang_total, False) for n, s in ranked[:5]] if lang_total else []
    rest = sum(s for _, s in ranked[5:])
    if rest:
        langs.append(("other", rest / lang_total, True))

    return dict(total=total, active=sum(1 for c in counts if c), ndays=len(days),
                today=days[-1][0] if days else None, current=cur, current_start=cur_start,
                last_active=last_active, longest=best, longest_span=best_span,
                weekday=top_wd, weekday_share=(by_wd[top_wd] / wd_total if wd_total else 0),
                weeks=weeks, langs=langs)


# --------------------------------------------------------------------------- type

class Type:
    """Set text as <use> references to glyph outlines defined once per document."""
    CODES = {"mono-400": "a", "mono-500": "b", "grotesk-700": "g"}

    def __init__(self, path):
        with open(path, encoding="utf-8") as fh:
            self.fonts = json.load(fh)
        self.used = {}

    def _run(self, text, font, tracking):
        f = self.fonts[font]
        pen, prev, out = 0, None, []
        track = round(tracking * f["upem"])
        for ch in text:
            if ch not in f["adv"]:
                ch = "?"
            if prev is not None:
                pen += f["kern"].get(prev + ch, 0) + track
            out.append((ch, pen))
            pen += f["adv"][ch]
            prev = ch
        return out, pen

    def measure(self, text, font, size, tracking=0.0):
        return self._run(text, font, tracking)[1] * size / self.fonts[font]["upem"]

    def fit(self, text, font, size, max_width, tracking=0.0):
        """Largest size <= `size` at which `text` fits in `max_width`."""
        w = self.measure(text, font, size, tracking)
        return size if w <= max_width else size * max_width / w

    def text(self, text, font, size, x, y, fill, anchor="start", tracking=0.0, extra=""):
        f = self.fonts[font]
        glyphs, adv = self._run(text, font, tracking)
        s = size / f["upem"]
        x -= {"start": 0, "middle": adv * s / 2, "end": adv * s}[anchor]
        code = self.CODES[font]
        uses = []
        for ch, gx in glyphs:
            if ch in f["d"]:
                gid = f"{code}{ord(ch):x}"
                self.used[gid] = f["d"][ch]
                uses.append(f'<use href="#{gid}" x="{gx}"/>' if gx else f'<use href="#{gid}"/>')
        return (f'<g fill="{fill}" transform="translate({x:.1f} {y:.1f}) scale({s:.5f} {-s:.5f})"{extra}>'
                + "".join(uses) + "</g>"), adv * s

    def defs(self):
        return "".join(f'<path id="{k}" d="{v}"/>' for k, v in sorted(self.used.items()))


def fmt_date(d):
    return f"{MONTHS[d.month - 1]} {d.day}" if d else "—"


def fmt_pct(p):
    if p <= 0:
        return "0%"
    if p < 0.001:
        return "<0.1%"
    return f"{p * 100:.1f}%" if p < 0.1 else f"{p * 100:.0f}%"


def op_attr(op):
    return "" if op == 1 else f' opacity="{op}"'


def plural(n, word):
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# --------------------------------------------------------------------------- stats card

W, M = 1200, 40
IW = W - 2 * M


def stats_svg(st, theme, login, updated, lang_note):
    c = TOKENS[theme]
    T = Type(os.path.join(HERE, "glyphs.json"))
    out = []
    add = out.append

    # ---- header
    add(f'<circle class="ps-pulse" cx="{M + 5}" cy="45.5" r="4.5" fill="{c["green"]}"/>')
    g, w = T.text("detector readout", "mono-500", 16, M + 18, 50, c["text"], tracking=0.06)
    add(g)
    add(T.text(f"· github.com/{login}", "mono-400", 16, M + 18 + w + 10, 50, c["muted"], tracking=0.02)[0])
    add(T.text(f"updated {updated.isoformat()}", "mono-400", 15, W - M, 50, c["muted"], "end", 0.04)[0])
    add(f'<path d="M{M} 70.5H{W - M}" stroke="{c["line"]}"/>')

    # ---- readout tiles
    ty, th, gap = 90, 128, 16
    tw = (IW - 3 * gap) / 4
    cur, lon = st["current"], st["longest"]
    if cur:
        cur_sub = "active today" if cur == 1 and st["current_start"] == st["today"] else f"since {fmt_date(st['current_start'])}"
    else:
        cur_sub = f"last active {fmt_date(st['last_active'])}" if st["last_active"] else "no activity yet"
    if lon:
        a, b = st["longest_span"]
        lon_sub = fmt_date(a) if a == b else f"{fmt_date(a)} → {fmt_date(b)}"
    else:
        lon_sub = "no activity yet"
    wd = WEEKDAYS[st["weekday"]] if st["weekday"] is not None else "—"
    wd_sub = f"{fmt_pct(st['weekday_share'])} of contributions" if st["weekday"] is not None else "no activity yet"
    tiles = [
        ("contributions", f"{st['total']:,}", "", f"on {st['active']} active {'day' if st['active'] == 1 else 'days'}", "green"),
        ("current streak", str(cur), "day" if cur == 1 else "days", cur_sub, "green"),
        ("longest streak", str(lon), "day" if lon == 1 else "days", lon_sub, "violet"),
        ("busiest weekday", wd, "", wd_sub, "violet"),
    ]
    for i, (label, value, unit, sub, accent) in enumerate(tiles):
        x = M + i * (tw + gap)
        add(f'<rect x="{x + .5:.1f}" y="{ty + .5}" width="{tw - 1:.1f}" height="{th - 1}" rx="10" '
            f'fill="{c["bg1"]}" stroke="{c["line"]}"/>')
        add(f'<rect x="{x:.1f}" y="{ty + 22}" width="3" height="16" rx="1.5" fill="{c[accent]}"/>')
        add(T.text(label, "mono-500", 15, x + 22, ty + 35, c["muted"], tracking=0.06)[0])
        unit_w = T.measure(unit, "mono-400", 17) + 10 if unit else 0
        size = T.fit(value, "grotesk-700", 50, tw - 44 - unit_w, tracking=-0.01)
        g, vw = T.text(value, "grotesk-700", size, x + 22, ty + 90, c["text"], tracking=-0.01)
        add(g)
        if unit:
            add(T.text(unit, "mono-400", 17, x + 22 + vw + 9, ty + 90, c["muted"], tracking=0.02)[0])
        add(T.text(sub, "mono-400", 14.5, x + 22, ty + 113, c["muted"], tracking=0.02)[0])

    # ---- calorimeter towers: weekly contributions, log scale, 8 segments per tower
    py, ph = 236, 196
    add(f'<rect x="{M + .5}" y="{py + .5}" width="{IW - 1}" height="{ph - 1}" rx="12" '
        f'fill="{c["bg1"]}" stroke="{c["line"]}"/>')
    add(T.text("weekly contributions · 52 weeks · log scale", "mono-500", 15, M + 22, py + 34,
               c["muted"], tracking=0.06)[0])
    weeks = st["weeks"]
    peak = max((n for _, n in weeks), default=0)
    x0, x1 = M + 22, W - M - 22
    base, height, nseg = py + 156, 104, 8
    seg = height / nseg
    pitch = (x1 - x0) / 52
    bw = round(pitch * 0.62, 1)
    off = 52 - len(weeks)  # right-align when the calendar is shorter than 52 weeks
    if peak:
        pi = max(range(len(weeks)), key=lambda i: (weeks[i][1], i))
        g, w = T.text(f"{peak:,} · week of {fmt_date(weeks[pi][0])}", "mono-400", 15, x1, py + 34,
                      c["muted"], "end", 0.04)
        add(g)
        add(T.text("▲ peak", "mono-500", 15, x1 - w - 10, py + 34, c["amber"], "end", 0.04)[0])
    else:
        pi = None
        add(T.text("no deposits yet", "mono-400", 15, x1, py + 34, c["muted"], "end", 0.04)[0])

    ghost, lit = [], []
    for i in range(52):
        bx = x0 + i * pitch + (pitch - bw) / 2
        ghost.append(f"M{bx:.1f} {base - height + 3:.1f}h{bw}v{height - 3}h{-bw}Z")
        j = i - off
        if 0 <= j < len(weeks) and weeks[j][1] > 0:
            lvl = max(1, round(nseg * math.log1p(weeks[j][1]) / math.log1p(peak)))
            top = base - lvl * seg + 3
            fill = c["amber"] if j == pi else "url(#ps-heat)"
            lit.append(f'<rect x="{bx:.1f}" y="{top:.1f}" width="{bw}" height="{lvl * seg - 3:.1f}" fill="{fill}"/>')
    add(f'<path d="{"".join(ghost)}" fill="{c["line"]}" opacity="{0.55 if theme == "dark" else 0.6}"/>')
    add("".join(lit))
    # segment gaps: bg1 stripes across the whole tower field (explicit, no <pattern> tiling seams)
    stripes = "".join(f"M{x0} {base - height + k * seg:.1f}h{x1 - x0}v3h{x0 - x1}Z" for k in range(nseg))
    add(f'<path d="{stripes}" fill="{c["bg1"]}"/>')
    add(f'<path d="M{x0} {base + 6.5}H{x1}" stroke="{c["line"]}"/>')

    # month ticks under the first week that contains the 1st of a month; "now" under the last
    last_label_x = -1e9
    for j, (start, _) in enumerate(weeks):
        if start is None:
            continue
        end = start + dt.timedelta(days=6)
        first = end.replace(day=1)
        if not (start <= first <= end) or j == 0:
            continue
        lx = x0 + (j + off) * pitch + (pitch - bw) / 2
        if lx - last_label_x < 44 or lx > x1 - 60:
            continue
        add(f'<path d="M{lx:.1f} {base + 6.5}v5" stroke="{c["muted"]}" opacity=".6"/>')
        add(T.text(MONTHS[first.month - 1], "mono-400", 14, lx, base + 28, c["muted"], tracking=0.04)[0])
        last_label_x = lx
    add(T.text("now", "mono-500", 14, x1, base + 28, c["green"], "end", 0.04)[0])

    # scan line (decorative; hidden for reduced motion)
    sweep = (f'<g clip-path="url(#ps-clip)"><g class="ps-sweep">'
             f'<rect x="{x0 - 64}" y="{base - height - 8}" width="64" height="{height + 8}" fill="url(#ps-trail)"/>'
             f'<rect x="{x0 - 1.5}" y="{base - height - 8}" width="1.5" height="{height + 8}" fill="{c["green"]}" opacity=".7"/>'
             f'</g></g>')
    add(sweep)

    # ---- language composition
    ly = 456
    add(T.text("languages", "mono-500", 15, M, ly + 20, c["muted"], tracking=0.06)[0])
    add(T.text(lang_note, "mono-400", 14, W - M, ly + 20, c["muted"], "end", 0.04)[0])
    by, bh = ly + 36, 12
    langs = st["langs"]
    bar = [f'<rect x="{M}" y="{by}" width="{IW}" height="{bh}" fill="{c["line"]}"/>']
    legend_items = []
    if langs:
        bar = []
        cx = float(M)
        widths = [max(4.0, p * IW) for _, p, _ in langs]  # keep slivers visible
        scale = IW / sum(widths)
        for k, ((name, p, rest), wv) in enumerate(zip(langs, widths)):
            wv *= scale
            key, op = OTHER_COLOR if rest else LANG_COLORS[k]
            col = c[key]
            gapw = 3 if k < len(langs) - 1 else 0
            bar.append(f'<rect x="{cx:.1f}" y="{by}" width="{max(1.0, wv - gapw):.1f}" height="{bh}" '
                       f'fill="{col}"{op_attr(op)}/>')
            legend_items.append((name, fmt_pct(p), col, op))
            cx += wv
    add(f'<g clip-path="url(#ps-bar)">{"".join(bar)}</g>')
    lx = M
    lb = by + bh + 34
    if not legend_items:
        add(T.text("no public code yet", "mono-400", 17, M, lb, c["muted"], tracking=0.02)[0])
    for name, pct, col, op in legend_items:
        nw = T.measure(name, "mono-400", 17, 0.02)
        pw = T.measure(pct, "mono-400", 17, 0.02)
        if lx > M and lx + 19 + nw + 10 + pw > W - M:  # wrap long legends
            lx, lb = M, lb + 32
        add(f'<rect x="{lx}" y="{lb - 11.5}" width="11" height="11" rx="2" fill="{col}"{op_attr(op)}/>')
        add(T.text(name, "mono-400", 17, lx + 19, lb, c["text"], tracking=0.02)[0])
        add(T.text(pct, "mono-400", 17, lx + 19 + nw + 10, lb, c["muted"], tracking=0.02)[0])
        lx += 19 + nw + 10 + pw + 36
    H = lb + 30

    # ---- assemble
    wd_txt = f"most active on {wd}s ({fmt_pct(st['weekday_share'])})" if st["weekday"] is not None else "no activity yet"
    lang_txt = ", ".join(f"{n} {fmt_pct(p)}" for n, p, _ in langs) or "none yet"
    label = (f"GitHub activity for {login}, last 12 months: {plural(st['total'], 'contribution')} "
             f"on {plural(st['active'], 'day')}; current streak {plural(cur, 'day')}; longest streak {plural(lon, 'day')}; "
             f"{wd_txt}; busiest week {plural(peak, 'contribution')}. Languages by bytes: {lang_txt}. "
             f"Updated {updated.isoformat()}.")
    heat_lo = 0.38 if theme == "dark" else 0.45
    style = (
        "@keyframes ps-sweep{0%{transform:translateX(0);opacity:0}6%{opacity:1}64%{opacity:1}"
        f"70%,100%{{transform:translateX({x1 - x0 + 64}px);opacity:0}}}}"
        "@keyframes ps-pulse{0%,100%{opacity:1}50%{opacity:.3}}"
        ".ps-sweep{animation:ps-sweep 9s linear infinite}"
        ".ps-pulse{animation:ps-pulse 2.4s ease-in-out infinite}"
        "@media (prefers-reduced-motion:reduce){.ps-sweep{animation:none;display:none}.ps-pulse{animation:none}}"
    )
    defs = (
        f'<linearGradient id="ps-heat" gradientUnits="userSpaceOnUse" x1="0" y1="{base}" x2="0" y2="{base - height}">'
        f'<stop offset="0" stop-color="{c["green"]}" stop-opacity="{heat_lo}"/>'
        f'<stop offset="1" stop-color="{c["green"]}"/></linearGradient>'
        f'<linearGradient id="ps-trail" x1="0" x2="1" y1="0" y2="0">'
        f'<stop offset="0" stop-color="{c["green"]}" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="{c["green"]}" stop-opacity="{0.14 if theme == "dark" else 0.12}"/></linearGradient>'
        f'<clipPath id="ps-clip"><rect x="{x0}" y="{py + 1}" width="{x1 - x0}" height="{ph - 2}"/></clipPath>'
        f'<clipPath id="ps-bar"><rect x="{M}" y="{by}" width="{IW}" height="{bh}" rx="{bh / 2}"/></clipPath>'
        + T.defs()
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'role="img" aria-label="{esc(label)}">'
        f'<title id="ps-title">GitHub activity · {esc(login)}</title><desc id="ps-desc">{esc(label)}</desc>'
        f'<style>{style}</style><defs>{defs}</defs>'
        f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="16" fill="{c["bg0"]}" stroke="{c["line"]}"/>'
        + "".join(out) + "</svg>\n"
    ), label


# --------------------------------------------------------------------------- snake card

def snake_svg(raw, theme, login):
    """Frame Platane/snk output as a card that matches the stats card."""
    c = TOKENS[theme]
    m = re.match(r'\s*<svg\b([^>]*)>(.*)</svg>\s*$', raw, re.S)
    vb = re.search(r'viewBox="([-\d.\s]+)"', m.group(1)) if m else None
    if not vb:
        raise ValueError("unexpected snk output")
    vx, vy, vw, vh = (float(v) for v in vb.group(1).split())
    inner = m.group(2)
    # snk: 16px cells, 12px dots; viewBox = 1 cell each side, 2 above (snake's start pose),
    # grid, then 3 below for its progress bar. We drop that bar (.u) and keep 1 spare cell
    # under the grid, because the snake may route through the ring of cells just outside it.
    rows = round(vh / 16) - 5
    vh = (rows + 1) * 16 - vy
    s = IW / (vw - 36)  # dots span raw x in [vx + 18, vx + vw - 18] -> card x in [M, W - M]
    nx, ny = M - 18 * s, 104 - (2 - vy) * s
    H = round(ny + vh * s) + 12
    T = Type(os.path.join(HERE, "glyphs.json"))
    g, w = T.text("contribution grid", "mono-500", 15, M, 50, c["text"], tracking=0.06)
    head = g + T.text("· last 12 months", "mono-400", 15, M + w + 10, 50, c["muted"], tracking=0.02)[0]
    head += T.text("snake · platane/snk", "mono-400", 14, W - M, 50, c["muted"], "end", 0.04)[0]
    label = f"Animated snake eating the GitHub contribution grid of {login} for the last 12 months."
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'role="img" aria-label="{esc(label)}">'
        f'<title id="sn-title">Contribution snake · {esc(login)}</title><desc id="sn-desc">{esc(label)}</desc>'
        '<style>.u{display:none}@media (prefers-reduced-motion:reduce){.c,.s{animation:none!important}}</style>'
        f'<defs>{T.defs()}</defs>'
        f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="16" fill="{c["bg0"]}" stroke="{c["line"]}"/>'
        f'{head}<path d="M{M} 70.5H{W - M}" stroke="{c["line"]}"/>'
        f'<svg x="{nx:.2f}" y="{ny:.2f}" width="{vw * s:.2f}" height="{vh * s:.2f}" viewBox="{vx:g} {vy:g} {vw:g} {vh:g}">{inner}</svg>'
        "</svg>\n"
    )


# --------------------------------------------------------------------------- main

def split_list(values):
    return [x.strip() for v in values or [] for x in v.split(",") if x.strip()]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--user", default=os.environ.get("GITHUB_REPOSITORY_OWNER") or "afinitus")
    ap.add_argument("--out", default="dist")
    ap.add_argument("--exclude-lang", action="append", help="language(s) to leave out, comma separated; repeatable")
    ap.add_argument("--exclude-repo", action="append", help="repo name(s) to leave out, comma separated; repeatable")
    ap.add_argument("--snake-dir", help="dir with raw snk output snake-dark.svg / snake-light.svg to frame")
    ap.add_argument("--from-json", help="render from saved API data instead of calling GitHub")
    ap.add_argument("--save-json", help="also save the fetched API data here")
    ap.add_argument("--today", help="override the 'updated' date (YYYY-MM-DD)")
    a = ap.parse_args()

    if a.from_json:
        with open(a.from_json, encoding="utf-8") as fh:
            raw = json.load(fh)
    else:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            sys.exit("GITHUB_TOKEN is not set")
        raw = fetch(token, a.user)
    if a.save_json:
        with open(a.save_json, "w", encoding="utf-8") as fh:
            json.dump(raw, fh)

    ex_l, ex_r = split_list(a.exclude_lang), split_list(a.exclude_repo)
    st = analyse(raw, ex_l, ex_r)
    updated = dt.date.fromisoformat(a.today) if a.today else dt.datetime.now(dt.timezone.utc).date()
    note = "bytes of code · own public repos" + (" · excl. " + ", ".join(x.lower() for x in ex_l + ex_r) if ex_l or ex_r else "")
    login = raw.get("login") or a.user

    os.makedirs(a.out, exist_ok=True)
    for theme in ("dark", "light"):
        svg, label = stats_svg(st, theme, login, updated, note)
        path = os.path.join(a.out, f"stats-{theme}.svg")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(svg)
        print(f"wrote {path} ({len(svg) / 1024:.1f} KB)")
    print(label)

    if a.snake_dir:
        for theme in ("dark", "light"):
            src = os.path.join(a.snake_dir, f"snake-{theme}.svg")
            dst = os.path.join(a.out, f"snake-{theme}.svg")
            if not os.path.exists(src):
                print(f"::warning::{src} missing; no snake-{theme}.svg this run")
                continue
            with open(src, encoding="utf-8") as fh:
                raw_svg = fh.read()
            try:
                svg = snake_svg(raw_svg, theme, login)
            except Exception as e:  # fail: the publish step then keeps yesterday's good assets
                sys.exit(f"::error::could not frame {src}: {e}")
            with open(dst, "w", encoding="utf-8") as fh:
                fh.write(svg)
            print(f"wrote {dst} ({len(svg) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
