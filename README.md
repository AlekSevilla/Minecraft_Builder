# Minecraft Image Builder

Build things in a Bedrock world from a web page.

- **Describe it**: type what you want, see it in a 3D viewer (rotate it), then keep prompting to change it ("add a
  second floor", "make the roof red"). Changed blocks are highlighted, Undo steps back, then build it. Needs an API key.
- **Quick builds**: shopping mall (massive, 3 floors, ~100 shops, built for hide and seek), airport (big, furnished, with planes), castle, lighthouse, barn, cottage, tower, pyramid, glass sphere, wall.
  Pick one, rotate the 3D preview, build.
- **Import a build (no API)**: load a `.json` build file, or paste JSON or `fill`/`setblock` commands. The page can
  copy a prompt for any AI chat (ChatGPT, Claude.ai, ...) that produces a JSON build you paste back in.
  Any build can be downloaded as JSON and shared.
- **Pixel art**: upload an image, build it as a wall or floor mural.
- **3D build from photos** (needs an Anthropic API key): Claude designs a build from 1-4 photos.

## Setup
1. `pip install -r requirements.txt`
2. Optional, for photos: put `ANTHROPIC_API_KEY=...` in a `.env` file next to `builder.py`
3. `py builder.py`
4. In Minecraft (cheats on): `/connect localhost:19131`
5. Open http://localhost:8080

Stand still in an open, flat area facing the direction you selected; builds are placed relative to you.
If you see "block not found" errors, switch Block names to Modern at the top of the page.
Chat commands still work too: `build airport`, `build castle`, ...

## Build file format
```json
{"name": "Hut", "description": "", "width": 7, "depth": 7, "height": 7, "y_offset": 0,
 "parts": [{"label": "walls", "shape": "hollow", "block": "oak_planks", "x0": 0, "y0": 0, "z0": 0, "x1": 6, "y1": 4, "z1": 6}]}
```
x runs left to right as seen from the front, y up, z away from you. Parts apply in order; `air` carves.
`shape` is `fill` or `hollow`. Add your own builds to `library.py`.
