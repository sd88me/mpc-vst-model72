#!/usr/bin/env python3
"""Offline preview of skins/TUI.json: each page's background, its widgets at their default values (film-strip frames, button
images, value text as boxes) and the Q-Link rectangles in red. -> docs/skin-preview/<n>_<tab>.png. Pass kb=1 to show the keyboard."""
import json, os, re, sys
from PIL import Image, ImageDraw
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, "skins")
OUT = os.path.join(ROOT, "docs", "skin-preview")
os.makedirs(OUT, exist_ok=True)
LOCK = [l.strip() for l in open(os.path.join(ROOT, "vst", "params.lock")) if l.strip()]
SPEC = {}
for m in re.finditer(r'\{"(\w+)", "[^"]*", ([-\d.]+)f, ([-\d.]+)f, ([-\d.]+)f, (\d+)', open(os.path.join(ROOT, "src", "params_gen.h")).read()):
    SPEC[m.group(1)] = tuple(float(m.group(i)) for i in (2, 3, 4))
kb = "kb=1" in sys.argv
t = json.load(open(os.path.join(S, "TUI.json")))["pageData"]
D = {d["key"]: d["value"] for d in t["componentDefinitions"]["localComponentDefinitions"]}


def norm(handle):
    if not handle or not handle.startswith("Parameter "):
        return 0.0
    k = LOCK[int(handle.split()[1])]
    if k == "kb_open":
        return 1.0 if kb else 0.0
    lo, hi, d = SPEC[k]
    return (d - lo) / (hi - lo) if hi > lo else 0.0


def visible(c, handle_val):
    for h in c["bounds"].get("additionalInvalidatingHandles", []):
        m = re.match(r"IndexedEnabling/(\d+)/(\d+)/(Parameter \d+)", h)
        if m:
            i, n = int(m.group(1)), int(m.group(2))
            if round(norm(m.group(3)) * (n - 1)) != i:
                return False
    return True


def draw(img, comps, ox, oy, handle):
    d = ImageDraw.Draw(img)
    for c in comps:
        if not visible(c, None):
            continue
        cd = c["componentData"]
        x, y, w, h = map(int, c["bounds"]["bounds"].split())
        m = c["handle remapping"]["map"]
        hnd = m[0]["value"] if m else handle
        typ, data = cd["type"], cd["data"]
        if typ in D:
            draw(img, D[typ]["componentsData"], ox + x, oy + y, hnd)
        elif typ == "Image":
            if data.get("image"):
                im = Image.open(os.path.join(S, data["image"])).convert("RGBA").resize((w, h))
                img.alpha_composite(im, (ox + x, oy + y))
        elif typ == "Knob":
            st = Image.open(os.path.join(S, data["filmStrip"])).convert("RGBA")
            n = data["numFrames"]
            fh = st.height // n
            f = round(norm(hnd) * (n - 1))
            img.alpha_composite(st.crop((0, f * fh, st.width, (f + 1) * fh)).resize((w, h)), (ox + x, oy + y))
        elif typ == "Button":
            n = data["numButtonsInGroup"]
            v = round(norm(hnd) * (max(n, 2) - 1))
            im = Image.open(os.path.join(S, data["onImage" if v == data["buttonId"] else "offImage"])).convert("RGBA").resize((w, h))
            img.alpha_composite(im, (ox + x, oy + y))
        elif typ == "Label":
            if data["textStyle"]["font"]["height"] > 0:
                d.rectangle((ox + x, oy + y, ox + x + w - 1, oy + y + h - 1), outline=(80, 160, 255, 160))


for i, tab in enumerate(t["tabs"]):
    img = Image.new("RGBA", (1280, 628), (14, 13, 12, 255))
    draw(img, tab["componentDefinition"]["componentsData"], 0, 0, None)
    d = ImageDraw.Draw(img)
    for r in tab["qlinkBoundsData"]:
        x, y, w, h = map(int, r.split())
        d.rectangle((x, y, x + w - 1, y + h - 1), outline=(255, 40, 40, 255), width=3)
    name = "%d_%s%s.png" % (i + 1, tab["tabName"].replace(" ", "_").lower(), "_%d" % (tab["fnKeySubIndex"] + 1) if tab["fnKeySubIndex"] or tab["tabName"] == "MIXER FILTER" else "")
    if kb and tab["tabName"] != "PRESETS":
        continue
    img.convert("RGB").save(os.path.join(OUT, ("kb_" if kb else "") + name))
    print(name)
