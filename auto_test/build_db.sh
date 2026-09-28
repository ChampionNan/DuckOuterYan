#!/usr/bin/env bash
# ============================================================================
# build_db.sh — Build all databases used by the OuterYan test suite.
#
# USAGE:
#   bash auto_test/build_db.sh [target...]
#   Targets: graph | tpch | tpcds | job | all  (default: all)
#
# Databases:
#   graph_db   — R1..R10 tables from SNAP graph data (default: epinions)
#   tpch_db    — TPC-H via CALL dbgen(sf=N)
#   tpcds_db   — TPC-DS via CALL dsdgen(sf=N)
#   job_db     — IMDb/JOB (21 parquet files from duckdb-data release)
#
# Environment (all optional):
#   DUCKDB_BIN       Path to duckdb binary (default build/release/duckdb)
#   GRAPH_DATASET    SNAP graph to use for graph R1..R10 (default epinions)
#                    Options: bitcoin | epinions | google | wiki | dblp
#   TPCH_SF          TPC-H scale factor (default 100)
#   TPCDS_SF         TPC-DS scale factor (default 50)
#   GRAPH_DATA_DIR   SNAP graph download dir (default $REPO/graph_data)
#   FORCE=1          Rebuild even if DB already exists
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/configs.sh"
REPO_ROOT="$OY_REPO_ROOT"

# --- defaults ---------------------------------------------------------------
GRAPH_DATASET="${GRAPH_DATASET:-bitcoin}"
TPCH_SF="${TPCH_SF:-100}"
TPCDS_SF="${TPCDS_SF:-50}"
GRAPH_DATA_DIR="${GRAPH_DATA_DIR:-$REPO_ROOT/graph_data}"

# Parse targets
TARGETS=()
if [ $# -eq 0 ]; then TARGETS=(all); else TARGETS=("$@"); fi
want() { local t; for t in "${TARGETS[@]}"; do [[ "$t" == "$1" || "$t" == "all" ]] && return 0; done; return 1; }

[ -x "$DUCKDB_BIN" ] || { echo "ERROR: DUCKDB_BIN=$DUCKDB_BIN not executable. Build first." >&2; exit 2; }

# --- helper: download a single SNAP graph if not cached ----------------------
_download_snap_graph() {
    local name="$1" dir="$2"
    mkdir -p "$dir"
    [ -s "$dir/${name}.txt" ] && return 0
    echo "  [get ] $name"
    case "$name" in
        bitcoin)
            curl -fSL --retry 5 -o "$dir/soc-sign-bitcoinalpha.csv.gz" \
                "https://snap.stanford.edu/data/soc-sign-bitcoinalpha.csv.gz" 2>/dev/null
            gzip -df "$dir/soc-sign-bitcoinalpha.csv.gz"
            mv "$dir/soc-sign-bitcoinalpha.csv" "$dir/bitcoin.txt";;
        epinions)
            curl -fSL --retry 5 -o "$dir/soc-Epinions1.txt.gz" \
                "https://snap.stanford.edu/data/soc-Epinions1.txt.gz" 2>/dev/null
            gzip -df "$dir/soc-Epinions1.txt.gz"
            tail -n +5 "$dir/soc-Epinions1.txt" > "$dir/epinions.txt"
            rm -f "$dir/soc-Epinions1.txt";;
        google)
            curl -fSL --retry 5 -o "$dir/web-Google.txt.gz" \
                "https://snap.stanford.edu/data/web-Google.txt.gz" 2>/dev/null
            gzip -df "$dir/web-Google.txt.gz"
            tail -n +5 "$dir/web-Google.txt" > "$dir/google.txt"
            rm -f "$dir/web-Google.txt";;
        wiki)
            curl -fSL --retry 5 -o "$dir/wiki-topcats.txt.gz" \
                "https://snap.stanford.edu/data/wiki-topcats.txt.gz" 2>/dev/null
            gzip -df "$dir/wiki-topcats.txt.gz"
            mv "$dir/wiki-topcats.txt" "$dir/wiki.txt";;
        dblp)
            curl -fSL --retry 5 -o "$dir/com-dblp.ungraph.txt.gz" \
                "https://snap.stanford.edu/data/bigdata/communities/com-dblp.ungraph.txt.gz" 2>/dev/null
            gzip -df "$dir/com-dblp.ungraph.txt.gz"
            tail -n +5 "$dir/com-dblp.ungraph.txt" > "$dir/dblp.txt"
            rm -f "$dir/com-dblp.ungraph.txt";;
        *) echo "ERROR: unknown graph '$name'" >&2; return 1;;
    esac
}

# --- helper: read_csv expression for a SNAP graph file -----------------------
_graph_read_expr() {
    local path="$1" name="$2"
    # bitcoin is comma-separated with extra cols; all others are tab-separated 2-col
    if [ "$name" = "bitcoin" ]; then
        echo "SELECT column0::BIGINT AS src, column1::BIGINT AS dst FROM read_csv('$path', header=false, delim=',', columns={'column0':'VARCHAR','column1':'VARCHAR','column2':'VARCHAR','column3':'VARCHAR'})"
    else
        echo "SELECT column0 AS src, column1 AS dst FROM read_csv('$path', header=false, delim=E'\t', columns={'column0':'BIGINT','column1':'BIGINT'})"
    fi
}

# --- helper: add a PRIMARY KEY if the table lacks one ------------------------
# OuterYan's PK-FK semi-join elimination keys off UNIQUE / PRIMARY KEY
# constraints (CheckPKFK in src/optimizer/outer_yan/common/outer_yan_tree.cpp);
# no foreign keys are needed. dbgen / dsdgen emit only NOT NULL and CTAS-from-
# parquet emits nothing, so the elimination never fires without this. We add PKs
# only to PK/build-side (dimension) tables — that is all the elimination looks
# at, and it avoids costly index builds on the large central fact tables.
# Idempotent (skips when a PK already exists) and non-fatal under `set -e`
# (duplicate/NULL keys or a missing table warn instead of aborting the build).
_add_pk() {
    local db="$1" tbl="$2" cols="$3" has
    has=$("$DUCKDB_BIN" "$db" -csv -noheader -c \
        "SELECT count(*) FROM duckdb_constraints() \
         WHERE table_name='$tbl' AND constraint_type='PRIMARY KEY';" 2>/dev/null || echo 0)
    [ "${has:-0}" != "0" ] && return 0
    if "$DUCKDB_BIN" "$db" -c "ALTER TABLE $tbl ADD PRIMARY KEY ($cols);" >/dev/null 2>&1; then
        echo "  [pk  ] $tbl ($cols)"
    else
        echo "  [warn] could not add PK to $tbl ($cols) — duplicate/NULL keys or table absent"
    fi
}

# ============================================================================
# 1. graph_db — R1..R10 from real SNAP graph data
#    All 10 tables use the SAME graph (so R{i}.dst overlaps R{i+1}.src, giving
#    meaningful multi-hop join results).
# ============================================================================
if want graph; then
    GRAPH_DB="${GRAPH_DB:-$REPO_ROOT/graph_db}"
    if [ -f "$GRAPH_DB" ] && [ "${FORCE:-0}" != "1" ]; then
        echo "[graph_db] already exists ($GRAPH_DB). Set FORCE=1 to rebuild."
    else
        echo "[graph_db] Building R1..R10 from SNAP graph: $GRAPH_DATASET ..."
        _download_snap_graph "$GRAPH_DATASET" "$GRAPH_DATA_DIR"
        GRAPH_FILE="$GRAPH_DATA_DIR/${GRAPH_DATASET}.txt"
        [ -s "$GRAPH_FILE" ] || { echo "ERROR: graph file not found: $GRAPH_FILE" >&2; exit 1; }

        READ_EXPR="$(_graph_read_expr "$GRAPH_FILE" "$GRAPH_DATASET")"

        rm -f "$GRAPH_DB" "$GRAPH_DB.wal"
        {
            for i in $(seq 1 10); do
                echo "CREATE TABLE R$i AS ${READ_EXPR};"
            done
            echo "CREATE VIEW R AS SELECT * FROM R1; CREATE VIEW S AS SELECT * FROM R2;"
            echo "CREATE VIEW T AS SELECT * FROM R3; CREATE VIEW K AS SELECT * FROM R4;"
            echo "CHECKPOINT;"
        } | "$DUCKDB_BIN" "$GRAPH_DB" >/dev/null
        NROWS=$("$DUCKDB_BIN" "$GRAPH_DB" -csv -noheader -c "SELECT COUNT(*) FROM R1;" 2>/dev/null)
        echo "[graph_db] done. graph=$GRAPH_DATASET rows/table=$NROWS $(du -h "$GRAPH_DB" | cut -f1)"
    fi
fi

# ============================================================================
# 2. Ensure duckdb binary has required extensions (auto-rebuild if needed)
# ============================================================================
_need_rebuild() {
    local need_flags=""
    # TPC-H extension
    if want tpch; then
        "$DUCKDB_BIN" -c "CALL dbgen(sf=0);" >/dev/null 2>&1 || need_flags="BUILD_TPCH=1"
    fi
    # TPC-DS extension
    if want tpcds; then
        "$DUCKDB_BIN" -c "CALL dsdgen(sf=0);" >/dev/null 2>&1 || need_flags="$need_flags BUILD_TPCDS=1"
    fi
    # httpfs extension
    need_flags="$(echo "$need_flags" | xargs)"  # trim
    if [ -n "$need_flags" ]; then
        echo "[make] duckdb binary missing extension(s), rebuilding with: $need_flags"
        echo "[make] cd $REPO_ROOT && $need_flags make release"
        (cd "$REPO_ROOT" && eval "$need_flags make release") \
            || { echo "ERROR: make release failed" >&2; exit 1; }
        echo "[make] rebuild done."
    fi
}
_need_rebuild

# ============================================================================
# 3. tpch_db — TPC-H via dbgen extension
# ============================================================================
if want tpch; then
    TPCH_DB="${TPCH_DB:-$REPO_ROOT/tpch_db}"
    if [ -f "$TPCH_DB" ] && [ "${FORCE:-0}" != "1" ]; then
        echo "[tpch_db] already exists ($TPCH_DB, sf=$(echo "SELECT count(*) FROM lineitem;" | "$DUCKDB_BIN" "$TPCH_DB" -csv -noheader 2>/dev/null || echo '?') rows lineitem). Set FORCE=1 to rebuild."
    else
        echo "[tpch_db] Building TPC-H SF=$TPCH_SF ..."
        rm -f "$TPCH_DB" "$TPCH_DB.wal"
        "$DUCKDB_BIN" "$TPCH_DB" -c "CALL dbgen(sf=$TPCH_SF); CHECKPOINT;" >/dev/null 2>&1 \
            || { echo "ERROR: dbgen failed (binary not built with BUILD_TPCH=1?)" >&2; rm -f "$TPCH_DB"; exit 1; }
        echo "[tpch_db] done. SF=$TPCH_SF $(du -h "$TPCH_DB" | cut -f1)"
    fi
    # TPC-H primary keys (idempotent). lineitem is intentionally omitted: it is
    # always the central fact / FK-probe side, never a PK build side, so its PK
    # index would add cost with no semi-join-elimination benefit.
    echo "[tpch_db] ensuring primary keys ..."
    _add_pk "$TPCH_DB" region   "r_regionkey"
    _add_pk "$TPCH_DB" nation   "n_nationkey"
    _add_pk "$TPCH_DB" part     "p_partkey"
    _add_pk "$TPCH_DB" supplier "s_suppkey"
    _add_pk "$TPCH_DB" partsupp "ps_partkey, ps_suppkey"
    _add_pk "$TPCH_DB" customer "c_custkey"
    _add_pk "$TPCH_DB" orders   "o_orderkey"
fi

# ============================================================================
# 4. tpcds_db — TPC-DS via dsdgen extension
# ============================================================================
if want tpcds; then
    TPCDS_DB="${TPCDS_DB:-$REPO_ROOT/tpcds_db}"
    if [ -f "$TPCDS_DB" ] && [ "${FORCE:-0}" != "1" ]; then
        echo "[tpcds_db] already exists ($TPCDS_DB). Set FORCE=1 to rebuild."
    else
        echo "[tpcds_db] Building TPC-DS SF=$TPCDS_SF ..."
        rm -f "$TPCDS_DB" "$TPCDS_DB.wal"
        "$DUCKDB_BIN" "$TPCDS_DB" -c "CALL dsdgen(sf=$TPCDS_SF); CHECKPOINT;" >/dev/null 2>&1 \
            || { echo "ERROR: dsdgen failed (binary not built with BUILD_TPCDS=1?)" >&2; rm -f "$TPCDS_DB"; exit 1; }
        echo "[tpcds_db] done. SF=$TPCDS_SF $(du -h "$TPCDS_DB" | cut -f1)"
    fi
    # TPC-DS dimension primary keys (single-column surrogate keys; idempotent).
    # Fact tables are intentionally skipped: they are the FK/probe side and their
    # surrogate-key columns are nullable, so a composite PK would fail anyway.
    echo "[tpcds_db] ensuring primary keys ..."
    _add_pk "$TPCDS_DB" call_center            "cc_call_center_sk"
    _add_pk "$TPCDS_DB" catalog_page           "cp_catalog_page_sk"
    _add_pk "$TPCDS_DB" customer               "c_customer_sk"
    _add_pk "$TPCDS_DB" customer_address       "ca_address_sk"
    _add_pk "$TPCDS_DB" customer_demographics  "cd_demo_sk"
    _add_pk "$TPCDS_DB" date_dim               "d_date_sk"
    _add_pk "$TPCDS_DB" household_demographics  "hd_demo_sk"
    _add_pk "$TPCDS_DB" income_band            "ib_income_band_sk"
    _add_pk "$TPCDS_DB" item                   "i_item_sk"
    _add_pk "$TPCDS_DB" promotion              "p_promo_sk"
    _add_pk "$TPCDS_DB" reason                 "r_reason_sk"
    _add_pk "$TPCDS_DB" ship_mode              "sm_ship_mode_sk"
    _add_pk "$TPCDS_DB" store                  "s_store_sk"
    _add_pk "$TPCDS_DB" time_dim               "t_time_sk"
    _add_pk "$TPCDS_DB" warehouse              "w_warehouse_sk"
    _add_pk "$TPCDS_DB" web_page               "wp_web_page_sk"
    _add_pk "$TPCDS_DB" web_site               "web_site_sk"
fi

# ============================================================================
# 5. job_db — IMDb (download parquet locally, then load into DuckDB)
# ============================================================================
if want job; then
    JOB_DB="${JOB_DB:-$REPO_ROOT/job_db}"
    JOB_DATA_DIR="${JOB_DATA_DIR:-$REPO_ROOT/job_data}"
    JOB_TABLES="aka_name aka_title cast_info char_name comp_cast_type company_name company_type complete_cast info_type keyword kind_type link_type movie_companies movie_info movie_info_idx movie_keyword movie_link name person_info role_type title"

    if [ -e "$JOB_DB" ] && [ "${FORCE:-0}" != "1" ]; then
        echo "[job_db] already exists ($JOB_DB). Set FORCE=1 to rebuild."
    else
        echo "[job_db] Downloading IMDb parquet files ..."
        mkdir -p "$JOB_DATA_DIR"
        for tbl in $JOB_TABLES; do
            local_file="$JOB_DATA_DIR/job_${tbl}.parquet"
            if [ ! -f "$local_file" ]; then
                curl -sL --retry 3 -o "$local_file" \
                    "https://github.com/duckdb/duckdb-data/releases/download/v1.0/job_${tbl}.parquet" \
                    || { echo "ERROR: failed to download job_${tbl}.parquet" >&2; exit 1; }
            fi
        done
        echo "[job_db] Loading parquet into DuckDB ..."
        rm -f "$JOB_DB" "$JOB_DB.wal"
        SQL=""
        for tbl in $JOB_TABLES; do
            SQL="${SQL}CREATE TABLE ${tbl} AS SELECT * FROM read_parquet('${JOB_DATA_DIR}/job_${tbl}.parquet');"
        done
        SQL="${SQL}CHECKPOINT;"
        "$DUCKDB_BIN" "$JOB_DB" -c "$SQL"
        echo "[job_db] done. $(du -h "$JOB_DB" | cut -f1)"
    fi
    # JOB/IMDb primary keys: every table's surrogate `id` column is its PK
    # (idempotent). These are the dimension/build sides for JOB join graphs.
    echo "[job_db] ensuring primary keys ..."
    for tbl in $JOB_TABLES; do
        _add_pk "$JOB_DB" "$tbl" "id"
    done
fi
