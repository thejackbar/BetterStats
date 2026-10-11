#!/usr/bin/env bash
# Installs FaceFusion (open source, CPU-capable) into $FACE_SWAP_HOME.
# Idempotent: safe to re-run. Needs git, ffmpeg and network access to
# github.com, huggingface.co and pypi.org. No GPU, API key or account needed.
set -euo pipefail

FACE_SWAP_HOME="${FACE_SWAP_HOME:-$HOME/tools}"
FACEFUSION_REF="${FACEFUSION_REF:-3.9.1}"   # tested release tag
REPO_DIR="$FACE_SWAP_HOME/facefusion"
VENV_DIR="$FACE_SWAP_HOME/ff-venv"
PY="$VENV_DIR/bin/python"

command -v git >/dev/null    || { echo "git is required" >&2; exit 1; }
command -v ffmpeg >/dev/null || { echo "ffmpeg is required (apt-get install -y ffmpeg)" >&2; exit 1; }

mkdir -p "$FACE_SWAP_HOME"

# 1. Source
if [ ! -d "$REPO_DIR/.git" ]; then
  git clone https://github.com/facefusion/facefusion.git "$REPO_DIR"
fi
git -C "$REPO_DIR" fetch --tags --quiet || true
git -C "$REPO_DIR" checkout --quiet "$FACEFUSION_REF"

# 2. Python venv. FaceFusion pins numpy/onnxruntime wheels that are safest on 3.10-3.12.
if [ ! -x "$PY" ]; then
  PYBIN=""
  for c in python3.12 python3.11 python3.10; do
    if command -v "$c" >/dev/null; then PYBIN="$(command -v "$c")"; break; fi
  done
  if command -v uv >/dev/null; then
    uv venv --python "${PYBIN:-3.12}" "$VENV_DIR"
  elif [ -n "$PYBIN" ]; then
    "$PYBIN" -m venv "$VENV_DIR"
  else
    echo "Need Python 3.10-3.12 (or uv) to build the venv" >&2; exit 1
  fi
fi

# 3. Dependencies (versions are pinned in FaceFusion's requirements.txt)
if command -v uv >/dev/null; then
  uv pip install --python "$PY" -r "$REPO_DIR/requirements.txt"
else
  "$PY" -m pip install -r "$REPO_DIR/requirements.txt"
fi

# 4. Sanity check that the install imports and runs.
(cd "$REPO_DIR" && "$PY" facefusion.py headless-run --help >/dev/null)

# Models are NOT downloaded here. FaceFusion fetches only the ones a job needs on the
# first real run and caches them in $REPO_DIR/.assets (so the first run is slower).
# `force-download` is deliberately not used: it pulls every processor's models.
echo "FaceFusion $FACEFUSION_REF ready in $REPO_DIR"
