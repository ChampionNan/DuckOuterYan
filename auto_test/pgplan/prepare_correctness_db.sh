#!/usr/bin/env bash
# Canonical PGPlan entry point. The implementation path is retained so older
# automation can share the same dependency-free builder.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/../postgres_replay/prepare_correctness_db.sh" "$@"
