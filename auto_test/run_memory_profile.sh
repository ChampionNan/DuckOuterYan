#!/usr/bin/env bash
# CPU9 SF50 memory experiment, separate from the five-run runtime experiment.
set -euo pipefail
case "${1:---help}" in
    --run) ;;
    --help|-h)
        echo 'Usage: bash auto_test/run_memory_profile.sh --run'
        echo '281 pinned queries; both engines; 32 threads; 1 warmup + 1 profile; 600s EACH execution.'
        echo 'Requires an already compiled Release binary with operator memory observations.'
        exit 0;;
    *) echo 'Expected --run or --help' >&2; exit 2;;
esac
[ "$#" -le 1 ] || { echo 'Unexpected arguments' >&2; exit 2; }
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"
PYTHON_BIN="${PYTHON_BIN:-python3}"
RUN_TS="$(date '+%Y%m%d_%H%M%S')"
OUT="$SCRIPT_DIR/results/memory_benchmark_${RUN_TS}_t32"
mkdir -p "$SCRIPT_DIR/results"
exec > >(tee "${OUT}.run.log") 2>&1
echo "Memory run: $OUT"
echo 'Both engines; correctness disabled; exactly one warmup + one profiled execution.'
echo '600 seconds per execution per engine. No five-run timings are replaced.'
"$PYTHON_BIN" "$SCRIPT_DIR/memory_profile.py" run --out "$OUT" --threads 32 --timeout 600
