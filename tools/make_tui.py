#!/usr/bin/env python3
"""Model-72's native MPC skin: skins/TUI.json + skins/Q-Links.json + the PNGs they use (the SDK method, docs/SDK-PORTING.md).

The four 1.0.1 pages are rebuilt from vst/layout.conf on the same art (vst/art, drawn by skin/make_skin.py), at the same places
and sizes as the released skin (y = layout y - 86, knob = 2r + 10 with its value under it, readout boxes painted in). What is new:
  * Q-Links in blocks of four, each block a printed-panel group with its own rectangle (QBLOCKS below; > 4 blocks = sub-tabs);
  * a fifth tab, PRESETS: + SAVE / - DELETE a user preset, and the naming keyboard over the page while kb_open = 1.
    python3 tools/make_tui.py        # -> skins/   (build-sdk.sh copies it to Plugin Skins/)"""
import json, os, re, shutil, sys
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "skins")
ART = os.path.join(ROOT, "vst", "art")
LOCK = [l.strip() for l in open(os.path.join(ROOT, "vst", "params.lock")) if l.strip()]
PARAMS = {p["key"]: p for p in json.load(open(os.path.join(ROOT, "vst", "params.json")))["params"]}
GEN = open(os.path.join(ROOT, "src", "params_gen.h")).read()
FAV_MAX = int(re.search(r"kFavNameMax = (\d+)", GEN).group(1))
FAV_SLOTS = int(re.search(r"kFavSlots = (\d+)", GEN).group(1))
Y_OFF = 86
sys.path.insert(0, os.path.join(ROOT, "skin"))
import make_skin as ms   # the panel's own drawing (wood, face, URW Gothic), for the PRESETS page

AMBER, INK, DIM, BOX, BOX_EDGE = (232, 134, 43), (232, 226, 208), (143, 136, 120), (14, 13, 12), (42, 40, 35)


def P(key):
    return "Parameter %d" % LOCK.index(key)


# ---- TUI.json building blocks (the SDK's schema, as Welle / Acid write it) --------------------------------------------
def bounds(b, focus="No", visible="Always", invalid="Show", ind=None):
    return {"version": 2, "acceptsHWFocus": focus, "showWhenDataModelInvalid": invalid, "whenVisible": visible,
            "boundsType": "Absolute", "bounds": b, "additionalInvalidatingHandles": ind or []}


def entry(name, typ, data, b, remap=None, focus="No", visible="Always", invalid="Show", ind=None):
    return {"version": 2, "componentData": {"version": 1, "name": name, "type": typ, "data": data},
            "handle remapping": {"version": 1, "map": [{"key": "Data", "value": remap}] if remap else []},
            "bounds": bounds(b, focus, visible, invalid, ind)}


def bg(colour="0"):
    side = {"version": 1, "colour": colour, "image": ""}
    return {"version": 1, "focussed": side, "unfocussed": dict(side)}


def component(children, actions=None, ignore=False, background=None):
    return {"version": 2, "actions": actions or [], "backgroundData": background or bg(), "ignoreMousePresses": ignore,
            "disableCoarseDataWheel": False, "componentsData": children}


def act(on, handler, extra="", handle="Data"):
    return {"version": 1, "onAction": on, "handler": handler, "handleName": handle, "additionalData": extra}


def text_style(h, colour, just="horizontallyCentred verticallyCentred", case="Original", style="SemiBold"):
    return {"version": 1, "font": {"version": 1, "name": "Titillium Web", "style": style, "height": float(h)}, "colour": colour,
            "justification": just, "case": case}


def value_label(b, h, colour="ff8f8878", remap=None, case="Upper Case", ind=None, just="horizontallyCentred verticallyCentred"):
    return entry("Value", "Label", {"version": 1, "textStyle": text_style(h, colour, just, case), "type": "Value", "handleName": "Data"},
                 b, remap, ind=ind)


NO_FOCUS = {"version": 1, "backgroundColour": "00000000", "outlineColour": "00000000", "backgroundInset": 2.0, "outlineThickness": 0.0}
KNOB_ACTIONS = [act("Mouse Down", "Q-Link"), act("Double Click", "Show Overlay", "knob overlay", ""), act("Enter Pressed", "Show Overlay", "knob overlay", "")]


def overlay_def():
    """The MPC's big knob overlay (double tap / Enter on a knob). The released skin lacked it; the SDK pages need it defined."""
    ov = {"version": 2, "actions": [act("Focus Lost", "Focus Lost", handle="Focus Lost")], "overlayType": "Knob With Header",
          "scaleType": "Linear", "polarityType": "Unipolar", "showMinusSign": True, "handleName": "Data"}
    return {"key": "knob overlay", "value": component([entry("overlay", "KnobOverlay", ov, "0 0 1280 800", focus="Yes")], ignore=True)}


DEFS = {}


def define(key, value):
    DEFS.setdefault(key, value)
    return key


def copy_art(name):
    shutil.copy(os.path.join(ART, os.path.basename(name)), os.path.join(OUT, os.path.basename(name)))
    return os.path.basename(name)


def save(im, name):
    im.save(os.path.join(OUT, name))
    return name


# ---- the 1.0.1 pages, from vst/layout.conf --------------------------------------------------------------------------
def parse_layout():
    tabs, order, cur = {}, [], None
    for line in open(os.path.join(ROOT, "vst", "layout.conf")):
        line = line.strip()
        m = re.match(r"\[tab (.+)\]", line)
        if m:
            cur = tabs.setdefault(m.group(1), {"items": [], "art": None})
            order.append(m.group(1))
            continue
        if not cur or not line or line.startswith("#") or line.startswith("qlinks"):
            continue
        kind, rest = line.split(None, 1)
        a = {k: v.strip('"') for k, v in re.findall(r'(\w+)=("[^"]*"|\S+)', rest)}
        if kind == "art":
            cur["art"] = a["file"]
        else:
            cur["items"].append((kind, a))
    return order, tabs


def widgets(spec, art):
    """The page's widgets at the released skin's places; pos[key] = the control's centre (for the Q-Link rectangles)."""
    kids, pos, d = [], {}, ImageDraw.Draw(art)
    for kind, a in spec["items"]:
        key = a["key"]
        g = lambda k: int(a[k])
        if kind == "knob":
            r, bw, vs = g("r"), g("bw"), g("vs")
            ks = 2 * r + 10
            strip = copy_art(a["strip"])
            name = define("knob_%s" % key, component([
                entry("Focus", "Focus", NO_FOCUS, "0 0 %d %d" % (bw, ks + 33), visible="WhenFocussed"),
                entry("Knob", "Knob", {"version": 5, "knobType": "FilmStrip", "filmStrip": strip, "numFrames": g("frames"), "invert": False,
                                       "dragOrientation": "Vertical", "handleName": "Data"}, "%d 0 %d %d" % ((bw - ks) // 2, ks, ks)),
                value_label("0 %d %d 30" % (ks - 3, bw), vs)], actions=KNOB_ACTIONS))
            x, y = g("cx") - bw // 2, g("cy") - Y_OFF - ks // 2
            kids.append(entry("", name, {"version": 1, "handleName": "Data"}, "%d %d %d %d" % (x, y, bw, ks + 33), P(key), "Yes", invalid="Hide"))
            pos[key] = (x, y, x + bw, y + ks + 33, True)
        elif kind == "toggle":
            w, h = g("w"), g("h")
            on, off = copy_art(a["img_on"]), copy_art(a["img"])
            name = define("toggle_%s" % key, component([
                entry("Focus", "Focus", NO_FOCUS, "0 0 %d %d" % (w, h), visible="WhenFocussed"),
                entry("Button", "Button", {"version": 2, "onImage": on, "offImage": off, "buttonId": 1, "numButtonsInGroup": 1, "handleName": "Data",
                                           "gestureBehaviour": "Instant"}, "0 0 %d %d" % (w, h))],
                actions=[act("Mouse Down", "Q-Link"), act("Enter Pressed", "Toggle Switch")]))
            kids.append(entry("", name, {"version": 1, "handleName": "Data"}, "%d %d %d %d" % (g("cx") - w // 2, g("cy") - Y_OFF - h // 2, w, h),
                              P(key), "Yes", invalid="Hide"))
            pos[key] = (g("cx") - w // 2, g("cy") - Y_OFF - h // 2, g("cx") + w // 2, g("cy") - Y_OFF + h // 2, False)
        elif kind == "picture":   # one image per value, shown while the value is that one
            files = a["files"].split(",")
            for i, f in enumerate(files):
                kids.append(entry(key, "Image", {"version": 2, "imageType": "Regular", "colour": "0", "image": copy_art(f)},
                                  "%d %d %d %d" % (g("x"), g("y") - Y_OFF, g("w"), g("h")), ind=["IndexedEnabling/%d/%d/%s" % (i, len(files), P(key))]))
        elif kind == "enum_h":    # transparent radio buttons over the picture
            n, sw, sh = len(a["options"].split(",")), g("sw"), g("sh")
            x0, y = g("cx") - (n * sw + (n - 1) * 2) // 2, g("cy") - Y_OFF - sh // 2
            clear = copy_art(a["img"])
            for i in range(n):
                name = define("seg_%s_%d" % (key, i), component([
                    entry("Button", "Button", {"version": 2, "onImage": clear, "offImage": clear, "buttonId": i, "numButtonsInGroup": n, "handleName": "Data",
                                               "gestureBehaviour": "Instant"}, "0 0 %d %d" % (sw, sh))], actions=[act("Mouse Down", "Q-Link")]))
                kids.append(entry("", name, {"version": 1, "handleName": "Data"}, "%d %d %d %d" % (x0 + i * (sw + 2), y, sw, sh), P(key),
                                  "Yes" if i == 0 else "No", invalid="Hide"))
            pos[key] = (x0, y, x0 + n * sw + (n - 1) * 2, y + sh, False)
        elif kind == "readout":   # a dark box painted into the page, the value in amber
            w, h = g("w"), g("h")
            x, y = g("cx") - w // 2, g("cy") - Y_OFF - h // 2
            d.rectangle((x, y, x + w - 1, y + h - 1), fill=BOX, outline=BOX_EDGE)
            kids.append(value_label("%d %d %d %d" % (x + 8, y, w - 16, h), g("tsize"), "ff" + a["tcolor"], P(key), "Original"))
        elif kind == "slider_v":
            w, h = g("w"), g("h")
            name = define("slider_%s" % key, component([
                entry("Focus", "Focus", NO_FOCUS, "0 0 %d %d" % (w + 46, h + 34), visible="WhenFocussed"),
                entry("Slider", "Knob", {"version": 5, "knobType": "FilmStrip", "filmStrip": copy_art(a["strip"]), "numFrames": g("frames"),
                                         "invert": False, "dragOrientation": "Vertical", "handleName": "Data"}, "23 0 %d %d" % (w, h)),
                value_label("0 %d %d 26" % (h + 2, w + 46), g("vs"))], actions=KNOB_ACTIONS))
            kids.append(entry("", name, {"version": 1, "handleName": "Data"}, "%d %d %d %d" % (g("cx") - (w + 46) // 2, g("cy") - Y_OFF - h // 2, w + 46, h + 34),
                              P(key), "Yes", invalid="Hide"))
            pos[key] = (g("cx") - (w + 46) // 2, g("cy") - Y_OFF - h // 2, g("cx") + (w + 46) // 2, g("cy") - Y_OFF + h // 2 + 34, True)
        elif kind == "meter":     # the STEREO field: one strip per voice dot, read only
            w, h = g("w"), g("h")
            name = define("meter_field", component([
                entry("Meter", "Knob", {"version": 5, "knobType": "FilmStrip", "filmStrip": copy_art(a["strip"]), "numFrames": g("frames"), "invert": False,
                                        "dragOrientation": "Vertical", "handleName": "Data"}, "0 0 %d %d" % (w, h))], ignore=True))
            kids.append(entry("", name, {"version": 1, "handleName": "Data"}, "%d %d %d %d" % (g("cx") - w // 2, g("cy") - Y_OFF - h // 2, w, h), P(key)))
        else:
            raise SystemExit("layout.conf: unknown widget " + kind)
    return kids, pos


# Q-Link blocks of four (a block = one row of the 16 Q-Links, top row first), per tab, per sub-tab. Each block is a group printed
# on the panel; its rectangle is drawn round its controls.
QBLOCKS = {
    "OSCILLATORS": [[
        ["tune", "glide", "mod_mix", "osc_mod"],                        # CONTROLLERS
        ["osc1_range", "osc2_range", "osc3_range", "osc3_control"],     # RANGE column (+ OSC 3 CONTROL beside OSC 3)
        ["osc2_frequency", "osc3_frequency"],                           # FREQUENCY column
        ["osc1_waveform", "osc2_waveform", "osc3_waveform"],            # WAVEFORM column
    ]],
    "MIXER FILTER": [[                                                  # sub-tab 1: the filter and the loudness contour
        ["cutoff", "emphasis", "contour_amount", "filter_mode"],        # cutoff first; FILTER MODE sits in the same row
        ["filter_attack", "filter_decay", "filter_sustain"],
        ["loudness_attack", "loudness_decay", "loudness_sustain"],
        (["filter_mod", "keyboard_control_1", "keyboard_control_2", "bass_comp"], {"y0": 216}),   # the switch column under it
    ], [                                                                # sub-tab 2: the mixer, column by column
        ["osc1_volume", "osc2_volume", "osc3_volume"],                  # volumes
        ["osc1_on", "ext_on", "osc2_on", "noise_on"],                   # ON switches
        ["patch", "noise_volume", "noise_type"],                        # PATCH and NOISE (EXT VOLUME: touch only, user 2026-11-18)
        ["osc3_on"],                                                    # OSC 3 ON, at the foot of the switches
    ]],
    "OUTPUT": [[
        ["drive", "auto_gain", "volume", "a440"],                       # OUTPUT
        ["mode", "voices", "entropy", "quality"],                       # VOICES
        ["note_priority", "retrigger", "glide_on", "decay_on"],         # keyboard
        ["midi_bend_range", "mod_wheel"],                               # CONTROLLER
    ]],
    "STEREO": [[
        ["spread", "inner", "double"],
        ["played_as", "placement"],
    ]],
}


NO_QLINK = {"ext_volume"}   # controls left off the Q-Links on purpose


def qrect(keys, pos, edge=None):
    """The block's rectangle: round its widgets' bounds (a knob's includes its value), with room above for the printed captions.
    `edge` moves an edge (x0 / y0 / x1 / y1) where a block would overlap its neighbour."""
    bs = [pos[k] for k in keys]
    x0, y0 = min(b[0] for b in bs) - 8, min(b[1] for b in bs) - (20 if any(b[4] for b in bs) else 8)
    x1, y1 = max(b[2] for b in bs) + 8, max(b[3] for b in bs)
    e = edge or {}
    x0, y0, x1, y1 = e.get("x0", x0), e.get("y0", y0), e.get("x1", x1), e.get("y1", y1)
    x0, y0, x1, y1 = max(x0, 2), max(y0, 30), min(x1, 1278), min(y1, 598)
    return "%d %d %d %d" % (x0, y0, x1 - x0, y1 - y0)


class Page:
    def __init__(self, name, fn, sub, kids, bgfile, blocks=(), pos=None):
        self.name, self.fn, self.sub, self.kids, self.bgfile = name, fn, sub, kids, bgfile
        blocks = [b if isinstance(b, tuple) else (b, None) for b in blocks]
        self.blocks = [list(b) for b, _ in blocks]
        self.rects = [qrect(b, pos, e) for b, e in blocks]

    def tab(self):
        kids = [entry("bg", "Image", {"version": 2, "imageType": "Regular", "colour": "0", "image": self.bgfile}, "0 0 1280 628")] + self.kids
        return {"version": 1, "tabName": self.name, "fnKeyIndex": self.fn, "fnKeySubIndex": self.sub,
                "componentDefinition": component(kids, background=bg("ff0e0d0c")), "qlinkBoundsData": self.rects}


# ---- PRESETS: save / delete a user preset, the naming keyboard -----------------------------------------------------------
def key_image(w, h, cap, lit, size=22):
    """A key in the panel's style: an amber push tab when lit, a dark one with ivory legend otherwise (URW Gothic, as the panel)."""
    S = ms.SS
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w * S - 1, h * S - 1), 7 * S, fill=AMBER + (255,) if lit else (34, 32, 29, 255), outline=(90, 84, 72, 255), width=S)
    d.text((w * S // 2, h * S // 2), cap, font=ms.font(size, True), fill=(20, 16, 10) if lit else INK, anchor="mm")
    return im.resize((w, h), Image.LANCZOS)


def presets_page(fn):
    t = ms.Tab("PRESETS", [], silver=("l", "r"))
    t.title(640, "PRESETS")
    t.text(640, 96, "USER PRESETS", 22, True, ms.TITLE)
    lines = ["Pick a preset in the PRESET menu at the top of the screen: the 19 factory presets,",
             "then your own, U01 to U%02d." % FAV_SLOTS,
             "SAVE names the sound as it is now and adds it to the list.",
             "DELETE removes the user preset that is picked.",
             "Your presets are kept in the plugin's folder and shared by every project."]
    for i, s in enumerate(lines):
        t.text(640, 300 + i * 30, s, 17, False, ms.DIM)
    art = ms.to_rgb_final(t.hi, 1280, 628)
    kids = []

    def button(key, x, y, w, h, cap, ind=None):
        on, off = save(key_image(w, h, cap, True), "%s_on.png" % key), save(key_image(w, h, cap, False), "%s_off.png" % key)
        kids.append(entry(key, "Button", {"version": 2, "onImage": on, "offImage": off, "buttonId": 1, "numButtonsInGroup": 1, "handleName": "Data",
                                          "gestureBehaviour": "Instant"}, "%d %d %d %d" % (x, y, w, h), remap=P(key), ind=ind))
    button("fav_add", 640 - 20 - 300, 150, 300, 84, "+ SAVE PRESET")
    button("fav_del", 640 + 20, 150, 300, 84, "- DELETE PRESET")
    keyboard(kids, button)
    return Page("PRESETS", fn, 0, kids, save(art, "bg_presets.png"))


KB_ROWS = [("1234567890", ["kb_bksp"]), ("QWERTYUIOP", []), ("ASDFGHJKL-", []), ("ZXCVBNM", ["kb_space"])]


def keyboard(kids, button):
    """Profit-5's naming keyboard, in the panel's look: a full page shown while kb_open = 1 (+ SAVE PRESET opens it)."""
    ind = ["IndexedEnabling/1/2/%s" % P("kb_open")]
    t = ms.Tab("KEYBOARD", [], silver=("l", "r"))
    t.text(140, 70, "PRESET NAME", 18, True, ms.TITLE)
    art = ms.to_rgb_final(t.hi, 1280, 628)
    d = ImageDraw.Draw(art)
    d.rectangle((250, 44, 1210, 96), fill=BOX, outline=BOX_EDGE)
    d.text((1196, 70), "MAX %d CHARACTERS" % FAV_MAX, font=ms.ImageFont.truetype(os.path.join(ms.A, "URWGothic-Book.otf"), 15), fill=DIM, anchor="rm")
    kids.append(entry("kb panel", "Image", {"version": 2, "imageType": "Regular", "colour": "0", "image": save(art, "kb_panel.png")}, "0 0 1280 628", ind=ind))
    kids.append(entry("kb name", "Label", {"version": 1, "textStyle": text_style(32, "ffff9a3c", "left verticallyCentred"), "type": "Value",
                                            "handleName": "Data"}, "266 44 760 52", remap=P("fav_name"), ind=ind))
    kw, kh, gap, x0, y0 = 98, 80, 8, 70, 116
    for r, (chars, extra) in enumerate(KB_ROWS):
        y, x = y0 + r * (kh + gap), x0 + r * 30
        for c in chars:
            button("kb_" + ("dash" if c == "-" else c.lower()), x, y, kw, kh, c, ind)
            x += kw + gap
        for k in extra:
            button(k, x, y, 1210 - x, kh, {"kb_bksp": "DEL", "kb_space": "SPACE"}[k], ind)
    y = y0 + 4 * (kh + gap)
    button("kb_shift", x0, y, 200, kh, "SHIFT", ind)
    button("kb_cancel", 640 - 130, y, 260, kh, "CANCEL", ind)
    button("kb_save", 1210 - 260, y, 260, kh, "SAVE", ind)


# ---- Q-Links.json ----------------------------------------------------------------------------------------------------
def qlinks_for(pages):
    maps = []
    for p in pages:
        q = {"Q-Link %d" % n: -1 for n in range(1, 17)}
        for gi, keys in enumerate(p.blocks[:4]):
            first = 13 - 4 * gi                        # block 1 = the top row (Q-Links 13-16), as Welle / Acid
            for i, key in enumerate(keys):
                q["Q-Link %d" % (first + i)] = LOCK.index(key)
        maps.append({"Tab": p.fn + 1, "SubTab": p.sub + 1, "Bank Direction": "RowTopDown", "Q-Links": q})
    prog = dict(maps[0]["Q-Links"])
    return {"version": 4, "info": {"version": 1, "type": "CompleteDescription"}, "Screen Mode Q-Links": {"version": 4, "map": maps},
            "Program Mode Q-Links": prog}


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    order, tabs = parse_layout()
    pages, used = [], set()
    for fn, name in enumerate(order):
        spec = tabs[name]
        art = Image.open(os.path.join(ART, os.path.basename(spec["art"]))).convert("RGB")
        kids, pos = widgets(spec, art)
        bgfile = save(art, "bg_%s.png" % name.replace(" ", "_").lower())
        for sub, blocks in enumerate(QBLOCKS[name]):
            for b in blocks:
                b = b[0] if isinstance(b, tuple) else b
                assert len(b) <= 4 and all(k in pos for k in b), (name, b)
                used.update(b)
            pages.append(Page(name, fn, sub, kids, bgfile, blocks, pos))
    controls = {a["key"] for s in tabs.values() for kind, a in s["items"] if kind in ("knob", "toggle", "enum_h", "slider_v")}
    missing = controls - used - NO_QLINK
    if missing:
        raise SystemExit("controls without a Q-Link: %s" % sorted(missing))
    pages.append(presets_page(len(order)))
    os.makedirs(os.path.join(OUT, "browser_images"))
    shutil.copy(os.path.join(ART, "tile.png"), os.path.join(OUT, "browser_images", "soundsmode.png"))
    tui = {"pageData": {"version": 1,
                        "componentDefinitions": {"version": 2, "importFiles": [],
                                                 "localComponentDefinitions": [overlay_def()] + [{"key": k, "value": v} for k, v in DEFS.items()]},
                        "replacementStrings": [], "info": {"version": 1, "type": "CompleteDescription"}, "tabs": [p.tab() for p in pages]}}
    json.dump(tui, open(os.path.join(OUT, "TUI.json"), "w"), indent=1)
    json.dump(qlinks_for(pages), open(os.path.join(OUT, "Q-Links.json"), "w"), indent=1)
    print("wrote skins/: %d tabs (%s), %d files" % (len(pages), ", ".join("%s%s" % (p.name, " %d" % (p.sub + 1) if p.sub or p.name == "MIXER FILTER" else "")
                                                                         for p in pages), len(os.listdir(OUT))))


if __name__ == "__main__":
    main()
