#!/usr/bin/env python3
"""Stitch the zoom-0 tiles of one Dynmap map into a single image: stitch.py <tiles/world dir> <map prefix> <out.png>

HD map tiles are cut from one continuous image, so a plain grid works for every perspective.
"""
import glob, os, re, sys
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
TILE = re.compile(r"^(-?\d+)_(-?\d+)\.(png|jpg)$")


def stitch(world_dir, prefix, out):
    tiles = {}
    for f in glob.glob(f"{world_dir}/{prefix}/*/*"):
        m = TILE.match(os.path.basename(f))   # zoomed-out tiles start with z_ and do not match
        if m:
            tiles[(int(m.group(1)), int(m.group(2)))] = f
    if not tiles:
        raise SystemExit(f"no tiles for map prefix '{prefix}' in {world_dir}")
    xs = [k[0] for k in tiles]
    ys = [k[1] for k in tiles]
    x0, y1 = min(xs), max(ys)
    size = Image.open(next(iter(tiles.values()))).size[0]
    img = Image.new("RGBA", ((max(xs) - x0 + 1) * size, (y1 - min(ys) + 1) * size), (0, 0, 0, 255))
    for (x, y), f in tiles.items():
        img.paste(Image.open(f).convert("RGBA"), ((x - x0) * size, (y1 - y) * size))
    img.save(out)
    return len(tiles), img


if __name__ == "__main__":
    n, img = stitch(*sys.argv[1:4])
    print(f"{n} tiles -> {sys.argv[3]} {img.size}")
