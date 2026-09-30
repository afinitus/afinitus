#!/usr/bin/env python3
"""Supporting art for the profile README: link pills and the section divider (and optional project cards).

Same visual language as the banner ("event display -> kinematic chain"):
green = particles (tracks, jet cones), violet = robots (kinematic skeletons, joint rings, soft hulls),
amber = calorimeter deposits, rose = the one displaced vertex. Hairline `line` borders, rx 14-16 cards
with their own bg0 fill, lowercase mono labels, Space Grotesk titles. All text is outlined with
text2path.py (GitHub's image CSP blocks every kind of font).

    python3 scripts/art/components.py                 # writes assets/link-*, divider-* (and card-* for FEATURED)

Motion is deliberately cheap. Every animation starts and ends on the complete resting picture, which is also
frame 0 and the prefers-reduced-motion state, and every animation has a finite repeat count: Chrome re-rasterises
an animated <img> SVG every frame while it is on screen (measured ~3% CPU per image for an endless loop), but costs
nothing once the animations have finished.
  * cards   - a short replay (a hit pulse runs out along the tracks and the calorimeter cells flash, or the arm
              servos and the gripper closes/reopens) every PERIOD s, REPEATS times, starting START s after load.
  * divider - a pulse travels from the vertex (green) to the joint ring (violet) every D_PERIOD s, D_REPEATS times.
  * pills   - static.
Pass --card-repeats / --divider-repeats infinite to loop forever instead (costs CPU while visible).
"""
import argparse
import math
import os
import re
import sys
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
ASSETS = os.path.join(REPO, "assets")
sys.path.insert(0, HERE)
import text2path  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402
from text2path import measure, text_path  # noqa: E402

# ------------------------------------------------------------------------------------------------
# data: project cards (none are shown right now). To bring a card back, add an entry here and list its
# repo in FEATURED. Fields: repo, url, title, kicker, provenance, blurb (`_X` = one-letter subscript),
# lang, category ("robotics" | "physics" | "agents"), glyph (which line-art helper draws the top-right art).
# ------------------------------------------------------------------------------------------------
FEATURED = ()
PROJECTS = []

LINKS = [
    # name, label, icon, aria text
    ("x", "x.com/nishgite", "x", "Nishank Gite on X: x.com/nishgite"),
    ("nrvna", "nrvna.ai", "arm", "Nirvana Robotics: nrvna.ai"),
    ("linkedin", "linkedin", "in", "Nishank Gite on LinkedIn"),
]

# ------------------------------------------------------------------------------------------------
# design tokens (shared with scripts/art/banner.py)
# ------------------------------------------------------------------------------------------------
TOKENS = {
    "dark": dict(bg0="#0b0f14", bg1="#12171e", line="#21262d", text="#e6edf3", muted="#8b949e",
                 green="#3fb950", violet="#a78bfa", amber="#fbbf24", rose="#fb7185"),
    "light": dict(bg0="#fbfcfe", bg1="#f3f5f7", line="#d8dee4", text="#1f2328", muted="#59636e",
                  green="#1a7f37", violet="#7c3aed", amber="#d97706", rose="#e11d48"),
}
HULL_A = {"dark": 0.16, "light": 0.11}          # robot hulls: violet over bg0, as in the banner
ACCENT = {"robotics": "violet", "physics": "green", "agents": "amber", "other": "muted"}
REDUCED = "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"


def f(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def pt(p):
    return f"{f(p[0])} {f(p[1])}"


def mix(c1, c2, a):
    """c1 over c2 at alpha a, as an opaque hex colour (a tint of c1, not a new hue)."""
    x = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    y = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(a * p + (1 - a) * q):02x}" for p, q in zip(x, y))


def along(p, a_deg, L):
    a = math.radians(a_deg)
    return (p[0] + L * math.cos(a), p[1] + L * math.sin(a))


def P(c, r, a_deg):
    return along(c, a_deg, r)


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def ang(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def esc(s):
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def svg_doc(w, h, label, css, body, defs=""):
    lab = esc(label)
    style = f"<style>{css}</style>" if css else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {f(w)} {f(h)}" width="{f(w)}" height="{f(h)}" '
            f'role="img" aria-label="{lab}"><title>{lab}</title>{style}{defs}{body}</svg>\n')


# ------------------------------------------------------------------------------------------------
# text
# ------------------------------------------------------------------------------------------------
_TOK = re.compile(r"[MLHVCQZ]|-?(?:\d+\.?\d*|\.\d+)")


def _fmt(n):
    """integer tenths -> shortest decimal string ('.5', '-1.2', '3')"""
    s = "-" if n < 0 else ""
    i, r = divmod(abs(n), 10)
    return s + (str(i) if r == 0 else (f"{i}.{r}" if i else f".{r}"))


def compact(d):
    """Absolute M/L/H/V/Q/C/Z path data (as text2path emits it) -> relative commands on a 0.1 grid.
    Deltas are taken between rounded absolute points, so there is no drift. Saves ~40% of the bytes."""
    toks = _TOK.findall(d)
    out, last, i = [], None, 0
    cx = cy = sx = sy = 0

    def emit(cmd, nums):
        nonlocal last
        if cmd != last or cmd in "mz":
            out.append(cmd)
        for n in nums:
            s = _fmt(n)
            p = out[-1] if out else ""
            if p and p[-1] not in "mlhvcqz" and not s.startswith("-") and not (s.startswith(".") and "." in p):
                out.append(" ")
            out.append(s)
        last = cmd

    def num():
        nonlocal i
        v = round(float(toks[i]) * 10)
        i += 1
        return v

    cmd = None
    while i < len(toks):
        if toks[i] in "MLHVCQZ":
            cmd = toks[i]
            i += 1
            if cmd == "Z":
                emit("z", [])
                cx, cy = sx, sy
                continue
        elif cmd == "M":
            cmd = "L"  # implicit lineto after moveto
        if cmd == "M":
            x, y = num(), num()
            if out:
                emit("m", [x - cx, y - cy])
            else:  # absolute first moveto, so compacted paths can be concatenated
                out.extend(["M", _fmt(x)] + ([] if _fmt(y).startswith("-") else [" "]) + [_fmt(y)])
                last = "M"
            cx, cy = sx, sy = x, y
        elif cmd == "L":
            x, y = num(), num()
            if y == cy:
                emit("h", [x - cx])
            elif x == cx:
                emit("v", [y - cy])
            else:
                emit("l", [x - cx, y - cy])
            cx, cy = x, y
        elif cmd == "H":
            x = num()
            emit("h", [x - cx])
            cx = x
        elif cmd == "V":
            y = num()
            emit("v", [y - cy])
            cy = y
        elif cmd in "QC":
            n = 2 if cmd == "Q" else 3
            pts = [(num(), num()) for _ in range(n)]
            emit(cmd.lower(), [v for (x, y) in pts for v in (x - cx, y - cy)])
            cx, cy = pts[-1]
        else:
            raise ValueError(f"unexpected path token {toks[i]!r}")
    return "".join(out)


@lru_cache(maxsize=None)
def _cmap(font):
    return frozenset(TTFont(os.path.join(text2path.FONT_DIR, f"{font}.ttf")).getBestCmap())


def font_runs(s, font):
    """Split s into runs per font: characters the font lacks (Space Grotesk has no Greek, e.g. the gamma in
    'H -> gamma gamma') fall back to JetBrains Mono of the same weight."""
    fb = "mono-" + font.split("-")[1]
    runs = []
    for ch in s:
        fnt = font if (ord(ch) in _cmap(font) or ch == " ") else fb
        if runs and runs[-1][1] == fnt:
            runs[-1][0] += ch
        else:
            runs.append([ch, fnt])
    return runs


def tw(s, font, size, tracking=0.0):
    runs = font_runs(s, font)
    return sum(measure(t, fn, size, tracking) for t, fn in runs) + tracking * size * (len(runs) - 1)


def tp(s, font, size, x, y, anchor="start", tracking=0.0):
    """Outlined text -> (compact path data, advance width), with per-character font fallback."""
    w = tw(s, font, size, tracking)
    x -= {"start": 0, "middle": w / 2, "end": w}[anchor]
    ds = []
    for t, fn in font_runs(s, font):
        d, rw = text_path(t, fn, size, x, y, tracking=tracking, precision=1)
        ds.append(compact(d))
        x += rw + tracking * size
    return "".join(ds), w


def runs_of(word):
    """'low-p_T' -> [('low-p', False), ('T', True)]"""
    out, i = [], 0
    for m in re.finditer(r"_(.)", word):
        if m.start() > i:
            out.append((word[i:m.start()], False))
        out.append((m.group(1), True))
        i = m.end()
    if i < len(word):
        out.append((word[i:], False))
    return out


SUB = 0.7  # subscript size factor


def rich_width(word, font, size):
    return sum(tw(t, font, size * (SUB if sub else 1)) for t, sub in runs_of(word))


def rich_path(line, font, size, x, y):
    """Draw a line that may contain _X subscripts; returns path data."""
    ds = []
    for t, sub in runs_of(line):
        if sub:
            d, w = tp(t, font, size * SUB, x, y + size * 0.22)
        else:
            d, w = tp(t, font, size, x, y)
        ds.append(d)
        x += w
    return " ".join(ds)


def wrap(text, font, size, width):
    words, lines, cur = text.split(" "), [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if rich_width(cand, font, size) <= width or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# ------------------------------------------------------------------------------------------------
# glyph helpers (event display + kinematic chain, as in the banner).
# Glyphs draw in card coordinates into the top-right zone (x > ~240, y < ~112). The card clips them
# to its rounded rectangle, so an event display may bleed off the top/right edge like a zoomed view.
# ------------------------------------------------------------------------------------------------
class Arc:
    """Transverse track: a circular arc from `o` with initial direction phi (deg), radius R, s=+1 clockwise
    on screen. Ends where its distance from `c` reaches r_end, or after amax degrees (loopers)."""

    def __init__(self, o, phi, R, s, c, r_end, amax=300.0):
        self.o, self.R, self.s = o, R, s
        n = (-math.sin(math.radians(phi)), math.cos(math.radians(phi)))
        self.c = (o[0] + s * R * n[0], o[1] + s * R * n[1])
        self.b0 = math.atan2(o[1] - self.c[1], o[0] - self.c[0])
        a, step = 0.0, 0.25
        while a < amax and dist(self.at(a + step), c) < r_end:
            a += step
        if a >= amax:
            self.alpha = amax
        else:
            lo, hi = a, a + step
            for _ in range(30):
                mid = (lo + hi) / 2
                lo, hi = (mid, hi) if dist(self.at(mid), c) < r_end else (lo, mid)
            self.alpha = hi
        self.end = self.at(self.alpha)

    def at(self, a_deg):
        b = self.b0 + self.s * math.radians(a_deg)
        return (self.c[0] + self.R * math.cos(b), self.c[1] + self.R * math.sin(b))

    def d(self):
        n = max(1, math.ceil(self.alpha / 150.0))
        sweep = 1 if self.s > 0 else 0
        return f"M{pt(self.o)}" + "".join(f"A{f(self.R)} {f(self.R)} 0 0 {sweep} {pt(self.at(self.alpha * i / n))}"
                                          for i in range(1, n + 1))


def arc_d(c, r, a0, a1):
    p0, p1 = P(c, r, a0), P(c, r, a1)
    large = 1 if (a1 - a0) % 360 > 180 else 0
    return f"M{pt(p0)}A{f(r)} {f(r)} 0 {large} 1 {pt(p1)}"


def sector(c, r0, r1, a0, a1):
    p0, p1, p2, p3 = P(c, r0, a0), P(c, r1, a0), P(c, r1, a1), P(c, r0, a1)
    return f"M{pt(p0)}L{pt(p1)}A{f(r1)} {f(r1)} 0 0 1 {pt(p2)}L{pt(p3)}A{f(r0)} {f(r0)} 0 0 0 {pt(p0)}Z"


def chamber(c, r, a_deg, th, hw):
    u = (math.cos(math.radians(a_deg)), math.sin(math.radians(a_deg)))
    v = (-u[1], u[0])
    m = P(c, r, a_deg)
    pts = [(m[0] + sx * th / 2 * u[0] + sy * hw * v[0], m[1] + sx * th / 2 * u[1] + sy * hw * v[1])
           for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    return "M" + "L".join(pt(p) for p in pts) + "Z"


# the banner's detector, zoomed: pixel/strip arcs, solenoid, 64-segment EM + two HAD layers, muon stations
SEG = 360 / 64
R_TRK = (15, 21.5, 28, 34.5)
R_SOL = 41.0
R_EM = (45.0, 58.0)
R_HAD = ((61.0, 73.0), (76.0, 88.0))
R_MU = ((101.0, 6.0), (119.0, 6.0))
PV_XY = (266.0, 104.0)
SLICE = (-101.0, -1.0)


def detector_slice(k, c=PV_XY, a0=SLICE[0], a1=SLICE[1]):
    o = [f'<path d="{"".join(arc_d(c, r, a0, a1) for r in R_TRK)}" fill="none" stroke="{k["line"]}" stroke-width="1"/>',
         f'<path d="{arc_d(c, R_SOL, a0, a1)}" fill="none" stroke="{k["muted"]}" stroke-opacity=".4" stroke-width="1.1"/>']
    radii = [R_EM[0], R_EM[1]] + [r for layer in R_HAD for r in layer]
    cal = "".join(arc_d(c, r, a0, a1) for r in radii)
    ticks = "".join(f"M{pt(P(c, R_EM[0], i * SEG))}L{pt(P(c, R_EM[1], i * SEG))}"
                    + "".join(f"M{pt(P(c, r0, i * SEG))}L{pt(P(c, r1, i * SEG))}" for r0, r1 in R_HAD)
                    for i in range(math.ceil(a0 / SEG), math.floor(a1 / SEG) + 1))
    o.append(f'<path d="{cal}{ticks}" fill="none" stroke="{k["line"]}" stroke-width="1"/>')
    ch = []
    for i in range(-8, 1):
        a = i * 22.5
        if a - 11.25 < a0 - 2 or a + 11.25 > a1 + 1:   # whole chambers only, never below the slice
            continue
        big = i % 2 == 0
        for r, th in R_MU:
            rr = r if big else r + 4
            ch.append(chamber(c, rr, a, th, rr * math.tan(math.radians(11.25)) * (0.9 if big else 0.6)))
    o.append(f'<path d="{"".join(ch)}" fill="{k["bg1"]}" stroke="{k["line"]}" stroke-width="1"/>')
    return "".join(o)


def cells(k, deposits, c=PV_XY, cls=""):
    """deposits: [(phi_deg, energy)] -> amber EM/HAD cells with a simple shower profile."""
    em, had = {}, [{}, {}]
    for phi, e in deposits:
        i = math.floor(phi / SEG)
        for d_, w in ((-2, .12), (-1, .4), (0, 1.0), (1, .4), (2, .12)):
            em[i + d_] = em.get(i + d_, 0) + e * w
        for layer, prof in enumerate((((-1, .3), (0, .75), (1, .3)), ((0, .4), (1, .15), (-1, .1)))):
            for d_, w in prof:
                had[layer][i + d_] = had[layer].get(i + d_, 0) + e * w
    buckets, gap = {}, 0.9
    for (r0, r1), ee in [(R_EM, em)] + list(zip(R_HAD, had)):
        for i, e in ee.items():
            if e < 0.1:
                continue
            op = round(min(1.0, 0.2 + 0.8 * e) * 10) / 10
            buckets.setdefault(op, []).append(sector(c, r0 + 1.2, r1 - 1.2, i * SEG + gap / 2, (i + 1) * SEG - gap / 2))
    inner = "".join(f'<path d="{"".join(v)}" fill-opacity="{f(op)}"/>' for op, v in sorted(buckets.items()))
    c_attr = f' class="{cls}"' if cls else ""
    return f'<g{c_attr} fill="{k["amber"]}">{inner}</g>'


def ring(k, c, r, color, sw=1.6, cls="", fill=None, extra=""):
    c_attr = f' class="{cls}"' if cls else ""
    return (f'<circle{c_attr} cx="{f(c[0])}" cy="{f(c[1])}" r="{f(r)}" fill="{fill or k["bg0"]}" '
            f'stroke="{color}" stroke-width="{f(sw)}"{extra}/>')


def gripper(p, a, spread, lf, open_deg):
    """Two-finger gripper at palm point p, pointing along a (deg)."""
    pa, pb = along(p, a - 90, spread), along(p, a + 90, spread)
    return (f"M{pt(pa)}L{pt(pb)}M{pt(pa)}L{pt(along(pa, a - open_deg, lf))}"
            f"M{pt(pb)}L{pt(along(pb, a + open_deg, lf))}")


# ------------------------------------------------------------------------------------------------
# motion: one short replay per card, repeated a few times after load, then everything rests.
# Every keyframe list starts and ends at the resting state, which is also frame 0 and the
# prefers-reduced-motion state.
# ------------------------------------------------------------------------------------------------
PERIOD = 7.0      # one replay every PERIOD seconds...
REPEATS = 3       # ...this many times, then the image is static (no CPU)
START = 1.0       # first replay starts this long after the image loads


def anim(name):
    return f"animation:{name} {f(PERIOD)}s {f(START)}s {REPEATS} both"


def kf(name, frames):
    return f"@keyframes {name}{{" + "".join(f"{f(100 * t / PERIOD)}%{{{css}}}" for t, css in frames) + "}"


def servo_css(uid, joints):
    """Arm replay: each joint turns a few degrees and back, staggered down the chain."""
    io = "cubic-bezier(.55,0,.3,1)"
    out = []
    for i, (p, deg) in enumerate(joints, start=1):
        lag = 0.1 * (i - 1)
        n = f"{uid}a{i}"
        out.append(f".{n}{{transform-box:view-box;transform-origin:{f(p[0])}px {f(p[1])}px;{anim(n)}}}"
                   + kf(n, [(0, f"transform:rotate(0);animation-timing-function:{io}"),
                            (lag, f"transform:rotate(0);animation-timing-function:{io}"),
                            (lag + 0.7, f"transform:rotate({f(deg)}deg);animation-timing-function:{io}"),
                            (lag + 1.5, "transform:rotate(0)"), (PERIOD, "transform:rotate(0)")]))
    return "".join(out)


def grip_css(uid, fingers):
    """Gripper replay: fingers close and reopen once (fingers = [(pivot, closing_deg)])."""
    io = "cubic-bezier(.55,0,.3,1)"
    out = []
    for j, (p, deg) in enumerate(fingers):
        n = f"{uid}f{j}"
        out.append(f".{n}{{transform-box:view-box;transform-origin:{f(p[0])}px {f(p[1])}px;{anim(n)}}}"
                   + kf(n, [(0, f"transform:rotate(0);animation-timing-function:{io}"),
                            (0.5, f"transform:rotate(0);animation-timing-function:{io}"),
                            (0.85, f"transform:rotate({f(deg)}deg);animation-timing-function:{io}"),
                            (1.35, f"transform:rotate({f(deg)}deg);animation-timing-function:{io}"),
                            (1.75, "transform:rotate(0)"), (PERIOD, "transform:rotate(0)")]))
    return "".join(out)


# ------------------------------------------------------------------------------------------------
# glyphs: fn(k, theme, uid) -> (svg, css, defs), card coordinates
# ------------------------------------------------------------------------------------------------
def event(k, uid, tracks, deposits, sv=None, cone=None, fat=None, extra=""):
    """Physics glyph: detector slice + jet cone + tracks + cells, with a hit-pulse replay."""
    c = PV_XY
    o = [detector_slice(k)]
    rc = R_HAD[-1][1]
    if cone:
        ax, half = cone
        o.append(f'<path d="M{pt(c)}L{pt(P(c, rc, ax - half))}A{f(rc)} {f(rc)} 0 0 1 {pt(P(c, rc, ax + half))}Z" '
                 f'fill="{k["green"]}" fill-opacity=".07"/>')
    if fat:
        ax, half = fat
        o.append(f'<path d="M{pt(c)}L{pt(P(c, rc, ax - half))}A{f(rc)} {f(rc)} 0 0 1 {pt(P(c, rc, ax + half))}Z" '
                 f'fill="{k["green"]}" fill-opacity=".05"/>')
        o.append(f'<path d="M{pt(P(c, 9, ax - half))}L{pt(P(c, rc + 3, ax - half))}M{pt(P(c, 9, ax + half))}'
                 f'L{pt(P(c, rc + 3, ax + half))}" fill="none" stroke="{k["green"]}" stroke-opacity=".6" '
                 f'stroke-width="1" stroke-dasharray="3 3"/>')
    o.append(cells(k, deposits, cls=f"{uid}c"))
    o.append(extra)
    tks = [(Arc(orig, phi, R, s, c, R_EM[0], **kw), soft) for (orig, phi, R, s, soft, kw) in tracks]
    hard = "".join(f'<path d="{t.d()}"/>' for t, soft in tks if not soft)
    softd = "".join(f'<path d="{t.d()}"/>' for t, soft in tks if soft)
    o.append(f'<g fill="none" stroke="{k["green"]}" stroke-width="1.7" stroke-linecap="round">{hard}'
             f'<g stroke-width="1.3" stroke-opacity=".7">{softd}</g></g>')
    pulse = "".join(f'<path pathLength="1" d="{t.d()}"/>' for t, soft in tks if not soft)
    o.append(f'<g class="{uid}p" fill="none" stroke="{k["text"]}" stroke-width="2.1" stroke-linecap="round" '
             f'stroke-dasharray=".14 2" stroke-dashoffset=".2">{pulse}</g>')
    o.append(f'<circle cx="{f(c[0])}" cy="{f(c[1])}" r="12" fill="url(#{uid}g)"/>')
    o.append(f'<circle class="{uid}x" cx="{f(c[0])}" cy="{f(c[1])}" r="6" fill="none" stroke="{k["green"]}" '
             f'stroke-width="1.3" opacity="0"/>')
    o.append(f'<circle cx="{f(c[0])}" cy="{f(c[1])}" r="2.5" fill="{k["text"]}"/>')
    if sv:
        o.append(ring(k, sv, 2.3, k["rose"], 1.4))
    ez = "cubic-bezier(.25,.75,.25,1)"
    css = (f".{uid}p{{{anim(uid + 'p')}}}"
           + kf(uid + "p", [(0, f"stroke-dashoffset:.2;animation-timing-function:{ez}"), (0.85, "stroke-dashoffset:-1.2"),
                            (PERIOD, "stroke-dashoffset:-1.2")])
           + f".{uid}c{{{anim(uid + 'c')}}}"
           + kf(uid + "c", [(0, "opacity:1"), (0.38, "opacity:1"), (0.5, "opacity:.3"), (1.5, "opacity:1"),
                            (PERIOD, "opacity:1")])
           + f".{uid}x{{transform-box:fill-box;transform-origin:center;{anim(uid + 'x')}}}"
           + kf(uid + "x", [(0, "opacity:0;transform:scale(.3)"), (0.03, "opacity:1;transform:scale(.4)"),
                            (0.7, "opacity:0;transform:scale(2.4)"), (PERIOD, "opacity:0;transform:scale(2.4)")]))
    defs = (f'<radialGradient id="{uid}g"><stop offset="0" stop-color="{k["green"]}" stop-opacity=".45"/>'
            f'<stop offset="1" stop-color="{k["green"]}" stop-opacity="0"/></radialGradient>')
    return "".join(o), css, defs


def T(orig, phi, R, s, soft=False, **kw):
    return (orig, phi, R, s, soft, kw)


def glyph_bjet(k, theme, uid):
    """b-jet: narrow anti-kt R=0.4 cone, three tracks from a displaced secondary vertex (rose)."""
    ax = -52.0
    sv = P(PV_XY, 9.5, ax)
    tracks = [T(sv, ax + 5, 200, +1), T(sv, ax - 5, 150, -1), T(sv, ax + 1, 420, -1),
              T(PV_XY, ax - 12, 120, +1), T(PV_XY, ax + 13, 230, -1),
              T(PV_XY, -10, 70, -1, True), T(PV_XY, -86, 55, +1, True), T(PV_XY, -135, 9, +1, True, amax=290)]
    return event(k, uid, tracks, [(ax, 1.0), (ax + 6, .35), (-8, .25)], sv=sv, cone=(ax, math.degrees(0.4)))


def glyph_topjet(k, theme, uid):
    """Top jet: one large-R jet (dashed edges) with three prongs, three calorimeter clusters."""
    prongs = (-27.0, -50.0, -73.0)
    tracks = []
    for i, a in enumerate(prongs):
        tracks += [T(PV_XY, a + 2.5, 260 + 50 * i, +1), T(PV_XY, a - 2.2, 190 + 40 * i, -1)]
    tracks[2:2] = [T(PV_XY, -50 + 0.5, 700, -1)]
    tracks += [T(PV_XY, -96, 44, +1, True), T(PV_XY, -150, 10, +1, True, amax=280)]
    return event(k, uid, tracks, [(a, .75) for a in prongs], fat=(-50.0, 35.0))


def glyph_diphoton(k, theme, uid):
    """H -> gamma gamma: two neutral photons (dashed, no track) into EM clusters, a few soft tracks."""
    c = PV_XY
    photons = "".join(f"M{pt(P(c, 5, a))}L{pt(P(c, R_EM[0] + 6, a))}" for a in (-20, -80))
    extra = (f'<path d="{photons}" fill="none" stroke="{k["amber"]}" stroke-width="1.6" stroke-dasharray="3 3" '
             f'stroke-linecap="round"/>')
    tracks = [T(c, -40, 90, -1), T(c, -55, 140, +1), T(c, -10, 70, -1, True), T(c, -86, 55, +1, True)]
    deps = [(-20, 1.1), (-80, 1.1)]
    return event(k, uid, tracks, deps, extra=extra)


def arm_chain(k, uid, S, angles, lengths, hull, hull_w, spread, lf, open_deg, radii, servo, grip_deg):
    """Shoulder S -> elbow -> wrist -> palm with a two-finger gripper, as nested joint groups (like the banner).
    Hull (soft tint) and skeleton reuse the same joint classes, so they move together in the replay.
    Returns (hull_svg, skeleton_svg, css)."""
    v = k["violet"]
    (a1, a2, a3), (L1, L2, L3) = angles, lengths
    E = along(S, a1, L1)
    Wr = along(E, a2, L2)
    G = along(Wr, a3, L3)
    pa, pb = along(G, a3 - 90, spread), along(G, a3 + 90, spread)
    hl = (f'<g class="{uid}a1"><path d="M{pt(S)}L{pt(E)}"/><g class="{uid}a2"><path d="M{pt(E)}L{pt(Wr)}"/>'
          f'<g class="{uid}a3"><path d="M{pt(Wr)}L{pt(G)}"/></g></g></g>')
    hull_svg = f'<g fill="none" stroke="{hull}" stroke-width="{f(hull_w)}" stroke-linecap="round">{hl}</g>'
    fing = (f'<path class="{uid}f0" d="M{pt(pa)}L{pt(along(pa, a3 - open_deg, lf))}"/>'
            f'<path class="{uid}f1" d="M{pt(pb)}L{pt(along(pb, a3 + open_deg, lf))}"/>')
    rs, re_, rw = radii
    sk = (f'<g class="{uid}a1"><path d="M{pt(S)}L{pt(E)}"/>'
          f'<g class="{uid}a2"><path d="M{pt(E)}L{pt(Wr)}"/>'
          f'<g class="{uid}a3"><path d="M{pt(Wr)}L{pt(G)}M{pt(pa)}L{pt(pb)}"/>{fing}</g>'
          f'{ring(k, Wr, rw, v, 1.5)}</g>{ring(k, E, re_, v, 1.5)}</g>')
    skel = (f'<g fill="none" stroke="{v}" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">{sk}</g>'
            + ring(k, S, rs, v, 1.6))
    css = (servo_css(uid, [(S, servo[0]), (E, servo[1]), (Wr, servo[2])])
           + grip_css(uid, [(pa, grip_deg), (pb, -grip_deg)]))
    return hull_svg, skel, css


def glyph_humanoid(k, theme, uid):
    """The banner's wheeled dual-arm humanoid, scaled down and mirrored: it reaches left, into the card."""
    s = 0.44
    v = k["violet"]
    hull = mix(k["violet"], k["bg0"], HULL_A[theme])
    S = (364.0, 38.0)                                  # shoulder

    def R(x, y):                                       # banner units relative to the shoulder, mirrored
        return (S[0] - x * s, S[1] + y * s)

    def rect(x0, y0, w, h, rx):                        # banner-unit rect, mirrored
        a = R(x0 + w, y0)
        return f'<rect x="{f(a[0])}" y="{f(a[1])}" width="{f(w * s)}" height="{f(h * s)}" rx="{f(rx * s)}" fill="{hull}"/>'

    o = []
    floor = R(0, 172)[1]
    xa, xb = R(84, 0)[0], R(-70, 0)[0]
    hatch = "".join(f"M{f(x)} {f(floor + 1)}l-3.5 4.5" for x in range(int(xa) + 5, int(xb) + 1, 6))
    o.append(f'<path d="M{f(xa)} {f(floor)}H{f(xb)}{hatch}" stroke="{k["line"]}" stroke-width="1.1" fill="none"/>')
    B0, K, HP, N = R(-8, 124), R(19, 88), R(-2, 54), R(1, -24)
    o.append(rect(-50, 116, 96, 34, 11))                # chassis
    o.append(f'<path d="M{pt(B0)}L{pt(K)}L{pt(HP)}" fill="none" stroke="{hull}" stroke-width="{f(16 * s)}" '
             f'stroke-linecap="round" stroke-linejoin="round"/>')
    o.append(rect(-18, -18, 35, 68, 12))                # chest
    o.append(rect(-15, -53, 39, 27, 9))                 # head
    o.append(f'<path d="M{pt(B0)}L{pt(K)}L{pt(HP)}L{pt(S)}L{pt(N)}" fill="none" stroke="{v}" stroke-width="1.8" '
             f'stroke-linejoin="round" stroke-linecap="round"/>')
    o.append(ring(k, K, 2.4, v, 1.4) + ring(k, HP, 2.4, v, 1.4) + ring(k, B0, 2, v, 1.3) + ring(k, N, 1.9, v, 1.3))
    o.append(ring(k, R(15, -39.5), 1.9, v, 1.3))       # camera
    for wx in (-28, 25):
        c = R(wx, 160)
        o.append(ring(k, c, 12 * s, v, 1.5) + f'<circle cx="{f(c[0])}" cy="{f(c[1])}" r="1.2" fill="{v}"/>')
    # reaching arm (nested joint groups for the servo replay)
    hl, sk, css = arm_chain(k, uid, S, (-150.0, -176.0, 179.0), (68 * s, 60 * s, 12 * s), hull, 13 * s,
                            3.2, 15 * s * 1.15, 16, (3.1, 2.6, 2.3), (8.0, -10.0, 8.0), 14.0)
    o += [hl, sk]
    # planner goal ahead of the gripper (an RViz-style target: ring + crosshair, dotted approach)
    tip = along(along(along(S, -150.0, 68 * s), -176.0, 60 * s), 179.0, 12 * s + 15 * s * 1.15)
    goal = (tip[0] - 26, tip[1] + 9)
    ticks = "".join(f"M{pt(along(goal, a, 6))}L{pt(along(goal, a, 9))}" for a in (0, 90, 180, 270))
    o.append(f'<path d="M{pt(along(tip, ang(tip, goal), 4))}L{pt(along(goal, ang(goal, tip), 7.5))}" fill="none" '
             f'stroke="{v}" stroke-opacity=".7" stroke-width="1.3" stroke-dasharray="0 3.4" stroke-linecap="round"/>')
    o.append(f'<circle cx="{f(goal[0])}" cy="{f(goal[1])}" r="4.2" fill="none" stroke="{v}" stroke-width="1.3"/>'
             f'<path d="{ticks}" stroke="{v}" stroke-width="1.3" stroke-linecap="round"/>'
             f'<circle cx="{f(goal[0])}" cy="{f(goal[1])}" r="1.2" fill="{v}"/>')
    return "".join(o), css, ""


def glyph_simarm(k, theme, uid):
    """Simulation: a manipulator on a perspective floor grid, gripper over a cube."""
    hull = mix(k["violet"], k["bg0"], HULL_A[theme])
    o = []
    y_top, y_bot, vp = 70.0, 112.0, (330.0, 14.0)
    g = []
    for i in range(-9, 10):
        xb = vp[0] + i * 26
        t = (y_top - vp[1]) / (y_bot - vp[1])
        g.append(f"M{f(vp[0] + (xb - vp[0]) * t)} {f(y_top)}L{f(xb)} {f(y_bot)}")
    # rows: evenly spaced in depth -> y = vp + h / z
    for z in (1.0, 1.25, 1.6, 2.1, 2.85):
        y = vp[1] + (y_bot - vp[1]) / z
        if y_top - 0.1 <= y <= y_bot:
            g.append(f"M200 {f(y)}H420")
    o.append(f'<path d="{"".join(g)}" fill="none" stroke="url(#{uid}gf)" stroke-width="1"/>')
    # the object
    cx, cy, cs, dx, dy = 352.0, 82.0, 14.0, 6.0, -5.0
    o.append(f'<path d="M{f(cx)} {f(cy)}h{f(cs)}v{f(cs)}h{f(-cs)}ZM{f(cx)} {f(cy)}l{f(dx)} {f(dy)}h{f(cs)}l{f(-dx)} {f(-dy)}'
             f'M{f(cx + cs)} {f(cy)}l{f(dx)} {f(dy)}v{f(cs)}l{f(-dx)} {f(-dy)}" fill="{k["bg1"]}" stroke="{k["muted"]}" '
             f'stroke-width="1.1" stroke-linejoin="round"/>')
    base, sh = (304.0, 98.0), (304.0, 70.0)
    o.append(f'<rect x="{f(base[0] - 13)}" y="{f(base[1] - 6)}" width="26" height="13" rx="4.5" fill="{hull}"/>')
    o.append(f'<path d="M{pt(base)}L{pt(sh)}" stroke="{hull}" stroke-width="9" stroke-linecap="round"/>')
    hl, sk, css = arm_chain(k, uid, sh, (-64.0, 24.0, 90.0), (40.0, 40.0, 7.0), hull, 9, 4.2, 7.5, 14,
                            (3.3, 2.9, 2.5), (-7.0, 9.0, -6.0), 12.0)
    o += [hl, f'<path d="M{pt(base)}L{pt(sh)}" fill="none" stroke="{k["violet"]}" stroke-width="1.9" '
                 f'stroke-linecap="round"/>', sk, ring(k, base, 2.4, k["violet"], 1.4)]
    defs = (f'<linearGradient id="{uid}gf" gradientUnits="userSpaceOnUse" x1="226" y1="0" x2="300" y2="0">'
            f'<stop offset="0" stop-color="{k["line"]}" stop-opacity="0"/>'
            f'<stop offset="1" stop-color="{k["line"]}"/></linearGradient>')
    return "".join(o), css, defs


def glyph_window(k, theme, uid):
    """Agents: an app window with a cursor."""
    x, y, w, h = 292.0, 16.0, 104.0, 78.0
    o = [f'<rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}" rx="8" fill="{k["bg1"]}" stroke="{k["muted"]}" '
         f'stroke-opacity=".6" stroke-width="1.2"/>',
         f'<path d="M{f(x)} {f(y + 14)}H{f(x + w)}" stroke="{k["line"]}" stroke-width="1"/>',
         "".join(f'<circle cx="{f(x + 10 + 7 * i)}" cy="{f(y + 7)}" r="2" fill="{k["muted"]}" fill-opacity=".6"/>'
                 for i in range(3))]
    lines = "".join(f"M{f(x + 11)} {f(y + 28 + 10 * i)}h{f(L)}" for i, L in enumerate((54, 74, 42, 62)))
    o.append(f'<path d="{lines}" stroke="{k["line"]}" stroke-width="3.2" stroke-linecap="round"/>')
    o.append(f'<path d="M{f(x + 11)} {f(y + 28)}h30" stroke="{k["amber"]}" stroke-opacity=".85" stroke-width="3.2" '
             f'stroke-linecap="round"/>')
    cx, cy = x + 74, y + 50
    o.append(f'<circle cx="{f(cx)}" cy="{f(cy)}" r="7.5" fill="none" stroke="{k["amber"]}" stroke-width="1.2"/>')
    o.append(f'<path d="M{f(cx)} {f(cy)}v17l4.6-4.3 3.2 7.1 3.1-1.4-3.2-6.9 6.1-.5Z" fill="{k["bg0"]}" '
             f'stroke="{k["text"]}" stroke-width="1.3" stroke-linejoin="round"/>')
    return "".join(o), "", ""


def glyph_globe(k, theme, uid):
    c, r = (344.0, 58.0), 44.0
    o = [f'<circle cx="{f(c[0])}" cy="{f(c[1])}" r="{f(r)}" fill="{k["bg1"]}" stroke="{k["muted"]}" '
         f'stroke-opacity=".7" stroke-width="1.2"/>']
    mer = "".join(f'<ellipse cx="{f(c[0])}" cy="{f(c[1])}" rx="{f(r * q)}" ry="{f(r)}"/>' for q in (0.35, 0.75))
    par = "".join(f"M{f(c[0] - math.sqrt(r * r - yy * yy))} {f(c[1] + yy)}h{f(2 * math.sqrt(r * r - yy * yy))}"
                  for yy in (-22, 0, 22))
    o.append(f'<g fill="none" stroke="{k["line"]}" stroke-width="1">{mer}<path d="{par}"/></g>')
    o.append(f'<path d="{arc_d(c, r + 8, -160, -40)}" fill="none" stroke="{k["green"]}" stroke-width="1.4" '
             f'stroke-dasharray="2 3" stroke-linecap="round"/>')
    o.append(f'<circle cx="{f(c[0] + 15)}" cy="{f(c[1] - 13)}" r="2.6" fill="{k["amber"]}"/>')
    return "".join(o), "", ""


GLYPHS = {"humanoid": glyph_humanoid, "sim-arm": glyph_simarm, "b-jet": glyph_bjet, "top-jet": glyph_topjet,
          "diphoton": glyph_diphoton, "window": glyph_window, "globe": glyph_globe}

# ------------------------------------------------------------------------------------------------
# project card
# ------------------------------------------------------------------------------------------------
CW, CH = 420.0, 244.0
PAD = 26.0
RX = 14.0
TITLE_SIZE, TITLE_MIN = 30.0, 24.0
BLURB_SIZE, BLURB_LH = 14.5, 20.0
KICK_SIZE, KICK_TR = 11.5, 0.06
META_SIZE, META_TR = 11.5, 0.03


def kicker_parts(p):
    """kicker minus the language segment (the footer already shows the language)."""
    segs = [s.strip() for s in p["kicker"].split("·")]
    lang = p["lang"].lower()
    return [s for i, s in enumerate(segs) if not (i > 0 and s == lang)]


def card(p, theme, uid="g"):
    k = TOKENS[theme]
    acc = k[ACCENT[p["category"]]]
    o, css = [], []
    o.append(f'<rect x=".6" y=".6" width="{f(CW - 1.2)}" height="{f(CH - 1.2)}" rx="{f(RX)}" fill="{k["bg0"]}" '
             f'stroke="{k["line"]}" stroke-width="1.2"/>')
    gsvg, gcss, gdefs = GLYPHS[p["glyph"]](k, theme, uid)
    o.append(f'<g clip-path="url(#{uid}k)">{gsvg}</g>')
    css.append(gcss)
    defs = (f'<defs><clipPath id="{uid}k"><rect x="1.2" y="1.2" width="{f(CW - 2.4)}" height="{f(CH - 2.4)}" '
            f'rx="{f(RX - .6)}"/></clipPath>{gdefs}</defs>')
    # kicker: category (accent) over provenance (muted), top left
    segs = kicker_parts(p)
    kd, _ = tp(segs[0], "mono-500", KICK_SIZE, PAD, 38, tracking=KICK_TR)
    o.append(f'<path d="{kd}" fill="{acc}"/>')
    rest = " · ".join(segs[1:])
    if rest:
        rd, _ = tp(rest, "mono-400", KICK_SIZE, PAD, 56, tracking=KICK_TR)
        o.append(f'<path d="{rd}" fill="{k["muted"]}"/>')
    # title: fit to the width (shrink down to TITLE_MIN)
    avail = CW - 2 * PAD
    size = TITLE_SIZE
    wt = tw(p["title"], "grotesk-700", size, -0.01)
    if wt > avail:
        size = max(TITLE_MIN, size * avail / wt)
    td, wt = tp(p["title"], "grotesk-700", size, PAD - 1, 142, tracking=-0.01)
    if wt > avail + 0.5:
        raise SystemExit(f"title too wide for the card: {p['title']!r} ({wt:.0f} > {avail:.0f})")
    o.append(f'<path d="{td}" fill="{k["text"]}"/>')
    # blurb: at most two lines (shrinks a little if needed)
    bs = BLURB_SIZE
    lines = wrap(p["blurb"], "grotesk-400", bs, avail)
    while len(lines) > 2 and bs > 12.5:
        bs -= 0.5
        lines = wrap(p["blurb"], "grotesk-400", bs, avail)
    if len(lines) > 2:
        raise SystemExit(f"blurb too long for two lines: {p['blurb']!r}")
    bd = "".join(rich_path(ln, "grotesk-400", bs, PAD, 171 + i * BLURB_LH) for i, ln in enumerate(lines))
    o.append(f'<path d="{bd}" fill="{k["muted"]}"/>')
    # footer: language dot + name (left), repo name + arrow (right)
    fy = CH - 24
    o.append(f'<circle cx="{f(PAD + 4.5)}" cy="{f(fy - 4)}" r="4.5" fill="{acc}"/>')
    ld, _ = tp(p["lang"].lower(), "mono-400", META_SIZE, PAD + 15, fy, tracking=META_TR)
    ad, aw = tp("↗", "mono-400", META_SIZE + 1, CW - PAD, fy, anchor="end")
    rd, _ = tp(p["repo"], "mono-400", META_SIZE, CW - PAD - aw - 5, fy, anchor="end", tracking=META_TR)
    o.append(f'<path d="{ld}{rd}" fill="{k["muted"]}"/>')
    o.append(f'<path d="{ad}" fill="{acc}"/>')
    css.append(REDUCED)
    return svg_doc(CW, CH, p["alt"], "".join(c for c in css if c), "".join(x for x in o if x), defs)


# ------------------------------------------------------------------------------------------------
# link pills
# ------------------------------------------------------------------------------------------------
PH = 44.0
PILL_TEXT = 15.0


def pill_icon(k, theme, kind, c):
    """14-unit radius badge with a line-art icon."""
    x, y = c
    if kind in ("x", "in"):   # a plain letterform badge (no copied brand logos)
        bd = f'<circle cx="{f(x)}" cy="{f(y)}" r="14" fill="{k["bg1"]}" stroke="{k["line"]}" stroke-width="1"/>'
        xd, _ = tp("X" if kind == "x" else "in", "mono-700", 16.5 if kind == "x" else 14.5, x, y + 5.5, anchor="middle")
        return bd + f'<path d="{xd}" fill="{k["text"]}"/>'
    # "arm": a tiny kinematic chain in a violet-tint badge
    hull = mix(k["violet"], k["bg0"], HULL_A[theme] + 0.04)
    v = k["violet"]
    b, e, w = (x - 6, y + 6.5), (x - 2.5, y - 5), (x + 6.5, y - 1)
    g = gripper(w, ang(e, w), 2.6, 3.6, 22)
    return (f'<circle cx="{f(x)}" cy="{f(y)}" r="14" fill="{hull}"/>'
            f'<path d="M{pt(b)}L{pt(e)}L{pt(w)}{g}" fill="none" stroke="{v}" stroke-width="1.6" '
            f'stroke-linecap="round" stroke-linejoin="round"/>'
            + ring(k, b, 2.1, v, 1.4, fill=hull) + ring(k, e, 2.1, v, 1.4, fill=hull))


def pill(label, icon, aria, theme):
    k = TOKENS[theme]
    lw = tw(label, "mono-500", PILL_TEXT, 0.02)
    aw = tw("↗", "mono-400", PILL_TEXT)
    w = math.ceil(8 + 28 + 11 + lw + 10 + aw + 16)
    o = [f'<rect x=".6" y=".6" width="{f(w - 1.2)}" height="{f(PH - 1.2)}" rx="{f((PH - 1.2) / 2)}" fill="{k["bg0"]}" '
         f'stroke="{k["line"]}" stroke-width="1.2"/>']
    o.append(pill_icon(k, theme, icon, (8 + 14, PH / 2)))
    td, _ = tp(label, "mono-500", PILL_TEXT, 8 + 28 + 11, PH / 2 + 5.3, tracking=0.02)
    o.append(f'<path d="{td}" fill="{k["text"]}"/>')
    ad, _ = tp("↗", "mono-400", PILL_TEXT, w - 16, PH / 2 + 5.3, anchor="end")
    o.append(f'<path d="{ad}" fill="{k["muted"]}"/>')
    return svg_doc(w, PH, aria, "", "".join(o))


# ------------------------------------------------------------------------------------------------
# divider: a thin track from a vertex (left) to a joint (right), one pulse travelling along it
# ------------------------------------------------------------------------------------------------
DW, DH = 1200.0, 28.0
D_PERIOD = 7.0     # one pulse every D_PERIOD seconds...
D_TRAVEL = 3.2     # ...taking this long to cross...
D_REPEATS = 3      # ...this many times, then the divider is static (an endless loop costs ~3% CPU per image)
D_START = 0.8


def divider(theme):
    k = TOKENS[theme]
    y = DH / 2
    x0, x1 = 12.0, DW - 14.0
    jr = 4.2
    o, css = [], []
    defs = (f'<defs><linearGradient id="dg" gradientUnits="userSpaceOnUse" x1="{f(x0)}" y1="0" x2="{f(x1)}" y2="0">'
            f'<stop offset="0" stop-color="{k["green"]}"/><stop offset=".55" stop-color="{k["green"]}"/>'
            f'<stop offset="1" stop-color="{k["violet"]}"/></linearGradient></defs>')
    track = f"M{f(x0 + 4)} {f(y)}H{f(x1 - jr - 3)}"
    o.append(f'<path d="{track}" stroke="{k["line"]}" stroke-width="1.2"/>')
    o.append(f'<path d="{track}" stroke="url(#dg)" stroke-opacity=".28" stroke-width="1.2"/>')
    # tracker hits: short ticks, denser near the vertex
    xs, x, i = [], x0 + 26, 0
    while x < x1 - 60:
        xs.append(x)
        i += 1
        x += 18 + i * 2.1 + (7 if i % 3 == 0 else 0)
    ticks = "".join(f"M{f(t)} {f(y - 3.5)}v7" for t in xs)
    o.append(f'<path d="{ticks}" stroke="{k["line"]}" stroke-width="1.2"/>')
    # vertex + joint ring
    o.append(f'<circle cx="{f(x0 + 1)}" cy="{f(y)}" r="2.6" fill="{k["green"]}"/>')
    o.append(f'<circle class="dj" cx="{f(x1 - 1)}" cy="{f(y)}" r="{f(jr)}" fill="none" stroke="{k["violet"]}" '
             f'stroke-width="1.6"/>')
    # pulse: three dashes of the full-width gradient stroke, heads aligned (a comet with a tail)
    for n, (L, sw, op) in enumerate(((0.12, 1.6, .22), (0.05, 1.8, .5), (0.01, 2.4, 1))):
        o.append(f'<path class="dp d{n}" pathLength="1" d="{track}" stroke="url(#dg)" stroke-width="{f(sw)}" '
                 f'stroke-opacity="{f(op)}" stroke-linecap="round" stroke-dasharray="{f(L)} 3" '
                 f'stroke-dashoffset="{f(L)}"/>')
        # head runs 0 -> 1.14 (past the end by more than the longest tail), so rest states show no dash
        css.append(f".d{n}{{animation-name:d{n}}}@keyframes d{n}{{0%{{stroke-dashoffset:{f(L)}}}"
                   f"{f(100 * D_TRAVEL / D_PERIOD)}%,100%{{stroke-dashoffset:{f(L - 1.14)}}}}}")
    t_arr = D_TRAVEL / 1.14 / D_PERIOD * 100      # when the head reaches the joint ring
    timing = f"{f(D_PERIOD)}s linear {f(D_START)}s {D_REPEATS} both"
    css.insert(0, f".dp{{animation:{timing}}}"
                  f".dj{{transform-box:fill-box;transform-origin:center;animation:dj {timing}}}")
    css.append(f"@keyframes dj{{0%,{f(t_arr - 1.5)}%{{transform:scale(1)}}{f(t_arr + 1)}%{{transform:scale(1.45)}}"
               f"{f(t_arr + 5)}%,100%{{transform:scale(1)}}}}")
    css.append(REDUCED)
    return svg_doc(DW, DH, "section divider", "".join(css), "".join(o), defs)


# ------------------------------------------------------------------------------------------------
def write(path, s):
    with open(path, "w") as fh:
        fh.write(s)
    return len(s.encode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=ASSETS)
    ap.add_argument("--card-repeats", help=f"card replay count, a number or 'infinite' (default {REPEATS})")
    ap.add_argument("--divider-repeats", help=f"divider pulse count, a number or 'infinite' (default {D_REPEATS})")
    a = ap.parse_args()
    if a.card_repeats:
        globals()["REPEATS"] = a.card_repeats
    if a.divider_repeats:
        globals()["D_REPEATS"] = a.divider_repeats
    os.makedirs(a.out, exist_ok=True)
    report = []
    for theme in ("dark", "light"):
        for p in (p for p in PROJECTS if p["repo"] in FEATURED):
            fn = os.path.join(a.out, f"card-{p['repo']}-{theme}.svg")
            report.append((fn, write(fn, card(p, theme))))
        for name, label, icon, aria in LINKS:
            fn = os.path.join(a.out, f"link-{name}-{theme}.svg")
            report.append((fn, write(fn, pill(label, icon, aria, theme))))
        fn = os.path.join(a.out, f"divider-{theme}.svg")
        report.append((fn, write(fn, divider(theme))))
    for fn, n in report:
        print(f"{n:7d}  {os.path.relpath(fn, REPO)}")


if __name__ == "__main__":
    main()
