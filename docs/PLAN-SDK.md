# Model-72 on the MPC Plugin SDK (branch rev-sdk)

Method: ~/mpc-vst-plugins-postlaunch/docs/SDK-PORTING.md. Branched from the 1.0.1 release (tag `model72-v1.0.1`, 677ed7c;
`main` lacks that release's `vst/params.lock`).

## Frozen identity (from the released 1.0.1 build)
- Name `Model-72`, vendor `sd88me`, uid `M072` (0x4d303732), folder `sd88me - VST - Model-72`.
- Parameter order: `vst/params.lock` (72, as released) = `vst/params.json`; `tools/gen_sdk_params.py` refuses any other order.
  New parameters are appended after index 71 only.
- Beta: `Model-72 2 Beta`, its own uid, installed next to the release.

## Old state
The 1.0.1 build (mpc-vst-plugins wrapper 8c7be1c) saves the engine's `"state"` text as the VST chunk: `key=value;...` over the 72
engine keys (choices as indices), NUL-terminated. `tests/fixtures/state-1.0.1.txt` is one, dumped from the release engine
(x86 build of the same `engine/` source). The SDK front end recognises a chunk that starts with `quality=` (no SDK header) and
hands it to the engine unchanged. `auto_db` and `dot_1..10` are engine readouts: pushed to the host, never written back.

## Status log
- 2026-11-18: phase 1 (repo survey) and phase 2 (identity frozen, plugin.json, param generator, old chunk fixture).
- 2026-11-18: phase 3. `src/Model72Plugin.cpp` (Profit-5's front end adapted: settle rule, debounced QUALITY, engine readouts pushed,
  19 factory programs + 64 user presets with a naming keyboard, params 72..117 appended). `tests/run.sh` (ASan/UBSan, real engine): OK,
  incl. the 1.0.1 chunk, HI's circuit filter, a 48 kHz host. `host_sim`: PASS (19/0/0). arm32 (glibc <= 2.29) + arm64 built with zig,
  validator clean. Default SDK skin until phase 4.
- 2026-11-18: phase 4. `tools/make_tui.py` rebuilds the four 1.0.1 pages from `vst/layout.conf` on the same art, places and film strips (the released
  skin's geometry: y - 86, knob 2r+10 + value, readout boxes painted in), adds the knob overlay, Q-Links in blocks of four with rectangles
  (MIXER FILTER = 2 sub-tabs: filter, mixer), and a PRESETS tab (+ SAVE / - DELETE, the naming keyboard). `tools/preview_tui.py` -> docs/skin-preview/.
  Validator: 0 errors, 0 warnings.
