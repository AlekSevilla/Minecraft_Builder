"""Photo(s) -> 3D Minecraft build, designed by Claude's vision and expressed as box primitives."""
import base64
import hashlib
import io
import json
import re

import anthropic
from PIL import Image, ImageOps

from imagebuild import COLORS, FACING

MODEL = "claude-opus-5-5"
MAX_DIM = 1000          # sanity ceilings only; effectively unlimited
MAX_PARTS = 20000
MAX_FILL = 32768        # Bedrock's per-command fill limit
BLOCK_RE = re.compile(r"^[a-z0-9_]+$")
BANNED = {"command_block", "chain_command_block", "repeating_command_block", "structure_block",
          "structure_void", "jigsaw", "tnt", "lava", "flowing_lava", "water", "flowing_water",
          "fire", "bedrock", "barrier", "allow", "deny", "border_block"}

SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "width": {"type": "integer"},
        "depth": {"type": "integer"},
        "height": {"type": "integer"},
        "parts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "shape": {"type": "string", "enum": ["fill", "hollow"]},
                    "block": {"type": "string"},
                    "x0": {"type": "integer"}, "y0": {"type": "integer"}, "z0": {"type": "integer"},
                    "x1": {"type": "integer"}, "y1": {"type": "integer"}, "z1": {"type": "integer"},
                },
                "required": ["label", "shape", "block", "x0", "y0", "z0", "x1", "y1", "z1"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["name", "description", "width", "depth", "height", "parts"],
    "additionalProperties": False,
}

SYSTEM = """You are an expert Minecraft Bedrock Edition architect. You are shown photo(s) or screenshot(s) of a \
structure (real building, landmark, vehicle, statue, a Minecraft build, ...). Design a faithful, recognizable \
blocky version of it that can be built with /fill commands, and return it as a list of box primitives. \
(You may instead be given only a text description; then design what it describes.)

Coordinate system (all integers, inclusive, origin at the front-left-bottom corner of the build):
- x: 0 at the left, increasing to the right, as seen by a viewer standing in front of the build.
- y: 0 is the lowest layer (it sits on the ground), increasing upward.
- z: 0 is the front face (the side the main photo shows), increasing toward the back.
Every coordinate must satisfy 0 <= x < width, 0 <= y < height, 0 <= z < depth, and the build must fit in the \
size limits given by the user.

Primitives, applied in order (later parts overwrite earlier ones):
- shape "fill": every cell in the box becomes `block`.
- shape "hollow": the outer shell of the box becomes `block` and the inside becomes air.
- block "air" carves space: use it for doorways, windows, arches, interiors and cut-outs.

Guidelines:
- Capture the real proportions, silhouette, roof shape, number of floors/towers, symmetry, and the colors and \
materials you see. Pick blocks that match the colors (white_concrete, red_concrete, stone_bricks, \
spruce_planks, quartz_block, sandstone, bricks, glass, glass_pane, dark_oak_log, ...).
- Use real Bedrock block identifiers without a namespace, lowercase with underscores. Only plain full blocks, \
slabs (bottom half by default), fences, walls, glass panes, lanterns, and other blocks that need no orientation or \
block states. Avoid stairs, doors, beds, trapdoors, ladders, signs, buttons, torches on walls and anything else \
that needs facing; build roofs as stepped layers of shrinking boxes, and doorways as air gaps.
- Build the main structure only, not the surrounding scenery, sky, people or vehicles, unless the subject is one.
- Start with the big masses (foundation, walls, roof), then add detail (windows, columns, trim, chimneys, doors). \
Prefer large boxes and repeat modules; keep the total under about 700 parts unless the subject truly needs more.
- Give each wall depth: hollow shells for rooms, and thicker walls for large buildings.
- Fill in width, depth and height with the actual extents you used.
"""


def _prep_image(data):
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.thumbnail((1568, 1568), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return base64.standard_b64encode(buf.getvalue()).decode()


def _ask(system, content, schema, what="design"):
    """One structured-output request to Claude. Returns the parsed JSON object, or raises RuntimeError."""
    client = anthropic.Anthropic()
    kwargs = dict(
        model=MODEL,
        max_tokens=64000,
        system=system,
        thinking={"type": "adaptive"},
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": content}],
    )
    try:
        try:
            # server-side fallback: if the safety classifiers decline, the API retries on another model
            with client.beta.messages.stream(betas=["server-side-fallback-2026-07-01"],
                                             extra_body={"fallbacks": "default"}, **kwargs) as stream:
                msg = stream.get_final_message()
        except anthropic.BadRequestError as e:
            if "fallback" not in str(e).lower():
                raise
            with client.messages.stream(**kwargs) as stream:
                msg = stream.get_final_message()
    except anthropic.AuthenticationError:
        raise RuntimeError("Anthropic API key missing or invalid. Set ANTHROPIC_API_KEY and restart builder.py.")
    except anthropic.RateLimitError:
        raise RuntimeError("Rate limited by the Anthropic API, try again in a minute.")
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"Anthropic API error ({e.status_code}): {e.message}")
    except anthropic.APIConnectionError:
        raise RuntimeError("Could not reach the Anthropic API. Check your internet connection.")
    except TypeError as e:  # SDK raises this when no credentials are configured
        raise RuntimeError(f"Anthropic credentials not configured: {e}. Set ANTHROPIC_API_KEY and restart.")

    if msg.stop_reason == "refusal":
        raise RuntimeError(f"The model declined this request. Try rewording it.")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError(f"The {what} was too large to finish. Try a smaller size or a simpler request.")
    raw = next((b.text for b in msg.content if b.type == "text"), "")
    try:
        return json.loads(raw)
    except ValueError:
        raise RuntimeError(f"The model returned an unreadable {what}. Try again.")


def analyze(images, hint, max_size):
    """Design from photos. Returns the validated plan dict. Raises RuntimeError with a user message."""
    max_size = max(8, min(MAX_DIM, max_size))
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _prep_image(d)}}
               for d in images]
    text = (f"Design this as a Minecraft build. Size limit: at most {max_size} blocks on each axis "
            f"(width, depth and height), and use as much of it as the subject deserves.")
    if len(images) > 1:
        text += " The images show the same subject from different angles."
    if hint.strip():
        text += f"\nUser notes: {hint.strip()}"
    content.append({"type": "text", "text": text})
    return validate(_ask(SYSTEM, content, SCHEMA), max_size)


def generate(description, max_size):
    """Design from a text description."""
    max_size = max(8, min(MAX_DIM, max_size))
    text = (f"Design this as a Minecraft build: {description.strip()}\n"
            f"Size limit: at most {max_size} blocks on each axis (width, depth and height); use as much of it as "
            f"the subject deserves, and make it detailed and furnished where that makes sense.")
    return validate(_ask(SYSTEM, [{"type": "text", "text": text}], SCHEMA), max_size)


PATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "width": {"type": "integer"},
        "depth": {"type": "integer"},
        "height": {"type": "integer"},
        "remove_indices": {"type": "array", "items": {"type": "integer"}},
        "add_parts": SCHEMA["properties"]["parts"],
    },
    "required": ["description", "width", "depth", "height", "remove_indices", "add_parts"],
    "additionalProperties": False,
}

EDIT_RULES = """

You are now EDITING an existing build, not starting over. You are given the current build: its size and its parts \
as numbered lines "index: shape block x0 y0 z0 x1 y1 z1 (label)", applied in index order. Apply the user's request \
with a minimal patch:
- add_parts: new parts appended AFTER all existing parts, so they overwrite what is there. Use block "air" parts to \
cut openings or remove things that would otherwise stay.
- remove_indices: indices of existing parts to delete outright (for example a roof you are replacing).
- width/depth/height: the new overall size. It may grow to fit what you add (up to the limit given), never shrink. \
Existing coordinates never move, so to extend the build to the left or toward the front, put new parts in the \
space that already exists or grow width/depth/height toward the right, back and top.
- description: one sentence describing the whole build after the change.
Keep the existing style and materials unless asked otherwise. Do not repeat parts that already exist."""


def _plan_lines(plan):
    out = [f"size: width {plan['width']}, depth {plan['depth']}, height {plan['height']}, "
           f"y_offset {plan.get('y_offset', 0)}", f"name: {plan['name']}"]
    for i, p in enumerate(plan["parts"]):
        (x0, y0, z0), (x1, y1, z1) = p["lo"], p["hi"]
        out.append(f"{i}: {p['shape']} {p['block']} {x0} {y0} {z0} {x1} {y1} {z1}"
                   + (f" ({p['label']})" if p.get("label") else ""))
    return "\n".join(out)


def refine(plan, instruction):
    """Apply a text instruction to an existing plan. Returns a new validated plan."""
    bound = MAX_DIM
    text = (f"Current build:\n{_plan_lines(plan)}\n\nThere is no practical size limit; grow the build as much as the request needs.\n"
            f"User request: {instruction.strip()}")
    patch = _ask(SYSTEM + EDIT_RULES, [{"type": "text", "text": text}], PATCH_SCHEMA, "change")
    return apply_patch(plan, patch, bound)


def apply_patch(plan, patch, bound):
    try:
        remove = {int(i) for i in patch.get("remove_indices", [])}
        dims = {"width": plan["width"], "depth": plan["depth"], "height": plan["height"]}
        for k in dims:
            dims[k] = max(dims[k], min(bound, int(patch.get(k, dims[k]))))
        added = _validate({**dims, "parts": patch.get("add_parts", [])}, bound, MAX_PARTS)["parts"] \
            if patch.get("add_parts") else []
    except (KeyError, TypeError, ValueError, AttributeError, RuntimeError) as e:
        raise RuntimeError(f"The model's change couldn't be applied ({e}). Try rewording it.")
    kept = [p for i, p in enumerate(plan["parts"]) if i not in remove]
    if not added and len(kept) == len(plan["parts"]):
        raise RuntimeError("The model made no change. Try describing it differently.")
    return {**plan, **dims, "description": str(patch.get("description") or plan["description"])[:400],
            "parts": kept + added}


def validate(plan, max_size, max_parts=MAX_PARTS):
    """Clamp a plan in the model's JSON format into bounds and drop unusable parts."""
    try:
        return _validate(plan, max_size, max_parts)
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise RuntimeError(f"Invalid build format ({type(e).__name__}: {e}). See the format help.")


def _validate(plan, max_size, max_parts):
    dims = {k: max(1, min(max_size, int(plan.get(k, 1)))) for k in ("width", "depth", "height")}
    parts = []
    for p in plan.get("parts", [])[:max_parts]:
        block = str(p.get("block", "")).lower().removeprefix("minecraft:")
        if not BLOCK_RE.match(block) or block in BANNED or p.get("shape") not in ("fill", "hollow"):
            continue
        lo = [min(p[a + "0"], p[a + "1"]) for a in "xyz"]
        hi = [max(p[a + "0"], p[a + "1"]) for a in "xyz"]
        limit = [dims["width"], dims["height"], dims["depth"]]
        lo = [max(0, v) for v in lo]
        hi = [min(limit[i] - 1, v) for i, v in enumerate(hi)]
        if any(lo[i] > hi[i] for i in range(3)):
            continue
        parts.append({"label": str(p.get("label", ""))[:60], "shape": p["shape"], "block": block,
                      "lo": lo, "hi": hi})
    if not parts:
        raise RuntimeError("The design came back empty. Try again or add a hint.")
    return {"name": str(plan.get("name", "Build"))[:80], "description": str(plan.get("description", ""))[:400],
            **dims, "y_offset": max(-8, min(0, int(plan.get("y_offset", 0)))), "parts": parts}


def plan_to_json(plan):
    """Export a plan in the same flat format the model (and the import box) uses."""
    return {
        "name": plan["name"], "description": plan["description"],
        "width": plan["width"], "depth": plan["depth"], "height": plan["height"],
        "y_offset": plan.get("y_offset", 0),
        "parts": [{"label": p["label"], "shape": p["shape"], "block": p["block"],
                   "x0": p["lo"][0], "y0": p["lo"][1], "z0": p["lo"][2],
                   "x1": p["hi"][0], "y1": p["hi"][1], "z1": p["hi"][2]} for p in plan["parts"]],
    }


COMMAND_RE = re.compile(r"^/?(fill|setblock)\s+[~^0-9\-.\s]+[a-z0-9_:]+(\s+[\w\[\]\"=,.\- ]+)?$")


def parse_import(text, max_size=MAX_DIM, max_parts=MAX_PARTS):
    """Parse pasted/uploaded text: a JSON build plan (code fences allowed) or a list of fill/setblock commands.
    Returns ("plan", plan) or ("commands", [lines])."""
    text = text.strip()
    if not text:
        raise RuntimeError("Nothing to import.")
    if "{" in text and "}" in text and not text.lstrip("/").startswith(("fill", "setblock")):
        try:
            data = json.loads(text[text.index("{"): text.rindex("}") + 1])
        except ValueError as e:
            raise RuntimeError(f"That isn't valid JSON: {e}")
        return "plan", validate(data, max_size, max_parts)
    cmds = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if not COMMAND_RE.match(line):
            raise RuntimeError(f"Only fill and setblock commands are supported. Can't use: {line[:80]}")
        cmds.append(line.lstrip("/"))
        if len(cmds) > 500000:
            raise RuntimeError("Too many commands (limit 500000).")
    if not cmds:
        raise RuntimeError("No commands found.")
    return "commands", cmds


_LEGACY = {"concrete": "concrete", "concrete_powder": "concrete_powder", "wool": "wool",
           "terracotta": "stained_hardened_clay", "stained_glass": "stained_glass",
           "stained_glass_pane": "stained_glass_pane", "carpet": "carpet"}
_COLOR_RE = re.compile("^(" + "|".join(COLORS) + ")_(" + "|".join(sorted(_LEGACY, key=len, reverse=True)) + ")$")


def block_ref(name, syntax):
    """Colored blocks are flattened names ("red_concrete") or, on older Bedrock, "concrete 14"."""
    m = _COLOR_RE.match(name)
    if syntax == "legacy" and m:
        return f"{_LEGACY[m.group(2)]} {COLORS.index(m.group(1))}"
    return name


# ---------- voxels, commands, preview ----------

def voxelize(plan):
    """Replay the parts in order. Returns {(x,y,z): block}."""
    grid = {}
    for p in plan["parts"]:
        (x0, y0, z0), (x1, y1, z1) = p["lo"], p["hi"]
        hollow = p["shape"] == "hollow"
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                for z in range(z0, z1 + 1):
                    edge = x in (x0, x1) or y in (y0, y1) or z in (z0, z1)
                    block = p["block"] if (edge or not hollow) else "air"
                    if block == "air":
                        grid.pop((x, y, z), None)
                    else:
                        grid[(x, y, z)] = block
    return grid


def to_commands(plan, facing, distance=3, syntax="legacy"):
    fx, fz, rx, rz = FACING[facing]
    half = plan["width"] // 2
    dy = plan.get("y_offset", 0)

    def pos(x, y, z):
        a, d = x - half, distance + z
        return fx * d + rx * a, y + dy, fz * d + rz * a

    def rel(n):
        return "~" if n == 0 else f"~{n}"

    def emit(lo, hi, block, hollow, out):
        size = [hi[i] - lo[i] + 1 for i in range(3)]
        if size[0] * size[1] * size[2] > MAX_FILL:
            # a hollow box can't be split safely, so approximate it as shell + carved interior
            if hollow:
                emit(lo, hi, block, False, out)
                if all(s > 2 for s in size):
                    emit([v + 1 for v in lo], [v - 1 for v in hi], "air", False, out)
                return
            ax = size.index(max(size))
            mid = lo[ax] + size[ax] // 2
            a_hi, b_lo = list(hi), list(lo)
            a_hi[ax], b_lo[ax] = mid - 1, mid
            emit(lo, a_hi, block, False, out)
            emit(b_lo, hi, block, False, out)
            return
        x0, y0, z0 = pos(*lo)
        x1, y1, z1 = pos(*hi)
        out.append(f"fill {rel(x0)} {rel(y0)} {rel(z0)} {rel(x1)} {rel(y1)} {rel(z1)} {block_ref(block, syntax)}"
                   + (" hollow" if hollow else ""))

    cmds = []
    for p in plan["parts"]:
        emit(p["lo"], p["hi"], p["block"], p["shape"] == "hollow", cmds)
    return cmds


_COLORS = [
    ("glass", (170, 210, 230)), ("white", (230, 230, 230)), ("quartz", (232, 228, 220)), ("snow", (245, 248, 250)),
    ("light_gray", (150, 150, 145)), ("gray", (80, 82, 85)), ("black", (25, 25, 28)), ("blackstone", (40, 36, 42)),
    ("red", (160, 45, 40)), ("brick", (150, 85, 70)), ("orange", (225, 110, 20)), ("terracotta", (160, 90, 65)),
    ("yellow", (235, 195, 40)), ("gold", (240, 200, 60)), ("lime", (110, 185, 30)), ("green", (85, 120, 40)),
    ("leaves", (60, 130, 50)), ("grass", (95, 150, 55)), ("moss", (90, 110, 45)), ("cyan", (30, 130, 140)),
    ("light_blue", (60, 170, 215)), ("blue", (50, 60, 160)), ("purple", (115, 45, 160)), ("magenta", (180, 70, 170)),
    ("pink", (235, 140, 170)), ("brown", (110, 72, 45)), ("dark_oak", (65, 45, 25)), ("spruce", (110, 80, 50)),
    ("birch", (210, 195, 140)), ("jungle", (170, 125, 85)), ("acacia", (175, 95, 55)), ("oak", (165, 130, 80)),
    ("planks", (165, 130, 80)), ("log", (100, 78, 45)), ("sandstone", (218, 205, 150)), ("sand", (225, 210, 160)),
    ("dirt", (125, 90, 60)), ("cobble", (120, 120, 120)), ("stone", (125, 125, 125)), ("deepslate", (70, 70, 75)),
    ("iron", (200, 200, 200)), ("copper", (190, 110, 80)), ("ice", (150, 190, 240)), ("lantern", (250, 200, 100)),
]


def block_color(name):
    for key, rgb in _COLORS:
        if key in name:
            return rgb
    h = hashlib.md5(name.encode()).digest()
    return (90 + h[0] % 120, 90 + h[1] % 120, 90 + h[2] % 120)


def preview_data(grid, changed=(), limit=250000):
    """Surface voxels as [x, y, z, paletteIndex] plus the palette, for the browser's 3D preview."""
    counts = {}
    for b in grid.values():
        counts[b] = counts.get(b, 0) + 1
    names = sorted(counts, key=lambda n: -counts[n])
    index = {n: i for i, n in enumerate(names)}
    out = []
    for (x, y, z), b in grid.items():
        if all((x + dx, y + dy, z + dz) in grid
               for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))):
            continue
        out.append([x, y, z, index[b], 1 if (x, y, z) in changed else 0])
    palette = [{"name": n, "rgb": block_color(n), "count": counts[n]} for n in names]
    return out[:limit], palette


def import_prompt():
    """A prompt to paste into any AI chat (with a photo or a description) to get a build the import box accepts."""
    example = {
        "name": "Little hut", "description": "A small hut.", "width": 7, "depth": 7, "height": 7,
        "parts": [
            {"label": "walls", "shape": "hollow", "block": "oak_planks", "x0": 0, "y0": 0, "z0": 0, "x1": 6, "y1": 4, "z1": 6},
            {"label": "door", "shape": "fill", "block": "air", "x0": 3, "y0": 1, "z0": 0, "x1": 3, "y1": 2, "z1": 0},
            {"label": "roof", "shape": "fill", "block": "spruce_planks", "x0": 0, "y0": 5, "z0": 0, "x1": 6, "y1": 5, "z1": 6},
        ],
    }
    return (SYSTEM + "\nOutput format: reply with ONLY one JSON object (no explanation), shaped like this example. "
            "Keys: name, description, width, depth, height, optional y_offset (0, or -1 to sink the first layer "
            "into the ground), and parts, each with label, shape (fill or hollow), block, x0 y0 z0 x1 y1 z1. "
            "Make it as big as the subject deserves.\n\n"
            + json.dumps(example, indent=1))


def plan_volume(plan):
    """Total cells the parts cover, to decide whether a voxel preview is affordable."""
    return sum((p["hi"][0] - p["lo"][0] + 1) * (p["hi"][1] - p["lo"][1] + 1) * (p["hi"][2] - p["lo"][2] + 1)
               for p in plan["parts"])
