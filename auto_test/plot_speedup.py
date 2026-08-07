#!/usr/bin/env python3
"""
plot_speedup.py  --  Visualise OuterYan ON/OFF speed-up results.

Reads one or more `experiment_onoff_*.csv` files (the output of
auto_test/experiment_onoff.sh) and renders a set of comparison figures:

  * box_*        : T1 & TM speed-up distributions grouped by kernel / reorder /
                   family / topology
  * relations    : T1 & TM speed-up by relation count across every family
  * phase_breakdown_* : per-query native R1 / R2 / R3 / Other profile breakdown
  * sparsity     : TM speed-up vs sparsity (s01..s95) for the graph corpus
  * ratio        : median TM/T1  (multi-thread amplifies >1 / penalises <1)
  * winloss      : win / no-op / regress counts per kernel & family
  * geomean      : geomean T1 & TM speed-up per kernel & family
  * top_bottom   : best / worst queries by TM speed-up
  * machine_cmp  : per-query TM speed-up across runs (when >1 csv is given)
  * dashboard    : the six most useful panels on one page

Output layout: with a single CSV the figures land directly in the output dir.
With several CSVs each source file gets its OWN subfolder `<outdir>/<run>/...`
(run = the part of the filename after `experiment_onoff_`), and one shared
`<outdir>/machine_cmp.png` compares them.

Speed-up = time(OFF) / time(ON):  >1 means OuterYan ON is FASTER.

With no arguments it uses the editable DEFAULT_INPUTS / DEFAULT_OUTDIR constants
near the top of this file (set DEFAULT_INPUTS = [] to instead auto-glob
auto_test/results/). CLI arguments always override those defaults.

Usage
-----
    python3 plot_speedup.py                         # uses DEFAULT_INPUTS -> DEFAULT_OUTDIR
    python3 plot_speedup.py a.csv b.csv             # explicit files (override defaults)
    python3 plot_speedup.py *.csv -o my_plots       # custom output dir
    python3 plot_speedup.py --format png --dpi 300  # raster instead of pdf

Only matplotlib + pandas + numpy are required.
"""
import argparse, glob, os, re, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")                 # headless / no display needed
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

# ----------------------------------------------------------------------------- style
C_T1, C_TM = "#4C72B0", "#DD8452"                       # single / multi thread
KERNEL_ORDER = ["bitmap", "mixed", "hash", "none"]
KERNEL_COLOR = {"bitmap": "#55A868", "mixed": "#C44E52",
                "hash": "#8172B3", "none": "#999999"}
FAMILY_ORDER = ["graph", "TPC-H", "TPC-DS", "JOB"]
PHASES = [
    ("R1 semi-join", "profile_round1_operator_s", "profile_round1_ratio", "#4C72B0"),
    ("R2 semi-join", "profile_round2_operator_s", "profile_round2_ratio", "#55A868"),
    ("R3 real join", "profile_round3_operator_s", "profile_round3_ratio", "#DD8452"),
    ("Other", "profile_other_elapsed_s", "profile_other_ratio", "#B0B0B0"),
]

# =============================== EDIT ME : defaults ==================================
# Used when you run `python3 plot_speedup.py` with NO command-line arguments.
# Entries may be exact files OR glob patterns, may use '~', and RELATIVE paths are
# resolved against this script's directory (auto_test/). Comment a line with '#'.
DEFAULT_INPUTS = [
    "results/experiment_onoff_*.csv",       # all runs under auto_test/results/
    # "~/Desktop/experiment_onoff_20260622_081932.csv",   # or point somewhere else
]
# Output directory (relative -> under auto_test/). Used when you don't pass -o/--outdir.
DEFAULT_OUTDIR = "results/plots"            # -> auto_test/results/plots/
# Tip: set DEFAULT_INPUTS = [] to auto-glob auto_test/results/ then the cwd.
# ====================================================================================

# Output format / quality (override with --format / --dpi). PDF is vector = sharpest.
OUT_FORMATS = ["pdf"]
OUT_DPI = 1200


def gmean(x):
    """Geometric mean over finite, strictly-positive values."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x) & (x > 0)]
    return float(np.exp(np.mean(np.log(x)))) if x.size else np.nan


def fmt(x):
    return f"{x:5.2f}" if np.isfinite(x) else "   - "


# ----------------------------------------------------------------------------- load
def enrich(df, run):
    df = df.copy()
    df["run"] = run
    numeric_columns = [
        "t1_off", "t1_on", "t1_speedup", "tm_off", "tm_on", "tm_speedup", "rows",
        "profile_total_time_s",
        *(seconds for _, seconds, _, _ in PHASES),
        *(ratio for _, _, ratio, _ in PHASES),
    ]
    for c in numeric_columns:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # kernel type (prefer the bNhM detail; fall back to the kernel column)
    def parse_detail(d):
        if isinstance(d, str):
            m = re.match(r"b(\d+)h(\d+)", d)
            if m:
                return int(m.group(1)), int(m.group(2))
        return np.nan, np.nan
    nb, nh = zip(*df.get("kernel_detail", pd.Series([np.nan] * len(df))).map(parse_detail))
    df["nb"], df["nh"] = nb, nh

    def ktype(r):
        declared = str(r.get("kernel", "")).strip()
        if declared == "not-run":
            return "not-run"
        b, h = r["nb"], r["nh"]
        if pd.notna(b):
            if b > 0 and h > 0: return "mixed"
            if b > 0:           return "bitmap"
            if h > 0:           return "hash"
            return "none"
        return "none" if declared in ("-", "", "nan") else declared
    df["kernel_type"] = df.apply(ktype, axis=1)

    def family(q):
        if q.startswith("oy_th"): return "TPC-H"
        if q.startswith("oy_ds"): return "TPC-DS"
        if q.startswith("oy_jb"): return "JOB"
        return "graph"
    df["family"] = df["query"].map(family)

    def topology(q):
        if "_real_" in q:
            return "real"
        core = re.sub(r"^oy_(th|ds|jb)_(th|ds|jb|real)_", "", q)
        m = re.match(r"([A-Za-z]+)", core)
        return m.group(1).lower() if m else "other"
    df["topology"] = df["query"].map(topology)
    df["right_deep"] = df["query"].str.contains("_rd_")

    def grab(pat, q, conv=str):
        m = re.search(pat, q)
        return conv(m.group(1)) if m else None

    def relation_count_from_name(q):
        """Best-effort fallback for CSVs written before relation_count existed."""
        for pat in (r"(?:^|_)N(\d+)(?=_|$)",
                    r"(?:^|_)(?:line|bushyBal|bushy|rdeep|rd|branch|star)"
                    r"(\d+)[a-z]?(?=_|$)"):
            count = grab(pat, q, int)
            if count is not None:
                return count
        # Every generated numbered aggregate uses one three-relation base.
        if re.search(r"_(?:th|ds|jb)_agg\d+$", q):
            return 3
        return np.nan

    fallback_count = df["query"].map(relation_count_from_name)
    if "sql_path" in df:
        corpus_root = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "outerjoin_query")

        def relation_count_from_sql_path(relative_path):
            """Recover exact metadata for old CSV rows whose label omits depth."""
            if not isinstance(relative_path, str) or not relative_path:
                return np.nan
            normalized = os.path.normpath(relative_path)
            unsafe_parent = normalized == ".." or normalized.startswith(".." + os.sep)
            if os.path.isabs(normalized) or unsafe_parent:
                return np.nan
            query_path = os.path.join(corpus_root, normalized)
            try:
                with open(query_path, encoding="utf-8") as query_file:
                    sql = query_file.read()
            except OSError:
                return np.nan
            count = len(re.findall(r"\b(?:FROM|JOIN)\b", sql, flags=re.IGNORECASE))
            return count if count > 0 else np.nan

        path_count = df["sql_path"].map(relation_count_from_sql_path)
        fallback_count = fallback_count.fillna(path_count)
    if "relation_count" in df:
        reported_count = pd.to_numeric(df["relation_count"], errors="coerce")
        reported_count = reported_count.where(
            (reported_count > 0) & (reported_count == np.floor(reported_count)))
        df["relation_count"] = reported_count.fillna(fallback_count)
    else:
        df["relation_count"] = fallback_count
    df["mix"] = df["query"].map(lambda q: grab(r"mix([ABC])", q))
    df["sparsity"] = df["query"].map(lambda q: grab(r"_s(\d+)", q, int))
    df["is_agg"] = df["query"].str.contains("agg")
    df["ratio"] = df["tm_speedup"] / df["t1_speedup"]            # >1 multi amplifies
    return df


def load(paths):
    frames = []
    for p in paths:
        try:
            raw = pd.read_csv(p)
        except Exception as e:
            print(f"  ! skip {p}: {e}", file=sys.stderr); continue
        if "query" not in raw.columns:
            print(f"  ! skip {p}: no 'query' column", file=sys.stderr); continue
        run = re.sub(r"^experiment_onoff_|\.csv$", "", os.path.basename(p)) or os.path.basename(p)
        frames.append(enrich(raw, run))
        print(f"  loaded {p}  ({len(raw)} rows, run='{run}')")
    if not frames:
        sys.exit("No usable CSV files.")
    return pd.concat(frames, ignore_index=True)


# ----------------------------------------------------------------------------- helpers
def timed(df):
    """Rows that were actually correct & timed (have at least one speed-up)."""
    ok = df.get("correct", "TRUE").astype(str).str.upper().eq("TRUE")
    return df[ok & (df["t1_speedup"].notna() | df["tm_speedup"].notna())].copy()


def grouped_box(ax, df, group_col, order, title, label_pos="side"):
    """Side-by-side T1 / TM box+strip per group, log y, reference line at 1.
    The number on each box is the GEOMETRIC MEAN (same stat as geomean_family);
    label_pos='side' places it beside the box, 'above' lifts it over the box."""
    order = [g for g in order if g in set(df[group_col].dropna())]
    if not order:
        ax.set_visible(False); return
    width = 0.38
    rng = np.random.default_rng(0)
    for j, (col, color) in enumerate([("t1_speedup", C_T1), ("tm_speedup", C_TM)]):
        data = [df.loc[df[group_col] == g, col].dropna().values for g in order]
        pos = [i + (j - 0.5) * width for i in range(len(order))]
        bp = ax.boxplot(data, positions=pos, widths=width * 0.9, patch_artist=True,
                        showfliers=False, medianprops=dict(color="black", lw=1.3),
                        whiskerprops=dict(color=color), capprops=dict(color=color),
                        boxprops=dict(color=color))
        for b in bp["boxes"]:
            b.set(facecolor=color, alpha=0.55)
        for i, vals in enumerate(data):
            if not len(vals):
                continue
            ax.scatter(rng.normal(pos[i], 0.03, len(vals)), vals,
                       s=11, color=color, edgecolor="k", lw=0.2, alpha=0.55, zorder=3)
            geo = gmean(vals)                          # geomean — matches geomean_family
            if not np.isfinite(geo):
                continue
            ax.scatter([pos[i]], [geo], marker="D", s=15, color="white",
                       edgecolor="black", lw=0.7, zorder=7)          # geomean marker
            if label_pos == "above":
                ax.annotate(f"{geo:.2f}", (pos[i], geo), textcoords="offset points",
                            xytext=(0, 7), ha="center", va="bottom", fontsize=5,
                            color="black", zorder=8)
            else:
                xlab = pos[i] + (-1 if j == 0 else 1) * (width * 0.9 / 2 + 0.04)
                ax.annotate(f"{geo:.2f}", (xlab, geo), ha=("right" if j == 0 else "left"),
                            va="center", fontsize=5, color="black", zorder=8)
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels([f"{g}\n(n={int((df[group_col]==g).sum())})" for g in order])  # horizontal
    ax.set_xlim(-0.9, len(order) - 0.1)            # room for the beside-box value labels
    ax.axhline(1.0, color="grey", ls="--", lw=1)
    ax.set_yscale("log")
    ax.set_ylabel("ON speed-up (x > 1 = faster)")
    ax.set_title(title)
    ax.legend(handles=[Patch(facecolor=C_T1, alpha=.55, label="single-thread (T1)"),
                       Patch(facecolor=C_TM, alpha=.55, label="multi-thread (TM)")],
              fontsize=8, loc="upper right")


def fig_per_query_by_family(t, outdir, metric="tm"):
    """One horizontal-bar PNG per family showing EVERY timed query (T1 + TM),
    sorted by `metric`. Bar thickness is constant, so the figure height scales
    with the (variable) query count -- it never crowds or stretches the bars."""
    col = f"{metric}_speedup"
    other = "t1_speedup" if metric == "tm" else "tm_speedup"
    olabel = other.split("_")[0].upper()
    BAR = 0.40                                        # fixed bar thickness (data units)
    for fam in FAMILY_ORDER:
        sub = t[t["family"] == fam].dropna(subset=[col]).copy()
        plans = sub.get(
            "selected_plan", pd.Series("", index=sub.index, dtype="object")
        ).astype(str).str.upper()
        sub["_plan_label"] = np.select(
            [plans.eq("OUTERYAN"), plans.eq("DUCKDB")], ["OY", "D"], default="?"
        )
        sub = sub.sort_values(col)
        n = len(sub)
        if n == 0:
            continue
        height = min(38, max(2.4, 0.30 * n + 1.0))    # dynamic, clamped
        fig, ax = plt.subplots(figsize=(9.5, height))
        y = np.arange(n)
        ax.barh(y + BAR / 2, sub[col], height=BAR, edgecolor="k", lw=0.3, color=C_TM)
        ax.barh(y - BAR / 2, sub[other], height=BAR, edgecolor="k", lw=0.3, color="#cccccc")
        if n <= 24:                                    # only label when not crowded
            for yi, v in zip(y, sub[col].values):
                if np.isfinite(v):
                    ax.text(v, yi + BAR / 2, f" {v:.2f}", va="center", ha="left",
                            fontsize=6, color="0.2")
        ax.axvline(1, color="grey", ls="--", lw=1)
        ax.set_xscale("log")
        query_labels = [
            f"{query} [{plan}]" for query, plan in zip(sub["query"], sub["_plan_label"])
        ]
        ax.set_yticks(y); ax.set_yticklabels(query_labels, fontsize=7)
        ax.set_ylim(-1, n)
        ax.set_xlabel("speed-up (×, log, >1 = ON faster)")
        ax.set_title(f"{fam}: all {n} timed queries by {metric.upper()} speed-up")
        ax.legend(handles=[Patch(facecolor=C_TM, label=metric.upper()),
                           Patch(facecolor="#cccccc", label=olabel)],
                  fontsize=7, loc="lower right")
        fig.tight_layout()
        save(fig, outdir, f"per_query_{fam.replace('-', '').lower()}")


def fig_phase_by_family(t, outdir):
    """Plot per-phase native operator time for every complete query profile.

    The four phase bars are grouped rather than stacked and their endpoints use
    a base-10 logarithmic x-axis. This keeps small R1/R2 measurements visible
    beside much larger R3/Other values. DuckDB plans legitimately have no R1/R2
    operators, so structural zeros are left blank on the logarithmic axis; all
    other missing or inconsistent profiles are omitted.
    """
    seconds_columns = [seconds for _, seconds, _, _ in PHASES]
    ratio_columns = [ratio for _, _, ratio, _ in PHASES]
    required = seconds_columns + ratio_columns + ["profile_total_time_s"]
    if not set(required).issubset(t.columns):
        return

    for fam in FAMILY_ORDER:
        family_rows = t[t["family"] == fam].copy()
        if family_rows.empty:
            continue

        for column in required:
            family_rows[column] = pd.to_numeric(family_rows[column], errors="coerce")
        plans = family_rows.get(
            "selected_plan", pd.Series("", index=family_rows.index, dtype="object")
        ).astype(str).str.upper()
        duckdb = plans.eq("DUCKDB")
        sj_columns = seconds_columns[:2] + ratio_columns[:2]
        for column in sj_columns:
            family_rows.loc[duckdb & family_rows[column].isna(), column] = 0.0

        seconds = family_rows[seconds_columns]
        ratios = family_rows[ratio_columns]
        seconds_total = seconds.sum(axis=1, min_count=len(seconds_columns))
        ratio_total = ratios.sum(axis=1, min_count=len(ratio_columns))
        total_time = family_rows["profile_total_time_s"]
        finite_seconds = np.isfinite(seconds).all(axis=1)
        nonnegative_seconds = seconds.ge(0).all(axis=1)
        finite_ratios = np.isfinite(ratios).all(axis=1)
        bounded_ratios = ratios.ge(0).all(axis=1) & ratios.le(1).all(axis=1)
        seconds_close = np.isclose(seconds_total, total_time, rtol=1e-6, atol=1e-9)
        ratios_close = (ratio_total - 1.0).abs().le(1e-6)
        paired_ratios_close = np.isclose(
            ratios.to_numpy(float), seconds.div(total_time, axis=0).to_numpy(float),
            rtol=0, atol=1e-6,
        ).all(axis=1)
        known_plan = plans.isin(["DUCKDB", "OUTERYAN"])
        duckdb_sj_is_zero = ~duckdb | family_rows[sj_columns].eq(0).all(axis=1)
        complete = (finite_seconds & nonnegative_seconds & finite_ratios & bounded_ratios
                    & np.isfinite(total_time) & total_time.gt(0)
                    & seconds_close & ratios_close & paired_ratios_close
                    & known_plan & duckdb_sj_is_zero)
        sub = family_rows.loc[complete].copy()
        if sub.empty:
            continue

        sub["_plan_label"] = np.select(
            [plans.loc[complete].eq("OUTERYAN"), plans.loc[complete].eq("DUCKDB")],
            ["OY", "D"], default="?"
        )
        sub = sub.sort_values(["profile_total_time_s", "query"], kind="stable")
        n = len(sub)
        skipped = len(family_rows) - n
        height = min(50, max(3.2, 0.42 * n + 1.4))
        fig, ax = plt.subplots(figsize=(11.0, height))
        y = np.arange(n)
        positive_phase_times = sub[seconds_columns].to_numpy(float)
        positive_phase_times = positive_phase_times[positive_phase_times > 0]
        if positive_phase_times.size == 0:
            continue
        axis_floor = 10 ** np.floor(np.log10(positive_phase_times.min()))
        phase_offsets = np.linspace(-0.27, 0.27, len(PHASES))
        for offset, (label, seconds, _, color) in zip(phase_offsets, PHASES):
            values = sub[seconds].to_numpy(float)
            positive = values > 0
            # On a logarithmic axis bars cannot start at zero. Starting at the
            # common decade floor makes the endpoint (the encoded value) exact
            # while keeping structural zero phases absent.
            ax.barh(y[positive] + offset, values[positive] - axis_floor,
                    left=axis_floor, height=0.16, color=color,
                    edgecolor="white", linewidth=0.25, label=label)

        # Mark and label the matched total without treating it as another phase.
        totals = sub["profile_total_time_s"].to_numpy(float)
        ax.scatter(totals, y, marker="|", s=42, linewidths=0.8,
                   color="black", zorder=4, label="Total-Time")
        for yi, total in zip(y, sub["profile_total_time_s"].to_numpy(float)):
            ax.annotate(f"{total:.3g} s", xy=(total, yi), xytext=(4, 0),
                        textcoords="offset points", ha="left", va="center",
                        fontsize=6, color="0.2", clip_on=False)

        query_labels = [
            f"{query} [{plan}]" for query, plan in zip(sub["query"], sub["_plan_label"])
        ]
        ax.set_yticks(y)
        ax.set_yticklabels(query_labels, fontsize=7)
        ax.set_ylim(-0.8, n - 0.2)
        ax.set_xscale("log", base=10)
        ax.set_xlim(axis_floor, totals.max() * 1.55)
        ax.grid(axis="x", which="major", color="0.84", linewidth=0.65)
        ax.grid(axis="x", which="minor", color="0.92", linewidth=0.4)
        ax.set_axisbelow(True)
        ax.set_xlabel("native operator time (seconds, base-10 log scale)")
        omission = f"; {skipped} incomplete omitted" if skipped else ""
        title = f"{fam}: native phase breakdown ({n} queries{omission})"
        top = 1.0 - min(0.20, 0.55 / height)
        fig.tight_layout(rect=(0, 0, 1, top))
        fig.suptitle(title, y=0.995)
        fig.legend(
            handles=[Patch(facecolor=color, label=label) for label, _, _, color in PHASES]
                    + [plt.Line2D([], [], color="black", marker="|", linestyle="None",
                                  markersize=8, label="Total-Time")],
            ncol=5, fontsize=7, loc="upper center",
            bbox_to_anchor=(0.5, 0.995 - 0.25 / height), frameon=False,
        )
        save(fig, outdir, f"phase_breakdown_{fam.replace('-', '').lower()}")


def fig_machine_cmp(t, outdir):
    runs = t["run"].unique()
    if len(runs) < 2: return
    piv = t.pivot_table(index="query", columns="run", values="tm_speedup", aggfunc="median")
    piv = piv.dropna()
    if len(piv) < 2: return
    a, b = runs[0], runs[1]
    fig, ax = plt.subplots(figsize=(6.5, 6))
    ax.scatter(piv[a], piv[b], s=28, alpha=0.75, color="#4C72B0", edgecolor="k", lw=0.3)
    lim = [max(0.005, min(piv.min().min(), 0.1)), piv.max().max() * 1.3]
    ax.plot(lim, lim, color="grey", ls="--", lw=1)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel(f"TM speed-up  [{a}]"); ax.set_ylabel(f"TM speed-up  [{b}]")
    ax.set_title("Per-query TM speed-up: run vs run")
    fig.tight_layout(); save(fig, outdir, "machine_cmp")


# ----------------------------------------------------------------------------- io
def save(fig, outdir, name):
    for ext in OUT_FORMATS:
        dpi = OUT_DPI
        if ext == "png":                      # keep raster pixel count sane on very tall figures
            dpi = min(OUT_DPI, int(16000 / max(fig.get_size_inches())))
        fig.savefig(os.path.join(outdir, f"{name}.{ext}"), dpi=dpi, bbox_inches="tight", format=ext)
    plt.close(fig)
    print(f"  wrote {os.path.join(outdir, name)}.{{{','.join(OUT_FORMATS)}}}")


def render_run(t, outdir, metric, runlabel):
    """Render the full single-run figure set for dataframe `t` into `outdir`."""
    os.makedirs(outdir, exist_ok=True)
    # Clear stale PNGs so a family/figure absent in the new data does not linger
    # (e.g. a run with no JOB results must not keep a previous per_query_job.png).
    for old in glob.glob(os.path.join(outdir, "*.png")) + glob.glob(os.path.join(outdir, "*.pdf")):
        os.remove(old)
    fams = sorted(set(t["family"]))
    print(f"    families present: {', '.join(fams)}")

    # kernel + join-order share ONE figure (two tight panels)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    grouped_box(axes[0], t, "kernel_type", KERNEL_ORDER, "Speed-up by kernel")
    grouped_box(axes[1], t, "reorder", ["Yes", "No"], "Speed-up by join order")
    fig.tight_layout(); save(fig, outdir, "speedup_by_kernel_joinorder")

    fig, ax = plt.subplots(figsize=(8, 5))
    grouped_box(ax, t, "family", FAMILY_ORDER, "Speed-up by benchmark family")
    fig.tight_layout(); save(fig, outdir, "speedup_by_benchmark")

    topo = sorted(t["topology"].dropna().unique())                 # labels ABOVE the boxes here
    fig, ax = plt.subplots(figsize=(max(9, 1.5 * len(topo)), 5))
    grouped_box(ax, t, "topology", topo, "Speed-up by shape", label_pos="above")
    fig.tight_layout(); save(fig, outdir, "speedup_by_shape")

    # speed-up by relation count across every benchmark family
    by_relations = t[t["relation_count"].notna()].copy()
    if len(by_relations):
        by_relations["relation_count_label"] = (
            by_relations["relation_count"].astype("Int64").astype(str))
        relation_order = sorted(by_relations["relation_count_label"].unique(), key=int)
        fig, ax = plt.subplots(figsize=(max(8, 0.9 * len(relation_order)), 5))
        grouped_box(ax, by_relations, "relation_count_label", relation_order,
                    "Speed-up by #relations (all families)", label_pos="above")
        fig.tight_layout(); save(fig, outdir, "speedup_by_relations")

    fig_per_query_by_family(t, outdir, metric)
    fig_phase_by_family(t, outdir)

    print(f"\n[{runlabel}] geomean speed-up (T1 / TM):")
    for k in KERNEL_ORDER:
        s = t[t["kernel_type"] == k]
        if len(s):
            print(f"    kernel {k:7s}  n={len(s):3d}  T1={fmt(gmean(s.t1_speedup))}  TM={fmt(gmean(s.tm_speedup))}")
    for f in FAMILY_ORDER:
        s = t[t["family"] == f]
        if len(s):
            print(f"    family {f:7s}  n={len(s):3d}  T1={fmt(gmean(s.t1_speedup))}  TM={fmt(gmean(s.tm_speedup))}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="*", help="experiment_onoff_*.csv files (default: <results>/*.csv)")
    ap.add_argument("-o", "--outdir", default=None, help="output directory (default: <results>/plots)")
    ap.add_argument("--metric", default="tm", choices=["t1", "tm"], help="metric for per-query sort")
    ap.add_argument("--exclude-none", action="store_true",
                    help="drop no-op queries (kernel=none, b0h0: OuterYan inserted no filter)")
    ap.add_argument("--format", default="pdf", choices=["pdf", "png", "both"],
                    help="output format; pdf (vector) is the default")
    ap.add_argument("--dpi", type=int, default=1200, help="output DPI (default 1200)")
    args = ap.parse_args()

    global OUT_FORMATS, OUT_DPI
    OUT_FORMATS = {"both": ["pdf", "png"], "pdf": ["pdf"], "png": ["png"]}[args.format]
    OUT_DPI = args.dpi

    # Input resolution: explicit CLI paths > in-code DEFAULT_INPUTS > glob results/ dir.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    results_dir = os.path.join(script_dir, "results")

    def resolve(pat):
        """Expand ~, make relative paths script-relative, glob wildcards."""
        p = os.path.expanduser(pat)
        if not os.path.isabs(p):
            p = os.path.join(script_dir, p)
        hits = sorted(glob.glob(p))
        return hits if hits else ([] if any(c in pat for c in "*?[") else [p])

    if args.csv:
        paths = list(args.csv)
    elif DEFAULT_INPUTS:
        paths = [p for pat in DEFAULT_INPUTS for p in resolve(pat)]
    else:
        paths = (sorted(glob.glob(os.path.join(results_dir, "experiment_onoff_*.csv")))
                 or sorted(glob.glob("experiment_onoff_*.csv")))    # fall back to cwd
    paths = [p for p in paths if p.lower().endswith(".csv")]
    if not paths:
        sys.exit(f"No CSV files (edit DEFAULT_INPUTS, pass paths, or populate {results_dir}/).")

    # Output resolution: -o/--outdir > in-code DEFAULT_OUTDIR (script-relative) > <results>/plots.
    if args.outdir:
        outdir = args.outdir
    elif DEFAULT_OUTDIR:
        outdir = os.path.expanduser(DEFAULT_OUTDIR)
        if not os.path.isabs(outdir):
            outdir = os.path.join(script_dir, outdir)
    else:
        outdir = os.path.join(results_dir, "plots")
    args.outdir = outdir
    os.makedirs(args.outdir, exist_ok=True)
    for ext in ("png", "pdf"):                                 # drop a stale comparison
        sc = os.path.join(args.outdir, f"machine_cmp.{ext}")   # (e.g. when re-run single)
        if os.path.exists(sc):
            os.remove(sc)

    df = load(paths)
    t_full = timed(df)                            # correct & timed (incl. no-op 'none')
    t_all = t_full
    if args.exclude_none:
        t_all = t_full[t_full["kernel_type"] != "none"].copy()
        print(f"\nexcluding {len(t_full) - len(t_all)} no-op (kernel=none) queries")
    print(f"\n{len(t_all)} plotted rows of {len(df)} total")

    runs = list(dict.fromkeys(df["run"]))         # source files, in load order
    multi = len(runs) > 1
    for run in runs:
        sub = t_all[t_all["run"] == run]
        timed_run = int((t_full["run"] == run).sum())             # correct & timed
        skipped = int((df["run"] == run).sum()) - timed_run       # timeout/error rows
        rdir = os.path.join(args.outdir, run) if multi else args.outdir
        print(f"\n>>> run '{run}'  ({len(sub)} plotted, {skipped} skipped) -> {rdir}/")
        render_run(sub, rdir, args.metric, run)

    if multi:
        fig_machine_cmp(t_all, args.outdir)        # cross-run comparison at the root
        print(f"\nCross-run comparison -> {args.outdir}/machine_cmp.png")

    layout = ("one subfolder per source file + machine_cmp.*"
              if multi else "open dashboard.pdf first")
    print(f"\nDone -> {args.outdir}/   ({layout})")


if __name__ == "__main__":
    main()
