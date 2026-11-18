#!/usr/bin/env bash
# Offline x86 test under ASan/UBSan (no device): the native front end + the real CA-72 engine, driven by tests/host_test.cpp. Must print OK.
# M72_NAME / M72_UID_HEX: the build's name and uid (beta tests).
set -euo pipefail
cd "$(dirname "$0")/.."
SDK="${MPC_SDK:-$HOME/mpc-plugin-builder-sdk}"
python3 tools/gen_sdk_params.py >/dev/null
[ -f build/rust/x86_64/libca72_mpc.a ] || tools/build_engine.sh x86_64
T=build/test; mkdir -p "$T"
UIDDEF=()
[ -n "${M72_UID_HEX:-}" ] && UIDDEF=(-DM72_UID="$(echo "$M72_UID_HEX" | sed -E "s/(..)(..)(..)(..)/0x\1,0x\2,0x\3,0x\4/")")
S="-fsanitize=address,undefined -fno-sanitize-recover=undefined -O1 -g -std=c++17 -pthread"
g++ $S -Wall -Wextra -DM72_TEST -DM72_EXPECT_NAME="\"${M72_NAME:-Model-72}\"" -DM72_EXPECT_UID="0x${M72_UID_HEX:-4d303732}" ${M72_NAME:+-DM72_NAME="\"$M72_NAME\""} "${UIDDEF[@]}" \
  -I"$SDK/framework" -Isrc -o "$T/m72test" src/Model72Plugin.cpp tests/host_test.cpp build/rust/x86_64/libca72_mpc.a -ldl -lm
pf="$(mktemp -d)"; trap 'rm -rf "$pf"' EXIT
cp plugin.json "$pf/"
MPC_PLUGIN_FOLDER="$pf" ASAN_OPTIONS=detect_leaks=1 "$T/m72test" tests/fixtures
