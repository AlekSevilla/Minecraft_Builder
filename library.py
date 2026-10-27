"""Built-in build library. Each entry returns a plan in the same format ai3d produces.

Coordinates are local to the build: x grows to the right (seen from the front), y up, z away from the player.
`y_offset` shifts the whole build vertically, -1 makes layer y=0 replace the ground surface.
"""
import math


class Plan:
    def __init__(self, name, description, width, depth, height, y_offset=0):
        self.meta = dict(name=name, description=description, width=width, depth=depth, height=height,
                         y_offset=y_offset)
        self.parts = []

    def _add(self, shape, block, a, b, label=""):
        lo = [min(a[i], b[i]) for i in range(3)]
        hi = [max(a[i], b[i]) for i in range(3)]
        self.parts.append({"label": label, "shape": shape, "block": block, "lo": lo, "hi": hi})

    def fill(self, block, a, b):
        self._add("fill", block, a, b)

    def hollow(self, block, a, b):
        self._add("hollow", block, a, b)

    def air(self, a, b):
        self._add("fill", "air", a, b)

    def set(self, block, at):
        self._add("fill", block, at, at)

    def plan(self):
        return {**self.meta, "parts": self.parts}


def disc(p, block, cx, cz, r, y0, y1, hollow=False):
    """Circle of radius r as row fills. hollow=True keeps only a 1-block wall."""
    for dz in range(-r, r + 1):
        a = int(math.sqrt(max(0, r * r + r - dz * dz)))
        if hollow and r >= 2 and abs(dz) <= r - 1:
            b = int(math.sqrt(max(0, (r - 1) ** 2 + (r - 1) - dz * dz)))
            if b >= 0 and (r - 1) ** 2 + (r - 1) - dz * dz >= 0:
                p.fill(block, (cx - a, y0, cz + dz), (cx - b - 1, y1, cz + dz))
                p.fill(block, (cx + b + 1, y0, cz + dz), (cx + a, y1, cz + dz))
                continue
        p.fill(block, (cx - a, y0, cz + dz), (cx + a, y1, cz + dz))


def ball(p, block, cx, cy, cz, R):
    """Hollow sphere shell."""
    for dy in range(-R, R + 1):
        for dz in range(-R, R + 1):
            o = R * R + R - dy * dy - dz * dz
            if o < 0:
                continue
            a = int(math.sqrt(o))
            i = (R - 1) ** 2 + (R - 1) - dy * dy - dz * dz
            if R >= 2 and i >= 0:
                b = int(math.sqrt(i))
                p.fill(block, (cx - a, cy + dy, cz + dz), (cx - b - 1, cy + dy, cz + dz))
                p.fill(block, (cx + b + 1, cy + dy, cz + dz), (cx + a, cy + dy, cz + dz))
            else:
                p.fill(block, (cx - a, cy + dy, cz + dz), (cx + a, cy + dy, cz + dz))


def ring_cells(x0, z0, x1, z1):
    """Cells around the edge of a rectangle, clockwise."""
    cells = [(x0, z) for z in range(z0, z1 + 1)]
    cells += [(x, z1) for x in range(x0 + 1, x1 + 1)]
    cells += [(x1, z) for z in range(z1 - 1, z0 - 1, -1)]
    cells += [(x, z0) for x in range(x1 - 1, x0, -1)]
    return cells


# ---------- simple builds ----------

def house():
    p = Plan("Cottage", "A small oak cottage with a stepped roof and a furnished room.", 11, 11, 12, -1)
    p.fill("cobblestone", (1, 0, 1), (9, 0, 9))
    p.hollow("oak_planks", (1, 1, 1), (9, 5, 9))
    for i in range(6):
        p.fill("spruce_planks", (i, 6 + i, i), (10 - i, 6 + i, 10 - i))
    p.air((5, 2, 1), (5, 3, 1))
    for x in (3, 7):
        p.fill("glass_pane", (x, 3, 1), (x, 4, 1))
    for x in (1, 9):
        p.fill("glass_pane", (x, 3, 5), (x, 4, 5))
    p.set("crafting_table", (3, 2, 3))
    p.set("furnace", (4, 2, 3))
    p.set("white_wool", (8, 2, 7))
    p.set("red_wool", (8, 2, 8))
    p.set("oak_fence", (5, 2, 5))
    p.set("lantern", (5, 3, 5))
    return p.plan()


def tower():
    p = Plan("Stone tower", "A tall stone brick tower with a floating spiral staircase and battlements.", 9, 9, 23)
    p.hollow("stone_bricks", (1, 0, 1), (7, 20, 7))
    p.fill("stone_bricks", (0, 21, 0), (8, 21, 8))
    for x, z in ring_cells(0, 0, 8, 8):
        if (x + z) % 2 == 0:
            p.set("stone_bricks", (x, 22, z))
    p.air((4, 1, 1), (4, 2, 1))
    for y in (2, 7, 12, 17):
        p.set("glass_pane", (7, y, 4))
        p.set("glass_pane", (1, y, 4))
    ring = ring_cells(2, 2, 6, 6)
    for i in range(20):
        x, z = ring[i % len(ring)]
        p.set("stone_bricks", (x, i + 1, z))
    for i in (19, 20):
        x, z = ring[i % len(ring)]
        p.set("air", (x, 21, z))
    p.set("lantern", (4, 21, 4))
    return p.plan()


def pyramid():
    p = Plan("Pyramid", "A sandstone pyramid with a tunnel entrance and a treasure chamber.", 21, 21, 11)
    for i in range(11):
        p.fill("sandstone", (i, i, i), (20 - i, i, 20 - i))
    p.air((10, 1, 0), (10, 2, 8))
    p.air((6, 1, 6), (14, 5, 14))
    p.set("gold_block", (10, 1, 10))
    for x, z in ((6, 6), (14, 6), (6, 14), (14, 14)):
        p.fill("chiseled_sandstone", (x, 1, z), (x, 4, z))
    p.set("lantern", (10, 2, 10))
    return p.plan()


def sphere():
    p = Plan("Glass sphere", "A hollow glass sphere with a floor.", 17, 17, 17)
    ball(p, "glass", 8, 8, 8, 8)
    p.fill("stone_bricks", (3, 4, 3), (13, 4, 13))
    p.air((5, 4, 5), (11, 4, 11))
    p.fill("quartz_block", (5, 4, 5), (11, 4, 11))
    p.set("sea_lantern", (8, 5, 8))
    return p.plan()


def wall():
    p = Plan("Castle wall", "A 31 long stone brick wall with a walkway and battlements.", 31, 3, 7)
    p.fill("stone_bricks", (0, 0, 0), (30, 4, 2))
    p.fill("stone_brick_slab", (0, 5, 0), (30, 5, 2))
    for x in range(0, 31, 2):
        p.fill("stone_bricks", (x, 5, 0), (x, 6, 0))
        p.fill("stone_bricks", (x, 5, 2), (x, 6, 2))
    p.fill("stone_brick_slab", (0, 5, 1), (30, 5, 1))
    return p.plan()


# ---------- bigger builds ----------

def castle():
    W = 45
    p = Plan("Castle", "A walled castle with four corner towers, a gatehouse and a furnished keep.", W, W, 30)
    p.fill("grass_block", (0, 0, 0), (W - 1, 0, W - 1))
    p.fill("stone_bricks", (4, 0, 4), (W - 5, 0, W - 5))
    # curtain walls
    p.hollow("stone_bricks", (4, 1, 4), (W - 5, 9, W - 5))
    p.air((5, 1, 5), (W - 6, 9, W - 6))
    p.fill("stone_bricks", (4, 9, 4), (W - 5, 9, W - 5))
    p.air((7, 9, 7), (W - 8, 9, W - 8))
    for x, z in ring_cells(4, 4, W - 5, W - 5):
        if (x + z) % 2 == 0:
            p.set("stone_bricks", (x, 10, z))
    # corner towers with cone roofs
    for tx, tz in ((2, 2), (W - 7, 2), (2, W - 7), (W - 7, W - 7)):
        p.hollow("stone_bricks", (tx, 1, tz), (tx + 4, 16, tz + 4))
        p.fill("stone_bricks", (tx - 1, 17, tz - 1), (tx + 5, 17, tz + 5))
        for k in range(3):
            p.fill("dark_oak_planks", (tx + k, 18 + k, tz + k), (tx + 4 - k, 18 + k, tz + 4 - k))
        p.set("dark_oak_planks", (tx + 2, 21, tz + 2))
        p.fill("glass_pane", (tx + 2, 9, tz), (tx + 2, 10, tz))
    # gatehouse on the front wall
    gx = W // 2
    p.hollow("stone_bricks", (gx - 4, 1, 2), (gx + 4, 13, 8))
    p.air((gx - 2, 1, 2), (gx + 2, 6, 8))
    p.fill("iron_bars", (gx - 2, 4, 3), (gx + 2, 6, 3))
    p.fill("stone_bricks", (gx - 5, 14, 1), (gx + 5, 14, 9))
    for x in range(gx - 5, gx + 6, 2):
        p.fill("stone_bricks", (x, 15, 1), (x, 16, 1))
    p.fill("red_wool", (gx - 1, 1, 9), (gx + 1, 1, 25))
    # keep
    kx = W // 2 - 6
    p.hollow("stone_bricks", (kx, 1, 18), (kx + 12, 20, 30))
    p.fill("oak_planks", (kx + 1, 1, 19), (kx + 11, 1, 29))
    p.fill("white_concrete", (kx - 1, 21, 17), (kx + 13, 21, 31))
    for k in range(5):
        p.fill("spruce_planks", (kx - 1 + k * 2, 22 + k, 17 + k * 2), (kx + 13 - k * 2, 22 + k, 31 - k * 2))
    p.air((kx + 6, 2, 18), (kx + 6, 4, 18))
    for y in (4, 12):
        for x in (kx + 3, kx + 9):
            p.fill("glass_pane", (x, y, 18), (x, y + 2, 18))
    for z in (22, 26):
        p.fill("glass_pane", (kx, 4, z), (kx, 6, z))
        p.fill("glass_pane", (kx + 12, 4, z), (kx + 12, 6, z))
    p.fill("oak_planks", (kx + 1, 10, 19), (kx + 11, 10, 29))
    p.air((kx + 9, 10, 27), (kx + 11, 10, 29))
    p.fill("red_wool", (kx + 4, 2, 21), (kx + 8, 2, 27))
    p.fill("oak_fence", (kx + 5, 2, 23), (kx + 7, 2, 25))
    p.fill("oak_planks", (kx + 5, 3, 23), (kx + 7, 3, 25))
    p.set("lantern", (kx + 6, 4, 24))
    p.set("crafting_table", (kx + 1, 2, 28))
    p.set("furnace", (kx + 2, 2, 28))
    p.set("bookshelf", (kx + 11, 2, 19))
    p.fill("bookshelf", (kx + 11, 2, 21), (kx + 11, 3, 24))
    p.set("white_wool", (kx + 8, 11, 19))
    p.set("red_wool", (kx + 8, 11, 20))
    # steps up to the first floor along the west wall of the keep
    for i in range(9):
        p.fill("stone_bricks", (kx + 1, 1 + i, 28 - i), (kx + 2, 1 + i, 28 - i))
    p.air((kx + 1, 10, 19), (kx + 2, 10, 21))
    return p.plan()


def lighthouse():
    p = Plan("Lighthouse", "A red and white striped lighthouse with a glass lantern room.", 13, 13, 40)
    cx = cz = 6
    p.fill("stone_bricks", (0, 0, 0), (12, 0, 12))
    disc(p, "stone_bricks", cx, cz, 6, 0, 1)
    y = 2
    for band in range(10):
        r = 5 - band // 4
        block = "white_concrete" if band % 2 == 0 else "red_concrete"
        disc(p, block, cx, cz, r, y, y + 2, hollow=True)
        y += 3
    top = y
    disc(p, "black_concrete", cx, cz, 6, top, top)
    disc(p, "iron_bars", cx, cz, 6, top + 1, top + 1, hollow=True)
    disc(p, "glass", cx, cz, 3, top + 1, top + 4, hollow=True)
    p.set("sea_lantern", (cx, top + 1, cz))
    p.fill("sea_lantern", (cx, top + 2, cz), (cx, top + 3, cz))
    disc(p, "red_concrete", cx, cz, 4, top + 5, top + 5)
    disc(p, "red_concrete", cx, cz, 2, top + 6, top + 6)
    p.set("red_concrete", (cx, top + 7, cz))
    p.air((cx, 2, cz - 5), (cx, 3, cz - 5))
    ring = ring_cells(cx - 3, cz - 3, cx + 3, cz + 3)
    for i in range(top - 2):
        x, z = ring[i % len(ring)]
        p.set("stone_bricks", (x, 2 + i, z))
    p.air((cx - 3, top, cz - 3), (cx + 3, top, cz + 3))
    p.fill("black_concrete", (cx - 5, top, cz - 5), (cx - 4, top, cz + 5))
    p.fill("black_concrete", (cx + 4, top, cz - 5), (cx + 5, top, cz + 5))
    p.fill("black_concrete", (cx - 3, top, cz - 5), (cx + 3, top, cz - 4))
    p.fill("black_concrete", (cx - 3, top, cz + 4), (cx + 3, top, cz + 5))
    p.air((cx - 2, top, cz - 2), (cx + 2, top, cz + 2))
    return p.plan()


def barn():
    p = Plan("Barn", "A red barn with a hayloft, big doors, hay bales and a fenced yard.", 21, 31, 16, -1)
    p.fill("grass_block", (0, 0, 0), (20, 0, 30))
    p.fill("coarse_dirt", (4, 0, 0), (16, 0, 10))
    p.hollow("red_concrete", (3, 1, 11), (17, 7, 29))
    p.fill("oak_planks", (4, 1, 12), (16, 1, 28))
    for i in range(7):
        p.fill("spruce_planks", (3 + i, 8 + i, 11), (17 - i, 8 + i, 29))
        if i:
            p.air((3 + i + 1, 8 + i, 12), (17 - i - 1, 8 + i, 28))
    p.fill("spruce_planks", (3, 8, 11), (3, 8, 29))
    p.fill("spruce_planks", (17, 8, 11), (17, 8, 29))
    p.fill("white_concrete", (3, 1, 11), (3, 7, 11))
    p.fill("white_concrete", (17, 1, 11), (17, 7, 11))
    p.fill("white_concrete", (8, 1, 11), (12, 7, 11))
    p.fill("red_concrete", (9, 1, 11), (11, 7, 11))
    p.air((9, 2, 11), (11, 5, 11))
    p.fill("white_concrete", (8, 2, 11), (8, 5, 11))
    p.fill("white_concrete", (12, 2, 11), (12, 5, 11))
    p.fill("white_concrete", (8, 6, 11), (12, 6, 11))
    p.fill("oak_planks", (4, 8, 12), (16, 8, 28))
    p.air((13, 8, 24), (16, 8, 28))
    p.fill("glass_pane", (6, 3, 11), (6, 4, 11))
    p.fill("glass_pane", (14, 3, 11), (14, 4, 11))
    for z in (16, 22, 27):
        p.fill("glass_pane", (3, 3, z), (3, 4, z))
        p.fill("glass_pane", (17, 3, z), (17, 4, z))
    for z in (14, 17, 20):
        p.fill("hay_block", (4, 2, z), (5, 3, z + 1))
    p.fill("hay_block", (14, 2, 20), (16, 3, 22))
    p.fill("hay_block", (4, 9, 14), (7, 10, 18))
    p.fill("oak_fence", (12, 2, 25), (16, 2, 25))
    p.set("lantern", (10, 3, 20))
    p.set("oak_fence", (10, 2, 20))
    for x, z in ring_cells(1, 0, 19, 10):
        if not (8 <= x <= 12 and z == 10):
            p.set("oak_fence", (x, 1, z))
    return p.plan()


# ---------- the airport ----------

def _airliner(p, t, L, span, fin, accent, seats=True, engines=True):
    """Draw a plane. t(u, v) -> (x, z) maps along-fuselage u (0 = nose) and sideways v onto the grid."""
    def box(shape, block, u0, u1, v0, v1, y0, y1):
        xa, za = t(u0, v0)
        xb, zb = t(u1, v1)
        p._add(shape, block, (xa, y0, za), (xb, y1, zb))

    W, G, B = "white_concrete", "light_gray_concrete", "black_concrete"
    box("fill", W, 0, 0, -1, 1, 3, 5)                           # nose tip
    box("hollow", W, 1, L - 4, -2, 2, 2, 6)                     # fuselage shell
    for v in (-2, 2):                                           # round off the corners
        box("fill", "air", 2, L - 5, v, v, 2, 2)
        box("fill", "air", 2, L - 5, v, v, 6, 6)
    box("fill", W, L - 3, L - 2, -1, 1, 3, 5)                   # tail cone
    box("fill", W, L - 1, L - 1, 0, 0, 3, 5)
    box("fill", B, 1, 1, -1, 1, 4, 5)                           # windscreen
    box("fill", B, 2, 3, -2, -2, 4, 5)
    box("fill", B, 2, 3, 2, 2, 4, 5)
    for u in range(5, L - 5, 2):                                # cabin windows
        box("fill", "light_blue_concrete", u, u, -2, -2, 4, 4)
        box("fill", "light_blue_concrete", u, u, 2, 2, 4, 4)
    for v in (-2, 2):                                           # livery stripe
        box("fill", accent, 3, L - 6, v, v, 3, 3)
    if seats:
        for u in range(5, L - 5, 2):
            box("fill", "blue_wool", u, u, -1, -1, 3, 3)
            box("fill", "blue_wool", u, u, 1, 1, 3, 3)
        for u in range(6, L - 6, 5):
            box("fill", "sea_lantern", u, u, 0, 0, 5, 5)
        box("fill", "gray_concrete", 2, 3, -1, 1, 3, 3)         # cockpit
    wu = max(4, L // 3)                                         # wings, swept back
    for k in range(span // 2 - 2):
        us = wu + (k + 1) // 2
        block = accent if k >= span // 2 - 4 else G
        box("fill", block, us, us + 4, 3 + k, 3 + k, 3, 3)
        box("fill", block, us, us + 4, -3 - k, -3 - k, 3, 3)
    if engines:
        for s in (-1, 1):
            a, b = sorted((s * 6, s * 7))
            box("fill", G, wu + 1, wu + 5, a, b, 2, 3)
            box("fill", B, wu + 1, wu + 1, a, b, 2, 3)
    box("fill", B, 3, 3, 0, 0, 1, 1)                            # landing gear
    for s in (-1, 1):
        box("fill", B, wu + 2, wu + 3, s, s, 1, 1)
    for i in range(fin):                                        # tail fin
        box("fill", accent, L - 6 + (i * 4) // max(1, fin), L - 1, 0, 0, 7 + i, 7 + i)
    box("fill", accent, L - 5, L - 1, 0, 0, 6, 6)
    box("fill", W, L - 4, L - 2, -4, 4, 5, 5)                   # tailplane


def airport():
    Wd, D, H = 100, 86, 30
    p = Plan("Airport",
             "A big furnished airport: two-storey terminal with check-in, seating, baggage and cafe, control tower, "
             "hangar, runway, taxiway, vehicles and four planes.", Wd, D, H, -1)
    p.air((0, 1, 0), (Wd - 1, 24, D - 1))                         # clear the site
    p.fill("grass_block", (0, 0, 0), (Wd - 1, 0, D - 1))

    # roads, apron, taxiway, runway
    p.fill("gray_concrete", (0, 0, 0), (Wd - 1, 0, 5))
    for x in range(1, Wd - 3, 6):
        p.fill("white_concrete", (x, 0, 3), (x + 3, 0, 3))
    p.fill("light_gray_concrete", (0, 0, 30), (Wd - 1, 0, 58))
    p.fill("gray_concrete", (0, 0, 60), (Wd - 1, 0, 64))
    for x in range(1, Wd - 4, 8):
        p.fill("yellow_concrete", (x, 0, 62), (x + 4, 0, 62))
    for cx in (20, 46, 74):
        p.fill("yellow_concrete", (cx, 0, 33), (cx, 0, 58))
        p.fill("yellow_concrete", (cx, 0, 59), (cx, 0, 61))
    p.fill("black_concrete", (0, 0, 68), (Wd - 1, 0, 80))
    p.fill("white_concrete", (0, 0, 68), (Wd - 1, 0, 68))
    p.fill("white_concrete", (0, 0, 80), (Wd - 1, 0, 80))
    for z in range(69, 80, 2):
        p.fill("white_concrete", (2, 0, z), (8, 0, z))
        p.fill("white_concrete", (Wd - 9, 0, z), (Wd - 3, 0, z))
    for x in range(14, Wd - 14, 9):
        p.fill("white_concrete", (x, 0, 74), (x + 5, 0, 74))
    for x in range(2, Wd, 8):
        p.set("sea_lantern", (x, 0, 67))
        p.set("sea_lantern", (x, 0, 81))
    # connector taxiways from apron to runway
    p.fill("gray_concrete", (10, 0, 65), (14, 0, 67))
    p.fill("gray_concrete", (80, 0, 65), (84, 0, 67))

    # front road lamps
    for x in range(4, Wd, 14):
        p.fill("oak_fence", (x, 1, 6), (x, 4, 6))
        p.set("lantern", (x, 5, 6))

    # terminal
    tx0, tx1, tz0, tz1 = 8, 57, 10, 29
    p.hollow("white_concrete", (tx0, 0, tz0), (tx1, 11, tz1))
    p.fill("light_gray_concrete", (tx0 - 1, 12, tz0 - 1), (tx1 + 1, 12, tz1 + 1))
    p.fill("polished_andesite", (tx0 + 1, 0, tz0 + 1), (tx1 - 1, 0, tz1 - 1))
    for x in range(tx0 + 2, tx1 - 1, 6):                           # glass curtain wall at the front
        p.fill("glass", (x, 1, tz0), (x + 4, 9, tz0))
    for x in range(tx0 + 1, tx1, 6):
        p.fill("quartz_block", (x, 1, tz0), (x, 10, tz0))
    p.air((29, 1, tz0), (34, 4, tz0))                              # entrance
    p.fill("light_gray_concrete", (24, 6, 5), (39, 6, tz0))        # entrance canopy
    for x in (24, 39):
        p.fill("quartz_block", (x, 1, 6), (x, 5, 6))
    for x in range(tx0 + 3, tx1 - 3, 7):                           # back windows toward the apron
        p.fill("glass", (x, 2, tz1), (x + 4, 6, tz1))
    for z in (14, 18, 24):                                         # end walls
        for x in (tx0, tx1):
            p.fill("glass", (x, 2, z), (x, 5, z + 2))
    for gx in (20, 46):                                            # jet bridges to the gates
        p.air((gx - 1, 1, tz1), (gx + 1, 3, tz1))
        p.hollow("white_concrete", (gx - 2, 0, tz1 + 1), (gx + 2, 4, tz1 + 4))
        p.air((gx - 1, 1, tz1 + 1), (gx + 1, 3, tz1 + 4))
        p.fill("glass", (gx - 2, 2, tz1 + 2), (gx - 2, 3, tz1 + 3))
        p.fill("glass", (gx + 2, 2, tz1 + 2), (gx + 2, 3, tz1 + 3))
    # lighting and interior
    for x in range(tx0 + 5, tx1, 8):
        for z in (13, 19, 25):
            p.set("sea_lantern", (x, 10, z))
    for x0 in (14, 20):                                            # seating
        for z in (13, 16):
            p.fill("light_blue_wool", (x0, 1, z), (x0 + 4, 1, z))
    for x0 in (16, 24, 36, 44):                                    # check-in desks
        p.fill("quartz_block", (x0, 1, 23), (x0 + 4, 2, 23))
        p.fill("black_concrete", (x0 + 1, 3, 23), (x0 + 3, 3, 23))
        p.set("sea_lantern", (x0 + 2, 1, 22))
    p.fill("black_concrete", (40, 1, 14), (52, 1, 14))             # baggage carousel
    p.fill("iron_block", (39, 1, 13), (53, 1, 13))
    p.fill("iron_block", (39, 1, 15), (53, 1, 15))
    for x in (42, 45, 49):
        p.set("brown_concrete", (x, 2, 14))
    for i in range(4):                                             # stairs up to the mezzanine
        p.fill("quartz_block", (10, 1, 16 + i), (12, 1 + i, 16 + i))
    p.fill("smooth_stone", (9, 5, 20), (tx1 - 1, 5, 28))           # mezzanine
    p.fill("glass_pane", (9, 6, 20), (tx1 - 1, 6, 20))
    p.air((10, 6, 20), (12, 6, 20))
    p.fill("spruce_planks", (40, 6, 26), (52, 6, 26))               # cafe counter
    for x in (42, 46, 50):
        p.set("oak_fence", (x, 6, 23))
        p.set("oak_pressure_plate", (x, 7, 23))
    p.fill("barrel", (41, 6, 28), (43, 6, 28))
    p.fill("furnace", (47, 6, 28), (49, 6, 28))
    for x in (16, 24, 32):                                          # lounge sofas on the mezzanine
        p.fill("red_wool", (x, 6, 23), (x + 3, 6, 23))
        p.fill("red_wool", (x, 7, 24), (x + 3, 7, 24))
        p.fill("red_wool", (x, 6, 24), (x + 3, 6, 24))
    p.fill("lime_wool", (54, 6, 21), (55, 6, 27))                   # planters
    p.fill("green_wool", (54, 7, 21), (55, 7, 27))

    # control tower
    p.hollow("white_concrete", (71, 0, 15), (75, 18, 19))
    for y in range(3, 18, 5):
        p.fill("light_gray_concrete", (71, y, 15), (75, y, 19))
    p.air((73, 1, 15), (73, 2, 15))
    p.fill("black_concrete", (69, 18, 13), (77, 18, 21))
    p.air((72, 18, 16), (74, 18, 18))
    p.hollow("glass", (69, 19, 13), (77, 22, 21))
    p.air((70, 19, 14), (76, 22, 20))
    p.fill("black_concrete", (67, 23, 11), (79, 23, 23))
    p.fill("black_concrete", (70, 19, 14), (76, 19, 14))
    p.fill("sea_lantern", (72, 22, 17), (74, 22, 17))
    p.fill("iron_bars", (73, 24, 17), (73, 28, 17))
    p.set("iron_block", (73, 24, 16))
    p.fill("light_gray_concrete", (72, 27, 17), (74, 27, 17))
    ring = ring_cells(72, 16, 74, 18)
    for i in range(18):
        x, z = ring[i % len(ring)]
        p.set("quartz_block", (x, i + 1, z))

    # hangar
    p.hollow("light_gray_concrete", (82, 0, 8), (98, 14, 28))
    for i, (a, b) in enumerate(((83, 97), (85, 95), (87, 93))):
        p.fill("gray_concrete", (a, 15 + i, 8), (b, 15 + i, 28))
    p.air((84, 1, 28), (96, 8, 28))
    p.fill("iron_block", (83, 9, 28), (97, 9, 28))
    p.fill("sea_lantern", (84, 13, 12), (96, 13, 12))
    p.fill("sea_lantern", (84, 13, 24), (96, 13, 24))
    p.fill("polished_andesite", (83, 0, 9), (97, 0, 27))
    p.set("crafting_table", (84, 1, 10))
    p.set("anvil", (85, 1, 10))
    p.set("furnace", (86, 1, 10))
    p.fill("red_concrete", (96, 1, 10), (97, 2, 12))
    p.fill("barrel", (94, 1, 10), (95, 1, 10))
    p.fill("chest", (84, 1, 25), (85, 1, 25))

    # planes: two at the gates, one on the east apron, one on the runway, a small one in the hangar
    _airliner(p, lambda u, v: (20 + v, 34 + u), 22, 22, 7, "red_concrete")
    _airliner(p, lambda u, v: (46 + v, 34 + u), 22, 22, 7, "blue_concrete")
    _airliner(p, lambda u, v: (74 + v, 34 + u), 22, 22, 7, "orange_concrete")
    _airliner(p, lambda u, v: (62 - u, 74 + v), 22, 22, 7, "green_concrete")
    _airliner(p, lambda u, v: (91 + v, 14 + u), 14, 12, 5, "yellow_concrete", seats=False, engines=False)

    # airport vehicles
    p.fill("white_concrete", (60, 2, 42), (62, 3, 46))             # fuel truck tank
    p.fill("red_concrete", (60, 2, 38), (62, 3, 41))
    p.fill("black_concrete", (60, 4, 40), (62, 4, 40))
    p.fill("black_concrete", (60, 1, 38), (60, 1, 39))
    p.fill("black_concrete", (62, 1, 38), (62, 1, 39))
    p.fill("black_concrete", (60, 1, 44), (60, 1, 45))
    p.fill("black_concrete", (62, 1, 44), (62, 1, 45))
    p.fill("gray_concrete", (32, 1, 40), (33, 1, 43))              # baggage cart
    p.fill("brown_concrete", (32, 2, 41), (33, 2, 42))
    p.fill("yellow_concrete", (32, 1, 45), (33, 2, 46))
    # windsock
    p.fill("oak_fence", (96, 1, 62), (96, 7, 62))
    p.fill("orange_concrete", (95, 7, 62), (93, 7, 62))
    return p.plan()


# ---------- the mall ----------

class ShiftPlan(Plan):
    """Plan whose z coordinates are shifted, so a build can use negative z (a parking lot in front)."""
    def __init__(self, *args, dz=0, **kw):
        super().__init__(*args, **kw)
        self.dz = dz

    def _add(self, shape, block, a, b, label=""):
        super()._add(shape, block, (a[0], a[1], a[2] + self.dz), (b[0], b[1], b[2] + self.dz), label)


_THEMES = [  # floor, sign band, goods
    ("light_gray_wool", "red_concrete", "red_wool"), ("white_wool", "blue_concrete", "light_blue_wool"),
    ("light_gray_wool", "orange_concrete", "orange_wool"), ("white_wool", "green_concrete", "lime_wool"),
    ("light_gray_wool", "purple_concrete", "magenta_wool"), ("white_wool", "yellow_concrete", "yellow_wool"),
    ("light_gray_wool", "cyan_concrete", "cyan_wool"), ("white_wool", "pink_concrete", "pink_wool"),
]


def _shop(p, x0, z0, x1, z1, f, door, theme):
    """One shop room on floor f. door is the wall the shopfront is on: n (z0), s (z1), w (x0), e (x1)."""
    y = 8 * f
    floor, trim, goods = theme
    if door in "ns":
        Wd, Dp = x1 - x0 + 1, z1 - z0 + 1
    else:
        Wd, Dp = z1 - z0 + 1, x1 - x0 + 1

    def at(u, v):
        return {"n": (x0 + u, z0 + v), "s": (x0 + u, z1 - v),
                "w": (x0 + v, z0 + u), "e": (x1 - v, z0 + u)}[door]

    def box(block, u0, v0, u1, v1, ya, yb, shape="fill"):
        (xa, za), (xb, zb) = at(u0, v0), at(u1, v1)
        p._add(shape, block, (xa, y + ya, za), (xb, y + yb, zb))

    p.hollow("white_concrete", (x0, y + 1, z0), (x1, y + 7, z1))
    p.air((x0 + 1, y + 1, z0 + 1), (x1 - 1, y + 7, z1 - 1))
    p.fill(floor, (x0 + 1, y, z0 + 1), (x1 - 1, y, z1 - 1))
    box("glass", 1, 0, Wd - 2, 0, 1, 5)                       # glass shopfront, sign band above, door gap
    box(trim, 0, 0, Wd - 1, 0, 6, 7)
    mid = Wd // 2
    box("air", mid - 1, 0, mid + 1, 0, 1, 4)
    box("bookshelf", 1, Dp - 2, Wd - 2, Dp - 2, 1, 3)           # back wall shelves
    box("bookshelf", 1, 3, 1, Dp - 4, 1, 2)                     # side shelves
    box("quartz_block", 2, 3, mid, 3, 1, 1)                     # sales counter
    box(goods, 2, 3, mid, 3, 2, 2)
    for u in range(3, Wd - 3, 4):                               # display tables with goods
        box("oak_fence", u, Dp // 2, u + 1, Dp // 2, 1, 1)
        box(goods, u, Dp // 2, u + 1, Dp // 2, 2, 2)
    # fitting room: a closed cubicle with a gap in one side, good for hiding
    box("oak_planks", Wd - 5, Dp - 6, Wd - 2, Dp - 3, 1, 3, "hollow")
    box("air", Wd - 4, Dp - 5, Wd - 3, Dp - 4, 1, 3)
    box("air", Wd - 5, Dp - 5, Wd - 5, Dp - 5, 1, 2)
    box("lantern", Wd - 4, Dp - 4, Wd - 4, Dp - 4, 1, 1)
    box("barrel", 1, Dp - 5, 2, Dp - 4, 1, 2)                   # stock crates
    box("sea_lantern", mid, 2, mid, 2, 7, 7)
    box("sea_lantern", mid, Dp - 3, mid, Dp - 3, 7, 7)


def mall():
    W, D, H, Z = 120, 90, 28, 12
    p = ShiftPlan("Shopping mall",
                  "A massive three-storey mall for hide and seek: glass atrium with a fountain and skylight, "
                  "furnished shops with fitting rooms and stock crates, kiosks, pillars, planters and stairs "
                  "between floors, plus a parking lot with cars.", W, D + Z, H, -1, dz=Z)
    p.air((0, 1, -Z), (W - 1, 27, D - 1))
    # parking lot
    p.fill("gray_concrete", (0, 0, -Z), (W - 1, 0, -1))
    for x in range(2, W - 1, 6):
        p.fill("white_concrete", (x, 0, -11), (x, 0, -4))
    cars = ["red_concrete", "blue_concrete", "white_concrete", "black_concrete", "yellow_concrete", "green_concrete"]
    for i, x in enumerate(range(3, W - 5, 12)):
        c = cars[i % len(cars)]
        z = -10 if i % 2 == 0 else -6
        p.fill(c, (x, 1, z), (x + 3, 1, z + 1))
        p.fill(c, (x + 1, 2, z), (x + 2, 2, z + 1))
    for x in range(8, W, 24):
        p.fill("oak_fence", (x, 1, -2), (x, 4, -2))
        p.set("lantern", (x, 5, -2))

    # shell, floors, roof
    p.hollow("light_gray_concrete", (0, 0, 0), (W - 1, 24, D - 1))
    p.fill("polished_andesite", (1, 0, 1), (W - 2, 0, D - 2))
    for f in (1, 2):
        p.fill("quartz_block", (1, 8 * f, 1), (W - 2, 8 * f, D - 2))
    p.fill("black_concrete", (0, 25, 0), (W - 1, 25, 0))
    p.fill("black_concrete", (0, 25, D - 1), (W - 1, 25, D - 1))
    p.fill("black_concrete", (0, 25, 0), (0, 25, D - 1))
    p.fill("black_concrete", (W - 1, 25, 0), (W - 1, 25, D - 1))
    p.fill("blue_concrete", (0, 20, 0), (W - 1, 22, 0))         # front sign band
    ax0, ax1, az0, az1 = 45, 74, 25, 64                           # atrium
    for f in (1, 2):
        p.air((ax0, 8 * f, az0), (ax1, 8 * f, az1))
    p.fill("glass", (ax0, 24, az0), (ax1, 24, az1))               # skylight
    # facade glass bands with pillars on all four walls
    for f in range(3):
        y = 8 * f
        for z in (0, D - 1):
            p.fill("glass", (2, y + 2, z), (W - 3, y + 6, z))
            for x in range(4, W - 3, 8):
                p.fill("white_concrete", (x, y + 1, z), (x, y + 7, z))
        for x in (0, W - 1):
            p.fill("glass", (x, y + 2, 2), (x, y + 6, D - 3))
            for z in range(4, D - 3, 8):
                p.fill("white_concrete", (x, y + 1, z), (x, y + 7, z))

    # shops: front row, back row, left and right wings, on all three floors
    for f in range(3):
        skip = {5, 6} if f == 0 else set()
        n = 0
        for k in range(11):
            if k in skip:
                continue
            _shop(p, 1 + 10 * k, 1, 10 + 10 * k, 14, f, "s", _THEMES[(n + f) % 8])
            n += 1
        for k in range(11):
            _shop(p, 1 + 10 * k, 75, 10 + 10 * k, 88, f, "n", _THEMES[(n + f + 3) % 8])
            n += 1
        for k in range(6):
            _shop(p, 1, 15 + 10 * k, 28, 24 + 10 * k, f, "e", _THEMES[(n + f) % 8])
            _shop(p, 91, 15 + 10 * k, 118, 24 + 10 * k, f, "w", _THEMES[(n + f + 5) % 8])
            n += 1

    # main entrance and the ground floor lobby where the two front shops are left out
    p.air((54, 1, 0), (65, 5, 1))
    p.fill("light_gray_concrete", (50, 7, -6), (69, 7, 0))        # canopy
    for x in (50, 69):
        p.fill("quartz_block", (x, 1, -6), (x, 6, -6))
    p.fill("quartz_block", (51, 0, 1), (70, 0, 14))
    p.fill("red_wool", (58, 0, 1), (63, 0, 14))
    for x in (52, 69):
        p.fill("moss_block", (x, 1, 2), (x, 1, 5))
    p.fill("quartz_block", (53, 1, 8), (68, 1, 8))
    p.fill("black_concrete", (54, 2, 8), (67, 3, 8))              # directory board
    for x in range(54, 68, 3):
        p.set("sea_lantern", (x, 3, 8))

    # atrium: fountain, benches, planters, railings
    cx, cz = 59, 44
    p.fill("quartz_block", (cx - 5, 1, cz - 5), (cx + 5, 1, cz + 5))
    p.fill("light_blue_concrete", (cx - 4, 1, cz - 4), (cx + 4, 1, cz + 4))
    p.fill("quartz_block", (cx - 1, 2, cz - 1), (cx + 1, 6, cz + 1))
    p.set("sea_lantern", (cx, 7, cz))
    for x, z in ((47, 27), (72, 27), (47, 62), (72, 62)):
        p.fill("moss_block", (x - 1, 1, z - 1), (x + 1, 2, z + 1))
        p.fill("green_concrete", (x, 3, z), (x, 4, z))
    for z, dz in ((30, 1), (58, -1)):
        p.fill("spruce_planks", (50, 1, z), (68, 1, z))
        p.fill("spruce_planks", (51, 2, z + dz), (67, 2, z + dz))
    for f in (1, 2):
        y = 8 * f
        p.fill("glass_pane", (ax0, y + 1, az0), (ax1, y + 2, az0))
        p.fill("glass_pane", (ax0, y + 1, az1), (ax1, y + 2, az1))
        p.fill("glass_pane", (ax0, y + 1, az0), (ax0, y + 2, az1))
        p.fill("glass_pane", (ax1, y + 1, az0), (ax1, y + 2, az1))

    # stairs between floors in the front concourse, two flights
    for f in (0, 1):
        for x0 in (38, 79):
            p.air((x0, 8 * (f + 1), 17), (x0 + 2, 8 * (f + 1), 23))
            for i in range(8):
                p.fill("gray_concrete", (x0, 8 * f + 1, 17 + i), (x0 + 2, 8 * f + 1 + i, 17 + i))
            p.fill("yellow_concrete", (x0 - 1, 8 * f + 1, 17), (x0 - 1, 8 * f + 1, 24))

    # per-floor extras: pillars, kiosks, ceiling lights in the open concourse
    for f in range(3):
        y = 8 * f
        for x in range(31, 90, 8):
            for z in (19, 70):
                p.fill("quartz_block", (x, y + 1, z), (x + 1, y + 7, z + 1))
        for x, z in ((33, 33), (33, 55), (85, 33), (85, 55), (40, 44), (79, 44)):
            p.hollow("spruce_planks", (x, y + 1, z), (x + 2, y + 3, z + 2))
            p.air((x + 1, y + 1, z + 1), (x + 1, y + 2, z + 1))
            p.air((x + 1, y + 1, z), (x + 1, y + 2, z))
            p.fill(_THEMES[(x + z + f) % 8][1], (x, y + 4, z), (x + 2, y + 4, z + 2))
        for x in range(32, 89, 8):
            for z in range(17, 74, 8):
                if f > 0 and ax0 <= x <= ax1 and az0 <= z <= az1:
                    continue
                p.set("sea_lantern", (x, y + 7, z))
    return p.plan()


LIBRARY = {
    "mall": mall,
    "airport": airport,
    "castle": castle,
    "lighthouse": lighthouse,
    "barn": barn,
    "house": house,
    "tower": tower,
    "pyramid": pyramid,
    "sphere": sphere,
    "wall": wall,
}


def get(name):
    return LIBRARY[name]()
