#!/usr/bin/env bash
# The release zips, from the release build (./build-sdk.sh: build/sdk/"sd88me - VST - Model-72", identity Model-72 / M072), as 1.0.1 shipped them:
#   dist/Model-72-<ver>-mpc-armv7.zip, dist/Model-72-<ver>-mpc-aarch64.zip   one per CPU, made by mpc-vst-plugins' tools/release.py
#   dist/Model-72-<ver>-mpc-sdk.zip                                            one folder for both (tools/sdk_zip.py, MPC OS 3.10.1+)
# As 1.x, the .so is model72.so at the folder root, so the installer upgrades a 1.x install in place. model72-presets.dat (the user's
# presets) is user data, kept on upgrade. Presets/*.xpl are the factory presets as MPC preset files (tools/presets.py, without QUALITY).
# MPC_VST: an mpc-vst-plugins checkout with tools/release.py, sdk_zip.py and xpl.py.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
MPC_VST="${MPC_VST:-$HOME/mpc-vst-plugins-postlaunch}"
[ -f "$MPC_VST/tools/release.py" ] || { echo "need mpc-vst-plugins with tools/release.py (MPC_VST)" >&2; exit 1; }
DIR="sd88me - VST - Model-72"
SRC="$here/build/sdk/$DIR"
VER=$(python3 -c 'import json;print(json.load(open("'"$here"'/plugin.json"))["version"])')
python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); sys.exit(0 if m["uid"]=="M072" and m["name"]=="Model-72" else "not the release identity: run ./build-sdk.sh")' "$SRC/plugin.json"
out="$here/dist"; mkdir -p "$out"
for pair in armv7:arm32 aarch64:arm64; do
  IFS=: read -r cpu so <<<"$pair"
  [ -f "$SRC/VST/model72-$so.so" ] || { echo "missing $SRC/VST/model72-$so.so: run ./build-sdk.sh" >&2; exit 1; }
  st="$here/build/catalog/$cpu"; rm -rf "$st"; mkdir -p "$st/$DIR/legal"
  cp -r "$SRC/Plugin Skins" "$SRC/version.xml" "$st/$DIR/"
  cp "$here/LICENSE" "$here/THIRD-PARTY-NOTICES.txt" "$here/README.md" "$st/$DIR/legal/"
  cp "$here/skin/assets/URW-LICENSE" "$st/$DIR/legal/"
  MPC_VST_TOOLS="$MPC_VST/tools" python3 "$here/tools/presets.py" xpl "$st/$DIR"
  python3 - "$SRC/plugin.json" "$st/$DIR/plugin.json" "$cpu" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
m.pop("file32", None); m.pop("file64", None)
m["file32" if sys.argv[3] == "armv7" else "file64"] = "model72.so"
json.dump(m, open(sys.argv[2], "w"), indent=2)
PY
  cp "$SRC/VST/model72-$so.so" "$st/model72.so"
  printf '<PLUGIN name="Model-72" descriptiveName="Model-72" format="VST" category="Synth" manufacturer="sd88me" version="%s" file="model72.so" uid="4d303732" isInstrument="1" fileTime="0" infoUpdateTime="0" numInputs="0" numOutputs="2" isShell="0"/>\n' "$VER" > "$st/entry.xml"
  python3 "$MPC_VST/tools/release.py" --so "$st/model72.so" --skin "$st/$DIR" --entry "$st/entry.xml" --version "$VER" \
    --user-data model72-presets.dat --repo sd88me/mpc-vst-model72 --license GPL-3.0-or-later --id model-72 \
    --about "A circuit-modelled 1970s monosynth: CA-72's Minimoog Model D, LO (light) or HI (the circuit's own ladder filter), mono, poly or unison, with its own skin, user presets and Q-Links." \
    -o "$st/dist" >/dev/null
  z=$(ls "$st/dist"/*.zip); cp "$z" "$out/Model-72-$VER-mpc-$cpu.zip"
done
python3 "$MPC_VST/tools/sdk_zip.py" "$out/Model-72-$VER-mpc-sdk.zip" "$out/Model-72-$VER-mpc-armv7.zip" "$out/Model-72-$VER-mpc-aarch64.zip"
ls -la "$out"/Model-72-"$VER"-mpc-*.zip
