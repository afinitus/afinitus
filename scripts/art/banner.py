#!/usr/bin/env python3
"""Profile banner: "particles -> robots".

Left: a transverse (r-phi) collider event display in the style of ATLAS's Atlantis viewer.
Charged tracks curl out of the primary vertex in the solenoid field, calorimeter cells light up
where the jets land (box size ~ energy, like Atlantis), and a b-jet carries a displaced
secondary vertex (the one rose dot). One muon leaves the detector. Outside the solenoid it
flies straight, and that line runs into the shoulder of a wheeled dual-arm humanoid (drawn
RViz-style: soft hulls under a crisp kinematic skeleton), whose arm reaches toward the name.
Colour is a legend: green = particles, violet = robot, amber = energy.

Animation (CSS only, so prefers-reduced-motion stops all of it):
  hold the complete picture  ->  rewind (arm energy drains back down the muon into the
  vertex, tracks retract, the arm relaxes into a dim rest pose)  ->  collision flash, tracks
  and cells replay, the muon runs into the shoulder and energises the arm joint by joint,
  the arm lifts into its reach  ->  the head glances at its hand  ->  rest.
MODE "once" (default) plays that a single time and then stays still (no CPU once settled).
MODE "loop" repeats it every LOOP_T seconds, with a short muon pulse during the long rest.
Frame 0, the end state and the reduced-motion / no-CSS state are all the same complete picture.

GitHub serves README SVGs with a CSP that blocks fonts, so every glyph is outlined with
text2path.py (HarfBuzz shaping, OFL fonts in ./fonts).

Usage, from the repo root:
    python3 scripts/art/banner.py              # writes assets/banner-dark.svg, assets/banner-light.svg
    python3 scripts/art/banner.py --mode loop  # same files, looping variant (default: MODE below)
    python3 scripts/art/banner.py --out DIR    # write somewhere else
Needs: pip install fonttools uharfbuzz
"""
import argparse
import math
import os
import re
import sys
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
try:
    from text2path import text_path  # noqa: E402
except ImportError as err:  # fonttools / uharfbuzz missing
    raise SystemExit(f"{err}\nbanner.py needs fonttools and uharfbuzz:  pip install fonttools uharfbuzz")

# =========================================================================================
# Copy: edit freely. The layout re-measures everything (see layout_text()): the name and tagline
# must fit (the script stops with a message if not); the subline shrinks to fit.
# ROLE / COMPANY / CITY also feed the <title> and aria-label; SUBLINE may be overwritten directly.
# =========================================================================================
NAME = "Nishank Gite"
ROLE, COMPANY, CITY = "Co-Founder", "Nirvana Robotics", "New York"
SUBLINE = " · ".join((ROLE, COMPANY, CITY))  # Co-Founder · Nirvana Robotics · New York
# Tagline (kicker) above the name, colour-coded like the art: green = particles, violet = robots.
# Parts are (text, token); TAGLINE = () drops it.
TAGLINE = ()  # optional kicker above the name: ((text, token), ...)
# Decorative micro-labels (unreadable on phones by design).
CORNER_LABEL = ()  # optional top-right micro-label: ((text, token), ...)
FOOT_LABEL = ()  # optional bottom-left micro-label: ((text, token), ...)

TITLE = f"{NAME} · {ROLE}, {COMPANY} · {CITY}"
DESCRIPTION = (f"{NAME}, {ROLE} of {COMPANY}, {CITY}. Illustration: a particle-detector event display "
               "whose muon track leaves the detector and becomes the arm of a wheeled humanoid robot "
               "reaching toward the name.")

MODE = "once"      # "once": play once, then rest on the complete picture. "loop": repeat forever.
LOOP_T = 18.0      # loop length in seconds (MODE "loop" only)

# =========================================================================================
# Canvas, tokens, type
# =========================================================================================
W, H = 1200, 400

TOKENS = {
    "dark": dict(bg0="#0b0f14", bg1="#12171e", line="#21262d", text="#e6edf3", muted="#8b949e",
                 green="#3fb950", violet="#a78bfa", amber="#fbbf24", rose="#fb7185"),
    "light": dict(bg0="#fbfcfe", bg1="#f3f5f7", line="#d8dee4", text="#1f2328", muted="#59636e",
                  green="#1a7f37", violet="#7c3aed", amber="#d97706", rose="#e11d48"),
}
# per-theme tuning (opacities of existing tokens; no new hues)
THEME = {
    "dark": dict(hull=0.16, grid=0.8, cell_op=(0.62, 1.0)),
    "light": dict(hull=0.11, grid=0.72, cell_op=(0.42, 1.0)),
}

INK_X = 558.0          # left ink edge shared by tagline, name and subline (optically aligned)
NAME_Y, NAME_SIZE = 212.0, 102       # baseline; cap height = 0.7 * size (71 units = 21 px on a 360 px phone)
SUB_SIZE, SUB_MIN = 23.6, 16.0       # subline shrinks automatically if it would run off the card
SUB_GAP = 50.0                       # name baseline -> subline baseline
KICK_SIZE, KICK_GAP = 15.0, 26.0     # tagline size; its baseline sits KICK_GAP above the name's cap line
RIGHT_PAD = 40.0                     # nothing may end closer than this to the card's right edge
LABEL_SIZE = 11.5


def f(v):
    """compact number: 2 decimals, no trailing zeros"""
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def pt(p):
    return f"{f(p[0])} {f(p[1])}"


def mix(c1, c2, a):
    """c1 over c2 at alpha a, as an opaque hex colour (a tint of c1, not a new hue)."""
    x = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    y = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(a * p + (1 - a) * q):02x}" for p, q in zip(x, y))


# =========================================================================================
# Detector geometry (svg units; angles in degrees, clockwise on screen, 0 = +x)
# =========================================================================================
DS = 0.92                  # detector scale (1 = 169-unit outer radius)
CX, CY = 182.0, 200.0
R_SOL = 75 * DS
R_EM0, R_EM1 = 79 * DS, 95 * DS
R_HAD = tuple(r * DS for r in (99, 110, 121, 132))
NSEG = 64                  # calorimeter phi segmentation
MU_ST = tuple((r * DS, 6.5 * DS) for r in (143, 160))   # muon stations (radius, thickness)
MU_SMALL = 5 * DS          # small sectors sit this much further out


def P(r, a_deg, c=(CX, CY)):
    a = math.radians(a_deg)
    return (c[0] + r * math.cos(a), c[1] + r * math.sin(a))


def along(p, a_deg, L):
    a = math.radians(a_deg)
    return (p[0] + L * math.cos(a), p[1] + L * math.sin(a))


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def ang(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


class Track:
    """Transverse projection of a helix: a circular arc.

    phi: initial direction, R: radius of curvature (~ pT), s=+1 bends clockwise on screen.
    Ends where its distance from the primary vertex reaches r_end, or after amax degrees of turning.
    """

    def __init__(self, origin, phi, R, s, r_end=R_EM0, amax=330.0):
        self.o, self.phi, self.R, self.s = origin, phi, R, s
        n = (-math.sin(math.radians(phi)), math.cos(math.radians(phi)))
        self.c = (origin[0] + s * R * n[0], origin[1] + s * R * n[1])
        self.b0 = math.atan2(origin[1] - self.c[1], origin[0] - self.c[0])
        a, step, hit = 0.0, 0.25, None
        while a < amax:
            if dist(self.at(a + step), (CX, CY)) >= r_end:
                lo, hi = a, a + step
                for _ in range(40):
                    mid = (lo + hi) / 2
                    if dist(self.at(mid), (CX, CY)) >= r_end:
                        hi = mid
                    else:
                        lo = mid
                hit = hi
                break
            a += step
        self.alpha = hit if hit is not None else amax
        self.reaches = hit is not None
        self.end = self.at(self.alpha)
        self.length = self.R * math.radians(self.alpha)

    def at(self, a_deg):
        b = self.b0 + self.s * math.radians(a_deg)
        return (self.c[0] + self.R * math.cos(b), self.c[1] + self.R * math.sin(b))

    def tangent(self, a_deg):
        return self.phi + self.s * a_deg

    def d(self):
        out = [f"M{pt(self.o)}"]
        sweep = 1 if self.s > 0 else 0
        n = max(1, math.ceil(self.alpha / 150.0))
        for i in range(1, n + 1):
            out.append(f"A{f(self.R)} {f(self.R)} 0 0 {sweep} {pt(self.at(self.alpha * i / n))}")
        return "".join(out)


def sector(r0, r1, a0, a1):
    p0, p1, p2, p3 = P(r0, a0), P(r1, a0), P(r1, a1), P(r0, a1)
    return f"M{pt(p0)}L{pt(p1)}A{f(r1)} {f(r1)} 0 0 1 {pt(p2)}L{pt(p3)}A{f(r0)} {f(r0)} 0 0 0 {pt(p0)}Z"


def cell(r0, r1, a0, a1, s, pad=1.2):
    """a calorimeter cell drawn Atlantis-style: a box inside the cell, scaled by energy (s in 0..1)"""
    rm, am = (r0 + r1) / 2, (a0 + a1) / 2
    hr = ((r1 - r0) / 2 - pad) * s
    ha = ((a1 - a0) / 2 - math.degrees(pad / rm)) * s
    return sector(rm - hr, rm + hr, am - ha, am + ha)


def circle_d(r, c=(CX, CY)):
    return f"M{f(c[0] - r)} {f(c[1])}a{f(r)} {f(r)} 0 1 0 {f(2 * r)} 0a{f(r)} {f(r)} 0 1 0 {f(-2 * r)} 0"


def chamber(r, a_deg, th, hw):
    a = math.radians(a_deg)
    u = (math.cos(a), math.sin(a))
    v = (-u[1], u[0])
    c = P(r, a_deg)
    pts = [(c[0] + sx * th / 2 * u[0] + sy * hw * v[0], c[1] + sx * th / 2 * u[1] + sy * hw * v[1])
           for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    return "M" + "L".join(pt(p) for p in pts) + "Z"


def muon_chambers():
    out = []
    for i in range(16):
        a = i * 22.5
        big = i % 2 == 0
        for r, th in MU_ST:
            rr = r if big else r + MU_SMALL
            hw = rr * math.tan(math.radians(11.25)) * (0.9 if big else 0.6)
            out.append(chamber(rr, a, th, hw))
    return out


# ---- the event (illustrative, hand-tuned; radii of curvature scale with the detector) ----
PV = (CX, CY)
JET1 = -127.0   # b-jet (up-left)
JET2 = 57.0     # recoil jet (down-right)
SV = P(9.0 * DS, JET1)  # displaced secondary vertex (b-hadron decay)

TRACKS = [
    ("j1", Track(SV, JET1 + 4, 250 * DS, +1)),
    ("j1", Track(SV, JET1 - 5, 180 * DS, -1)),
    ("j1", Track(SV, JET1 + 0.5, 460 * DS, -1)),
    ("j1", Track(PV, JET1 - 9, 140 * DS, +1)),
    ("j1", Track(PV, JET1 + 10, 320 * DS, -1)),
    ("j2", Track(PV, JET2 - 3, 280 * DS, -1)),
    ("j2", Track(PV, JET2 + 6, 160 * DS, +1)),
    ("j2", Track(PV, JET2 - 9, 560 * DS, +1)),
    ("j2", Track(PV, JET2 + 2, 210 * DS, -1)),
    ("s", Track(PV, 158, 24 * DS, +1, amax=300)),    # loopers
    ("s", Track(PV, -38, 29 * DS, -1, amax=290)),
    ("s", Track(PV, 117, 66 * DS, -1)),               # soft tracks
    ("s", Track(PV, -76, 52 * DS, +1)),
]

# the muon: bends inside the solenoid, straight outside it
MU = Track(PV, -3.2, 1100 * DS, +1, r_end=R_SOL)
MU_DIR = MU.tangent(MU.alpha)
_mu = (math.cos(math.radians(MU_DIR)), math.sin(math.radians(MU_DIR)))


def on_muon_line(x):
    t = (x - MU.end[0]) / _mu[0]
    return (x, MU.end[1] + t * _mu[1])


def muon_at_radius(r):
    ex, ey = MU.end[0] - CX, MU.end[1] - CY
    b = 2 * (ex * _mu[0] + ey * _mu[1])
    c = ex * ex + ey * ey - r * r
    t = (-b + math.sqrt(b * b - 4 * c)) / 2
    return (MU.end[0] + t * _mu[0], MU.end[1] + t * _mu[1])


# =========================================================================================
# Text layout: measured, optically aligned on the left ink edge, guarded on the right
# =========================================================================================
_NUM = re.compile(r"[MLHVQCZ]|-?\d*\.?\d+(?:e-?\d+)?")


def ink_x(d):
    """(min x, max x) of the outline in path d (absolute M/L/H/V/Q/C/Z, as SVGPathPen writes it)"""
    xs, cmd, nums = [], None, []

    def flush():
        if cmd in ("M", "L", "Q", "C"):
            xs.extend(nums[0::2])
        elif cmd == "H":
            xs.extend(nums)

    for tok in _NUM.findall(d):
        if tok.isalpha():
            flush()
            cmd, nums = tok, []
        else:
            nums.append(float(tok))
    flush()
    return min(xs), max(xs)


def run(text, font, size, x, y, tracking):
    """text_path placed so that its left INK edge (not its advance box) lands on x"""
    d0, _ = text_path(text, font, size, 0, y, tracking=tracking, precision=1)
    lo, _ = ink_x(d0)
    d, w = text_path(text, font, size, x - lo, y, tracking=tracking, precision=1)
    return d, w, x - lo


def layout_text():
    """-> list of (path d, token) for name, subline and tagline, plus the name's ink (left, right) x"""
    x_max = W - RIGHT_PAD
    out = []
    name_d, _, _ = run(NAME, "grotesk-700", NAME_SIZE, INK_X, NAME_Y, -0.02)
    lo, hi = ink_x(name_d)
    if hi > x_max:
        raise SystemExit(f"NAME ends at x={hi:.0f} > {x_max:.0f}: lower NAME_SIZE or INK_X")
    out.append((name_d, "text"))

    size = SUB_SIZE
    while True:   # shrink the subline until it fits
        sub_d, _, _ = run(SUBLINE, "mono-400", size, INK_X, NAME_Y + SUB_GAP, 0.02)
        if ink_x(sub_d)[1] <= x_max:
            break
        size -= 0.25
        if size < SUB_MIN:
            raise SystemExit(f"SUBLINE is too long to fit at >= {SUB_MIN}px; shorten it")
    if size != SUB_SIZE:
        print(f"note: subline shrunk to {size}px to fit", file=sys.stderr)
    out.append((sub_d, "muted"))

    ky = NAME_Y - 0.7 * NAME_SIZE - KICK_GAP
    x, first = INK_X, True
    for part, tok in TAGLINE:
        if first:
            d, w, x0 = run(part, "mono-500", KICK_SIZE, x, ky, 0.08)
            x, first = x0, False
        else:
            d, w = text_path(part, "mono-500", KICK_SIZE, x, ky, tracking=0.08, precision=1)
        out.append((d, tok))
        x += w + KICK_SIZE * 0.08
    if TAGLINE and ink_x(out[-1][0])[1] > x_max:
        raise SystemExit("TAGLINE is too long; shorten it")
    return out, (lo, hi)


def label(parts, x, y, anchor):
    """multi-colour micro-label -> [(d, token)]"""
    if not parts:
        return []
    total = sum(text_path(p, "mono-400", LABEL_SIZE, 0, 0, tracking=0.04)[1] for p, _ in parts)
    total += LABEL_SIZE * 0.04 * (len(parts) - 1)
    x = x - total if anchor == "end" else x
    out = []
    for p, tok in parts:
        d, w = text_path(p, "mono-400", LABEL_SIZE, x, y, tracking=0.04, precision=1)
        if d:
            out.append((d, tok))
        x += w + LABEL_SIZE * 0.04
    return out


TEXT, (NAME_LO, NAME_HI) = layout_text()

# =========================================================================================
# Robot + reaching arm (side view, facing the name)
# =========================================================================================
S = on_muon_line(390.0)          # shoulder: on the muon line
FLOOR = 372.0
L1, L2, L3, LF = 57.0, 51.0, 11.0, 14.0   # upper arm, forearm, wrist->palm, finger
PALM = 6.0                                 # half-width of the palm crossbar

TARGET = (NAME_LO - 46.0, NAME_Y - 40.0)   # finger tips: well clear of the "N", level with its upper half
HAND_DIR = -4.0                            # gripper points slightly up, at the name


def ik(target, hand_dir):
    """planar 2-link IK (elbow up) -> absolute link angles (upper, fore, hand)"""
    wt = along(target, hand_dir + 180, L3 + LF - 2)
    d = min(dist(S, wt), L1 + L2 - 1e-3)
    c = (L1 * L1 + d * d - L2 * L2) / (2 * L1 * d)
    th1 = ang(S, wt) - math.degrees(math.acos(max(-1.0, min(1.0, c))))
    e = along(S, th1, L1)
    return th1, ang(e, wt), hand_dir


# The arm is three nested joint groups whose drawn (rest) geometry lies along the muon line.
# Every pose is a set of joint rotations relative to that line.
def rel(angles):
    a1, a2, a3 = angles
    return (a1 - MU_DIR, a2 - a1, a3 - a2)


POSE_REACH = rel(ik(TARGET, HAND_DIR))     # the static / final pose
POSE_REST = rel((68.0, 36.0, 56.0))        # powered down: hanging relaxed by the side
FINGER_OPEN, FINGER_REST, FINGER_SHUT = 17.0, 5.0, 2.0

E_A = along(S, MU_DIR, L1)                 # elbow / wrist / palm in the drawn geometry
W_A = along(E_A, MU_DIR, L2)
G_A = along(W_A, MU_DIR, L3)
PA, PB = along(G_A, MU_DIR - 90, PALM), along(G_A, MU_DIR + 90, PALM)
N_JOINT = (S[0] - 0.5, S[1] - 24.0)        # neck joint; the head pivots here

# =========================================================================================
# Timeline (seconds from load). Frame 0 = the complete picture.
# =========================================================================================
TL = dict(
    hold=3.4,              # complete picture, still
    drain=(3.4, 3.72),     # arm energy drains fingertips -> shoulder; joints unlock (grow + fade)
    dim=(3.45, 3.95),      # arm hulls dim to ARM_REST_HULL
    mu_back=(3.66, 4.06),  # muon retracts from the shoulder into the vertex
    tk_back=(3.74, 4.12),  # tracks retract into the vertex (4 groups, 30 ms apart)
    fade=(3.8, 4.1),       # cells, cone, chamber hits, secondary vertex fade out
    lower=(3.7, 4.55),     # arm relaxes into its rest pose
    bang=4.75,             # collision flash; tracks draw out of the vertex (0.9 s, ease-out)
    mu=(4.85, 5.8),        # muon runs out of the detector into the shoulder
    arm_speed=330.0,       # units/s: then the energy runs up the arm, joints lock on as it passes
    lift=(6.0, 7.2),       # arm lifts into its reach (shoulder; elbow and wrist lag 0.1 s each)
    hull_on=(5.95, 6.6),   # hulls brighten
    grip=(6.8, 7.3),       # gripper opens
    look=(7.7, 9.6),       # head glances at its hand while the gripper closes and reopens
    pulse=(13.0, 13.9),    # loop only: a green pulse runs along the muon into the shoulder
)
ARM_REST_HULL = 0.4        # hull opacity while powered down (the arm never disappears)
GHOST = 0.3                # skeleton opacity while powered down
LOOK_DEG = 7.0             # head tilt toward the hand
END_ONCE = TL["look"][1] + 0.05
EZ_OUT = "cubic-bezier(.25,.75,.25,1)"
EZ_IN = "cubic-bezier(.6,0,.9,.4)"
EZ_IO = "cubic-bezier(.55,0,.3,1)"
EZ_MU = "cubic-bezier(.35,.2,.65,.8)"


# =========================================================================================
def build(theme, mode):
    k, th = TOKENS[theme], THEME[theme]
    # Keyframe times below are seconds from load. Nothing animates during the opening hold: it is an
    # animation-delay, so the browser has no running animation to repaint and shows the static drawing.
    hold = TL["hold"]
    T = hold + LOOP_T if mode == "loop" else END_ONCE      # last keyframe, seconds from load
    span = T - hold                                         # animation-duration
    o, css = [], []

    def pct(t):
        return f"{f(100 * max(0.0, min(span, t - hold)) / span)}%"

    def kf(name, stops):
        """stops: [(t_seconds, 'decls', ease|None)] -> @keyframes; 0% and 100% must be the static state"""
        body = "".join(f"{pct(t)}{{{d}{';animation-timing-function:' + e if e else ''}}}" for t, d, e in stops)
        return f"@keyframes {name}{{{body}}}"

    v, cy_, am = k["violet"], k["green"], k["amber"]
    hull = mix(v, k["bg0"], th["hull"])
    hull2 = mix(v, k["bg0"], th["hull"] * 0.6)
    grid = f'stroke="{k["line"]}" stroke-opacity="{th["grid"]}"'

    # ---------------- card: 1 px border at every display width
    o.append(f'<rect x="2" y="2" width="{W - 4}" height="{H - 4}" rx="16" fill="{k["bg0"]}" stroke="{k["line"]}" '
             f'stroke-width="1" vector-effect="non-scaling-stroke"/>')
    o.append('<g clip-path="url(#card)">')

    # ---------------- detector (static)
    det = [f'<circle cx="{f(CX)}" cy="{f(CY)}" r="{f(R_SOL)}" fill="{k["bg1"]}"/>']
    rings = [r * DS for r in (3.5, 8.5, 13, 17.5, 26, 32, 38, 44)]          # pixel + strip layers
    trt = [(52 + i * 3.6) * DS for i in range(6)]                           # TRT straws
    det.append(f'<path d="{"".join(circle_d(r) for r in rings)}" fill="none" stroke="{k["line"]}" stroke-width="1"/>')
    det.append(f'<path d="{"".join(circle_d(r) for r in trt)}" fill="none" stroke="{k["line"]}" stroke-width=".8"/>')
    det.append(f'<circle cx="{f(CX)}" cy="{f(CY)}" r="{f(R_SOL)}" fill="none" stroke="{k["muted"]}" '
               f'stroke-opacity=".4" stroke-width="1.2"/>')                  # solenoid
    cal_r = [R_EM0, R_EM1] + list(R_HAD)
    seg = "".join(f"M{pt(P(R_EM0, a))}L{pt(P(R_EM1, a))}M{pt(P(R_HAD[0], a))}L{pt(P(R_HAD[-1], a))}"
                  for a in (i * 360 / NSEG for i in range(NSEG)))
    det.append(f'<path d="{"".join(circle_d(r) for r in cal_r)}{seg}" fill="none" {grid} stroke-width="1"/>')
    det.append(f'<path d="{"".join(muon_chambers())}" fill="{k["bg1"]}" {grid} stroke-width="1"/>')
    o.append("".join(det))

    # ---------------- the event
    half = math.degrees(0.4)  # anti-kt R=0.4 cone, in phi
    o.append(f'<path class="ev cone" d="M{pt(PV)}L{pt(P(R_HAD[-1], JET1 - half))}A{f(R_HAD[-1])} {f(R_HAD[-1])} 0 0 1 '
             f'{pt(P(R_HAD[-1], JET1 + half))}Z" fill="{cy_}" fill-opacity=".06"/>')

    # calorimeter energies: tracks that reach the EM layer + a shower profile around each jet axis
    em = [0.0] * NSEG
    had = [[0.0] * NSEG for _ in range(3)]
    step = 360 / NSEG

    def seg_of(a):
        return int((a % 360) / step) % NSEG

    for tag, tr in TRACKS:
        if tr.reaches:
            em[seg_of(ang(PV, tr.end))] += 0.5 if tag != "s" else 0.22
    for axis, sc in ((JET1, 1.0), (JET2, 0.8)):
        c = seg_of(axis)
        for d_, w_ in ((-2, .15), (-1, .45), (0, .9), (1, .45), (2, .15)):
            em[(c + d_) % NSEG] += w_ * sc
        for layer, prof in enumerate((((-1, .35), (0, .8), (1, .4), (2, .1)), ((-1, .25), (0, .6), (1, .3)),
                                      ((0, .35), (1, .15)))):
            for d_, w_ in prof:
                had[layer][(c + d_) % NSEG] += w_ * sc

    def owner(i):
        a = (i + 0.5) * step
        for tag, axis in (("j1", JET1), ("j2", JET2)):
            if abs(((a - axis + 180) % 360) - 180) < 30:
                return tag
        return "s"

    op_lo, op_hi = th["cell_op"]
    cells = {"j1": {}, "j2": {}, "s": {}, "mu": {}}

    def add(tag, r0, r1, i, e):
        e = min(1.0, e)
        s = 0.4 + 0.6 * e ** 0.6                         # box size ~ energy (Atlantis style)
        op = round((op_lo + (op_hi - op_lo) * e) * 5) / 5  # few opacity steps, high floor (no olive in dark)
        cells[tag].setdefault(op, []).append(cell(r0, r1, i * step, (i + 1) * step, s))

    for i, e in enumerate(em):
        if e > 0.08:
            add(owner(i), R_EM0, R_EM1, i, e)
    for layer in range(3):
        for i, e in enumerate(had[layer]):
            if e > 0.08:
                add(owner(i), R_HAD[layer], R_HAD[layer + 1], i, e)
    # the muon's minimum-ionising trail: small amber outlines threaded on its line (filled boxes under the
    # green line read as an olive dash)
    mip = []
    for r0, r1 in ((R_EM0, R_EM1),) + tuple((R_HAD[l], R_HAD[l + 1]) for l in range(3)):
        rm = (r0 + r1) / 2
        a = ang(PV, muon_at_radius(rm))
        hs = 3.1
        mip.append(sector(rm - hs, rm + hs, a - math.degrees(hs / rm), a + math.degrees(hs / rm)))
    for tag, buckets in cells.items():
        inner = "".join(f'<path d="{"".join(ds)}" fill-opacity="{f(op)}"/>' for op, ds in sorted(buckets.items()))
        if tag == "mu":
            inner = f'<path d="{"".join(mip)}" fill="none" stroke="{am}" stroke-width="1.2"/>'
        o.append(f'<g class="ev d-{tag}" fill="{am}">{inner}</g>')

    # muon chamber hits: a short segment where the muon crosses each station (no filled boxes: two lit
    # upright chambers read as a pause icon)
    ticks = "".join(f"M{pt(along(muon_at_radius(r), MU_DIR - 90, 4.5))}L{pt(along(muon_at_radius(r), MU_DIR + 90, 4.5))}"
                    for r, _ in MU_ST)
    o.append(f'<path class="ev mch" d="{ticks}" fill="none" stroke="{cy_}" stroke-width="2.2" stroke-linecap="round"/>')

    # tracks (4 stagger groups)
    trk = []
    for n, (tag, tr) in enumerate(TRACKS):
        extra = ' stroke-width="1.5" stroke-opacity=".7"' if tag == "s" else ""
        trk.append(f'<path class="tk t{n % 4}" d="{tr.d()}"{extra}/>')
    o.append(f'<g fill="none" stroke="{cy_}" stroke-width="1.9" stroke-linecap="round">{"".join(trk)}</g>')
    D_TK = math.ceil(max(tr.length for _, tr in TRACKS) + 6)

    o.append(f'<circle cx="{f(PV[0])}" cy="{f(PV[1])}" r="16" fill="url(#pvglow)"/>')
    o.append(f'<circle class="flash" cx="{f(PV[0])}" cy="{f(PV[1])}" r="10" fill="none" stroke="{cy_}" '
             f'stroke-width="1.5" opacity="0"/>')
    o.append(f'<circle cx="{f(PV[0])}" cy="{f(PV[1])}" r="2.8" fill="{k["text"]}"/>')
    o.append(f'<circle class="ev sv" cx="{f(SV[0])}" cy="{f(SV[1])}" r="2.5" fill="{k["bg0"]}" stroke="{k["rose"]}" '
             f'stroke-width="1.5"/>')

    # ---------------- robot body (RViz look: soft hulls in a violet tint under a crisp skeleton)
    sx, sy = S
    tcx = sx - 0.5                        # torso centre line; head and neck sit on it
    rb = []
    fx0, fx1 = sx - 58, sx + 72
    hatch = "".join(f"M{f(x)} {f(FLOOR + 1.5)}l-7 8" for x in range(int(fx0) + 8, int(fx1) + 1, 9))
    rb.append(f'<path d="M{f(fx0)} {f(FLOOR)}H{f(fx1)}{hatch}" stroke="{k["line"]}" stroke-width="1.3" fill="none"/>')
    B0 = (sx - 8, 324.0)                  # chassis mount
    K = (sx + 19, sy + 86)                # knee
    HP = (sx - 2, sy + 52)                # hip
    # far arm, behind everything: hull + faint skeleton, elbow bent, gripper forward
    fs, fe, fw = (sx - 3, sy + 3), (sx + 1, sy + 50), (sx + 38, sy + 43)
    fa = ang(fe, fw)
    fq, fr = along(fw, fa - 90, 5), along(fw, fa + 90, 5)
    rb.append(f'<path d="M{pt(fs)}L{pt(fe)}L{pt(fw)}" fill="none" stroke="{hull2}" stroke-width="12" '
              f'stroke-linecap="round" stroke-linejoin="round"/>')
    rb.append(f'<path d="M{pt(fe)}L{pt(fw)}M{pt(fq)}L{pt(fr)}M{pt(fq)}l{pt(along((0, 0), fa - 12, 9))}'
              f'M{pt(fr)}l{pt(along((0, 0), fa + 12, 9))}" fill="none" stroke="{v}" stroke-opacity=".45" '
              f'stroke-width="2" stroke-linecap="round"/>')
    # hulls: chassis, leg, torso, neck (joins head to torso)
    rb.append(f'<rect x="{f(sx - 50)}" y="316" width="96" height="34" rx="11" fill="{hull}"/>')
    rb.append(f'<path d="M{pt(B0)}L{pt(K)}L{pt(HP)}" fill="none" stroke="{hull}" stroke-width="16" '
              f'stroke-linecap="round" stroke-linejoin="round"/>')
    rb.append(f'<rect x="{f(tcx - 17.5)}" y="{f(sy - 18)}" width="35" height="68" rx="12" fill="{hull}"/>')
    rb.append(f'<rect x="{f(tcx - 7)}" y="{f(sy - 32)}" width="14" height="18" rx="3" fill="{hull}"/>')
    # skeleton: base -> knee -> hip -> shoulder -> neck
    rb.append(f'<path d="M{pt(B0)}L{pt(K)}L{pt(HP)}L{pt(S)}L{pt(N_JOINT)}" fill="none" stroke="{v}" '
              f'stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>')
    for j, r in ((B0, 3.6), (K, 4.4), (HP, 4.4)):
        rb.append(f'<circle cx="{f(j[0])}" cy="{f(j[1])}" r="{r}" fill="{k["bg0"]}" stroke="{v}" stroke-width="2"/>')
    # head: hull centred over the torso, camera ring on its face; pivots at the neck joint
    rb.append(f'<g class="hd" transform="rotate(0 {pt(N_JOINT)})">'
              f'<rect x="{f(tcx - 18)}" y="{f(sy - 55)}" width="36" height="27" rx="9" fill="{hull}"/>'
              f'<circle cx="{f(tcx + 8)}" cy="{f(sy - 41.5)}" r="3.6" fill="{k["bg0"]}" stroke="{v}" stroke-width="2"/>'
              f'</g>')
    rb.append(f'<circle cx="{f(N_JOINT[0])}" cy="{f(N_JOINT[1])}" r="3.4" fill="{k["bg0"]}" stroke="{v}" stroke-width="2"/>')
    for wx in (sx - 28, sx + 25):
        rb.append(f'<circle cx="{f(wx)}" cy="{f(FLOOR - 12)}" r="12" fill="{k["bg0"]}" stroke="{v}" stroke-width="2.2"/>'
                  f'<circle cx="{f(wx)}" cy="{f(FLOOR - 12)}" r="2.4" fill="{v}"/>')
    o.append("".join(rb))

    # ---------------- muon: arc, then straight into the shoulder; green blends to violet outside the detector
    mu_len = MU.length + dist(MU.end, S)
    D_MU = math.ceil(mu_len + 6)
    o.append(f'<path class="mu" d="{MU.d()}L{pt(S)}" fill="none" stroke="url(#mug)" stroke-width="2.4" '
             f'stroke-linecap="round"/>')
    if mode == "loop":
        o.append(f'<path class="mp" d="{MU.d()}L{pt(S)}" fill="none" stroke="url(#mug)" stroke-width="6.5" stroke-linecap="round" '
                 f'opacity="0"/>')

    # ---------------- the reaching arm: nested joint groups; drawn geometry lies on the muon line and each
    # group's transform attribute holds the reach pose (the static state). CSS animates the same transform.
    def rot_attr(a, c):
        return f'transform="rotate({f(a)} {pt(c)})"'

    joints = (S, E_A, W_A)
    r1, r2, r3 = POSE_REACH
    hulls = (f'<g class="hl" fill="none" stroke="{hull}" stroke-linecap="round">'
             f'<g class="j1" {rot_attr(r1, S)}><path d="M{pt(S)}L{pt(E_A)}" stroke-width="14"/>'
             f'<g class="j2" {rot_attr(r2, E_A)}><path d="M{pt(E_A)}L{pt(W_A)}" stroke-width="12"/>'
             f'<g class="j3" {rot_attr(r3, W_A)}><path d="M{pt(W_A)}L{pt(G_A)}" stroke-width="12"/></g></g></g></g>')

    def link(cls, a, b, width=2.8):
        """ghost (always there, dim) + live (drawn on / drained by the animation) copies of one link"""
        d = f"M{pt(a)}L{pt(b)}"
        return (f'<path d="{d}" stroke="{v}" stroke-opacity="{GHOST}" stroke-width="{width}"/>'
                f'<path class="lk {cls}" d="{d}" stroke="{v}" stroke-width="{width}"/>')

    def jring(cls, c, r):
        return f'<circle class="jt {cls}" cx="{f(c[0])}" cy="{f(c[1])}" r="{r}" fill="{k["bg0"]}" stroke="{v}" stroke-width="2.1"/>'

    u = MU_DIR
    fu_tip, fd_tip = along(PA, u, LF), along(PB, u, LF)
    arm = (f'<g class="j1" {rot_attr(r1, S)}>{link("l1", S, E_A)}'
           f'<g class="j2" {rot_attr(r2, E_A)}>{link("l2", E_A, W_A)}'
           f'<g class="j3" {rot_attr(r3, W_A)}>{link("l3", W_A, G_A)}{link("lp", PA, PB)}'
           f'<g class="fu" {rot_attr(-FINGER_OPEN, PA)}>{link("l4", PA, fu_tip, 2.3)}</g>'
           f'<g class="fd" {rot_attr(FINGER_OPEN, PB)}>{link("l4", PB, fd_tip, 2.3)}</g>'
           f'{jring("jw", W_A, 4.2)}</g>{jring("je", E_A, 4.8)}</g>{jring("js", S, 5.4)}</g>')
    o.append(hulls)
    o.append(f'<g fill="none" stroke-linecap="round" stroke-linejoin="round">{arm}</g>')

    # ---------------- type
    for d, tok in TEXT:
        o.append(f'<path d="{d}" fill="{k[tok]}"/>')
    labs = label(CORNER_LABEL, W - 30, 34, "end") + label(FOOT_LABEL, 30, H - 24, "start")
    for d, tok in labs:
        o.append(f'<path d="{d}" fill="{k[tok]}" fill-opacity=".8"/>')
    o.append("</g>")

    # =====================================================================================
    # animation (CSS). Everything lives inside prefers-reduced-motion:no-preference, so reduced motion,
    # CSS-less renderers and the end of the play-once all show the static attributes above.
    # Only transform, opacity and stroke-dashoffset are animated; no filters.
    # =====================================================================================
    def tr_rot(a, c):
        return f"translate({f(c[0])}px,{f(c[1])}px) rotate({f(a)}deg) translate({f(-c[0])}px,{f(-c[1])}px)"

    def tr_scale(s, c):
        return f"translate({f(c[0])}px,{f(c[1])}px) scale({f(s)}) translate({f(-c[0])}px,{f(-c[1])}px)"

    tl = TL
    bang = tl["bang"]
    # Draw-on / retract uses a dash longer than the path (dash D, gap D; offset 0 = fully drawn, D+2 = hidden).
    # The dasharray lives only inside the keyframes, so outside the animation every stroke is plain and solid.
    def dash(D, off):
        return f"stroke-dasharray:{D} {D};stroke-dashoffset:{off}"

    # tracks: retract into the vertex, then draw out of it at the same speed (particles all move at ~c)
    for i in range(4):
        b0, b1 = tl["tk_back"][0] + 0.03 * i, tl["tk_back"][1] + 0.03 * i
        g0 = bang + 0.04 * i
        css.append(kf(f"tk{i}", [(0, dash(D_TK, 0), None), (b0, dash(D_TK, 0), EZ_IN),
                                 (b1, dash(D_TK, D_TK + 2), None), (g0, dash(D_TK, D_TK + 2), EZ_OUT),
                                 (g0 + 0.9, dash(D_TK, 0), None), (T, dash(D_TK, 0), None)])
                   + f".t{i}{{animation-name:tk{i}}}")
    # muon
    m0, m1 = tl["mu_back"]
    css.append(kf("mu", [(0, dash(D_MU, 0), None), (m0, dash(D_MU, 0), EZ_IN), (m1, dash(D_MU, D_MU + 2), None),
                         (tl["mu"][0], dash(D_MU, D_MU + 2), EZ_MU), (tl["mu"][1], dash(D_MU, 0), None),
                         (T, dash(D_MU, 0), None)])
               + ".mu{animation-name:mu}")

    # cells, cone, chamber hits, secondary vertex: fade out with the rewind, light up as the replay lands
    f0, f1 = tl["fade"]
    for cls, t_on, fade_in in (("d-j1", bang + 0.42, .15), ("d-j2", bang + 0.48, .15), ("d-s", bang + 0.55, .15),
                               ("d-mu", bang + 0.5, .15), ("mch", bang + 0.62, .15), ("sv", bang + 0.02, .15),
                               ("cone", bang + 0.5, .5)):
        nm = cls.replace("-", "")
        css.append(kf(nm, [(0, "opacity:1", None), (f0, "opacity:1", None), (f1, "opacity:0", None),
                           (t_on, "opacity:0", None), (t_on + fade_in, "opacity:1", None), (T, "opacity:1", None)])
                   + f".{cls}{{animation-name:{nm}}}")
    fl0, fl1 = tr_scale(0.2, PV), tr_scale(2.6, PV)
    css.append(kf("flash", [(0, f"opacity:0;transform:{fl0}", None), (bang, f"opacity:0;transform:{fl0}", None),
                            (bang + 0.04, f"opacity:1;transform:{tr_scale(0.3, PV)}", None),
                            (bang + 0.75, f"opacity:0;transform:{fl1}", None),
                            (bang + 0.76, f"opacity:0;transform:{fl0}", None), (T, f"opacity:0;transform:{fl0}", None)])
               + ".flash{animation-name:flash}")

    # arm energy: live links drain fingertips -> shoulder, then draw shoulder -> fingertips as the muon arrives
    lens = dict(l1=L1, l2=L2, l3=L3, lp=2 * PALM, l4=LF)
    order = ("l1", "l2", "l3", "l4")                       # lp (palm) runs with l3
    d0, d1 = tl["drain"]
    per = (d1 - d0) / sum(lens[c] for c in order)
    drain, t = {}, d1
    for c in order:                                        # drain back to front, ending at d1
        drain[c] = (t - lens[c] * per, t)
        t -= lens[c] * per
    energise, t = {}, tl["mu"][1]
    for c in order:
        dt = lens[c] / tl["arm_speed"]
        energise[c] = (t, t + dt)
        t += dt
    drain["lp"], energise["lp"] = drain["l3"], energise["l3"]
    for c, L in lens.items():
        D = math.ceil(L + 4)
        (a0, a1), (b0, b1) = drain[c], energise[c]
        css.append(kf(c, [(0, dash(D, 0), None), (a0, dash(D, 0), None), (a1, dash(D, D + 2), None),
                          (b0, dash(D, D + 2), None), (b1, dash(D, 0), None), (T, dash(D, 0), None)])
                   + f".{c}{{animation-name:{c}}}")
    # joints unlock (grow + fade) as the energy leaves them, and lock on (1.6x -> 1x) as it arrives
    for cls, c, lk in (("jw", W_A, "l3"), ("je", E_A, "l2"), ("js", S, "l1")):
        t_off, t_on = drain[lk][1], energise[lk][0]
        one, big = tr_scale(1, c), tr_scale(1.6, c)
        css.append(kf(cls, [(0, f"opacity:1;transform:{one}", None), (t_off - 0.05, f"opacity:1;transform:{one}", EZ_OUT),
                            (t_off + 0.25, f"opacity:0;transform:{big}", None),
                            (t_on, f"opacity:0;transform:{big}", EZ_OUT),
                            (t_on + 0.35, f"opacity:1;transform:{one}", None), (T, f"opacity:1;transform:{one}", None)])
                   + f".{cls}{{animation-name:{cls}}}")
    # joint rotations: reach -> rest (lower) -> reach (lift). Loop mode adds a small servo after the pulse.
    lo0, lo1 = tl["lower"]
    li0, li1 = tl["lift"]
    for n, (cls, c) in enumerate(zip(("j1", "j2", "j3"), joints)):
        reach, rest = POSE_REACH[n], POSE_REST[n]
        stops = [(0, f"transform:{tr_rot(reach, c)}", None)]
        if mode == "loop":   # a small servo as the idle pulse arrives at the shoulder
            p1 = tl["pulse"][1] + 0.1 * n
            wig = (-3.0, 4.5, -5.0)[n]
            stops += [(p1, f"transform:{tr_rot(reach, c)}", EZ_IO),
                      (p1 + 0.7, f"transform:{tr_rot(reach + wig, c)}", EZ_IO),
                      (p1 + 1.8, f"transform:{tr_rot(reach, c)}", None)]
        stops += [(lo0 + 0.06 * n, f"transform:{tr_rot(reach, c)}", EZ_IO),
                  (lo1, f"transform:{tr_rot(rest, c)}", None),
                  (li0 + 0.1 * n, f"transform:{tr_rot(rest, c)}", EZ_IO),
                  (li1, f"transform:{tr_rot(reach, c)}", None), (T, f"transform:{tr_rot(reach, c)}", None)]
        stops.sort(key=lambda s: s[0])
        css.append(kf(cls, stops) + f".{cls}{{animation-name:{cls}}}")
    # gripper: open in the reach; half-closed at rest; opens at the end of the lift; closes/reopens in the glance
    g0, g1 = tl["grip"]
    k0, k1 = tl["look"]
    for cls, sgn, c in (("fu", -1, PA), ("fd", 1, PB)):
        op_, rs_, sh_ = (tr_rot(sgn * FINGER_OPEN, c), tr_rot(sgn * FINGER_REST, c), tr_rot(sgn * FINGER_SHUT, c))
        css.append(kf(cls, [(0, f"transform:{op_}", None), (lo0, f"transform:{op_}", EZ_IO),
                            (lo1, f"transform:{rs_}", None), (g0, f"transform:{rs_}", EZ_IO),
                            (g1, f"transform:{op_}", None), (k0 + 0.4, f"transform:{op_}", EZ_IO),
                            (k0 + 0.9, f"transform:{sh_}", None), (k1 - 0.9, f"transform:{sh_}", EZ_IO),
                            (k1 - 0.3, f"transform:{op_}", None), (T, f"transform:{op_}", None)])
                   + f".{cls}{{animation-name:{cls}}}")
    # head glances at its hand, then back
    h0, h1 = tr_rot(0, N_JOINT), tr_rot(LOOK_DEG, N_JOINT)
    css.append(kf("hd", [(0, f"transform:{h0}", None), (k0, f"transform:{h0}", EZ_IO), (k0 + 0.6, f"transform:{h1}", None),
                         (k1 - 0.6, f"transform:{h1}", EZ_IO), (k1, f"transform:{h0}", None), (T, f"transform:{h0}", None)])
               + ".hd{animation-name:hd}")
    # hulls dim while powered down, brighten as the arm is energised
    dm0, dm1 = tl["dim"]
    hn0, hn1 = tl["hull_on"]
    css.append(kf("hl", [(0, "opacity:1", None), (dm0, "opacity:1", None), (dm1, f"opacity:{ARM_REST_HULL}", None),
                         (hn0, f"opacity:{ARM_REST_HULL}", None), (hn1, "opacity:1", None), (T, "opacity:1", None)])
               + ".hl{animation-name:hl}")
    if mode == "loop":   # a short pulse restates particles -> robot without a full replay
        p0, p1 = tl["pulse"]
        pd = f"stroke-dasharray:12 {D_MU + 40};"     # a 12-unit bead, then a gap longer than the path
        css.append(kf("mp", [(0, pd + "opacity:0;stroke-dashoffset:18", None),
                             (p0, pd + "opacity:0;stroke-dashoffset:18", None),
                             (p0 + 0.05, pd + "opacity:1;stroke-dashoffset:10", EZ_MU),
                             (p1 - 0.05, pd + f"opacity:1;stroke-dashoffset:{-mu_len + 6:.0f}", None),
                             (p1, pd + f"opacity:0;stroke-dashoffset:{-mu_len:.0f}", None),
                             (T, pd + "opacity:0;stroke-dashoffset:18", None)])
                   + ".mp{animation-name:mp}")

    anim_classes = ".ev,.tk,.mu,.lk,.jt,.j1,.j2,.j3,.fu,.fd,.hd,.hl,.flash" + (",.mp" if mode == "loop" else "")
    head = (f"{anim_classes}{{animation-duration:{f(span)}s;animation-delay:{f(hold)}s;animation-timing-function:linear;"
            f"animation-iteration-count:{'infinite' if mode == 'loop' else 1}}}"
            ".j1,.j2,.j3,.fu,.fd,.hd,.jt,.flash{transform-origin:0 0}")
    style = ("@media (prefers-reduced-motion:no-preference){" + head + "".join(css) + "}"
             "@media (prefers-reduced-motion:reduce){*{animation:none!important}}")

    ex = muon_at_radius(MU_ST[0][0] - 4)
    defs = (f'<defs><clipPath id="card"><rect x="2.5" y="2.5" width="{W - 5}" height="{H - 5}" rx="15.5"/></clipPath>'
            f'<radialGradient id="pvglow"><stop offset="0" stop-color="{cy_}" stop-opacity=".5"/>'
            f'<stop offset="1" stop-color="{cy_}" stop-opacity="0"/></radialGradient>'
            f'<linearGradient id="mug" gradientUnits="userSpaceOnUse" x1="{f(ex[0])}" y1="{f(ex[1])}" x2="{f(S[0] - 6)}" '
            f'y2="{f(S[1])}"><stop offset="0" stop-color="{cy_}"/><stop offset="1" stop-color="{v}"/>'
            f'</linearGradient></defs>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
            f'aria-label="{escape(DESCRIPTION, {chr(34): "&quot;"})}"><title>{escape(TITLE)}</title>'
            f'<style>{style}</style>{defs}{"".join(o)}</svg>\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--mode", choices=("once", "loop"), default=MODE, help=f"animation mode (default: {MODE})")
    ap.add_argument("--out", default=os.path.join(REPO, "assets"), help="output directory")
    a = ap.parse_args()
    mode = a.mode
    os.makedirs(a.out, exist_ok=True)
    for theme in ("dark", "light"):
        path = os.path.join(a.out, f"banner-{theme}.svg")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(build(theme, mode))
        print(f"{path}  {os.path.getsize(path):,} B  ({mode})")


if __name__ == "__main__":
    main()
