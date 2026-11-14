#!/usr/bin/env bash
set -euo pipefail
RUSTC_BIN="$HOME/.cargo/bin/rustc"
if [ -x "$RUSTC_BIN" ] && [ "$("$RUSTC_BIN" --version | awk '{print $2}')" = "1.100.0" ]; then
    echo "rust 1.100.0 already present at $RUSTC_BIN"; exit 0
fi
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
  | sh -s -- -y --default-toolchain 1.100.0 --profile minimal
"$HOME/.cargo/bin/rustup" component add rustfmt clippy
"$HOME/.cargo/bin/rustc" --version
