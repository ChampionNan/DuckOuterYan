#!/usr/bin/env bash
# Source only when --bootstrap is requested. No sudo or system Python changes.
set -euo pipefail
OY_ENV_ROOT="$SCRIPT_DIR/results/environment"
OY_UV_VERSION=0.8.22
OY_PYTHON_VERSION=3.11.13
mkdir -p "$OY_ENV_ROOT"
case "$(uname -s)-$(uname -m)" in
    Linux-x86_64) OY_UV_PLATFORM=x86_64-unknown-linux-gnu;;
    Linux-aarch64) OY_UV_PLATFORM=aarch64-unknown-linux-gnu;;
    Darwin-arm64) OY_UV_PLATFORM=aarch64-apple-darwin;;
    Darwin-x86_64) OY_UV_PLATFORM=x86_64-apple-darwin;;
    *) err "Unsupported bootstrap platform; set PYTHON_BIN to Python 3.10+ instead";;
esac
OY_UV_DIR="$OY_ENV_ROOT/uv-$OY_UV_VERSION"
if [ ! -x "$OY_UV_DIR/uv" ]; then
    (
        scratch=$(mktemp -d "$OY_ENV_ROOT/download.XXXXXX")
        trap 'rm -f "$scratch/archive.tar.gz" "$scratch/checksum"; rmdir "$scratch" 2>/dev/null || true' EXIT
        base="https://github.com/astral-sh/uv/releases/download/$OY_UV_VERSION/uv-$OY_UV_PLATFORM.tar.gz"
        curl --fail --location --retry 5 --connect-timeout 30 "$base" -o "$scratch/archive.tar.gz"
        curl --fail --location --retry 5 --connect-timeout 30 "$base.sha256" -o "$scratch/checksum"
        expected=$(awk '{print $1}' "$scratch/checksum")
        if command -v sha256sum >/dev/null; then
            actual=$(sha256sum "$scratch/archive.tar.gz" | awk '{print $1}')
        else
            actual=$(LC_ALL=C shasum -a 256 "$scratch/archive.tar.gz" | awk '{print $1}')
        fi
        [[ "$expected" =~ ^[0-9a-f]{64}$ ]] && [ "$actual" = "$expected" ] || exit 1
        mkdir -p "$OY_UV_DIR"
        tar -xzf "$scratch/archive.tar.gz" --strip-components=1 -C "$OY_UV_DIR" "uv-$OY_UV_PLATFORM/uv"
    ) || err "Verified uv download failed"
fi
export UV_PYTHON_INSTALL_DIR="$OY_ENV_ROOT/python"
export UV_CACHE_DIR="$OY_ENV_ROOT/cache"
"$OY_UV_DIR/uv" python install "$OY_PYTHON_VERSION"
if [ ! -x "$OY_ENV_ROOT/venv/bin/python" ]; then
    "$OY_UV_DIR/uv" venv --python "$OY_PYTHON_VERSION" "$OY_ENV_ROOT/venv"
fi
export PYTHON_BIN="$OY_ENV_ROOT/venv/bin/python"
"$PYTHON_BIN" -c 'import sys; assert sys.version_info[:3] == (3, 11, 13)'
"$OY_UV_DIR/uv" pip sync --python "$PYTHON_BIN" "$SCRIPT_DIR/reproduction_requirements.txt"
export PATH="$OY_ENV_ROOT/venv/bin:$PATH"
