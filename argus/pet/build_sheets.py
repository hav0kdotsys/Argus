#!/usr/bin/env python3
"""Prepare Mira's sprite sheets for her pet (argus/pet/mira-pet): scaled and cut into grids a GPU can hold.

Input: ~/.argus/sprites/mira/*.png (one row of cells per clip) and clips.json (frames, fps per clip).
Output: ~/.argus/sprites/mira/grid/<clip>.png - the clip's cells at SCALE of their drawn size, laid out in rows of
at most MAX_SIDE pixels (the widest sheets are 22320 px, beyond many GPUs' texture limit) - and grid/grid.json:
{clip: {frames, fps, cw, ch, cols, rows, flipped}} (cell size after scaling). Re-run after replacing any sheet.

Usage: build_sheets.py [--scale 0.6] [--dir ~/.argus/sprites/mira]
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image

MAX_SIDE = 8192


def build(folder: Path, scale: float) -> dict:
    clips = json.loads((folder / "clips.json").read_text(encoding="utf-8"))["clips"]
    out = folder / "grid"
    out.mkdir(exist_ok=True)
    manifest = {}
    for name, info in sorted(clips.items()):
        sheet = Image.open(folder / info["file"]).convert("RGBA")
        frames, cw, ch = info["frames"], info["frame_width"], info["frame_height"]
        sw, sh = max(1, round(cw * scale)), max(1, round(ch * scale))
        cols = max(1, min(frames, MAX_SIDE // sw))
        rows = math.ceil(frames / cols)
        grid = Image.new("RGBA", (cols * sw, rows * sh), (0, 0, 0, 0))
        for i in range(frames):
            cell = sheet.crop((i * cw, 0, (i + 1) * cw, ch)).resize((sw, sh), Image.LANCZOS)
            grid.paste(cell, ((i % cols) * sw, (i // cols) * sh))
        grid.save(out / f"{name}.png", optimize=True)
        manifest[name] = {"frames": frames, "fps": info["fps"], "cw": sw, "ch": sh, "cols": cols, "rows": rows,
                          "flipped": info.get("flipped", False)}
    (out / "grid.json").write_text(json.dumps({"format": 1, "scale": scale, "clips": manifest}, indent=1) + "\n",
                                   encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scale", type=float, default=0.6)
    parser.add_argument("--dir", type=Path, default=Path.home() / ".argus" / "sprites" / "mira")
    args = parser.parse_args()
    manifest = build(args.dir.expanduser(), args.scale)
    widest = max(c["cols"] * c["cw"] for c in manifest.values())
    print(f"{len(manifest)} clips -> {args.dir / 'grid'} (widest grid {widest}px, scale {args.scale})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
