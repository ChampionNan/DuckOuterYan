#!/usr/bin/env bash
# Isolated retest: only the 16 pinned short Graph queries use Epinions.
# The normal benchmark and its Bitcoin graph_db are not rebuilt or modified.
# Usage: bash auto_test/run_graph_dataset_retest.sh --prepare-only
#        bash auto_test/run_graph_dataset_retest.sh --run
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/configs.sh"
case "${1:---prepare-only}" in
    --prepare-only|--run) MODE="${1:---prepare-only}";;
    *) echo "Usage: bash auto_test/run_graph_dataset_retest.sh [--prepare-only|--run]" >&2; exit 2;;
esac
[ "$#" -le 1 ] || { echo "Unexpected arguments" >&2; exit 2; }
EPINIONS_DB="${GRAPH_EPINIONS_DB:-$OY_REPO_ROOT/graph_epinions.duckdb}"
CORPUS="$SCRIPT_DIR/outerjoin_benchmark/graph_dataset_retest/epinions"
"$PYTHON_BIN" - "$EPINIONS_DB" "$GRAPH_DB" "$OY_REPO_ROOT/graph_db" <<'PY'
from pathlib import Path
import sys
target = Path(sys.argv[1]).resolve()
if any(target == Path(value).resolve() for value in sys.argv[2:]):
    sys.exit('GRAPH_EPINIONS_DB must not point at the Bitcoin database')
PY
# Do not let inherited FORCE/OY_FORCE_GRAPH_REBUILD replace either database.
GRAPH_DB="$EPINIONS_DB" GRAPH_DATASET=epinions FORCE=0 bash "$SCRIPT_DIR/build_db.sh" graph
"$PYTHON_BIN" "$SCRIPT_DIR/prepare_graph_dataset_retest.py" \
    --duckdb "$DUCKDB_BIN" --database "$EPINIONS_DB" --output "$CORPUS"
if [ "$MODE" = --prepare-only ]; then
    echo "Prepared only. Start the 16-query CPU9 retest with: bash auto_test/run_graph_dataset_retest.sh --run"
    exit 0
fi
RUN_TS="$(date '+%Y%m%d_%H%M%S')"
OUT="$SCRIPT_DIR/results/experiment_onoff_graph_epinions_${RUN_TS}_t32.txt"
export GRAPH_DB="$EPINIONS_DB" GRAPH_DATASET=epinions OY_CORPUS="$CORPUS"
export OY_FORCE_GRAPH_REBUILD=0
bash "$SCRIPT_DIR/experiment_onoff.sh" --only all --query-list "$CORPUS/query_list.txt" \
    --threads 32 --runs 5 --timeout 600 --profile --no-check-correctness --capture-plans --out "$OUT"
