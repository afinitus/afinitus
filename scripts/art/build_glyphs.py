#!/usr/bin/env python3
"""Build scripts/glyphs.json: outlined glyphs for the stdlib-only stats renderer.

The GitHub Action that draws the stats card runs `scripts/profile_stats.py` with the Python
standard library only (no fontTools / HarfBuzz on the runner). This tool pre-extracts everything
that script needs to set text as outlines:

    {
      "<font>": {
        "upem": 1000,                 # units per em
        "cap": 730, "xh": 550,        # cap height, x height (font units)
        "adv": {"A": 600, ...},       # advance widths (font units)
        "d":   {"A": "M..Z", ...},    # SVG path d in font units, y-up (flip when placing)
        "kern": {"AV": -40, ...}      # pair adjustments (font units), only non-zero pairs
      }, ...
    }

Fonts: mono-400, mono-500 (JetBrains Mono), grotesk-700 (Space Grotesk Bold).
Coverage: printable ASCII plus  · → ↗ — × ≈ ▲ ●.  Characters a font lacks are copied from
mono-500 (same 1000 upem), so the renderer never needs a fallback path.
Kerning is measured with HarfBuzz (shape each pair, compare with the unkerned advances), so it
matches what scripts/art/text2path.py produces for the static art.

Usage (development only; needs fonttools and uharfbuzz, the Action does not):
    python3 scripts/art/build_glyphs.py [--fonts scripts/art/fonts] [--out scripts/glyphs.json]
"""
import argparse
import json
import os

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = ["mono-400", "mono-500", "grotesk-700"]
FALLBACK = "mono-500"
EXTRA = "·→↗—×≈▲●"
CHARS = "".join(chr(c) for c in range(0x20, 0x7F)) + EXTRA


def ntos(v):
    return str(int(round(v)))


def glyph_table(path):
    tt = TTFont(path)
    cmap = tt.getBestCmap()
    gs = tt.getGlyphSet()
    upem = tt["head"].unitsPerEm
    os2 = tt["OS/2"]
    adv, d, have = {}, {}, set()
    for ch in CHARS:
        gname = cmap.get(ord(ch))
        if gname is None:
            continue
        have.add(ch)
        adv[ch] = int(round(gs[gname].width))
        pen = SVGPathPen(gs, ntos=ntos)
        gs[gname].draw(pen)
        cmd = pen.getCommands()
        if cmd:
            d[ch] = cmd
    return {"upem": upem, "cap": os2.sCapHeight, "xh": os2.sxHeight, "adv": adv, "d": d}, have


def kerning(path, chars):
    """Non-zero pair adjustments measured with HarfBuzz (kern feature on, no ligatures)."""
    with open(path, "rb") as fh:
        font = hb.Font(hb.Face(hb.Blob(fh.read())))
    feats = {"kern": True, "liga": False, "calt": False}

    def advances(s):
        buf = hb.Buffer()
        buf.add_str(s)
        buf.guess_segment_properties()
        hb.shape(font, buf, feats)
        return [p.x_advance for p in buf.glyph_positions]

    single = {c: advances(c)[0] for c in chars}
    kern = {}
    for a in chars:
        for b in chars:
            got = advances(a + b)
            if len(got) != 2:
                continue
            delta = got[0] - single[a]
            if delta:
                kern[a + b] = int(delta)
    return kern


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonts", default=os.path.join(HERE, "fonts"))
    ap.add_argument("--out", default=os.path.join(HERE, "..", "glyphs.json"))
    a = ap.parse_args()

    tables, cover = {}, {}
    for name in FONTS:
        tables[name], cover[name] = glyph_table(os.path.join(a.fonts, f"{name}.ttf"))
    for name in FONTS:
        t, fb = tables[name], tables[FALLBACK]
        missing = [c for c in CHARS if c not in cover[name]]
        for c in missing:
            if c in cover[FALLBACK]:
                t["adv"][c] = fb["adv"][c] * t["upem"] // fb["upem"]
                if c in fb["d"]:
                    t["d"][c] = fb["d"][c]
        if missing:
            print(f"{name}: copied from {FALLBACK}: {''.join(missing)}")
        kc = "".join(c for c in CHARS if c in cover[name] and c != " ")
        t["kern"] = kerning(os.path.join(a.fonts, f"{name}.ttf"), kc)
        print(f"{name}: {len(t['adv'])} glyphs, {len(t['kern'])} kern pairs")

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(tables, fh, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        fh.write("\n")
    print(f"wrote {a.out} ({os.path.getsize(a.out) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
