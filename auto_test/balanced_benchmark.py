#!/usr/bin/env python3
"""Deterministic, historically screened candidates; never invent measured eligibility.

Frozen evidence is explicit research curation, not an unbiased benchmark sample.
Generation never reads results/. Server-side qualification is a separate operation.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import replace
import csv
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import gen_outerjoin_benchmark as legacy
from benchmark_corpus import read_manifest, sql_fingerprint

ROOT = legacy.DEFAULT_ROOT
REVISION = "balanced-screened-20261002"
ARCHIVE = "unique_semantic_20260929"
DESIGN = ROOT / "sources/balanced_design.json"
EVIDENCE = ROOT / "sources/balanced_exclusions.json"
FAMILIES = ("graph", "tpch", "tpcds", "job")
TIERS = ("low", "medium", "high")
SHAPES = ("left_deep", "right_deep", "bushy")
TARGET = 180
QUALIFICATION_TIMEOUT_SECONDS = 900
HISTORICAL_ROLE = "historical_slow_baseline_case"
HISTORICAL_CASES = {
    "q80_alt": ("derived__ojb_tpcds_q80_store_channel_alt",
                "38e9b903da4302ed10c47b29b587fc2f472104a2a90541113df5934b4cc3ca00"),
    "q80_left_deep": ("derived__ojb_tpcds_q80_store_channel_ldmx",
                      "c0f055403e607df8bd2dbb21a5f8aeaea0e078d57d4e53277f3632dc4dab7cfe"),
    "q93_left_deep": ("derived__ojb_tpcds_q93_return_reason_ldmx",
                      "5461ee1745d99733ce99fe7766fbfbbba037117bb621555d20c70da011faf4ee"),
}


def is_historical_case(row):
    return row.get("evaluation_role") == HISTORICAL_ROLE


def historical_cases():
    """Restore exact archived SQL; never transfer its old timings to a new scale."""
    archive = ROOT / "revisions/pre_semantic_20260925/benchmark"
    manifest = {r["query_id"]: r for r in read_manifest(archive / "manifest.csv")}
    for name, (original_id, expected_hash) in HISTORICAL_CASES.items():
        old = manifest[original_id]
        source = archive / old["path"]
        if digest(source) != expected_hash:
            raise ValueError(f"Historical case definition changed: {source}")
        sql = source.read_text(encoding="utf-8")
        query = f"join__tpcds__historical__{name}"
        row = dict(family="tpcds", query_id=query, path=f"tpcds/{query}.sql",
                   query_class="join", workload_category="join", corpus_revision=REVISION,
                   source_seed=original_id, source_benchmark="TPC-DS", source_query=old["source_query"],
                   source_location=str(source.relative_to(legacy.REPO_ROOT)), source_sha256=expected_hash,
                   source_filter_adaptation="Historical SQL preserved verbatim, including item-only sales/returns edge",
                   topology=old["topology"], tree_shape=old["tree_shape"], join_vector=old["join_vector"],
                   relation_count=old["relation_count"], provenance_class="historical_case_study",
                   source_component="evaluation", evaluation_role=HISTORICAL_ROLE,
                   filter_design_revision="historical-modulo-20260925", semantic_tier="historical_unbanded",
                   selectivity_tier="legacy_modulo_unverified", selectivity_profile="legacy_tpcds_ticket_mod1000",
                   selectivity_anchor="ss.ss_ticket_number", selectivity_predicate="ss.ss_ticket_number % 1000 = 0",
                   calibration_in_range="not_applicable", selectivity_scope="historical modulo filter; not audited into balanced bands",
                   parameter_policy="User-requested historical case, selected using prior performance; report separately",
                   sql_fingerprint=sql_fingerprint(sql, "tpcds"), expression_fingerprint=expression_key(sql, "tpcds"),
                   content_sha256=expected_hash, candidate_batch=0, selectivity_stress="false", regression_guard="false",
                   qualification_status="PENDING_CPU9_MEASUREMENT",
                   qualification_timeout_seconds=QUALIFICATION_TIMEOUT_SECONDS,
                   qualification_min_runtime_s=1, qualification_min_speedup=.8)
        yield row, sql


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path, rows, fields=None):
    fields = fields or list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def body(sql):
    return re.sub(r"--[^\n]*", "", sql).strip()


def expression_key(sql, family):
    """Ignore projection and filter, but retain grouping, operands and every ON key."""
    expression = re.search(r"\bFROM\s+(.*?)\s+WHERE\b", body(sql), re.I | re.S)
    if not expression:
        raise ValueError("Expected flat FROM/WHERE query")
    return sql_fingerprint(expression.group(1), family)


def archive_current(root=ROOT):
    """Retain the exact previous definitions before replacing generated SQL."""
    source = root / "benchmark"
    if not (source / "manifest.csv").is_file():
        return
    rows = read_manifest(source / "manifest.csv")
    if {r["corpus_revision"] for r in rows} != {"unique-semantic-20260929"}:
        return
    for row in rows:
        if digest(source / row["path"]) != row["content_sha256"]:
            raise ValueError(f"Locally edited query; refusing replacement: {row['path']}")
    target = root / "revisions" / ARCHIVE / "benchmark"
    if target.exists():
        if digest(target / "manifest.csv") != digest(source / "manifest.csv"):
            raise ValueError("Historical archive differs; refusing overwrite")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)


def freeze_history(root=ROOT):
    """Explicit one-time evidence import; the portable generator uses only this pin."""
    archive_current(root)
    result_root = legacy.SCRIPT_DIR / "results"
    source_paths = sorted(result_root.glob("experiment_onoff_benchmark_20260926_*_t32_*.csv"))
    source_paths += [result_root / "experiment_onoff_benchmark_20260929_222836_t32.csv"]
    old = root / "revisions/pre_semantic_20260925"
    scopes = {"v1": "benchmark", "v2": "v2/benchmark", "v3_aggregation": "v3/benchmark",
              "v3_selectivity_stress": "v3/selectivity_stress"}
    excluded, sources = [], []
    for path in source_paths:
        if not path.exists():
            raise FileNotFoundError(path)
        logfile = path.with_suffix(".txt")
        if not logfile.exists():
            logfile = result_root / "server_snapshot_20260926/auto_test/results" / logfile.name
        timeout = None
        if logfile.exists():
            match = re.search(r"# timeout: hard (\d+)s/statement", logfile.read_text())
            timeout = int(match.group(1)) if match else None
        sources.append({"csv": path.name, "sha256": digest(path), "timeout_seconds": timeout})
        for row in read_manifest(path):
            reason = None
            speed = None
            try:
                off, on = float(row["tm_off"]), float(row["tm_on"])
                if row["correct"] == "TRUE" and all(math.isfinite(t) and t > 0 for t in (off, on)):
                    speed = off / on
                    if speed < .8:
                        reason = "measured_speedup_below_0.8"
            except (ValueError, KeyError):
                pass
            if "TIMEOUT" in row.get("note", "") and timeout == 1800:
                reason = "timeout_at_1800s"
            if not reason:
                continue
            scope = scopes.get(row.get("workload_category"))
            sqlpath = (old / scope if scope else root / "revisions" / ARCHIVE / "benchmark") / row["sql_path"]
            sql = sqlpath.read_text(encoding="utf-8")
            excluded.append({"family": row["family"], "query": row["query"],
                             "source_csv": path.name, "reason": reason, "speedup": speed,
                             "sql_fingerprint": sql_fingerprint(sql, row["family"]),
                             "expression_fingerprint": expression_key(sql, row["family"]),
                             "sql_path": str(sqlpath.relative_to(root)),
                             "content_sha256": digest(sqlpath)})
    write_json(root / "sources/balanced_exclusions.json", {
        "policy": "Conservative exclusion of exact SQL and unchanged join expressions across all filter tiers. "
                  "Corrected composite-key expressions are new candidates, not historical performance claims. "
                  "600s timeouts are not treated as proven 1800s timeouts.",
        "sources": sources, "excluded": excluded})
    print(f"Pinned {len(excluded)} exclusion observations")


def bootstrap_design(binary, root=ROOT):
    """Retune high-band literals and recount base entities; no workload execution."""
    design = json.loads((root / "sources/semantic_filter_design.json").read_text())
    design["revision"] = REVISION
    design["calibration_policy"] = "Three base-entity bands (0,5%), [5,40%), [40,60%]; " \
        "frozen local counts, mandatory target-server audit. This is a historically screened candidate corpus."
    design["tiers"][2]["upper_bound"] = .6
    high = {
        "job_person_name": "(" + " OR ".join("{column} LIKE '" + c + "%'" for c in "ABCDEFGHIJKL") + ")",
        "job_release_period": "{column} BETWEEN 1950 AND 2006",
        "tpch_stock_available": "{column} > 4500",
        "tpch_q05_period": "{column} >= DATE '1992-01-01' AND {column} < DATE '1995-08-01'",
        "tpch_q07_period": "{column} BETWEEN DATE '1993-06-01' AND DATE '1996-12-31'",
        "tpch_q08_period": "{column} BETWEEN DATE '1993-06-01' AND DATE '1996-12-31'",
        "sqlstorm_shipment_period": "{column} BETWEEN DATE '1994-06-01' AND DATE '1997-12-31'",
        "sqlstorm_order_period": "{column} BETWEEN DATE '1993-06-01' AND DATE '1996-12-31'",
    }
    # Three discrete info categories jump from 33% to 67%; do not claim 40–60%.
    design["profiles"].pop("job_info_category")
    spec = design["seeds"]["job_01a_skeleton"]
    spec.update(profile="job_release_year", column="t.production_year",
                adaptation="Source join graph retained; release-year cohort replaces discrete info-category "
                           "filter because its calibrated categories jump from 33% to 67%.")
    for name, predicate in high.items():
        profile = design["profiles"][name]
        profile["predicates"][2] = predicate
        predicates = [p.format(column=profile["column"]) for p in profile["predicates"]]
        sql = "SELECT COUNT(*) AS n," + ",".join(
            f"COUNT(*) FILTER (WHERE {p}) AS c{i}" for i, p in enumerate(predicates))
        sql += " FROM " + profile["calibration_from"]
        database = Path(os.environ.get(profile["family"].upper() + "_DB",
                                       legacy.REPO_ROOT / (profile["family"] + "_db")))
        result = subprocess.run([str(binary), "-readonly", "-no-init", "-bail", "-json", str(database),
                                 "-c", "SET disabled_optimizers='outer_yan'; SET threads=4; " + sql],
                                capture_output=True, text=True, check=True, timeout=120)
        counts = json.loads(result.stdout)[0]
        calibration = profile["calibration"]
        calibration.update(n=counts["n"], qualified_rows=[counts[f"c{i}"] for i in range(3)],
                           observed_fractions=[counts[f"c{i}"]/counts["n"] for i in range(3)])
        if not all(legacy.fraction_in_band(f, tier) for f, tier in
                   zip(calibration["observed_fractions"], design["tiers"])):
            raise ValueError(f"New calibration outside band: {name}: {calibration}")
        print(name, calibration["observed_fractions"], flush=True)
    design["curation"] = {
        "target_per_family": TARGET, "target_per_family_tier": TARGET // 3,
        "timeout_seconds": QUALIFICATION_TIMEOUT_SECONDS, "minimum_runtime_each_engine_exclusive": 1,
        "minimum_speedup": .8, "target_host": "cpu9",
        "target_repository": "/home/data/bchenba/DuckYanOuter",
        "eligibility": "Only measured pairs passing target-database selectivity audit; "
                       "correctness is verified or explicitly NOT-CHECKED with checks disabled. "
                       "New SQL is pending measurement, never assumed eligible.",
        "excluded_seeds": {"tpcds_q72_fulfillment":
            "Reduced source subgraph omits sales/inventory week constraint; historical 1800s timeouts."},
    }
    write_json(root / "sources/balanced_design.json", design)


def profile_metadata(design, profile_id, column, tier):
    """Reuse formatting without changing the legacy generator's frozen design."""
    profile = design["profiles"][profile_id]
    i = TIERS.index(tier)
    band = design["tiers"][i]
    if profile["kind"] == "predicates":
        predicate = profile["predicates"][i].format(column=column)
    elif profile["kind"] == "date_window":
        pivot = legacy.datetime_module.date.fromisoformat(profile["pivot"])
        delta = legacy.datetime_module.timedelta(days=int(profile["bounds"][i]))
        predicate = f"{column} BETWEEN DATE '{pivot-delta}' AND DATE '{pivot+delta}'"
    else:
        value = profile["bounds"][i]
        operator, value = (">=", -value) if profile["kind"] == "lower" else ("<=", value)
        predicate = f"{column} {operator} {value:.10g}"
    calibration = profile["calibration"]
    fraction = calibration["qualified_rows"][i] / calibration["n"]
    if not legacy.fraction_in_band(fraction, band):
        raise ValueError(f"{profile_id}/{tier} is outside its band")
    return dict(filter_design_revision=REVISION, semantic_tier=tier, selectivity_tier="sel_"+tier,
                selectivity_profile=profile_id, selectivity_anchor=column, selectivity_predicate=predicate,
                target_fraction=band["target_fraction"], target_min_fraction=band["lower_bound"],
                target_max_fraction=band["upper_bound"],
                target_min_inclusive=str(band["include_lower"]).lower(),
                target_max_inclusive=str(band["include_upper"]).lower(),
                calibration_rows=calibration["n"], calibration_qualified_rows=calibration["qualified_rows"][i],
                calibration_fraction=fraction, calibration_in_range="true", filter_semantics=profile["meaning"],
                selectivity_denominator=profile["calibration_from"],
                selectivity_scope="base entity including NULLs; not joined output",
                parameter_policy="frozen semantic cohorts; historically screened; server audit required")


def full_equality(predicate):
    """Keep ALL qualified column equalities on each source edge, not just the first."""
    matches = list(legacy.SIMPLE_EDGE_EQUALITY.finditer(predicate))
    if not matches:
        raise ValueError(f"No equality: {predicate}")
    pairs = {tuple(sorted(x.split('.')[0].lower() for x in m.groups())) for m in matches}
    if len(pairs) != 1:
        raise ValueError(f"Multiple relation pairs on one edge: {predicate}")
    return " AND ".join(m.group() for m in matches)


def expression(seed, shape, kinds, traversal=0):
    aliases = [legacy.relation_alias(r) for r in seed.relations]
    tables = dict(zip(aliases, seed.relations))
    edges = [(*legacy.predicate_aliases(p), i) for i, p in enumerate(seed.predicates)]

    def deep(nodes, right=False):
        ordered = [a for a in aliases if a in nodes]
        start = ordered[traversal % len(ordered)]
        visited, sql = {start}, tables[start]
        while visited != nodes:
            candidates = [(i, b if a in visited else a) for a, b, i in edges
                          if a in nodes and b in nodes and ((a in visited) != (b in visited))]
            i, new = (max(candidates) if traversal % 2 else min(candidates))
            pred = full_equality(seed.predicates[i])
            left, rhs = (tables[new], sql) if right else (sql, tables[new])
            sql = f"({left} {legacy.JOIN_SQL[kinds[i]]} {rhs} ON {pred})"
            visited.add(new)
        return sql

    if shape != "bushy":
        return deep(set(aliases), shape == "right_deep")
    partition = legacy.bushy_root_partition(seed)
    if partition is None:
        return None
    left, right, edge = partition
    if traversal % 2:
        left, right = right, left
    return (f"({deep(left)} {legacy.JOIN_SQL[kinds[edge]]} {deep(right, True)} "
            f"ON {full_equality(seed.predicates[edge])})")


def graph_seeds():
    seeds = []
    for n in (4, 5, 6):
        for topology in ("chain", "star", "branch"):
            if topology == "branch" and n == 4:
                continue
            for direction in ("forward", "converging"):
                parents = ([i-1 for i in range(2, n+1)] if topology == "chain" else
                           [1]*(n-1) if topology == "star" else [1, 2, 2] + [3]*(n-4))
                predicates = tuple(f"R{parent}.dst = R{i}.{'src' if direction == 'forward' else 'dst'}"
                                   for i, parent in enumerate(parents, 2))
                seeds.append(legacy.Seed("graph", f"graph_{topology}{n}_{direction}", "Synthetic Graph",
                    REVISION, f"{topology}/{n}/{direction}", "auto_test/balanced_benchmark.py", digest(Path(__file__)),
                    topology, "Synthetic acyclic graph control; independently enumerated structure.",
                    tuple(f"R{i} R{i}" for i in range(1,n+1)), predicates, "*", tuple("ILRF"[i%4] for i in range(n-1))))
    return seeds


def seed_projection(seed):
    if seed.projection != "*":
        return seed.projection
    # Keep connected source keys, not every wide text attribute in SELECT *.
    return ", ".join(dict.fromkeys(column for p in seed.predicates
                                  for match in legacy.SIMPLE_EDGE_EQUALITY.finditer(p) for column in match.groups()))


def candidate_rows(design, evidence, root=ROOT):
    banned = {r["expression_fingerprint"] for r in evidence["excluded"]}
    exact = {r["sql_fingerprint"] for r in evidence["excluded"]}
    seeds = [s for s in legacy.SEEDS if s.seed_id not in design["curation"]["excluded_seeds"]] + graph_seeds()
    vectors = list(itertools.permutations("ILRF")) + [("L", "R", "F"), ("R", "F", "L"), ("F", "L", "R")]
    groups, seen = [], set()
    for seed in seeds:
        if seed.family == "graph":
            spec = {"profile": "graph_source_range", "column": "R1.src", "adaptation": seed.semantics}
        else:
            legacy.verify_source(seed)
            spec = design["seeds"][seed.seed_id]
        for shape, rotation, traversal in itertools.product(SHAPES, range(len(vectors)), range(2)):
            vector = tuple(vectors[rotation][i % len(vectors[rotation])] for i in range(len(seed.predicates)))
            expr = expression(seed, shape, vector, traversal)
            if expr is None:
                continue
            probe = f"SELECT * FROM {expr} WHERE TRUE;"
            key = expression_key(probe, seed.family)
            if key in banned or key in seen:
                continue
            seen.add(key)
            rows = []
            for tier in TIERS:
                metadata = profile_metadata(design, spec["profile"], spec["column"], tier)
                sql = f"SELECT {seed_projection(seed)}\nFROM {expr}\nWHERE {metadata['selectivity_predicate']};\n"
                if sql_fingerprint(sql, seed.family) in exact:
                    break
                row = dict(metadata, family=seed.family, source_seed=seed.seed_id,
                           source_benchmark=seed.source_benchmark, source_query=seed.source_query,
                           source_location=seed.source_location, source_sha256=seed.source_hash,
                           source_filter_adaptation=spec["adaptation"], topology=seed.topology,
                           tree_shape=shape, join_vector="".join(re.findall(
                               r"\b(INNER|LEFT|RIGHT|FULL)(?:\s+OUTER)?\s+JOIN", expr)).replace("INNER","I").replace("LEFT","L").replace("RIGHT","R").replace("FULL","F"),
                           relation_count=len(seed.relations), expression_fingerprint=key,
                           provenance_class="synthetic_graph" if seed.family=="graph" else "source_derived",
                           source_component="evaluation" if seed.family=="graph" else "core",
                           evaluation_role="historically_screened_candidate", _sql=sql,
                           _seed=seed)
                rows.append(row)
            if len(rows) == 3:
                groups.append(rows)
    # Preserve application-oriented synthetic controls as a separate provenance
    # class. Their business-schema names must not imply source-query derivation.
    archived = root / "revisions" / ARCHIVE / "benchmark"
    for old in read_manifest(archived / "manifest.csv"):
        if "real_" not in old["query_id"]:
            continue
        sql = body((archived / old["path"]).read_text())
        key = expression_key(sql, old["family"])
        if key in banned or key in seen:
            continue
        seen.add(key)
        group = []
        for tier in TIERS:
            metadata = profile_metadata(design, old["selectivity_profile"], old["selectivity_anchor"], tier)
            content = legacy.replace_where(sql, metadata["selectivity_predicate"])
            row = dict(metadata, family=old["family"], source_seed=old["query_id"].split("__")[2],
                       source_benchmark="Industry-inspired synthetic control", source_query=old["query_id"],
                       source_location=str((archived/old["path"]).relative_to(legacy.REPO_ROOT)),
                       source_sha256=old["content_sha256"], source_filter_adaptation="Frozen business cohort replaces WHERE",
                       topology=old.get("topology") or "unspecified", tree_shape="left_deep",
                       join_vector=old["join_vector"], relation_count=old["relation_count"],
                       expression_fingerprint=key, provenance_class="industry_synthetic_control",
                       source_component="industry_inspired", evaluation_role="application_control",
                       _sql=content, _seed=None)
            group.append(row)
        groups.append(group)
    return groups


def select_groups(groups, per_family=180, batch=0):
    """Independent of candidate speed-ups: balance shapes, source reuse and edge kinds."""
    if per_family <= 0 or per_family % 9 or batch < 0:
        raise ValueError("per-family must be divisible by 9 (three tiers and shapes)")
    selected = []
    for family in FAMILIES:
        family_groups = [g for g in groups if g[0]["family"] == family]
        for shape in SHAPES:
            used_sources, used_topologies, used_kinds = Counter(), Counter(), Counter()
            controls = 0
            pool = [g for g in family_groups if g[0]["tree_shape"] == shape]
            quota = per_family // 9
            # Earlier batches are deterministic disjoint reserves, not renamed copies.
            chosen = []
            for _ in range((batch+1)*quota):
                if not pool:
                    raise ValueError(f"Insufficient distinct candidates for {family}/{shape}/batch{batch}")
                def rank(g):
                    r = g[0]
                    kinds = used_kinds + Counter(r["join_vector"])
                    return (0 if controls < 4 and r["provenance_class"] == "industry_synthetic_control" else 1,
                            used_sources[r["source_seed"]], used_topologies[r["topology"]],
                            max(kinds[k] for k in "ILRF")-min(kinds[k] for k in "ILRF"),
                            hashlib.sha256(r["expression_fingerprint"].encode()).hexdigest())
                group = min(pool, key=rank)
                pool.remove(group)
                row = group[0]
                controls += row["provenance_class"] == "industry_synthetic_control"
                used_sources[row["source_seed"]] += 1
                used_topologies[row["topology"]] += 1
                used_kinds.update(row["join_vector"])
                chosen.append(group)
            selected.extend(chosen[batch*quota:])
    return selected


def generate(root=ROOT, per_family=180, batch=0):
    design = json.loads(DESIGN.read_text())
    if design["curation"]["timeout_seconds"] != QUALIFICATION_TIMEOUT_SECONDS:
        raise ValueError("Pinned design and qualification timeout disagree")
    evidence = json.loads(EVIDENCE.read_text())
    groups = select_groups(candidate_rows(design, evidence), per_family, batch)
    records = []
    with tempfile.TemporaryDirectory(prefix="outeryan-balanced-") as directory:
        output = Path(directory) / "benchmark"
        output.mkdir()
        family_positions = Counter()
        for group in groups:
            sample = group[0]
            family = sample["family"]
            position = family_positions[family]
            family_positions[family] += 1
            # Every fourth structure is aggregate; all three selectivity levels pair.
            aggregate = ["global_count", "grouped_min", "global_count", "grouped_max", "grouped_sum"][position//4 % 5] if position%4==3 and sample["_seed"] else ""
            for source in group:
                row = {k:v for k,v in source.items() if not k.startswith("_")}
                sql = source["_sql"]
                category = "aggregate" if aggregate else "graph" if family=="graph" or source["provenance_class"]=="industry_synthetic_control" else "join"
                anchor = ""
                if aggregate:
                    sql, anchor = legacy.add_v3_aggregation(sql, source["_seed"], aggregate)
                    sql = body(sql) + "\n"
                fingerprint = sql_fingerprint(sql, family)
                query = f"{category}__{family}__{row['source_seed']}__{row['tree_shape']}__{row['join_vector'].lower()}__{row['expression_fingerprint'][:8]}__sel_{row['semantic_tier']}"
                if aggregate:
                    query += "__"+aggregate
                row.update(query_id=query, path=f"{family}/{query}.sql", query_class=category,
                           workload_category=category, corpus_revision=REVISION, sql_fingerprint=fingerprint,
                           aggregate_variant=aggregate, aggregate_anchor=anchor,
                           selectivity_stress="false", regression_guard="false", candidate_batch=batch,
                           qualification_status="PENDING_CPU9_MEASUREMENT",
                           qualification_timeout_seconds=QUALIFICATION_TIMEOUT_SECONDS,
                           qualification_min_runtime_s=1, qualification_min_speedup=.8)
                content = (f"-- corpus_revision: {REVISION}; pending cpu9 measurement\n"
                           f"-- source: {row['source_benchmark']} {row['source_query']}\n"
                           f"-- selectivity: {row['semantic_tier']}; base-entity cohort, not joined output\n"
                           "-- policy: historically screened; not an unbiased overall-performance sample\n" + sql)
                row["content_sha256"] = hashlib.sha256(content.encode()).hexdigest()
                path = output/row["path"]
                path.parent.mkdir(exist_ok=True)
                path.write_text(content, encoding="utf-8")
                records.append(row)
        balanced_records = list(records)
        # Supplementary cases do not consume balanced quotas or repeat in reserves.
        if batch == 0:
            for row, sql in historical_cases():
                path = output / row["path"]
                path.parent.mkdir(exist_ok=True)
                path.write_text(sql, encoding="utf-8")
                records.append(row)
        records.sort(key=lambda r:r["path"])
        write_csv(output/"manifest.csv", records)
        write_csv(output/"aliases.csv", [], ["canonical_query_id", "sql_fingerprint"])
        (output / "historical_cases.txt").write_text(
            "".join(r["path"] + "\n" for r in records if is_historical_case(r)), encoding="utf-8")
        for filename in ("selectivity_stress.txt", "job_regressions.txt"):
            (output/filename).write_text("")
        write_json(output/"design_summary.json", {
            "revision": REVISION, "status": "CANDIDATES_ONLY_NOT_MEASURED", "batch": batch,
            "target_host": "cpu9:/home/data/bchenba/DuckYanOuter", "counts": dict(Counter(r["family"] for r in records)),
            "balanced_counts": dict(Counter(r["family"] for r in balanced_records)),
            "supplementary_counts": dict(Counter(r["family"] for r in records if is_historical_case(r))),
            "family_tiers": {f:dict(Counter(r["semantic_tier"] for r in balanced_records if r["family"]==f)) for f in FAMILIES},
            "family_shapes": {f:dict(Counter(r["tree_shape"] for r in balanced_records if r["family"]==f)) for f in FAMILIES},
            "historical_exclusion_observations": len(evidence["excluded"]),
            "design_sha256": digest(DESIGN), "exclusions_sha256": digest(EVIDENCE),
            "selection": "No speed-ups invented; final eligibility and shortages require target-server measurements. "
                         "Historical supplementary cases are outside balanced quotas; their old timings are not reused."})
        validate(output)
        archive_current(root)
        destination = root/"benchmark"
        old = read_manifest(destination/"manifest.csv") if (destination/"manifest.csv").exists() else []
        if old and old[0].get("corpus_revision") == REVISION and any(
                int(r["candidate_batch"]) != batch for r in old):
            raise ValueError("Use a new --root for a reserve batch; do not overwrite measured candidates")
        for row in old:
            path = destination/row["path"]
            if path.exists() and digest(path)!=row["content_sha256"]:
                raise ValueError(f"Locally edited query: {path}")
        managed = {r["path"] for r in old}
        present = {str(p.relative_to(destination)) for p in destination.glob("*/*.sql")}
        if present-managed:
            raise ValueError(f"Unmanaged SQL would contaminate corpus: {sorted(present-managed)}")
        retained = {r["path"] for r in records}
        for row in old:
            if row["path"] not in retained:
                (destination/row["path"]).unlink()
        for source in output.rglob("*"):
            if source.is_file():
                target=destination/source.relative_to(output)
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(source,target)
    print(f"Generated {len(records)} pending candidates: {len(balanced_records)} balanced "
          f"({per_family} per family, {per_family//3} per tier), "
          f"{len(records)-len(balanced_records)} historical supplementary cases")
    return len(records)


def validate(benchmark):
    rows=read_manifest(benchmark/"manifest.csv")
    if not rows or {r["path"] for r in rows} != {str(p.relative_to(benchmark)) for p in benchmark.glob("*/*.sql")}:
        raise ValueError("Manifest does not match the active SQL file set")
    identities=set()
    expected_cases = {r["query_id"]: r for r, _ in historical_cases()}
    restored = []
    for r in rows:
        if r["corpus_revision"] != REVISION or r["family"] not in FAMILIES:
            raise ValueError("Not a balanced candidate corpus")
        if Path(r["path"]).is_absolute() or ".." in Path(r["path"]).parts:
            raise ValueError("Unsafe manifest SQL path")
        path=benchmark/r["path"]
        sql=path.read_text()
        fp=sql_fingerprint(sql,r["family"])
        if fp in identities or fp!=r["sql_fingerprint"] or digest(path)!=r["content_sha256"]:
            raise ValueError(f"Duplicate or modified SQL: {path}")
        identities.add(fp)
        kinds=legacy.sql_join_kind_counts(sql)
        if len([k for k,n in kinds.items() if n])<2:
            raise ValueError(f"Non-mixed query: {path}")
        if r["qualification_status"]!="PENDING_CPU9_MEASUREMENT":
            raise ValueError("Generator cannot certify runtime performance")
        if r["qualification_timeout_seconds"] != str(QUALIFICATION_TIMEOUT_SECONDS):
            raise ValueError("Candidate has an obsolete qualification timeout; regenerate the corpus")
        if is_historical_case(r):
            expected = expected_cases.get(r["query_id"])
            if expected is None or any(str(r.get(k, "")) != str(v) for k, v in expected.items()):
                raise ValueError(f"Invalid historical supplementary case: {path}")
            restored.append(r["query_id"])
        elif float(r["target_max_fraction"])>.6 or r["calibration_in_range"]!="true":
            raise ValueError(f"Out-of-band cohort: {path}")
    balanced = [r for r in rows if not is_historical_case(r)]
    batches = {int(r["candidate_batch"]) for r in balanced}
    if len(batches) != 1 or set(restored) != (set(expected_cases) if batches == {0} else set()):
        raise ValueError("Historical cases must occur exactly once in the primary batch only")
    if {r["family"] for r in balanced} != set(FAMILIES) or len(set(Counter(r["family"] for r in balanced).values()))!=1:
        raise ValueError("Unequal family counts")
    if len(set(Counter((r["family"],r["semantic_tier"]) for r in balanced).values()))!=1:
        raise ValueError("Unequal family/tier counts")
    return rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-history",action="store_true")
    parser.add_argument("--bootstrap-design",action="store_true")
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--per-family",type=int,default=180)
    parser.add_argument("--batch",type=int,default=0)
    parser.add_argument("--duckdb",type=Path,default=legacy.REPO_ROOT/"build/release/duckdb")
    args=parser.parse_args()
    if args.freeze_history:
        freeze_history(args.root)
    elif args.bootstrap_design:
        bootstrap_design(args.duckdb,args.root)
    else:
        generate(args.root,args.per_family,args.batch)


if __name__=="__main__":
    main()
