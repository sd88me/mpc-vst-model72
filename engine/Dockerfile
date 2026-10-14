# The engine's build image: Rust 1.97 with the armv7 (MPC Gen1 / Force) target and rustfmt.
FROM rust:1.97-bookworm
RUN rustup target add armv7-unknown-linux-gnueabihf && rustup component add rustfmt \
 && apt-get update -qq && apt-get install -y -qq gcc-arm-linux-gnueabihf >/dev/null \
 && rm -rf /var/lib/apt/lists/*
ENV CARGO_TARGET_ARMV7_UNKNOWN_LINUX_GNUEABIHF_LINKER=arm-linux-gnueabihf-gcc
