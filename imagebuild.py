"""Turn an image into Minecraft fill commands (pixel art out of colored blocks)."""
import base64
import io

from PIL import Image, ImageOps

COLORS = ["white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray",
          "light_gray", "cyan", "purple", "blue", "brown", "green", "red", "black"]

# legacy: Bedrock block id + data value (the data value is the index into COLORS)
# modern: flattened per-color block names
FAMILIES = {
    "concrete": {
        "legacy": "concrete", "modern": "{c}_concrete",
        "rgb": [(207, 213, 214), (224, 97, 1), (169, 48, 159), (35, 137, 198),
                (240, 175, 21), (94, 168, 24), (213, 101, 142), (54, 57, 61),
                (125, 125, 115), (21, 119, 136), (100, 32, 156), (45, 47, 143),
                (96, 60, 32), (73, 91, 36), (142, 33, 33), (8, 10, 15)],
    },
    "wool": {
        "legacy": "wool", "modern": "{c}_wool",
        "rgb": [(233, 236, 236), (240, 118, 19), (189, 68, 179), (58, 175, 217),
                (248, 197, 39), (112, 185, 25), (237, 141, 172), (62, 68, 71),
                (142, 142, 134), (21, 137, 145), (121, 42, 172), (53, 57, 157),
                (114, 71, 40), (84, 109, 27), (160, 39, 34), (20, 21, 25)],
    },
    "terracotta": {
        "legacy": "stained_hardened_clay", "modern": "{c}_terracotta",
        "rgb": [(209, 178, 161), (161, 83, 37), (149, 88, 108), (113, 108, 137),
                (186, 133, 35), (103, 117, 53), (161, 78, 78), (57, 41, 35),
                (135, 107, 98), (87, 91, 91), (118, 70, 86), (74, 59, 91),
                (77, 51, 35), (76, 83, 42), (143, 61, 46), (37, 22, 16)],
    },
}

MAX_SIZE = 256

# facing -> (forward x, forward z, right x, right z) as seen by the player
FACING = {
    "south": (0, 1, -1, 0),
    "north": (0, -1, 1, 0),
    "east": (1, 0, 0, 1),
    "west": (-1, 0, 0, -1),
}


def build_palette(families):
    pal = []
    for fam in families:
        for i, rgb in enumerate(FAMILIES[fam]["rgb"]):
            pal.append((fam, i, rgb))
    return pal


def _dist(a, b):
    rm = (a[0] + b[0]) / 2
    dr, dg, db = a[0] - b[0], a[1] - b[1], a[2] - b[2]
    return (2 + rm / 256) * dr * dr + 4 * dg * dg + (2 + (255 - rm) / 256) * db * db


def _nearest(rgb, pal):
    best, best_d = 0, 1e18
    for i, (_, _, p) in enumerate(pal):
        d = _dist(rgb, p)
        if d < best_d:
            best, best_d = i, d
    return best


def convert(data, width, dither, families):
    """Return (grid, palette). grid[row][col] is a palette index, or None for transparent."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGBA")
    width = max(1, min(MAX_SIZE, width))
    height = max(1, min(MAX_SIZE, round(img.height * width / img.width)))
    img = img.resize((width, height), Image.LANCZOS)
    pal = build_palette(families)
    px = img.load()

    # error rows for Floyd-Steinberg
    err = [[[0.0, 0.0, 0.0] for _ in range(width)] for _ in range(height)]
    cache = {}
    grid = []
    for y in range(height):
        row = []
        for x in range(width):
            r, g, b, a = px[x, y]
            if a < 128:
                row.append(None)
                continue
            if dither:
                e = err[y][x]
                want = tuple(max(0, min(255, c + e[k])) for k, c in enumerate((r, g, b)))
                idx = _nearest(want, pal)
                got = pal[idx][2]
                diff = [want[k] - got[k] for k in range(3)]
                for dx, dy, wt in ((1, 0, 7 / 16), (-1, 1, 3 / 16), (0, 1, 5 / 16), (1, 1, 1 / 16)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < width and ny < height:
                        for k in range(3):
                            err[ny][nx][k] += diff[k] * wt
            else:
                key = (r, g, b)
                idx = cache.get(key)
                if idx is None:
                    idx = cache[key] = _nearest(key, pal)
            row.append(idx)
        grid.append(row)
    return grid, pal


def merge(grid):
    """Greedy rectangles: merge same-colored runs, then stack identical runs on consecutive rows."""
    rects = []  # [col0, col1, row0, row1, palette index]
    open_ = {}
    w = len(grid[0])
    for r, row in enumerate(grid):
        runs = []
        c = 0
        while c < w:
            v = row[c]
            if v is None:
                c += 1
                continue
            e = c
            while e + 1 < w and row[e + 1] == v:
                e += 1
            runs.append((c, e, v))
            c = e + 1
        new_open = {}
        for key in runs:
            rect = open_.get(key)
            if rect:
                rect[3] = r
            else:
                rect = [key[0], key[1], r, r, key[2]]
                rects.append(rect)
            new_open[key] = rect
        open_ = new_open
    return rects


def block_name(fam, idx, syntax):
    f = FAMILIES[fam]
    if syntax == "modern":
        return f["modern"].format(c=COLORS[idx])
    return f"{f['legacy']} {idx}"


def _rel(n):
    return "~" if n == 0 else f"~{n}"


def to_commands(grid, pal, mode, facing, syntax, distance=3):
    fx, fz, rx, rz = FACING[facing]
    w, h = len(grid[0]), len(grid)
    half = w // 2

    def pos(col, row):
        a = col - half
        if mode == "wall":
            return fx * distance + rx * a, h - 1 - row, fz * distance + rz * a
        d = distance + (h - 1 - row)
        return fx * d + rx * a, -1, fz * d + rz * a

    cmds = []
    for c0, c1, r0, r1, idx in merge(grid):
        x0, y0, z0 = pos(c0, r0)
        x1, y1, z1 = pos(c1, r1)
        fam, ci, _ = pal[idx]
        cmds.append(f"fill {_rel(x0)} {_rel(y0)} {_rel(z0)} {_rel(x1)} {_rel(y1)} {_rel(z1)} "
                    f"{block_name(fam, ci, syntax)}")
    return cmds


def counts(grid, pal):
    tally = {}
    for row in grid:
        for v in row:
            if v is not None:
                tally[v] = tally.get(v, 0) + 1
    return [{"name": f"{COLORS[pal[i][1]].replace('_', ' ')} {pal[i][0]}", "rgb": pal[i][2], "count": n}
            for i, n in sorted(tally.items(), key=lambda t: -t[1])]


def preview_png(grid, pal, target=480):
    h, w = len(grid), len(grid[0])
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = img.load()
    for y, row in enumerate(grid):
        for x, v in enumerate(row):
            if v is not None:
                px[x, y] = (*pal[v][2], 255)
    scale = max(1, target // max(w, h))
    img = img.resize((w * scale, h * scale), Image.NEAREST)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
