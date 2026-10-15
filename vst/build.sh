#!/usr/bin/env bash
# Build the CA-72 MPC plugin: the Rust engine (static libraries for the device and for the x86 host test),
# then the plugin, skin and plugin-list entry through mpc-vst-plugins' tools/build_port.sh.
#   MPC_VST=/path/to/mpc-vst-plugins vst/build.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
MPC_VST="${MPC_VST:-$REPO/../mpc-vst-plugins}"
python3 "$REPO/tools/gen_params_rs.py"
docker build -q -t mpc-vst-ca72-rust "$REPO/engine" >/dev/null
mkdir -p "$HERE/build/rust/armv7" "$HERE/build/rust/aarch64" "$HERE/build/rust/x86_64" "$REPO/engine/.cargo-home"
docker run --rm -u "$(id -u):$(id -g)" -e CARGO_HOME=/w/engine/.cargo-home -v "$REPO":/w -w /w/engine mpc-vst-ca72-rust sh -euc '
  cargo build -q --release -p ca72-mpc --target armv7-unknown-linux-gnueabihf
  cargo build -q --release -p ca72-mpc --target aarch64-unknown-linux-gnu
  cargo build -q --release -p ca72-mpc
  cp target/armv7-unknown-linux-gnueabihf/release/libca72_mpc.a /w/vst/build/rust/armv7/
  cp target/aarch64-unknown-linux-gnu/release/libca72_mpc.a /w/vst/build/rust/aarch64/
  cp target/release/libca72_mpc.a /w/vst/build/rust/x86_64/'
"$MPC_VST/tools/build_port.sh" "$HERE/vst.json" "${1:-all}"
