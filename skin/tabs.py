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


def rocker(t, key, cx, cy, color, w=88, vertical=False, name=None, invert=False, pad=10):
    spr = lambda st: m.rocker_img(color, (not st) if invert else st, w, vertical)
    sp = spr(1)
    cw, ch = m.even(sp.width / SS) + 2 * pad, m.even(sp.height / SS) + 2 * pad
    t.hi.alpha_composite(m.shadow(t.hi.size, ((cx - sp.width / SS / 2) * SS, (cy - sp.height / SS / 2) * SS, (cx + sp.width / SS / 2) * SS, (cy + sp.height / SS / 2) * SS), 3, 120, (0, 2), False))
    t.controls.append(dict(kind="pair", key=key, cx=cx, cy=cy, w=cw, h=ch, draw=spr))
    if name:
        for i, ln in enumerate(name.split("\n")[::-1]):
            t.text(cx, cy - sp.height / SS / 2 - 13 - i * 15, ln, 14, True, INK)


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
    t = Tab("MIXER", ["osc1_volume", "osc2_volume", "osc3_volume", "ext_volume", "noise_volume", "volume", "feedback", "osc1_on", "osc2_on",
                      "osc3_on", "ext_on", "noise_on", "main_output", "a440", "bass_comp", "quality"])
    t.rule(700)
    t.title(350, "MIXER")
    t.title(983, "OUTPUT")
    rows = [134, 224, 314, 404, 494]
    for i, key in ((0, "osc1"), (2, "osc2"), (4, "osc3")):
        K(t, key + "_volume", 118, rows[i], 38, "ten", "OSC. %s VOLUME" % key[-1])
        t.line(118 + 36 + 22, rows[i], 300 - 48, rows[i], 2.4)
    for i, key, nm in ((1, "ext", "EXTERNAL INPUT\nVOLUME"), (3, "noise", "NOISE VOLUME")):
        K(t, key + "_volume", 520, rows[i], 36, "ten", nm)
        t.line(300 + 48, rows[i], 520 - 36 - 22, rows[i], 2.4)
    for i, key in enumerate(["osc1_on", "ext_on", "osc2_on", "noise_on", "osc3_on"]):
        rocker(t, key, 300, rows[i], "blue", 88)
        on_legend(t, 300, rows[i])
    t.text(655, rows[3] - 62, "WHITE", 12, True, INK)
    rocker(t, "noise_type", 655, rows[3], "blue", 88, vertical=True, invert=True)
    t.text(655, rows[3] + 62, "PINK", 12, True, INK)
    # OUTPUT
    K(t, "volume", 800, 150, 36, "ten", "VOLUME")
    rocker(t, "main_output", 975, 150, "blue", 88, name="MAIN OUTPUT")
    on_legend(t, 975, 150)
    t.text(1150, 90, "QUALITY", 14, True, INK)
    toggle2(t, "quality", 1150, 150, 54, "down", "mid")
    t.text(1100, 143, "HI", 12, True, INK)
    t.text(1150, 205, "LO", 12, True, INK)
    K(t, "feedback", 800, 345, 36, "ten", "FEEDBACK")
    # PATCH: a cable from the output into EXTERNAL INPUT, plugged at the jack
    t.text(975, 290, "PATCH", 14, True, INK)
    jk = m.asset("jack").resize((44 * SS, 44 * SS), m.Image.LANCZOS)

    def patch(st):
        im = Image.new("RGBA", (86 * SS, 86 * SS), (0, 0, 0, 0))
        im.alpha_composite(m.shadow(im.size, (21 * SS, 21 * SS, 65 * SS, 65 * SS), 3, 130))
        im.alpha_composite(jk, (21 * SS, 21 * SS))
        lamp = m.jewel(bool(st)).resize((20 * SS, 20 * SS), m.Image.LANCZOS)
        im.alpha_composite(lamp, (62 * SS, 6 * SS))
        return im

    t.controls.append(dict(kind="pair", key="patch", cx=975, cy=345, w=86, h=86, draw=patch))
    t.text(975, 392, "OUTPUT > EXT. INPUT", 11, True, m.DIM)
    rocker(t, "a440", 1140, 330, "blue", 88, name="A-440")
    on_legend(t, 1140, 330)
    rocker(t, "bass_comp", 1140, 440, "blue", 88, name="BASS COMP")
    on_legend(t, 1140, 440)
    return t


# ------------------------------------------------------------------------------------------------ 3

def modifiers(params, out):
    t = Tab("MODIFIERS", ["cutoff", "emphasis", "contour_amount", "filter_attack", "filter_decay", "filter_sustain", "loudness_attack",
                          "loudness_decay", "loudness_sustain", "mod_wheel", "filter_mode", "filter_mod", "keyboard_control_1",
                          "keyboard_control_2", "note_priority", "retrigger"])
    t.rule(795)
    t.title(420, "MODIFIERS")
    t.title(1030, "CONTROLLER")
    t.text(1030, 44, "LEFT HAND", 22, True, INK)
    rocker(t, "filter_mode", 80, 128, "orange", 88, name="FILTER\nMODE")
    t.text(52, 128 + 30, "LO", 12, True, INK)
    t.text(108, 128 + 30, "HI", 12, True, INK)
    rocker(t, "filter_mod", 80, 245, "orange", 88, name="FILTER\nMODULATION")
    on_legend(t, 80, 245)
    t.text(80, 322, "KEYBOARD", 14, True, INK)
    t.text(80, 338, "CONTROL", 14, True, INK)
    rocker(t, "keyboard_control_1", 80, 375, "orange", 88)
    rocker(t, "keyboard_control_2", 80, 440, "orange", 88)
    t.text(22, 375, "1", 14, True, INK)
    t.text(22, 440, "2", 14, True, INK)
    on_legend(t, 80, 440)
    t.text(450, 44, "FILTER", 22, True, INK)
    cols = [255, 435, 615]
    for x, key, spec, nm in zip(cols, ["cutoff", "emphasis", "contour_amount"], ["cutoff", "ten", "ten"], ["CUTOFF FREQUENCY", "EMPHASIS", "AMOUNT OF CONTOUR"]):
        K(t, key, x, 142, 38, spec, nm)
    for x, key, spec, nm in zip(cols, ["filter_attack", "filter_decay", "filter_sustain"], ["time", "time", "ten"], ["ATTACK TIME", "DECAY TIME", "SUSTAIN LEVEL"]):
        K(t, key, x, 284, 38, spec, nm)
    t.hrule(190, 700, 353)
    t.text(450, 366, "LOUDNESS CONTOUR", 18, True, INK)
    for x, key, spec, nm in zip(cols, ["loudness_attack", "loudness_decay", "loudness_sustain"], ["time", "time", "ten"], ["ATTACK TIME", "DECAY TIME", "SUSTAIN LEVEL"]):
        K(t, key, x, 464, 38, spec, nm)
    # left-hand controller
    t.text(870, 100, "PRIORITY", 14, True, INK, "mm")
    pr = [("down", -90), ("mid", 0), ("up", -90)]

    def prio(tab, lit):
        i = 1 if lit < 0 else lit
        which, rot = pr[i]
        tab.put(m.toggle_sprite(which, 52, rot), 985, 100)

    prio(t, -1)
    t.text(985, 62, "LAST", 11, True, INK)
    t.text(930, 112, "LOW", 11, True, INK)
    t.text(1040, 112, "HIGH", 11, True, INK)
    t.controls.append(dict(kind="options", key="note_priority", cx=985, cy=100, w=132, h=70, n=3, lit=prio, sw=44, sh=60))
    for y, key, nm in ((190, "retrigger", "RETRIGGER"), (270, "glide_on", "GLIDE"), (350, "decay_on", "DECAY")):
        rocker(t, key, 985, y, "ivory", 76)
        t.text(930, y, nm, 13, True, INK, "rm")
        on_legend(t, 985, y, 76)
    m.jack(t, 825, 270)
    m.jack(t, 825, 350)
    # the wheels
    pw = m.wheel_sprite(64, 220, 0.5)
    t.put(pw, 1115, 400)
    t.text(1115, 400 + 124, "PITCH", 13, True, INK)
    t.controls.append(dict(kind="wheel", key="mod_wheel", cx=1200, cy=400, w=64, h=220))
    t.text(1200, 400 + 124, "MOD.", 13, True, INK)
    return t


# ------------------------------------------------------------------------------------------------ 4

def perform(params, out):
    t = Tab("PERFORM", ["voices", "entropy", "drive", "level", "midi_bend_range", "mode", "auto_gain"])
    t.rule(620)
    t.title(310, "VOICES")
    t.title(943, "OUTPUT")
    bank(t, "mode", 310, 92, ["MONO", "POLY", "UNISON"], name="MODE")
    K(t, "voices", 200, 255, 46, "voices", "VOICES", vs=0, ring=70)
    readout(t, "voices", 365, 255)
    K(t, "entropy", 200, 440, 46, "ten", "ENTROPY", vs=0, ring=70)
    readout(t, "entropy", 365, 440)
    # AUTO GAIN
    t.text(775, 48, "AUTO GAIN", 14, True, INK)
    sp = lambda st: tab_sprite(120, 44, "ON", bool(st))
    t.controls.append(dict(kind="pair", key="auto_gain", cx=775, cy=92, w=144, h=68, draw=sp))
    readout(t, "auto_db", 945, 92, unit="dB")
    K(t, "drive", 775, 255, 46, "drive", "DRIVE", vs=0, ring=70)
    readout(t, "drive", 945, 255, unit="dB")
    K(t, "level", 775, 440, 46, "level", "LEVEL", vs=0, ring=70)
    readout(t, "level", 945, 440, unit="dB")
    K(t, "midi_bend_range", 1160, 255, 46, "bend", "MIDI BEND RANGE", vs=0, ring=70)
    readout(t, "midi_bend_range", 1160, 355, w=100, h=48, unit="st")
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


ALL = [oscillators, mixer, modifiers, perform, stereo]
