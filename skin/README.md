# The skin

`make_skin.py` and `tabs.py` draw Model-72's MPC skin from scratch for the MPC's 1280 x 628 plugin area, with
CA-72's own pictures and typeface, instead of cropping CA-72's 3108-unit-wide panel.

    tools/make_skin.sh       # -> vst/art/*.png (committed), vst/layout.conf, vst/preview/*.png

| | |
|---|---|
| `assets/*.png` | CA-72's pictures (`crates/ca72-panel/assets/worn/` at `3f99076`, GPL-3.0-or-later): the panel's black face, the walnut, the knobs, rockers, toggle, jack, jewel and push-button cap, the readouts' glass. No picture carries a name or a logo. |
| `assets/URWGothic-*.otf` | The panel's lettering: URW Gothic Book and Demi (AGPL-3.0 with a font exception, `assets/URW-LICENSE`), as CA-72 uses it. |
| `tabs.py` | The five tabs' layouts: where every control, scale, title and rule goes (screen pixels). |
| `make_skin.py` | The drawing: each tab's silkscreen at 2x (titles, scales, numerals, rules), then every control as a filmstrip or an on/off pair cut from that tab with the control in each position, so a frame sits exactly over its place. |

The wood bands, panel face and silver ends are the same on every tab, so the tabs read as one panel continuing. Knobs are
64-frame filmstrips; the pointer knobs (RANGE, WAVEFORM) six; the tabs and rockers on/off pairs; MODE, VOICES PLAYED AS,
PLACEMENT and PRIORITY a picture an option under clear touch segments; the stereo field a 49-frame display strip each of
ten dots drives (`dot_1` to `dot_10`, set by the engine).

Needs Pillow (the script is run in a `python:3.11-slim` container by `tools/make_skin.sh`).
