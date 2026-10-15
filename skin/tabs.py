"""Model-72's five tabs, laid out for the MPC's 1280x628 plugin area (coordinates are the screen's, y from the top of the plugin
area; the wood bands take the top and bottom 28 px)."""
from PIL import Image, ImageDraw

import make_skin as m
from make_skin import INK, SS, Tab, font

K = m.add_knob


def on_legend(t, cx, cy, w=88, text="ON"):
    t.text(cx + w * 0.30, cy + w * 0.19 + 12, text, 12, True, m.INK)


def readout(t, key, cx, cy, w=124, h=54, unit=None, tsize=28):
    t.glass(cx, cy, w, h)
    t.controls.append(dict(kind="readout", key=key, cx=cx, cy=cy, w=w - 12, h=h - 10, tsize=tsize))
    if unit:
        t.text(cx + w / 2 + 14, cy + 4, unit, 12, True, m.DIM)


def tab_sprite(w, h, label, lit):
    """An amber push tab with room round it for its glow, hi-res RGBA."""
    pad = 12
    im = Image.new("RGBA", ((w + 2 * pad) * SS, (h + 2 * pad) * SS), (0, 0, 0, 0))
    box = (pad * SS, pad * SS, (pad + w) * SS, (pad + h) * SS)
    if lit:
        glow = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(glow).rounded_rectangle((box[0] - 3 * SS, box[1] - 3 * SS, box[2] + 3 * SS, box[3] + 3 * SS), radius=9 * SS, fill=(255, 150, 40, 175))
        from PIL import ImageFilter
        im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(6 * SS)))
    base = m.asset("button").resize((box[2] - box[0], box[3] - box[1]), m.Image.LANCZOS)
    amber = (255, 168, 62) if lit else (150, 78, 18)
    g = m.ImageOps.autocontrast(m.ImageOps.grayscale(base.convert("RGB")))
    c = m.ImageOps.colorize(g, tuple(int(v * 0.55) for v in amber), tuple(min(255, int(v * 1.12)) for v in amber))
    c.putalpha(base.getchannel("A"))
    im.alpha_composite(c, (box[0], box[1]))
    ImageDraw.Draw(im).text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), label, font=font(14, True), fill=(60, 28, 4) if lit else (86, 42, 10), anchor="mm")
    return im


def bank(t, key, cx, cy, labels, w=120, h=44, gap=8, name=None):
    """A bank of tabs picking an option: one picture an option (that one lit) under clear segments."""
    n = len(labels)
    total = n * w + (n - 1) * gap
    x0 = cx - total / 2

    def draw(tab, lit):
        for i, s in enumerate(labels):
            tab.put(tab_sprite(w, h, s, i == lit), x0 + i * (w + gap) + w / 2, cy)

    draw(t, -1)
    if name:
        t.text(cx, cy - h / 2 - 20, name, 14, True, INK)
    t.controls.append(dict(kind="options", key=key, cx=int(cx), cy=int(cy), w=m.even(total) + 24, h=h + 28, n=n, lit=draw, sw=w + gap, sh=h))


def toggle2(t, key, cx, cy, w, off, on, rot=0, pad=10):
    so, sn = m.toggle_sprite(off, w, rot), m.toggle_sprite(on, w, rot)
    cw, ch = m.even(max(so.width, sn.width) / SS) + 2 * pad, m.even(max(so.height, sn.height) / SS) + 2 * pad
    t.controls.append(dict(kind="pair", key=key, cx=cx, cy=cy, w=cw, h=ch, draw=lambda st: sn if st else so))


def rocker(t, key, cx, cy, color, w=88, vertical=False, name=None, invert=False, pad=4):
    spr = lambda st: m.rocker_img(color, (not st) if invert else st, w, vertical)
    sp = spr(1)
    gp = 9                                              # the glow margin the picture carries
    capw, caph = sp.width / SS - 2 * gp, sp.height / SS - 2 * gp
    cw, ch = m.even(sp.width / SS) + 2 * pad, m.even(sp.height / SS) + 2 * pad
    t.hi.alpha_composite(m.shadow(t.hi.size, ((cx - capw / 2) * SS, (cy - caph / 2) * SS, (cx + capw / 2) * SS, (cy + caph / 2) * SS), 3, 120, (0, 2), False))
    t.controls.append(dict(kind="pair", key=key, cx=cx, cy=cy, w=cw, h=ch, draw=spr))
    if name:
        for i, ln in enumerate(name.split("\n")[::-1]):
            t.text(cx, cy - caph / 2 - 13 - i * 15, ln, 14, True, INK)


# ------------------------------------------------------------------------------------------------ 1

def oscillators(params, out):
    t = Tab("OSCILLATORS", ["tune", "glide", "mod_mix", "osc1_range", "osc2_range", "osc3_range", "osc1_waveform", "osc2_waveform",
                            "osc3_waveform", "osc2_frequency", "osc3_frequency", "osc_mod", "osc3_control"], silver=("l",))
    t.rule(330)
    t.title(172, "CONTROLLERS")
    t.title(800, "OSCILLATOR BANK")
    K(t, "tune", 110, 150, 40, "tune", "TUNE")
    K(t, "glide", 250, 150, 40, "ten", "GLIDE")
    K(t, "mod_mix", 110, 345, 40, "mix", "MODULATION MIX")
    rocker(t, "osc_mod", 250, 345, "orange", 88, name="OSCILLATOR\nMODULATION")
    on_legend(t, 250, 345)
    rows = [135, 300, 465]
    rng = ["LO", "32'", "16'", "8'", "4'", "2'"]
    w12 = ["tri", "shark", "saw", "sq", "wide", "narrow"]
    w3 = ["tri", "rev", "saw", "sq", "wide", "narrow"]
    for i, y in enumerate(rows):
        n = i + 1
        m.add_selector(t, "osc%d_range" % n, 545, y, 34, rng, "RANGE" if i == 0 else None)
        m.add_selector(t, "osc%d_waveform" % n, 1065, y, 34, w3 if n == 3 else w12, "WAVEFORM" if i == 0 else None)
    t.text(805, rows[0] - 6, "OSCILLATOR –1", 14, True, INK)
    t.text(805, rows[0] + 12, "FREQUENCY", 14, True, INK)
    K(t, "osc2_frequency", 805, rows[1], 42, "freq", "OSCILLATOR –2", kind="big", ring=64)
    K(t, "osc3_frequency", 805, rows[2], 42, "freq", "OSCILLATOR –3", kind="big", ring=64)
    rocker(t, "osc3_control", 388, rows[2], "orange", 88, vertical=True, name="OSC. 3\nCONTROL")
    t.text(388, rows[2] + 58, "ON", 12, True, INK)
    return t


# ------------------------------------------------------------------------------------------------ 2

def mixer(params, out):
    """The mixer on the left (each knob beside its rocker, the outer knobs the same distance either side) and the FILTER on the right."""
    t = Tab("MIXER FILTER", ["osc1_volume", "osc2_volume", "osc3_volume", "ext_volume", "noise_volume", "cutoff", "emphasis", "contour_amount",
                             "filter_attack", "filter_decay", "filter_sustain", "loudness_attack", "loudness_decay", "loudness_sustain", "bass_comp", "patch"])
    t.rule(585)
    t.title(300, "MIXER")
    t.title(935, "FILTER")
    rows = [134, 224, 314, 404, 494]
    rx, kl, kr = 292, 108, 476                      # rockers' column; left and right knobs the same 184 px off it
    for i, key in ((0, "osc1"), (2, "osc2"), (4, "osc3")):
        K(t, key + "_volume", kl, rows[i], 38, "ten", "OSC. %s VOLUME" % key[-1])
        t.line(kl + 36 + 22, rows[i], rx - 48, rows[i], 2.4)
    for i, key, nm in ((1, "ext", "EXTERNAL INPUT\nVOLUME"), (3, "noise", "NOISE VOLUME")):
        K(t, key + "_volume", kr, rows[i], 36, "ten", nm)
        t.line(rx + 48, rows[i], kr - 36 - 22, rows[i], 2.4)
    for i, key in enumerate(["osc1_on", "ext_on", "osc2_on", "noise_on", "osc3_on"]):
        rocker(t, key, rx, rows[i], "blue", 88)
        on_legend(t, rx, rows[i])
    # PATCH: the output cabled into EXTERNAL INPUT (its VOLUME sets how much)
    jk = m.asset("jack").resize((44 * SS, 44 * SS), m.Image.LANCZOS)

    def patch(st):
        im = Image.new("RGBA", (86 * SS, 86 * SS), (0, 0, 0, 0))
        im.alpha_composite(m.shadow(im.size, (21 * SS, 21 * SS, 65 * SS, 65 * SS), 3, 130))
        im.alpha_composite(jk, (21 * SS, 21 * SS))
        lamp = m.jewel(bool(st)).resize((20 * SS, 20 * SS), m.Image.LANCZOS)
        im.alpha_composite(lamp, (62 * SS, 6 * SS))
        return im

    t.text(430, 70, "PATCH", 14, True, INK, "rm")
    t.text(430, 88, "OUTPUT >", 10, True, m.DIM, "rm")
    t.text(430, 101, "EXT. INPUT", 10, True, m.DIM, "rm")
    t.controls.append(dict(kind="pair", key="patch", cx=476, cy=86, w=86, h=86, draw=patch))
    # noise colour: a horizontal rocker under the noise knob
    ny = rows[4] + 16
    t.text(kr - 66, ny, "WHITE", 12, True, INK, "rm")
    rocker(t, "noise_type", kr, ny, "blue", 88, invert=True)
    t.text(kr + 66, ny, "PINK", 12, True, INK, "lm")
    # FILTER: switches in a column at the left, the six knobs beside them
    cx0 = 690
    rocker(t, "filter_mode", cx0, 122, "orange", 88, name="FILTER\nMODE")
    t.text(cx0 - 28, 122 + 30, "LO", 12, True, INK)
    t.text(cx0 + 28, 122 + 30, "HI", 12, True, INK)
    rocker(t, "filter_mod", cx0, 232, "orange", 88, name="FILTER\nMODULATION")
    on_legend(t, cx0, 232)
    t.text(cx0, 308, "KEYBOARD", 14, True, INK)
    t.text(cx0, 324, "CONTROL", 14, True, INK)
    rocker(t, "keyboard_control_1", cx0, 358, "orange", 88)
    rocker(t, "keyboard_control_2", cx0, 418, "orange", 88)
    t.text(cx0 - 58, 358, "1", 14, True, INK)
    t.text(cx0 - 58, 418, "2", 14, True, INK)
    on_legend(t, cx0, 418)
    rocker(t, "bass_comp", cx0, 508, "blue", 88, name="BASS COMP")
    on_legend(t, cx0, 508)
    cols = [850, 1005, 1160]
    for x, key, spec, nm in zip(cols, ["cutoff", "emphasis", "contour_amount"], ["cutoff", "ten", "ten"], ["CUTOFF FREQUENCY", "EMPHASIS", "AMOUNT OF CONTOUR"]):
        K(t, key, x, 135, 38, spec, nm)
    for x, key, spec, nm in zip(cols, ["filter_attack", "filter_decay", "filter_sustain"], ["time", "time", "ten"], ["ATTACK TIME", "DECAY TIME", "SUSTAIN LEVEL"]):
        K(t, key, x, 277, 38, spec, nm)
    t.hrule(780, 1240, 350)
    t.text(1010, 366, "LOUDNESS CONTOUR", 18, True, INK)
    for x, key, spec, nm in zip(cols, ["loudness_attack", "loudness_decay", "loudness_sustain"], ["time", "time", "ten"], ["ATTACK TIME", "DECAY TIME", "SUSTAIN LEVEL"]):
        K(t, key, x, 480, 38, spec, nm)
    return t


# ------------------------------------------------------------------------------------------------ 3

def perform(params, out):
    """VOICES, then OUTPUT (in signal-flow order: filter drive, then volume), then the left-hand CONTROLLER."""
    t = Tab("OUTPUT", ["voices", "entropy", "drive", "volume", "midi_bend_range", "mode", "auto_gain", "quality", "a440", "note_priority",
                       "retrigger", "glide_on", "decay_on", "mod_wheel"])
    t.rule(340)
    t.rule(720)
    t.title(170, "OUTPUT")
    t.title(530, "VOICES")
    t.title(1000, "CONTROLLER")
    # OUTPUT (left): FILTER DRIVE then VOLUME, with AUTO GAIN and A-440 beside them
    K(t, "drive", 100, 190, 46, "drive", "FILTER DRIVE", vs=0, ring=70)
    K(t, "volume", 100, 420, 46, "ten", "VOLUME", vs=0, ring=70)
    t.text(250, 100, "AUTO GAIN", 14, True, INK)
    sp = lambda st: tab_sprite(110, 44, "ON", bool(st))
    t.controls.append(dict(kind="pair", key="auto_gain", cx=250, cy=150, w=134, h=68, draw=sp))
    readout(t, "auto_db", 250, 225, w=104, h=48, unit="dB", tsize=26)
    rocker(t, "a440", 250, 340, "blue", 88, name="A-440")
    on_legend(t, 250, 340)
    # VOICES (middle)
    bank(t, "mode", 530, 100, ["MONO", "POLY", "UNISON"], w=100, gap=6, name="MODE")
    K(t, "voices", 445, 265, 42, "voices", "VOICES", vs=0, ring=64)
    K(t, "entropy", 615, 265, 42, "ten", "ENTROPY", vs=0, ring=64)
    t.text(530, 380, "QUALITY", 14, True, INK)
    t.text(530, 408, "HI", 12, True, INK)
    toggle2(t, "quality", 530, 462, 54, "down", "mid")
    t.text(530, 516, "LO", 12, True, INK)
    # CONTROLLER (right): the switches at the left, BEND RANGE on top of the two wheels
    cx, py = 880, 140
    t.text(cx, py - 66, "PRIORITY", 14, True, INK)
    pr = [("down", -90), ("mid", 0), ("up", -90)]

    def prio(tab, lit):
        which, rot = pr[1 if lit < 0 else lit]
        tab.put(m.toggle_sprite(which, 52, rot), cx, py)

    t.text(cx, py - 42, "LAST", 11, True, INK)
    t.text(cx - 62, py + 14, "LOW", 11, True, INK)
    t.text(cx + 62, py + 14, "HIGH", 11, True, INK)
    t.controls.append(dict(kind="options", key="note_priority", cx=cx, cy=py, w=176, h=80, n=3, lit=prio, sw=58, sh=70))
    for y, key, nm in ((290, "retrigger", "RETRIGGER"), (385, "glide_on", "GLIDE"), (480, "decay_on", "DECAY")):
        rocker(t, key, cx, y, "ivory", 84)
        t.text(cx - 52, y, nm, 14, True, INK, "rm")
        on_legend(t, cx, y, 84)
    K(t, "midi_bend_range", 1110, 135, 40, "bend", "MIDI BEND RANGE", vs=0, ring=60)
    t.put(m.wheel_sprite(84, 310, 0.5), 1050, 365)
    t.text(1050, 365 + 172, "PITCH", 13, True, INK)
    t.controls.append(dict(kind="wheel", key="mod_wheel", cx=1175, cy=365, w=84, h=310))
    t.text(1175, 365 + 172, "MOD.", 13, True, INK)
    return t


# ------------------------------------------------------------------------------------------------ 5

def stereo(params, out):
    t = Tab("STEREO", ["spread", "inner", "double", "played_as", "placement"], silver=("r",))
    t.title(640, "STEREO")
    bank(t, "played_as", 330, 100, ["SCATTER", "DOUBLE"], w=132, name="VOICES PLAYED AS")
    bank(t, "placement", 950, 100, ["EVEN", "CENTER"], w=132, name="PLACEMENT")
    K(t, "spread", 230, 255, 46, "ten", "WIDTH", vs=0, ring=70)
    readout(t, "spread", 372, 255)
    K(t, "inner", 590, 255, 46, "ten", "INNER", vs=0, ring=70)
    readout(t, "inner", 732, 255)
    K(t, "double", 950, 255, 46, "detune", "DETUNE", vs=0, ring=70)
    readout(t, "double", 1092, 255)
    t.text(640, 378, "WHERE THE VOICES SOUND", 14, True, INK)
    t.text(60, 465, "L", 14, True, m.DIM)
    t.text(1208, 465, "R", 14, True, m.DIM)
    t.glass(640, 465, 1080, 100)
    t.controls.append(dict(kind="field", cx=640, cy=465, w=1080, h=100))
    return t


ALL = [oscillators, mixer, perform, stereo]
