#!/usr/bin/env bash
# The CA-72 engine (engine/ca72-mpc, Rust) as static libraries: build/rust/{x86_64,armv7,aarch64}/libca72_mpc.a, in the 1.x build's
# Docker image (engine/Dockerfile: Rust 1.97, armv7 + aarch64 targets).   tools/build_engine.sh [x86_64|armv7|aarch64 ...] (default: all)
set -euo pipefail
cd "$(dirname "$0")/.."
targets=("$@"); [ ${#targets[@]} -eq 0 ] && targets=(x86_64 armv7 aarch64)
docker image inspect mpc-vst-ca72-rust >/dev/null 2>&1 || docker build -q -t mpc-vst-ca72-rust engine >/dev/null
mkdir -p engine/.cargo-home
for t in "${targets[@]}"; do
  case $t in
    x86_64) tt="" ;; armv7) tt=armv7-unknown-linux-gnueabihf ;; aarch64) tt=aarch64-unknown-linux-gnu ;;
    *) echo "unknown target $t" >&2; exit 1 ;;
  esac
  docker run --rm -u "$(id -u):$(id -g)" -e CARGO_HOME=/w/engine/.cargo-home -v "$PWD":/w -w /w/engine mpc-vst-ca72-rust \
    cargo build -q --release -p ca72-mpc ${tt:+--target $tt}
  mkdir -p build/rust/$t
  cp engine/target/${tt:+$tt/}release/libca72_mpc.a build/rust/$t/
done
