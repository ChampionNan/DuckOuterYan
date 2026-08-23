#!/usr/bin/env bash
# Historical implementation entry point; user-facing commands live in pgplan/.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
exec "$PYTHON_BIN" "$SCRIPT_DIR/prepare_correctness_db.py" "$@"
