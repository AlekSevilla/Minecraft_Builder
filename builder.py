"""
Minecraft Bedrock image builder.

  1. pip install -r requirements.txt
  2. python builder.py
  3. In Minecraft (cheats ON) run:  /connect localhost:19131
  4. Open http://localhost:8080, upload an image, and hit Build.

Everything is placed relative to where you stand, so stand still in an open area
while it builds. You can also still type  build house|tower|pyramid|sphere|wall  in chat.
"""
import asyncio
import json
import os
import uuid
from pathlib import Path

import websockets
from aiohttp import web

import ai3d
import imagebuild
import library


def _load_env():
    """Read KEY=value lines from .env next to this file (real environment variables win)."""
    path = Path(__file__).parent / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, val = line.partition("=")
            if sep and not key.strip().startswith("#"):
                os.environ.setdefault(key.strip(), val.strip())


_load_env()

MC_PORT = int(os.environ.get("MC_PORT", 19131))
WEB_PORT = int(os.environ.get("WEB_PORT", 8080))
STATIC = Path(__file__).parent / "static"
COMMAND_DELAY = 0.05  # stay under Minecraft's command rate limit


class State:
    def __init__(self):
        self.ws = None
        self.job = None            # dict while/after a build runs
        self.previews = {}         # id -> (grid, pal)
        self.designs = {}          # id -> 3D plan
        self.ai_calls = 0          # paid API requests made this run


STATE = State()


# ---------- Minecraft websocket plumbing ----------

def _msg(purpose, body):
    return json.dumps({
        "header": {
            "version": 1,
            "requestId": str(uuid.uuid4()),
            "messagePurpose": purpose,
            "messageType": "commandRequest",
        },
        "body": body,
    })


async def send_command(ws, command):
    await ws.send(_msg("commandRequest", {
        "origin": {"type": "player"},
        "commandLine": command,
        "version": 1,
    }))


async def say(ws, text):
    await send_command(ws, f'tellraw @a {{"rawtext":[{{"text":"§a[Builder] {text}"}}]}}')


async def run_commands(label, cmds):
    ws = STATE.ws
    job = STATE.job = {"label": label, "total": len(cmds), "sent": 0, "errors": 0,
                       "last_error": None, "running": True, "cancel": False}
    try:
        await say(ws, f"Building {label} ({len(cmds)} commands)...")
        for c in cmds:
            if job["cancel"]:
                break
            await send_command(ws, c)
            job["sent"] += 1
            await asyncio.sleep(COMMAND_DELAY)
        await say(ws, f"{'Cancelled' if job['cancel'] else 'Done'}: {label}")
    except websockets.ConnectionClosed:
        job["last_error"] = "Minecraft disconnected mid-build"
    finally:
        job["running"] = False


def start_job(label, cmds):
    if STATE.ws is None:
        raise web.HTTPConflict(text="Minecraft is not connected")
    if STATE.job and STATE.job["running"]:
        raise web.HTTPConflict(text="A build is already running")
    asyncio.create_task(run_commands(label, cmds))


async def mc_handler(ws):
    print("Minecraft connected!")
    STATE.ws = ws
    try:
        await ws.send(_msg("subscribe", {"eventName": "PlayerMessage"}))
        await say(ws, "Connected. Open http://localhost:%d to build from an image." % WEB_PORT)
        async for raw in ws:
            data = json.loads(raw)
            header, body = data.get("header", {}), data.get("body", {})
            purpose = header.get("messagePurpose")
            if purpose == "commandResponse":
                job = STATE.job
                if job and job["running"] and body.get("statusCode", 0) != 0:
                    job["errors"] += 1
                    job["last_error"] = body.get("statusMessage")
            elif header.get("eventName") == "PlayerMessage" and body.get("type") == "chat":
                text = body.get("message", "").strip().lower()
                if text.startswith("build ") and not (STATE.job and STATE.job["running"]):
                    name = text.split(None, 1)[1]
                    if name in library.LIBRARY:
                        plan = library.get(name)
                        asyncio.create_task(run_commands(name, ai3d.to_commands(plan, "south")))
                    else:
                        await say(ws, f"Unknown build '{name}'. Options: {', '.join(library.LIBRARY)}")
    finally:
        print("Minecraft disconnected")
        if STATE.ws is ws:
            STATE.ws = None


# ---------- web app ----------

async def index(request):
    return web.FileResponse(STATIC / "index.html")


async def api_status(request):
    job = STATE.job
    return web.json_response({
        "connected": STATE.ws is not None,
        "job": job and {k: job[k] for k in ("label", "total", "sent", "errors", "last_error", "running")},
        "max_size": imagebuild.MAX_SIZE,
        "ai": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "ai_calls": STATE.ai_calls,
    })


async def api_preview(request):
    fields, data = {}, None
    async for part in await request.multipart():
        if part.name == "image":
            data = await part.read(decode=False)
        else:
            fields[part.name] = await part.text()
    if not data:
        raise web.HTTPBadRequest(text="No image uploaded")
    families = [f for f in fields.get("families", "concrete").split(",") if f in imagebuild.FAMILIES]
    if not families:
        raise web.HTTPBadRequest(text="Pick at least one block type")
    try:
        grid, pal = await asyncio.to_thread(
            imagebuild.convert, data, int(fields.get("width", 48)),
            fields.get("dither") == "1", families)
    except Exception as e:
        raise web.HTTPBadRequest(text=f"Could not read that image: {e}")
    pid = uuid.uuid4().hex
    STATE.previews[pid] = (grid, pal)
    while len(STATE.previews) > 10:
        STATE.previews.pop(next(iter(STATE.previews)))
    return web.json_response({
        "id": pid,
        "width": len(grid[0]),
        "height": len(grid),
        "image": imagebuild.preview_png(grid, pal),
        "blocks": imagebuild.counts(grid, pal),
        "commands": len(imagebuild.merge(grid)),
    })


async def api_build(request):
    body = await request.json()
    entry = STATE.previews.get(body.get("id"))
    if not entry:
        raise web.HTTPNotFound(text="Preview expired, upload the image again")
    grid, pal = entry
    mode = body.get("mode", "wall")
    facing = body.get("facing", "south")
    syntax = body.get("syntax", "legacy")
    if mode not in ("wall", "floor") or facing not in imagebuild.FACING or syntax not in ("legacy", "modern"):
        raise web.HTTPBadRequest(text="Bad build options")
    cmds = imagebuild.to_commands(grid, pal, mode, facing, syntax)
    start_job("image", cmds)
    return web.json_response({"commands": len(cmds)})


async def register_design(plan, prev=None):
    """Store a plan, build its 3D preview, and return the JSON the page needs.
    If prev (the plan this one was edited from) is given, voxels that changed are flagged."""
    def prepare():
        if ai3d.plan_volume(plan) > 60_000_000:      # too big to simulate for a preview; it still builds
            return [], [], len(ai3d.to_commands(plan, "south")), 0
        grid = ai3d.voxelize(plan)
        changed = set()
        if prev is not None:
            before = ai3d.voxelize(prev)
            changed = {k for k, v in grid.items() if before.get(k) != v}
        voxels, palette = ai3d.preview_data(grid, changed)
        return voxels, palette, len(ai3d.to_commands(plan, "south")), len(changed)

    voxels, palette, ncmds, nchanged = await asyncio.to_thread(prepare)
    did = uuid.uuid4().hex
    STATE.designs[did] = plan
    while len(STATE.designs) > 40:
        STATE.designs.pop(next(iter(STATE.designs)))
    return web.json_response({
        "id": did, "name": plan["name"], "description": plan["description"],
        "size": [plan["width"], plan["height"], plan["depth"]],
        "blocks": sum(p["count"] for p in palette),
        "commands": ncmds, "voxels": voxels, "palette": palette, "changed": nchanged,
    })


def require_credit_ok(request):
    """Paid endpoints only run when the page's AI tab was explicitly unlocked."""
    if request.headers.get("X-Credits-OK") != "1":
        raise web.HTTPForbidden(text="AI features are locked. Unlock them in an AI tab first.")
    STATE.ai_calls += 1


async def api_design(request):
    require_credit_ok(request)
    fields, images = {}, []
    async for part in await request.multipart():
        if part.name == "image":
            data = await part.read(decode=False)
            if data:
                images.append(data)
        else:
            fields[part.name] = await part.text()
    if not images:
        raise web.HTTPBadRequest(text="No image uploaded")
    if len(images) > 4:
        raise web.HTTPBadRequest(text="Upload at most 4 images")
    try:
        plan = await asyncio.to_thread(ai3d.analyze, images, fields.get("hint", ""),
                                       int(fields.get("size", 32)))
    except RuntimeError as e:
        raise web.HTTPBadGateway(text=str(e))
    except Exception as e:
        raise web.HTTPBadRequest(text=f"Could not read those images: {e}")
    return await register_design(plan)


async def api_text_design(request):
    """Describe a build in text (new), or change the build with the given id."""
    require_credit_ok(request)
    body = await request.json()
    prompt = str(body.get("prompt", "")).strip()
    if not prompt:
        raise web.HTTPBadRequest(text="Type what you want first")
    if len(prompt) > 4000:
        raise web.HTTPBadRequest(text="That description is too long (4000 characters max)")
    prev = None
    if body.get("id"):
        prev = STATE.designs.get(body["id"])
        if not prev or "raw_commands" in prev:
            raise web.HTTPNotFound(text="That build can't be edited. Start a new one.")
    try:
        if prev is None:
            plan = await asyncio.to_thread(ai3d.generate, prompt, int(body.get("size", 32)))
        else:
            plan = await asyncio.to_thread(ai3d.refine, prev, prompt)
    except RuntimeError as e:
        raise web.HTTPBadGateway(text=str(e))
    return await register_design(plan, prev)


async def api_library(request):
    out = []
    for key, fn in library.LIBRARY.items():
        plan = fn()
        out.append({"id": key, "name": plan["name"], "description": plan["description"],
                    "size": [plan["width"], plan["height"], plan["depth"]]})
    return web.json_response(out)


async def api_library_load(request):
    key = (await request.json()).get("id")
    if key not in library.LIBRARY:
        raise web.HTTPNotFound(text="Unknown build")
    return await register_design(library.get(key))


async def api_import(request):
    text = ""
    async for part in await request.multipart():
        if part.name in ("file", "text"):
            raw = await part.read(decode=False)
            try:
                text += raw.decode("utf-8-sig") + "\n"
            except UnicodeDecodeError:
                raise web.HTTPBadRequest(text="That file isn't text. Import a .json or .mcfunction/.txt file.")
    try:
        kind, value = ai3d.parse_import(text)
    except RuntimeError as e:
        raise web.HTTPBadRequest(text=str(e))
    if kind == "plan":
        return await register_design(value)
    did = uuid.uuid4().hex
    STATE.designs[did] = {"name": "Imported commands", "raw_commands": value}
    return web.json_response({
        "id": did, "name": "Imported commands", "raw": True, "commands": len(value),
        "description": f"{len(value)} commands imported. Commands are relative to where you stand, "
                       "so there is no preview and the facing setting is ignored.",
    })


async def api_export(request):
    plan = STATE.designs.get(request.query.get("id"))
    if not plan or "raw_commands" in plan:
        raise web.HTTPNotFound(text="Nothing to export")
    name = "".join(c if c.isalnum() else "_" for c in plan["name"]).strip("_").lower() or "build"
    return web.Response(text=json.dumps(ai3d.plan_to_json(plan), indent=1), content_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{name}.json"'})


async def api_format(request):
    return web.json_response({"prompt": ai3d.import_prompt()})


async def api_build_design(request):
    body = await request.json()
    plan = STATE.designs.get(body.get("id"))
    if not plan:
        raise web.HTTPNotFound(text="Design expired, load it again")
    facing = body.get("facing", "south")
    syntax = body.get("syntax", "legacy")
    if facing not in imagebuild.FACING or syntax not in ("legacy", "modern"):
        raise web.HTTPBadRequest(text="Bad build options")
    if "raw_commands" in plan:
        cmds = plan["raw_commands"]
    else:
        # "center" puts the player in the middle of the build, keeping huge builds inside loaded chunks
        distance = -(plan["depth"] // 2) if body.get("center") else 3
        cmds = ai3d.to_commands(plan, facing, distance=distance, syntax=syntax)
    start_job(plan["name"], cmds)
    return web.json_response({"commands": len(cmds)})


async def api_cancel(request):
    if STATE.job:
        STATE.job["cancel"] = True
    return web.json_response({})


async def main():
    app = web.Application(client_max_size=25 * 1024 * 1024)
    app.add_routes([
        web.get("/", index),
        web.get("/api/status", api_status),
        web.post("/api/preview", api_preview),
        web.post("/api/build", api_build),
        web.post("/api/design", api_design),
        web.post("/api/build_design", api_build_design),
        web.post("/api/text_design", api_text_design),
        web.get("/api/library", api_library),
        web.post("/api/library/load", api_library_load),
        web.post("/api/import", api_import),
        web.get("/api/export", api_export),
        web.get("/api/format", api_format),
        web.post("/api/cancel", api_cancel),
    ])
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", WEB_PORT).start()
    print(f"Web UI:    http://localhost:{WEB_PORT}")
    print(f"Minecraft: /connect localhost:{MC_PORT}")
    async with websockets.serve(mc_handler, "0.0.0.0", MC_PORT):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
