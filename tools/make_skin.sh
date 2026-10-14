#!/usr/bin/env bash
# Draw the skin art (vst/art, vst/layout.conf, vst/preview) with skin/make_skin.py in a Pillow container.
set -euo pipefail
cd "$(dirname "$0")/.."
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/w -w /w python:3.11-slim sh -c '
  pip install -q --target /tmp/p pillow >/dev/null 2>&1
  PYTHONPATH=/tmp/p:/w/skin python3 -c "import make_skin; make_skin.build(\"vst\")"'
