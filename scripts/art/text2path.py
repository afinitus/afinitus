#!/usr/bin/env python3
"""Turn text into SVG path data so it renders identically everywhere.

GitHub serves README SVGs with CSP `default-src 'none'`, which blocks embedded
or remote fonts. Every glyph must therefore ship as outlines.

Library use:
    from text2path import text_path, measure
    d, width = text_path("Nishank Gite", font="grotesk-700", size=64, x=40, y=120)
    svg += f'<path d="{d}" fill="currentColor"/>'

CLI:
    text2path.py "Nishank Gite" --font grotesk-700 --size 64 --x 40 --y 120 [--anchor start|middle|end] [--tracking 0.02]
    prints a <path> element (with data-width attr) to stdout.

Fonts (static instances of OFL fonts, in ./fonts or ../fonts): grotesk-{400,700} = Space Grotesk,
mono-{400,500,700} = JetBrains Mono. Units per em = 1000.
Shaping uses HarfBuzz with kerning on and ligatures/contextual alternates off.
"""
import argparse
import os
import sys
from functools import lru_cache

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

_HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = next((d for d in (os.environ.get("T2P_FONTS"), os.path.join(_HERE, "fonts"), os.path.join(_HERE, "..", "fonts"))
                 if d and os.path.isdir(d)), os.path.join(_HERE, "fonts"))


@lru_cache(maxsize=None)
def _load(font):
    path = os.path.join(FONT_DIR, f"{font}.ttf")
    with open(path, "rb") as fh:
        blob = hb.Blob(fh.read())
    hb_font = hb.Font(hb.Face(blob))
    tt = TTFont(path)
    return hb_font, tt, tt.getGlyphSet(), tt["head"].unitsPerEm


def _shape(text, font, tracking_em):
    hb_font, tt, glyphset, upem = _load(font)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hb_font, buf, {"kern": True, "liga": False, "calt": False})
    order = tt.getGlyphOrder()
    out, pen_x = [], 0.0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        out.append((order[info.codepoint], pen_x + pos.x_offset, pos.y_offset))
        pen_x += pos.x_advance + tracking_em * upem
    if text:
        pen_x -= tracking_em * upem  # no trailing tracking
    return out, pen_x, glyphset, upem


def measure(text, font="grotesk-700", size=16, tracking=0.0):
    """Advance width of `text` in px at `size`."""
    _, adv, _, upem = _shape(text, font, tracking)
    return adv * size / upem


def text_path(text, font="grotesk-700", size=16, x=0.0, y=0.0, anchor="start", tracking=0.0, precision=2):
    """Return (path_d, width_px). (x, y) is the baseline origin, like SVG <text>.

    tracking is extra letter spacing in em (0.05 = 5% of the font size).
    """
    glyphs, adv, glyphset, upem = _shape(text, font, tracking)
    scale = size / upem
    width = adv * scale
    if anchor == "middle":
        x -= width / 2
    elif anchor == "end":
        x -= width
    parts = []
    for name, gx, gy in glyphs:
        pen = SVGPathPen(glyphset, ntos=lambda v: f"{v:.{precision}f}".rstrip("0").rstrip("."))
        # font space is y-up; SVG is y-down
        tpen = TransformPen(pen, (scale, 0, 0, -scale, x + gx * scale, y - gy * scale))
        glyphset[name].draw(tpen)
        d = pen.getCommands()
        if d:
            parts.append(d)
    return " ".join(parts), width


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("--font", default="grotesk-700")
    ap.add_argument("--size", type=float, default=16)
    ap.add_argument("--x", type=float, default=0)
    ap.add_argument("--y", type=float, default=0)
    ap.add_argument("--anchor", default="start", choices=["start", "middle", "end"])
    ap.add_argument("--tracking", type=float, default=0.0)
    a = ap.parse_args()
    d, w = text_path(a.text, a.font, a.size, a.x, a.y, a.anchor, a.tracking)
    sys.stdout.write(f'<path data-width="{w:.2f}" d="{d}"/>\n')


if __name__ == "__main__":
    main()
