#!/usr/bin/env python3
"""Draws Model-72's MPC skin from scratch for the MPC's 1280x628 plugin area, with CA-72's own pictures
(skin/assets/: its knobs, rockers, toggles, jacks, walnut and panel face) and its typeface (URW Gothic).

    python3 skin/make_skin.py vst/          # -> vst/art/*.png, vst/layout.conf, vst/preview/*.png

Each tab is drawn once at 2x (the silkscreen: titles, scales, numerals, rules) and each control is then a filmstrip or an
on/off pair cut from that tab with the control in each position, so a frame sits exactly over its place in the background.
Needs Pillow."""
import copy
import json
import math
import os
import random
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(HERE, "assets")
SS = 2
W, H = 1280, 628
WOOD = 28
Y_OFF = 86          # layout y = plugin y + 86 (Force Shadow's)
INK = (236, 230, 212)
DIM = (176, 170, 154)
TITLE = (212, 206, 188)
FRAMES = 64


def asset(n, mode="RGBA"):
    return Image.open(os.path.join(A, n + ".png")).convert(mode)


FONTS = {}


def font(size, bold=False):
    k = (size, bold)
    if k not in FONTS:
        FONTS[k] = ImageFont.truetype(os.path.join(A, "URWGothic-%s.otf" % ("Demi" if bold else "Book")), int(round(size * SS)))
    return FONTS[k]


def even(x):
    n = int(math.ceil(x))
    return n + (n & 1)


def polar(cx, cy, r, deg):
    a = math.radians(deg)
    return cx + r * math.sin(a), cy - r * math.cos(a)


# ---------------------------------------------------------------- materials

_cache = {}


def face_panel(w, h):
    """The panel's black textured face, tiled (mirrored, so no seams) over w x h (hi-res pixels)."""
    if "face" not in _cache:
        f = asset("face", "L")
        ts = 640
        f = f.resize((ts, ts), Image.LANCZOS)
        r, g, b = [f.point(lambda v, m=m: min(255, int(v * m * 1.22))) for m in (1.04, 1.0, 0.93)]
        _cache["face"] = Image.merge("RGB", (r, g, b))
    f = _cache["face"]
    ts = f.width
    out = Image.new("RGB", (w, h))
    for iy in range(0, h // ts + 1):
        for ix in range(0, w // ts + 1):
            t = f
            if ix & 1:
                t = ImageOps.mirror(t)
            if iy & 1:
                t = ImageOps.flip(t)
            out.paste(t, (ix * ts, iy * ts))
    return out


def walnut_strip(w, h, y0):
    if "walnut" not in _cache:
        wn = asset("walnut", "RGB")
        _cache["walnut"] = wn.resize((W * SS, int(wn.height * W * SS / wn.width)), Image.LANCZOS)
    wn = _cache["walnut"]
    return wn.crop((0, y0, w, y0 + h))


def brushed(w, h):
    """Brushed aluminium, the grain running up and down."""
    noise = Image.effect_noise((w, 6), 36).resize((w, h), Image.BILINEAR)
    img = ImageChops.add(Image.new("L", (w, h), 176), noise, 1.0, -128)
    shade = Image.linear_gradient("L").rotate(90).resize((w, h))      # a little lighter at the left
    img = ImageChops.add(img, shade.point(lambda v: 22 - v // 6), 1.0, 0)
    return ImageOps.colorize(img, (40, 42, 44), (236, 237, 239)).convert("RGB")


# ---------------------------------------------------------------- sprites

def sprite(name, w):
    im = asset(name)
    return im.resize((w, max(1, round(im.height * w / im.width))), Image.LANCZOS)


def shadow(layer_size, box, blur=4, alpha=150, off=(0, 3), ellipse=True):
    sh = Image.new("RGBA", layer_size, (0, 0, 0, 0))
    d = ImageDraw.Draw(sh)
    x0, y0, x1, y1 = box
    (d.ellipse if ellipse else d.rounded_rectangle)((x0 + off[0] * SS, y0 + off[1] * SS, x1 + off[0] * SS, y1 + off[1] * SS), fill=(0, 0, 0, alpha))
    return sh.filter(ImageFilter.GaussianBlur(blur * SS))


def tint_ivory(im):
    a = im.getchannel("A")
    g = ImageOps.grayscale(im.convert("RGB"))
    g = ImageOps.autocontrast(g, cutoff=2)
    c = ImageOps.colorize(g, (70, 64, 52), (250, 244, 226), mid=(206, 198, 178))
    c.putalpha(a)
    return c


def jewel(lit):
    im = asset("jewel")
    if lit:
        return im
    a = im.getchannel("A")
    rgb = im.convert("RGB").point(lambda v: int(v * 0.42))
    rgb = Image.merge("RGB", (rgb.getchannel(0).point(lambda v: int(v * 0.8)), rgb.getchannel(1), rgb.getchannel(2)))
    rgb.putalpha(a)
    return rgb


# ---------------------------------------------------------------- the tab canvas

class Tab:
    def __init__(self, name, qlinks, silver=()):
        self.name = name
        self.qlinks = qlinks
        self.silver = silver            # "l", "r"
        self.hi = face_panel(W * SS, H * SS).convert("RGBA")
        self.controls = []              # things that need frames
        self.lines = []                 # layout lines (no frames)
        self.extra_layers = []
        self._wood_and_ends()

    # -- frame
    def _wood_and_ends(self):
        w, h = W * SS, H * SS
        top = walnut_strip(w, WOOD * SS, 250)
        bot = walnut_strip(w, WOOD * SS, 700)
        # the panel's shadow under the wood
        for y in range(6 * SS):
            a = int(120 * (1 - y / (6.0 * SS)) ** 2)
            for (yy, flip) in ((WOOD * SS + y, 0), (h - WOOD * SS - 1 - y, 1)):
                self.hi.alpha_composite(Image.new("RGBA", (w, 1), (0, 0, 0, a)), (0, yy))
        self.hi.paste(top, (0, 0))
        self.hi.paste(bot, (0, h - WOOD * SS))
        d = ImageDraw.Draw(self.hi)
        d.line([(0, WOOD * SS), (w, WOOD * SS)], fill=(14, 10, 8, 255), width=2 * SS)
        d.line([(0, h - WOOD * SS), (w, h - WOOD * SS)], fill=(14, 10, 8, 255), width=2 * SS)
        d.line([(0, WOOD * SS - SS), (w, WOOD * SS - SS)], fill=(96, 70, 52, 255), width=SS)
        # screws in the top wood
        scr = asset("screw").resize((9 * SS, 9 * SS), Image.LANCZOS)
        for x in (60, 640, 1220):
            self.hi.alpha_composite(scr, (x * SS, (WOOD // 2 - 4) * SS))
        # aluminium ends
        ew = 14 * SS
        for side in self.silver:
            strip = brushed(ew, h - 2 * WOOD * SS)
            x = 0 if side == "l" else w - ew
            self.hi.paste(strip, (x, WOOD * SS))
            d = ImageDraw.Draw(self.hi)
            ex = x + ew - 1 if side == "l" else x
            d.line([(ex, WOOD * SS), (ex, h - WOOD * SS)], fill=(20, 20, 20, 255), width=SS)

    @property
    def draw(self):
        return ImageDraw.Draw(self.hi)

    # -- silkscreen
    def text(self, x, y, s, size=14, bold=True, fill=INK, anchor="mm"):
        self.draw.text((x * SS, y * SS), s, font=font(size, bold), fill=fill, anchor=anchor)

    def line(self, x0, y0, x1, y1, w=2, fill=INK):
        self.draw.line([(x0 * SS, y0 * SS), (x1 * SS, y1 * SS)], fill=fill, width=max(1, int(w * SS)))

    def title(self, x, s):
        self.text(x, H - WOOD - 28, s, 33, True, TITLE)

    def rule(self, x):
        self.line(x, WOOD + 10, x, H - WOOD - 8, 2, (200, 196, 184, 210))

    def hrule(self, x0, x1, y):
        self.line(x0, y, x1, y, 2, (200, 196, 184, 210))

    def put(self, im, cx, cy):
        """Paste an RGBA sprite (hi-res) centred at (cx, cy) final pixels."""
        self.hi.alpha_composite(im, (int(round(cx * SS - im.width / 2)), int(round(cy * SS - im.height / 2))))

    def dial(self, cx, cy, r, spec, name=None, name_dy=-1, ring=None):
        """A knob's silkscreen: shadow, the scale's ticks and numerals round it, its name above."""
        ring = ring or r + 20
        self.hi.alpha_composite(shadow(self.hi.size, ((cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS)))
        scale(self, cx, cy, r, ring, spec)
        if name:
            y = cy - ring - 12 if name_dy == -1 else cy + name_dy
            for i, ln in enumerate(name.split("\n")):
                self.text(cx, y - (len(name.split("\n")) - 1 - i) * 15, ln, 14, True, INK)

    def glass(self, cx, cy, w, h):
        g = asset("display-glass", "RGB").resize((w * SS, h * SS), Image.LANCZOS)
        g = g.point(lambda v: int(v * 0.75))
        m = Image.new("L", g.size, 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, g.width - 1, g.height - 1), radius=6 * SS, fill=255)
        x, y = int(cx * SS - g.width / 2), int(cy * SS - g.height / 2)
        d = self.draw
        d.rounded_rectangle((x - 3 * SS, y - 3 * SS, x + g.width + 3 * SS, y + g.height + 3 * SS), radius=8 * SS, fill=(8, 8, 8), outline=(70, 66, 60), width=SS)
        self.hi.paste(g, (x, y), m)

    def button_row(self, cx, cy, labels, w=112, h=44, gap=8, lit=None):
        """A bank of amber push tabs (MODE's); `lit` the one lit."""
        n = len(labels)
        x0 = cx - (n * w + (n - 1) * gap) / 2
        for i, s in enumerate(labels):
            bx = x0 + i * (w + gap)
            tab_button(self, bx + w / 2, cy, w, h, s, i == lit)


def tab_button(t, cx, cy, w, h, label, lit):
    box = (int((cx - w / 2) * SS), int((cy - h / 2) * SS), int((cx + w / 2) * SS), int((cy + h / 2) * SS))
    if lit:
        glow = Image.new("RGBA", t.hi.size, (0, 0, 0, 0))
        ImageDraw.Draw(glow).rounded_rectangle((box[0] - 4 * SS, box[1] - 4 * SS, box[2] + 4 * SS, box[3] + 4 * SS), radius=9 * SS, fill=(255, 150, 40, 170))
        t.hi.alpha_composite(glow.filter(ImageFilter.GaussianBlur(7 * SS)))
    base = asset("button").resize((box[2] - box[0], box[3] - box[1]), Image.LANCZOS)
    amber = (255, 168, 62) if lit else (150, 78, 18)
    a = base.getchannel("A")
    g = ImageOps.grayscale(base.convert("RGB"))
    g = ImageOps.autocontrast(g)
    c = ImageOps.colorize(g, tuple(int(v * 0.55) for v in amber), tuple(min(255, int(v * 1.12)) for v in amber))
    c.putalpha(a)
    t.hi.alpha_composite(c, (box[0], box[1]))
    t.text(cx, cy, label, 14, True, (60, 28, 4) if lit else (84, 40, 8))


# ---------------------------------------------------------------- scales

def lin(n):
    return [i / (n - 1) for i in range(n)]


DIALS = {
    # each: (labels [(fraction, text)], minor fractions)
    "ten": ([(i / 10, str(i)) for i in range(0, 11, 2)], lin(11)),
    "tune": ([(i / 4, str(i - 2)) for i in range(5)], lin(5)),
    "cutoff": ([(i / 4, str(2 * i - 4)) for i in range(5)], lin(9)),
    "freq": ([(i / 14, str(i - 7)) for i in (0, 2, 4, 6, 7, 8, 10, 12, 14)], lin(15)),
    "time": ([(0, "10"), (0.2, "200"), (0.4, "600"), (0.6, "1"), (0.8, "5"), (1, "10")], lin(11)),
    "mix": ([(0, "OSC 3"), (0.25, "2"), (0.5, "5"), (0.75, "8"), (1, "NOISE")], lin(11)),
    "voices": ([(i / 8, str(i + 2)) for i in range(9)], lin(9)),
    "drive": ([(i / 4, str(6 * i)) for i in range(5)], lin(9)),
    "level": ([((v + 30) / 42, ("+" if v > 0 else "") + str(v)) for v in (-30, -20, -10, 0, 10)], [(v + 30) / 42 for v in range(-30, 13, 5)]),
    "detune": ([(i / 4, str(25 * i)) for i in range(5)], lin(9)),
    "bend": ([(v / 8.07, str(v)) for v in (0, 2, 4, 6, 8)], [v / 8.07 for v in range(0, 9)]),
}


def scale(t, cx, cy, r, ring, spec):
    labels, minors = DIALS[spec]
    for f in minors:
        a = -135 + 270 * f
        x0, y0 = polar(cx, cy, r + 5, a)
        x1, y1 = polar(cx, cy, r + 10, a)
        t.line(x0, y0, x1, y1, 1.6, INK)
    for f, s in labels:
        a = -135 + 270 * f
        x0, y0 = polar(cx, cy, r + 4, a)
        x1, y1 = polar(cx, cy, r + 12, a)
        t.line(x0, y0, x1, y1, 2.2, INK)
        x, y = polar(cx, cy, ring + (4 if len(s) > 2 else 0), a)
        t.text(x, y, s, 12 if len(s) < 4 else 10, True, INK)


WAVES = {
    "tri": [(-7, 5), (0, -5), (7, 5)],
    "shark": [(-7, 5), (-3, -5), (1, 3), (7, -5)],
    "saw": [(-7, 5), (7, -5), (7, 5)],
    "rev": [(-7, -5), (7, 5), (7, -5)],
    "sq": [(-7, 5), (-7, -5), (0, -5), (0, 5), (7, 5)],
    "wide": [(-7, 5), (-7, -5), (3, -5), (3, 5), (7, 5)],
    "narrow": [(-7, 5), (-4, 5), (-4, -5), (0, -5), (0, 5), (7, 5)],
}


def selector(t, cx, cy, r, labels, name=None):
    """A six-way pointer knob's silkscreen: its positions' ticks and legends (text or a waveform's drawing)."""
    ring = r + 22
    t.hi.alpha_composite(shadow(t.hi.size, ((cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS)))
    for i, lab in enumerate(labels):
        a = -120 + 48 * i
        x0, y0 = polar(cx, cy, r + 4, a)
        x1, y1 = polar(cx, cy, r + 11, a)
        t.line(x0, y0, x1, y1, 2.2, INK)
        x, y = polar(cx, cy, ring, a)
        if lab in WAVES:
            pts = [(x + px * 0.95, y + py * 0.95) for px, py in WAVES[lab]]
            t.draw.line([(px * SS, py * SS) for px, py in pts], fill=INK, width=int(1.8 * SS), joint="curve")
        else:
            t.text(x, y, lab, 12, True, INK)
    if name:
        t.text(cx, cy - ring - 14, name, 14, True, INK)


# ---------------------------------------------------------------- control frames

def knob_sprite(kind, d):
    name = {"knob": "knob", "big": "knob-big", "pointer": "pointer"}[kind]
    im = asset(name)
    cap = {"knob": 0.578, "big": 0.653, "pointer": 0.43}[kind]
    body = {"knob": 0.978, "big": 0.989, "pointer": 0.81}[kind]
    size = d / body                      # the picture's width so that the body's diameter is d
    s = int(round(size * SS * 1.0))
    return im.resize((s, s), Image.LANCZOS), cap


def turned(spr, cap, deg):
    s = spr.width
    rot = spr.rotate(-deg, resample=Image.BICUBIC)
    # the spun cap keeps its sheen whichever way the knob turns
    m = Image.new("L", (s, s), 0)
    r = int(cap * s / 2)
    ImageDraw.Draw(m).ellipse((s / 2 - r, s / 2 - r, s / 2 + r, s / 2 + r), fill=255)
    rot.paste(spr, (0, 0), m)
    return rot


def crop_hi(tab, cx, cy, w, h):
    x0, y0 = int(round((cx - w / 2) * SS)), int(round((cy - h / 2) * SS))
    return tab.hi.crop((x0, y0, x0 + w * SS, y0 + h * SS))


def to_rgb_final(im, w, h):
    return im.convert("RGB").resize((w, h), Image.LANCZOS)


def strip_from(frames, w, h):
    out = Image.new("RGB", (w, h * len(frames)))
    for i, f in enumerate(frames):
        out.paste(f, (0, i * h))
    return out


class Out:
    def __init__(self, root):
        self.root = root
        self.art = os.path.join(root, "art")
        import shutil
        shutil.rmtree(self.art, ignore_errors=True)       # (the art is all generated: no stale pictures)
        os.makedirs(self.art, exist_ok=True)
        self.layout = []

    def save(self, im, name):
        im.save(os.path.join(self.art, name), optimize=True)

    def add(self, line):
        self.layout.append(line)


def default_norm(params, key):
    p = params[key]
    if "options" in p:
        return p["options"].index(p["default"]) / max(1, len(p["options"]) - 1)
    return (p["default"] - p["min"]) / (p["max"] - p["min"])


def add_knob(t, key, cx, cy, r, spec, name, kind="knob", vs=15, bw=104, ring=None):
    """A knob: scale and name into the background, a 64-frame filmstrip, the layout line."""
    side = 2 * r + 10
    t.dial(cx, cy, r, spec, name, ring=ring)
    t.controls.append(dict(kind="knob", key=key, cx=cx, cy=cy, r=r, side=side, sprite=kind, vs=vs, bw=bw))


def add_selector(t, key, cx, cy, r, labels, name):
    side = even((2 * r - 4) / 0.81) + 6
    selector(t, cx, cy, r, labels, name)
    t.controls.append(dict(kind="selector", key=key, cx=cx, cy=cy, r=r, side=side, vs=0, bw=2 * r + 40))


def render_controls(t, out, params, preview):
    final_bg = t.hi.convert("RGB").resize((W, H), Image.LANCZOS)
    prev = final_bg.convert("RGBA")
    for c in t.controls:
        k = c["kind"]
        key = c.get("key")
        if k in ("knob", "selector"):
            side, r = c["side"], c["r"]
            kind = c.get("sprite", "pointer" if k == "selector" else "knob")
            d = 2 * r - (0 if kind != "pointer" else 4)
            spr, cap = knob_sprite(kind, d if kind != "big" else d)
            n = 6 if k == "selector" else FRAMES
            frames = []
            for i in range(n):
                v = i / (n - 1)
                deg = (-120 + 48 * i) if k == "selector" else -135 + 270 * v
                bgc = crop_hi(t, c["cx"], c["cy"], side, side)
                kn = turned(spr, cap, deg)
                bgc.alpha_composite(kn, ((bgc.width - kn.width) // 2, (bgc.height - kn.height) // 2))
                frames.append(to_rgb_final(bgc, side, side))
            out.save(strip_from(frames, side, side), key + ".png")
            dn = default_norm(params, key)
            prev.alpha_composite(frames[int(round(dn * (n - 1)))].convert("RGBA"), (int(c["cx"] - side / 2), int(c["cy"] - side / 2)))
            rr = (side - 10) // 2
            out.add('knob cx=%d cy=%d r=%d label="" key=%s strip=art/%s.png frames=%d ns=0 vs=%d bw=%d' %
                    (c["cx"], c["cy"] + Y_OFF, rr, key, key, n, c["vs"], c["bw"]))
        elif k == "pair":
            w, h = c["w"], c["h"]
            imgs = []
            for st in (0, 1):
                bgc = crop_hi(t, c["cx"], c["cy"], w, h)
                spr = c["draw"](st)
                bgc.alpha_composite(spr, ((bgc.width - spr.width) // 2, (bgc.height - spr.height) // 2))
                imgs.append(to_rgb_final(bgc, w, h))
            out.save(imgs[0], key + "_off.png")
            out.save(imgs[1], key + "_on.png")
            dn = default_norm(params, key)
            prev.alpha_composite(imgs[int(dn >= 0.5)].convert("RGBA"), (int(c["cx"] - w / 2), int(c["cy"] - h / 2)))
            out.add('toggle cx=%d cy=%d label="" key=%s img=art/%s_off.png img_on=art/%s_on.png w=%d h=%d ns=0' %
                    (c["cx"], c["cy"] + Y_OFF, key, key, key, w, h))
        elif k == "wheel":
            w, h, n = c["w"], c["h"], 48
            frames = []
            for i in range(n):
                bgc = crop_hi(t, c["cx"], c["cy"], w, h)
                spr = wheel_sprite(w, h, i / (n - 1))
                bgc.alpha_composite(spr, (0, 0))
                frames.append(to_rgb_final(bgc, w, h))
            out.save(strip_from(frames, w, h), key + ".png")
            prev.alpha_composite(frames[0].convert("RGBA"), (int(c["cx"] - w / 2), int(c["cy"] - h / 2)))
            out.add('slider_v cx=%d cy=%d w=%d h=%d label="" key=%s strip=art/%s.png frames=%d ns=0 vs=0' % (c["cx"], c["cy"] + Y_OFF, w, h, key, key, n))
        elif k == "options":
            # a bank of tabs: one picture an option (that option lit), under clear segments that pick it
            files = []
            for i in range(c["n"]):
                tmp = copy.copy(t)
                tmp.hi = t.hi.copy()
                c["lit"](tmp, i)
                f = to_rgb_final(crop_hi(tmp, c["cx"], c["cy"], c["w"], c["h"]), c["w"], c["h"])
                out.save(f, "%s_%d.png" % (key, i))
                files.append("art/%s_%d.png" % (key, i))
                if i == int(round(default_norm(params, key) * (c["n"] - 1))):
                    prev.alpha_composite(f.convert("RGBA"), (int(c["cx"] - c["w"] / 2), int(c["cy"] - c["h"] / 2)))
            out.add('picture x=%d y=%d w=%d h=%d key=%s files="%s"' % (c["cx"] - c["w"] // 2, c["cy"] - c["h"] // 2 + Y_OFF, c["w"], c["h"], key, ",".join(files)))
            out.add('enum_h cx=%d cy=%d label="" key=%s options="%s" sw=%d sh=%d img=art/clear.png img_on=art/clear.png' %
                    (c["cx"], c["cy"] + Y_OFF, key, ",".join([" "] * c["n"]), c["sw"], c["sh"]))
        elif k == "field":
            w, h, n = c["w"], c["h"], 49
            frames = []
            for i in range(n):
                bgc = crop_hi(t, c["cx"], c["cy"], w, h)
                if i:
                    at = (i / (n - 1) - 0.02) / 0.98
                    cxd = (14 + max(0.0, min(1.0, at)) * (w - 28)) * SS
                    cyd = h * SS / 2
                    glow = Image.new("RGBA", bgc.size, (0, 0, 0, 0))
                    ImageDraw.Draw(glow).ellipse((cxd - 17 * SS, cyd - 17 * SS, cxd + 17 * SS, cyd + 17 * SS), fill=(232, 110, 40, 150))
                    bgc.alpha_composite(glow.filter(ImageFilter.GaussianBlur(7 * SS)))
                    ImageDraw.Draw(bgc).ellipse((cxd - 9 * SS, cyd - 9 * SS, cxd + 9 * SS, cyd + 9 * SS), fill=(255, 150, 70, 255))
                frames.append(to_rgb_final(bgc, w, h))
            out.save(strip_from(frames, w, h), "field.png")
            for j in range(1, 11):
                out.add('meter cx=%d cy=%d w=%d h=%d key=dot_%d strip=art/field.png frames=%d' % (c["cx"], c["cy"] + Y_OFF, w, h, j, n))
        elif k == "readout":
            out.add('readout cx=%d cy=%d w=%d h=%d label="" key=%s tsize=%d tcolor=ff9a3c talign=center' %
                    (c["cx"], c["cy"] + Y_OFF, c["w"], c["h"], key, c.get("tsize", 28)))
        elif k == "meter":
            out.add('meter cx=%d cy=%d w=%d h=%d key=%s strip=art/%s frames=%d' % (c["cx"], c["cy"] + Y_OFF, c["w"], c["h"], key, c["strip"], c["frames"]))
    prev.convert("RGB").save(os.path.join(preview, t.name.lower() + ".png"))
    if t.name == "OSCILLATORS":
        # the Instruments browser's tile: the oscillator bank, halved
        final_bg.crop((420, 40, 960, 260)).resize((270, 110), Image.LANCZOS).save(os.path.join(out.art, "tile.png"))
    final_bg.save(os.path.join(out.art, t.name.lower() + ".png"), optimize=True)


def wheel_sprite(w, h, v):
    """The MODULATION wheel at v (0 back .. 1 forward): its ribbed ivory edge, the dot that travels."""
    s = SS
    im = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pad = 5 * s
    d.rounded_rectangle((0, 0, w * s - 1, h * s - 1), radius=8 * s, fill=(6, 6, 6, 255), outline=(60, 58, 54, 255), width=s)
    inner = (pad, pad, w * s - pad, h * s - pad)
    body = Image.new("RGB", (inner[2] - inner[0], inner[3] - inner[1]))
    bd = ImageDraw.Draw(body)
    bw_ = body.width
    for x in range(bw_):
        u = (x + 0.5) / bw_
        sh = 0.55 + 0.45 * math.sin(math.pi * u)
        bd.line([(x, 0), (x, body.height)], fill=(int(226 * sh), int(220 * sh), int(200 * sh)))
    rib = 11 * s
    off = (v * 2.0 * rib * 8) % rib
    for y in range(-rib, body.height + rib, rib):
        yy = int(y + off)
        bd.line([(0, yy), (bw_, yy)], fill=(70, 66, 56), width=max(1, s))
        bd.line([(0, yy + s), (bw_, yy + s)], fill=(255, 250, 236), width=max(1, s))
    mask = Image.new("L", body.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, body.width - 1, body.height - 1), radius=6 * s, fill=255)
    # roll the ends of the wheel dark
    fade = Image.linear_gradient("L").resize(body.size)
    fade = ImageChops.multiply(fade, ImageChops.invert(fade)).point(lambda p: min(255, p * 4))
    body = ImageChops.multiply(body, Image.merge("RGB", (fade.point(lambda p: 90 + p * 165 // 255),) * 3))
    im.paste(body, (inner[0], inner[1]), mask)
    # the dot
    top, bot = inner[1] + 12 * s, inner[3] - 12 * s
    y = bot - v * (bot - top)
    d.ellipse((w * s / 2 - 4 * s, y - 4 * s, w * s / 2 + 4 * s, y + 4 * s), fill=(14, 12, 10, 255))
    return im


# rocker images
def rocker_img(color, on, w, vertical=False, flip_vertical_on=True):
    base = asset("rocker-orange" if color == "orange" else "rocker-blue")
    if color == "ivory":
        base = tint_ivory(asset("rocker-blue"))
    base = base.resize((w * SS, max(1, round(base.height * w * SS / base.width))), Image.LANCZOS)
    if not on:
        base = ImageOps.mirror(base)
    if vertical:
        # right half raised -> top raised when on
        base = base.rotate(90, expand=True)
    return base


def add_rocker(t, key, cx, cy, color, w=88, vertical=False, name=None, pad=10):
    spr = lambda st: rocker_img(color, st, w, vertical)
    sp = spr(1)
    cw, ch = even(sp.width / SS) + 2 * pad, even(sp.height / SS) + 2 * pad
    # the opening's shadow in the background
    t.hi.alpha_composite(shadow(t.hi.size, ((cx - sp.width / SS / 2) * SS, (cy - sp.height / SS / 2) * SS, (cx + sp.width / SS / 2) * SS, (cy + sp.height / SS / 2) * SS), 3, 120, (0, 2), False))
    t.controls.append(dict(kind="pair", key=key, cx=cx, cy=cy, w=cw, h=ch, draw=spr))
    if name:
        for i, ln in enumerate(name.split("\n")[::-1]):
            t.text(cx, cy - sp.height / SS / 2 - 12 - i * 15, ln, 14, True, INK)


def jack(t, cx, cy, d=40):
    im = asset("jack").resize((d * SS, d * SS), Image.LANCZOS)
    t.hi.alpha_composite(shadow(t.hi.size, ((cx - d / 2) * SS, (cy - d / 2) * SS, (cx + d / 2) * SS, (cy + d / 2) * SS), 3, 130))
    t.put(im, cx, cy)


def toggle_sprite(which, w, rot=0):
    im = asset("toggle-" + which)
    im = im.crop(im.getbbox())
    sp = im.resize((w * SS, max(1, round(im.height * w * SS / im.width))), Image.LANCZOS)
    if rot:
        sp = sp.rotate(rot, expand=True, resample=Image.BICUBIC)
    return sp


def build(root):
    params = {p["key"]: p for p in json.load(open(os.path.join(root, "params.json")))["params"]}
    out = Out(root)
    preview = os.path.join(root, "preview")
    os.makedirs(preview, exist_ok=True)
    Image.new("RGBA", (4, 4), (0, 0, 0, 0)).save(os.path.join(out.art, "clear.png"))
    out.add("# generated by skin/make_skin.py: CA-72's pictures and typeface, drawn for the MPC's 1280x628 plugin area.\n"
            "theme_bg=0e0d0c\ntheme_panel=0e0d0c\ntheme_ink=e8e2d0\ntheme_ink_dim=8f8878\ntheme_accent=e8862b\n"
            "theme_accent_hi=ffb15c\ntheme_lcd=0e0d0c\ntheme_seg_active=0e0d0c\ntheme_seg_inactive=0e0d0c\n"
            "theme_seg_active_tx=0e0d0c\ntheme_box=0e0d0c")
    import tabs
    for build_tab in tabs.ALL:
        t = build_tab(params, out)
        render_controls_with_lines(t, out, params, preview)
    open(os.path.join(root, "layout.conf"), "w").write("\n".join(out.layout) + "\n")


def render_controls_with_lines(t, out, params, preview):
    out.add("\n[tab %s]\nart file=art/%s.png fit=stretch" % (t.name, t.name.lower()))
    render_controls(t, out, params, preview)
    for l in t.lines:
        out.add(l)
    out.add('qlinks "%s" = %s' % (t.name, ",".join(t.qlinks)))


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    import make_skin
    make_skin.build(sys.argv[1])
