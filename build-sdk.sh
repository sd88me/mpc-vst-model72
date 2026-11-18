#!/usr/bin/env bash
# Build Model-72 on the MPC Plugin SDK front end (src/Model72Plugin.cpp) into build/sdk/"sd88me - VST - <name>"/: arm32 (Force, MPC Live /
# One / X; glibc 2.29 at most) and arm64 (Live III). The CA-72 engine is Rust (engine/ca72-mpc), built as a static library in Docker
# (tools/build_engine.sh); the SDK's build.py only compiles src/*.cpp, so the front end is compiled and linked here with the SDK's zig and
# the same flags, the engine archive added. arm32 links against glibc 2.29 (not the SDK's 2.31): Rust's std wants gettid@GLIBC_2.30.
#   ./build-sdk.sh          gen params, engine, both targets, the folder (plugin.json, version.xml, Plugin Skins)
#   ./build-sdk.sh beta     the same as "Model-72 2 Beta" (uid M72B): installs next to the release
#   ./build-sdk.sh test     the offline test (tests/run.sh, ASan/UBSan) and the SDK's host_sim
# MPC_SDK: the plugin builder checkout. ZIG: zig 0.14.
set -euo pipefail
cd "$(dirname "$0")"
SDK="${MPC_SDK:-$HOME/mpc-plugin-builder-sdk}"
ZIG="${ZIG:-$(command -v zig || echo "$HOME/.local/zig/zig-x86_64-linux-0.14.1/zig")}"
[ -f "$SDK/framework/mpc_plugin.h" ] || { echo "need the plugin builder (MPC_SDK, now $SDK)" >&2; exit 1; }
NAME="Model-72"; UID_="'M','0','7','2'"; UIDS=M072; SLUG=model72
if [ "${1:-}" = beta ]; then NAME="Model-72 2 Beta"; UID_="'M','7','2','B'"; UIDS=M72B; SLUG=model72beta; fi
python3 tools/gen_sdk_params.py
FLAGS=(-std=c++17 -fPIC -shared -fvisibility=hidden -fvisibility-inlines-hidden -ffunction-sections -fdata-sections -Wall -Wextra -O2
       -I"$SDK/framework" -Isrc -Wl,--gc-sections -Wl,-s -Wl,--version-script="$SDK/tools/exports.map")

if [ "${1:-}" = test ]; then
  tests/run.sh
  mkdir -p build/sdk-native
  "$ZIG" c++ "${FLAGS[@]}" -target x86_64-linux-gnu.2.31 -o build/sdk-native/model72.so src/Model72Plugin.cpp build/rust/x86_64/libca72_mpc.a
  docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/b -v "$SDK":/sdk:ro -w /b ubuntu:24.04 sh -c \
    'cp plugin.json build/sdk-native/; /sdk/.sdk-tools/host_sim build/sdk-native/model72.so dump > build/sdk-native/params.json && /sdk/.sdk-tools/host_sim build/sdk-native/model72.so test --notes 48,55 | tail -n 15'
  exit
fi

tools/build_engine.sh armv7 aarch64
FOLDER="build/sdk/sd88me - VST - $NAME"
rm -rf "$FOLDER"; mkdir -p "$FOLDER/VST" "$FOLDER/Plugin Skins"
DEFS=(-DM72_NAME="\"$NAME\"" -DM72_UID="$UID_")
"$ZIG" c++ "${FLAGS[@]}" "${DEFS[@]}" -target arm-linux-gnueabihf.2.29 -mcpu=cortex_a17 -o "$FOLDER/VST/$SLUG-arm32.so" src/Model72Plugin.cpp build/rust/armv7/libca72_mpc.a &
"$ZIG" c++ "${FLAGS[@]}" "${DEFS[@]}" -target aarch64-linux-gnu.2.31 -mcpu=cortex_a55 -o "$FOLDER/VST/$SLUG-arm64.so" src/Model72Plugin.cpp build/rust/aarch64/libca72_mpc.a &
wait %1 && wait %2
for so in "$FOLDER"/VST/*.so; do   # the Force has glibc 2.29: refuse anything newer; only the entry point may be exported
  newest=$(readelf -V "$so" | grep -o 'GLIBC_[0-9.]*' | sort -V | tail -1)
  exports=$(readelf --dyn-syms -W "$so" | awk '$5=="GLOBAL" && $7!="UND" {print $8}' | tr '\n' ' ')
  echo "$(basename "$so"): newest $newest, exports: $exports"
  case "$so" in *arm32.so) [ "$(printf '%s\n' "$newest" GLIBC_2.29 | sort -V | tail -1)" = GLIBC_2.29 ] || { echo "arm32 needs $newest (> 2.29)" >&2; exit 1; } ;; esac
done
python3 - "$NAME" "$SLUG" "$UIDS" "$FOLDER" <<'PY'
import json, sys
name, slug, uid, folder = sys.argv[1:]
m = json.load(open("plugin.json"))
m.update(name=name, uid=uid, file32="VST/%s-arm32.so" % slug, file64="VST/%s-arm64.so" % slug)
json.dump(m, open(folder + "/plugin.json", "w"), indent=2)
open(folder + "/version.xml", "w").write('<?xml version="1.0" encoding="utf-8"?>\n<plugincontent version="1.0">\n    <version>%s.0</version>\n    <uiversion>0.1.0.0</uiversion>\n</plugincontent>\n' % m["version"])
PY
# Phase 1: the SDK's generated default skin. Phase 2 replaces it with skins/ from tools/make_tui.py.
if [ -f tools/make_tui.py ]; then python3 tools/make_tui.py; fi
if [ -d skins ]; then cp -r skins/. "$FOLDER/Plugin Skins/"
else
  [ -f build/sdk-native/params.json ] || { echo "run ./build-sdk.sh test first (params dump for the default skin)" >&2; exit 1; }
  python3 "$SDK/tools/gen_ui.py" --params build/sdk-native/params.json --out "$FOLDER/Plugin Skins" >/dev/null
fi
cp LICENSE THIRD-PARTY-NOTICES.txt "$FOLDER/"
python3 "$SDK/tools/validate.py" "$FOLDER" || true
echo "built: $FOLDER"
