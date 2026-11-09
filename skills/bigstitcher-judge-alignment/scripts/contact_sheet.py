#!/usr/bin/env python3
"""Tile the PNGs of one screenshot run into a single captioned sheet for a first look (triage: a 1024-px pair image is
shrunk into a --cell px tile, so judge fine doubles on the full-size PNG afterwards).

  contact_sheet.py SHOTS_DIR [--plane xy] [--kind pair] [--cols 3] [--cell 512] [--captions captions.json] [-o OUT.png]

Reads SHOTS_DIR/screenshots.json (the manifest `screenshot --json` wrote), keeps the images of the given plane and kind,
captions each tile with the setups, the plane, the scale (image px per global px) and, with --captions (pick_pairs.py
--captions), the pair's inliers / error. Default output SHOTS_DIR/sheet_<kind>_<plane>.png. Needs Pillow.
"""
import argparse
import json
import os
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("shots_dir")
    ap.add_argument("--plane", default="xy", help="xy, xz or yz (default xy); 'all' keeps every plane")
    ap.add_argument("--kind", default="pair", help="pair, overview, single or transform (default pair); 'all' keeps every kind")
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--cell", type=int, default=512, help="tile width in px (default 512)")
    ap.add_argument("--captions", help="JSON {'A,B': 'text'} per setup pair (pick_pairs.py --captions)")
    ap.add_argument("-o", "--out")
    a = ap.parse_args()
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        sys.exit("contact_sheet.py needs Pillow (pip install pillow); look at the PNGs one by one instead")

    manifest = os.path.join(a.shots_dir, "screenshots.json")
    if not os.path.isfile(manifest):
        sys.exit(f"{manifest} not found (run screenshot with --json)")
    m = json.load(open(manifest))
    entries = [e for e in m["images"] if (a.kind == "all" or e["kind"] == a.kind) and (a.plane == "all" or (e.get("plane") or "-") == a.plane)]
    if not entries:
        sys.exit(f"no {a.kind} images of plane {a.plane} in {manifest}")
    caps = json.load(open(a.captions)) if a.captions else {}

    try:
        font = ImageFont.load_default(size=max(12, a.cell // 36))
    except TypeError:
        font = ImageFont.load_default()
    text_h = max(16, a.cell // 24) + 6
    cols = min(a.cols, len(entries))
    rows = (len(entries) + cols - 1) // cols
    tiles = []
    for e in entries:
        img = Image.open(os.path.join(a.shots_dir, e["file"])).convert("RGB")
        f = min(a.cell / img.width, a.cell / img.height, 1.0)
        if f < 1.0:
            img = img.resize((max(1, round(img.width * f)), max(1, round(img.height * f))), Image.LANCZOS)
        s = e["setups"]
        key = f"{s[0]},{s[1]}" if len(s) == 2 else ""
        cap = caps.get(key) or (caps.get(f"{s[1]},{s[0]}") if len(s) == 2 else "")
        label = ("-".join(f"s{x}" for x in s) if len(s) <= 3 else f"{len(s)} views") + f" {e.get('plane') or e['kind']}"
        label += f"  1px={e['scale']:.2f}" + (f"  {cap}" if cap else "")
        if len(s) == 2 and e["kind"] == "pair":
            label += f"  (s{s[0]} magenta, s{s[1]} green)"
        tiles.append((img, label))
    cell_h = max(t[0].height for t in tiles) + text_h
    sheet = Image.new("RGB", (cols * a.cell, rows * cell_h), (0, 0, 0))
    draw = ImageDraw.Draw(sheet)
    for i, (img, label) in enumerate(tiles):
        x0, y0 = (i % cols) * a.cell, (i // cols) * cell_h
        sheet.paste(img, (x0 + (a.cell - img.width) // 2, y0))
        draw.text((x0 + 4, y0 + cell_h - text_h + 3), label, fill=(255, 255, 255), font=font)
    out = a.out or os.path.join(a.shots_dir, f"sheet_{a.kind}_{a.plane}.png")
    sheet.save(out)
    print(f"{out}: {len(tiles)} image(s), {cols} x {rows}, tile {a.cell} px; order: " + ", ".join(t[1].split('  ')[0] for t in tiles))


if __name__ == "__main__":
    main()
