#!/usr/bin/env python3
"""Exercise the real shell harness with a tiny, deterministic DuckDB stand-in."""

import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent


class MultiThreadExperimentTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="outeryan-threads-")
        self.root = Path(self.scratch.name)
        self.scripts = self.root / "auto_test"
        self.scripts.mkdir()
        for name in ("configs.sh", "thread_sweep.sh", "experiment_onoff.sh", "phase_profile.sh",
                     "gen_experiment_result.py", "benchmark_corpus.py"):
            shutil.copyfile(SCRIPT_DIR / name, self.scripts / name)
        corpus = self.root / "corpus" / "tpch"
        corpus.mkdir(parents=True)
        (corpus / "sample.sql").write_text("SELECT * FROM example;\n", encoding="utf-8")
        canonical = self.scripts / "outerjoin_benchmark" / "benchmark"
        family = canonical / "tpch"
        family.mkdir(parents=True)
        (family / "join__tpch__sample.sql").write_text("SELECT * FROM example;\n")
        (family / "aggregate__tpch__sample.sql").write_text("SELECT COUNT(*) FROM example;\n")
        (canonical / "selectivity_stress.txt").write_text("tpch/join__tpch__sample.sql\n")
        (canonical / "job_regressions.txt").write_text("tpch/join__tpch__sample.sql\n")
        self.database = self.root / "tpch.db"
        self.database.touch()
        self.calls = self.root / "calls.jsonl"
        self.duckdb = self.root / "duckdb"
        self.duckdb.write_text(f"#!{sys.executable}\n" + textwrap.dedent(r'''
            import json, os, re, sys
            from pathlib import Path
            sql = sys.stdin.read()
            match = re.search(r"PRAGMA threads=(\d+)", sql)
            if not match or int(match[1]) <= 1:
                sys.exit("Error: single-thread or implicit threads")
            threads = int(match[1])
            timing = ".timer on" in sql
            profiling = "CALL enable_profiling(" in sql
            off = "disabled_optimizers TO 'outer_yan'" in sql
            side = "off" if off else "on"
            def executed_schedule(profile=False):
                if os.environ.get("LEGACY_SCHEDULE_TRACE"):
                    return ""
                default_r1 = "0" if os.environ.get("SELECTED_PLAN") == "DUCKDB" else "1"
                prefix = "PROFILE_EXECUTED_" if profile else "EXECUTED_"
                r1 = os.environ.get(prefix + "R1", os.environ.get("EXECUTED_R1", default_r1))
                r2 = os.environ.get(prefix + "R2", os.environ.get("EXECUTED_R2", "0"))
                return (f" executed_round1_pairs={r1} executed_round1_filters={r1}"
                        f" executed_round2_pairs={r2} executed_round2_filters={r2}")
            if profiling and timing and not (sql.index("CALL enable_profiling(") < sql.index("PRAGMA disable_profiling;") < sql.index(".timer on")):
                sys.exit("Error: profile was not disabled before timing")
            with open(os.environ["HARNESS_CALLS"], "a") as log:
                log.write(json.dumps({"threads": threads, "timing": timing, "profiling": profiling,
                                      "argv": sys.argv[1:],
                                      "off": off, "sql": sql}) + "\n")
            if profiling:
                if os.environ.get("FAIL_PROFILE") in ("1", side):
                    print("OY_STAGE:profile")
                    print("Error: profile timeout", file=sys.stderr)
                    sys.exit(124)
                measured = re.findall(
                    r"save_location='([^']+)'[^\n]*\);\n(.*?);\n"
                    r"(?:PRAGMA disable_profiling;\n?|\Z)",
                    sql,
                    re.DOTALL,
                )
                for path, query in measured:
                    if os.environ.get("BAD_PROFILE_JSON"):
                        Path(path).write_text("invalid JSON")
                        continue
                    enabled = "optimizer_outeryan_" in path
                    total = 0.009 if enabled else 0.006
                    factor = 3
                    nodes = [
                        {"operator_name": name, "operator_type": kind,
                         "operator_timing": value * factor, "children": []}
                        for name, kind, value in [
                            ("SJ_BUILD_ROUND_1", "SJ_BUILD", 1),
                            ("SJ_PROBE_ROUND_1", "SJ_PROBE", 2),
                            ("HASH_JOIN", "HASH_JOIN", 3),
                            ("SEQ_SCAN", "TABLE_SCAN", 4),
                        ]
                    ]
                    if not enabled:
                        nodes = nodes[2:]
                    if enabled and os.environ.get("OMIT_SJ_PROFILE"):
                        nodes = nodes[2:]
                    if os.environ.get("BAD_PROFILE_ROUND") and enabled:
                        nodes[0]["operator_name"] = "SJ_BUILD_ROUND_2"
                    root = {
                        "query_name": f"{query};",
                        "all_optimizers": total,
                        "optimizer_outer_join_simplification": 0.001,
                        "optimizer_join_order": 0.002,
                        "latency": 6,
                        "cpu_time": 30,
                        "children": nodes,
                    }
                    Path(path).write_text(json.dumps(root))
                profile_trace = os.environ.get("DUCKDB_OY_PROFILE_TRACE")
                if profile_trace:
                    phase_fields = " ".join(
                        f"phase_{name}_s=0.0005" for name in (
                            "applicability", "build_ot", "simplification",
                            "semijoin_pair_planning", "desimplification",
                            "outeryan_join_reorder", "duckdb_simplification",
                            "duckdb_join_reorder", "cost_model", "resimplification",
                            "aggregate_pushdown_marking", "plan_lowering",
                            "semijoin_insertion", "aggregate_pushdown",
                        )
                    )
                    Path(profile_trace).write_text(f"[OY_DECISION] {phase_fields}{executed_schedule(True)}\n")
                    if os.environ.get("STALE_PROFILE_BINARY"):
                        with open(profile_trace, "a") as handle:
                            handle.write(f"[OY_DECISION] {phase_fields}\n")
            elif "EXPLAIN" in sql:
                trace = os.environ.get("DUCKDB_OYTRACE")
                if trace:
                    selected = os.environ.get("SELECTED_PLAN", "OUTERYAN")
                    aggregate = int(
                        os.environ.get("AGGREGATE_QUERY", "") == "1"
                        or bool(re.search(r"\b(?:COUNT|SUM|MIN|MAX)\s*\(", sql, re.IGNORECASE))
                    )
                    aggregate_pushdown = int(
                        os.environ.get(
                            "AGGREGATE_PUSHDOWN",
                            "1" if aggregate and selected == "OUTERYAN" else "0",
                        )
                        == "1"
                    )
                    reason = "COST_OUTERYAN_BETTER" if selected == "OUTERYAN" else "COST_DUCKDB_BETTER"
                    raw_winner = "OUTERYAN" if selected == "OUTERYAN" else "DUCKDB"
                    gate_result = "PASS" if selected == "OUTERYAN" else "FAIL"
                    Path(trace).write_text(
                        f"[OY_DECISION] formula_id=TEST selection_mode=GATED aggregate_query={aggregate} "
                        f"aggregate_pushdown_applied={aggregate_pushdown} "
                        f"selected_plan={selected} "
                        f"outer_reordered=1 cost_gate_applied=1 outer_yan_selected={int(selected == 'OUTERYAN')} "
                        f"reason={reason} raw_cost_winner={raw_winner} gate_result={gate_result} "
                        "baseline_proven_empty=0 "
                        "default_filter_upper_bound_checked=0 default_filter_upper_bound_selected=0 "
                        "full_reduction_cardinality_lower_bound_applied=0 uncertain_filter_amplification_guard=0 "
                        "stretch_cost_gate_eligible=0 stretch_cost_gate_selected=0 "
                        "low_selectivity_cost_gate_eligible=0 low_selectivity_cost_gate_selected=0 "
                        f"round1_pairs={os.environ.get('REFERENCE_R1', '1')} "
                        f"round2_pairs={os.environ.get('REFERENCE_R2', '0')}"
                        f"{executed_schedule()}\n"
                    )
                print("plan")
            if timing:
                print("OY_STAGE:timing")
                if os.environ.get("TIMEOUT_TIMING") in ("1", side):
                    sys.exit(124)
                if os.environ.get("FAIL_TIMING_THREADS") == str(threads):
                    sys.exit("Error: timing failed")
                count = len(re.findall(r"(?m)^SELECT ", sql.split(".timer on\n", 1)[1]))
                supplied = os.environ.get("TIMER_VALUES_" + side.upper())
                values = json.loads(supplied) if supplied else [(160 if off else 80) / threads] * count
                for seconds in values:
                    print(f"Run Time (s): real {seconds:.9f} user 0 sys 0")
            elif os.environ.get("DUCKDB_SJ_KERNEL_TRACE"):
                if os.environ.get("TIMEOUT_KERNEL"):
                    sys.exit("Error: INTERRUPT Error: Maximum execution time exceeded")
                print("[SJ_KERNEL] BITMAP", file=sys.stderr)
            elif "EXPLAIN" not in sql and not profiling:
                timeout_mode = os.environ.get("TIMEOUT_CORRECTNESS")
                if timeout_mode == "1" or timeout_mode == ("off" if off else "on"):
                    if os.environ.get("NATIVE_TIMEOUT"):
                        sys.exit("Error: INTERRUPT Error: Maximum execution time exceeded")
                    sys.exit(124)
                mismatch = os.environ.get("FAIL_CORRECTNESS_THREADS") == str(threads)
                print("43" if mismatch and not off else "42")
        ''').lstrip(), encoding="utf-8")
        self.duckdb.chmod(0o755)

    def tearDown(self):
        self.scratch.cleanup()

    def run_harness(self, *args, **overrides):
        use_default_corpus = overrides.pop("USE_DEFAULT_CORPUS", False)
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("OY_", "PGPLAN_", "PG_REPLAY_", "DUCKDB_"))}
        env.update({
            "DUCKDB_BIN": str(self.duckdb), "TPCH_DB": str(self.database),
            "OY_TMPDIR": str(self.root / "tmp"),
            "OY_TIMEOUT_SECS": "0", "HARNESS_CALLS": str(self.calls), "LC_ALL": "C",
        })
        if not use_default_corpus:
            env["OY_CORPUS"] = str(self.root / "corpus")
        env.update(overrides)
        result = subprocess.run(
            ["bash", str(self.scripts / "experiment_onoff.sh"), "--only", "tpch",
             "--capture-plans", "--out", str(self.root / "result.txt"), *args],
            env=env, text=True, capture_output=True, timeout=45,
        )
        return result

    def read_row(self):
        with (self.root / "result.csv").open(newline="") as handle:
            return next(csv.DictReader(handle))

    def mixed_graph_fixture(self):
        corpus = self.root / "mixed_graph"
        (corpus / "graph").mkdir(parents=True)
        records = []
        for index, dataset in enumerate(("bitcoin", "epinions"), start=1):
            relative = f"graph/graph__{dataset}.sql"
            sql = f"SELECT * FROM R1 WHERE src = {index};\n"
            (corpus / relative).write_text(sql)
            records.append(dict(query_id=f"graph__{dataset}", path=relative, family="graph",
                                graph_dataset=dataset, content_sha256=hashlib.sha256(sql.encode()).hexdigest()))
        with (corpus / "manifest.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, records[0].keys())
            writer.writeheader()
            writer.writerows(records)
        (corpus / "graph_dataset_promotion.json").write_text("{}")
        self.epinions = self.root / "graph_epinions.duckdb"
        self.epinions.touch()
        return corpus

    def test_mixed_graph_routes_each_statement_to_its_manifest_database(self):
        corpus = self.mixed_graph_fixture()
        result = self.run_harness("--only", "graph", OY_CORPUS=str(corpus),
                                  GRAPH_DB=str(self.database), GRAPH_EPINIONS_DB=str(self.epinions),
                                  GRAPH_DATASET="bitcoin")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with (self.root / "result.csv").open() as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual({r["graph_dataset"] for r in rows}, {"bitcoin", "epinions"})
        for row in rows:
            self.assertIn(row["graph_dataset"], row["query"])
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        for index, database in ((1, self.database), (2, self.epinions)):
            matching = [call for call in calls if f"src = {index}" in call["sql"]]
            self.assertTrue(matching)
            self.assertTrue(all(str(database) in call["argv"] for call in matching))

    def test_mixed_graph_rejects_shared_database_path_before_executing(self):
        corpus = self.mixed_graph_fixture()
        result = self.run_harness("--only", "graph", OY_CORPUS=str(corpus),
                                  GRAPH_DB=str(self.database), GRAPH_EPINIONS_DB=str(self.database),
                                  GRAPH_DATASET="bitcoin")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("database paths must differ", result.stderr)
        self.assertFalse(self.calls.exists())

    def assert_result(self, path, threads, expected_correct="TRUE", expected_speedup="2.000"):
        with path.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertNotIn(None, row)
        self.assertFalse(any(key.startswith("t1_") for key in row))
        self.assertIn("profile_status", row)
        for field in ("experiment_group", "corpus_revision", "corpus_scope", "workload_category", "query_class"):
            self.assertIn(field, row)
        self.assertEqual(row["timing_threads"], str(threads))
        self.assertEqual(row["correct"], expected_correct)
        self.assertEqual(row["tm_speedup"], expected_speedup)
        self.assertFalse(path.with_suffix(".attempts.csv").exists())
        report = path.with_suffix(".txt").read_text()
        self.assertNotIn("T1:", report)
        return report

    def test_default_timeout_is_ten_minutes_per_engine_and_is_recorded(self):
        result = self.run_harness(OY_TIMEOUT_SECS="")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.read_row()["timeout_seconds"], "600")
        self.assertEqual(self.read_row()["duckdb_timeout_seconds"], "600")
        self.assertEqual(self.read_row()["outeryan_timeout_seconds"], "600")
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertTrue(calls)
        self.assertTrue(all("SET max_execution_time=600000;" in call["sql"] for call in calls))
        self.assertIn("DuckDB=600s", (self.root / "result.txt").read_text())

    def test_five_sample_watchdog_does_not_replace_per_statement_timeout(self):
        # Observe the actual watchdog arguments without waiting for a slow SQL.
        binaries = self.root / "bin"
        binaries.mkdir()
        wrapper = binaries / "timeout"
        wrapper.write_text(f"#!{sys.executable}\n" + textwrap.dedent('''
            import json, os, sys
            with open(os.environ["HARNESS_TIMEOUT_CALLS"], "a") as handle:
                handle.write(json.dumps(sys.argv[1:]) + "\\n")
            os.execv(sys.argv[2], sys.argv[2:])
        ''').lstrip())
        wrapper.chmod(0o755)
        watchdogs = self.root / "watchdogs.jsonl"
        result = self.run_harness(
            "--timeout", "600", "--no-check-correctness",
            PATH=str(binaries) + os.pathsep + os.environ["PATH"],
            HARNESS_TIMEOUT_CALLS=str(watchdogs),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertTrue(all("SET max_execution_time=600000;" in c["sql"] for c in calls))
        limits = [json.loads(line)[0] for line in watchdogs.read_text().splitlines()]
        # One warm-up + one profile + five samples, independently for OFF/ON.
        self.assertEqual(limits.count("4230"), 2)
        self.assertTrue(all(limit in ("600", "4230") for limit in limits))
        for call in calls:
            if call["timing"]:
                self.assertEqual(call["sql"].split(".timer on\n")[1].count("SELECT * FROM example;"), 5)

    def test_input_filter_subqueries_do_not_inflate_relation_count(self):
        sql = ("SELECT R1.src FROM ((R1 R1 LEFT JOIN (SELECT src,dst FROM R2 WHERE src<=10) R2 "
               "ON R1.dst=R2.src) FULL JOIN (SELECT src,dst FROM R3 WHERE src<=10) R3 "
               "ON R2.dst=R3.src) WHERE R1.src<=2;\n")
        (self.root / "corpus/tpch/sample.sql").write_text(sql)
        result = self.run_harness()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read_row()["relation_count"], "3")
        self.assertEqual(self.read_row()["correct"], "TRUE")

    def test_default_warms_and_profiles_before_five_timings_in_each_process(self):
        result = self.run_harness()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = self.assert_result(self.root / "result.csv", 32)
        self.assertIn("# corpus : revision=custom", report)
        for label in ("query=sample", "result: correct=TRUE", "context: family=tpch", "decision: plan="):
            self.assertIn(label, report)
        self.assertFalse((self.root / "result_t16.csv").exists())
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual({call["threads"] for call in calls}, {32})
        timed = [call for call in calls if call["timing"]]
        self.assertEqual(len(timed), 2)
        self.assertTrue(all(call["sql"].count("SELECT * FROM example;") == 7 for call in timed))
        self.assertTrue(all("CALL disable_profiling();" in call["sql"] for call in calls))
        profiles = [call for call in calls if call["profiling"]]
        self.assertEqual(len(profiles), 2)
        self.assertNotIn("EXPLAIN", profiles[0]["sql"])
        self.assertTrue(profiles[0]["off"])
        self.assertEqual(profiles[0]["sql"].count("SELECT * FROM example;"), 7)
        self.assertEqual([call["off"] for call in profiles], [True, False])
        for call in timed:
            sql = call["sql"]
            self.assertLess(sql.index("CALL enable_profiling("), sql.index("PRAGMA disable_profiling;"))
            self.assertLess(sql.index("PRAGMA disable_profiling;"), sql.index(".timer on"))
            self.assertEqual(sql.split(".timer on\n")[1].count("SELECT * FROM example;"), 5)
        row = self.read_row()
        self.assertEqual(row["timeout_seconds"], "0")
        self.assertEqual(row["correctness_check"], "enabled")
        self.assertEqual(row["timing_samples"], "5")
        self.assertEqual(row["timing_estimator"], "median_post_warmup")
        self.assertEqual(row["warmup_runs_per_side"], "2")
        self.assertIn("correct=1  not-checked=0", report)
        checked = [call for call in calls if "EXPLAIN" not in call["sql"] and ".mode trash" not in call["sql"]]
        self.assertEqual([call["off"] for call in checked], [True, False])
        self.assertTrue(all(call["sql"].count("SELECT * FROM example;") == 1 for call in checked))
        self.assertEqual(len(row["sql_content_sha256"]), 64)
        self.assertEqual(len(row["database_signature"]), 64)
        self.assertTrue(row["execution_host"])
        self.assertEqual(row["profile_status"], "OK")
        self.assertEqual(row["profile_threads"], "32")
        self.assertEqual(row["profile_timed_samples"], "1")
        self.assertEqual(float(row["profile_wall_time_s"]), 6)
        self.assertEqual(float(row["profile_round1_operator_s"]), 9)
        self.assertEqual(float(row["profile_round2_operator_s"]), 0)
        self.assertEqual(float(row["profile_round3_operator_s"]), 9)
        self.assertEqual(float(row["profile_total_time_s"]), 30)
        self.assertEqual(float(row["profile_cpu_time_s"]), 30)
        self.assertEqual(float(row["profile_other_elapsed_s"]), 12)
        self.assertEqual(row["optimizer_profile_status"], "OK")
        self.assertEqual(row["optimizer_timed_samples"], "1")
        self.assertEqual(float(row["optimizer_duckdb_total_s"]), 0.006)
        self.assertEqual(float(row["optimizer_outeryan_total_s"]), 0.0095)
        self.assertAlmostEqual(
            float(row["optimizer_outeryan_to_duckdb_ratio"]), 0.0095 / 0.006
        )
        self.assertIn("desimplification", json.loads(row["optimizer_outeryan_phases_json"]))
        self.assertEqual(row["profile_directory"], "-")
        self.assertFalse((self.root / "result.profiles").exists())

    def test_phase_validation_uses_executed_not_costed_schedule(self):
        result = self.run_harness(REFERENCE_R1="3", REFERENCE_R2="2", EXECUTED_R1="1", EXECUTED_R2="0")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        row = self.read_row()
        self.assertEqual(row["profile_status"], "OK")
        self.assertEqual(row["round1_pairs"], "3")
        self.assertEqual(row["round2_pairs"], "2")
        self.assertEqual(row["executed_round1_pairs"], "1")
        self.assertEqual(row["executed_round2_pairs"], "0")
        self.assertEqual(row["executed_round1_filters"], "1")
        self.assertEqual(row["executed_round2_filters"], "0")
        self.assertNotIn(None, row)
        self.assertIn("executed_SJ=[R1(pairs=1 filters=1) R2(pairs=0 filters=0)]",
                      (self.root / "result.txt").read_text())

    def test_partial_reduction_can_eliminate_both_rounds(self):
        result = self.run_harness(REFERENCE_R1="3", REFERENCE_R2="2", EXECUTED_R1="0", EXECUTED_R2="0",
                                  OMIT_SJ_PROFILE="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        row = self.read_row()
        self.assertEqual(row["profile_status"], "OK")
        self.assertEqual(row["executed_round1_pairs"], "0")
        self.assertEqual(row["executed_round2_pairs"], "0")
        self.assertEqual(float(row["profile_round1_operator_s"]), 0)
        self.assertEqual(float(row["profile_round2_operator_s"]), 0)

    def test_profiled_schedule_takes_precedence_over_explain(self):
        result = self.run_harness(EXECUTED_R2="1", PROFILE_EXECUTED_R2="0")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        row = self.read_row()
        self.assertEqual(row["profile_status"], "OK")
        self.assertEqual(row["executed_round2_pairs"], "0")

    def test_executed_schedule_still_detects_missing_required_round(self):
        result = self.run_harness(REFERENCE_R2="0", EXECUTED_R2="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        row = self.read_row()
        self.assertEqual(row["profile_status"], "ERROR")
        self.assertEqual(row["executed_round2_pairs"], "1")
        self.assertEqual(row["profile_round2_operator_s"], "NA")
        self.assertIn("R2 has planned pairs but did not run", result.stderr)

    def test_legacy_schedule_trace_keeps_cost_count_fallback(self):
        result = self.run_harness(LEGACY_SCHEDULE_TRACE="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        row = self.read_row()
        self.assertEqual(row["profile_status"], "OK")
        self.assertEqual(row["round1_pairs"], "1")
        self.assertEqual(row["executed_round1_pairs"], "NA")
        self.assertEqual(row["executed_round2_pairs"], "NA")

    def test_query_type_selects_only_matching_sql(self):
        graph = self.scripts / "outerjoin_benchmark/benchmark/tpch/graph__tpch__sample.sql"
        graph.write_text("SELECT * FROM example;\n")
        for kind in ("aggregate", "graph"):
            with self.subTest(query_type=kind):
                result = self.run_harness("--query-type", kind, "--only", "all", USE_DEFAULT_CORPUS=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                row = self.read_row()
                self.assertEqual(row["workload_category"], kind)
                self.assertTrue(row["query"].startswith(kind + "__tpch__"))
        invalid = self.run_harness("--version", "v2")
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("Version selection is retired", invalid.stderr)

    def test_diagnostic_scope_references_the_same_canonical_sql(self):
        result = self.run_harness("--only", "all", "--corpus-scope", "selectivity-stress",
                                  USE_DEFAULT_CORPUS=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        row = self.read_row()
        self.assertEqual(row["query"], "join__tpch__sample")
        self.assertEqual(row["corpus_scope"], "selectivity-stress")
        self.assertEqual(row["workload_category"], "join")

    def test_default_runs_each_query_once_in_one_result_file(self):
        result = self.run_harness(USE_DEFAULT_CORPUS=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with (self.root / "result.csv").open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["workload_category"] for row in rows}, {"join", "aggregate"})
        self.assertEqual(len(list(self.root.glob("result*.csv"))), 1)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual(len([call for call in calls if call["timing"]]), 4)

    def test_explicit_sweep_runs_16_then_32(self):
        result = self.run_harness("--threads", "16,32")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for threads in (16, 32):
            self.assert_result(self.root / f"result_t{threads}.csv", threads)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual({call["threads"] for call in calls}, {16, 32})
        self.assertEqual([call["threads"] for call in calls], sorted(call["threads"] for call in calls))
        timed = [call for call in calls if call["timing"]]
        self.assertEqual(len(timed), 4)
        self.assertTrue(all(call["sql"].count("SELECT * FROM example;") == 7 for call in timed))
        self.assertTrue(all("CALL disable_profiling();" in call["sql"] for call in calls))
        self.assertEqual([call["threads"] for call in calls if call["profiling"]], [16, 16, 32, 32])

    def test_cli_single_override_takes_precedence_and_preserves_explicit_out(self):
        result = self.run_harness("--threads", "8", OY_THREAD_COUNTS="16 32")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_result(self.root / "result.csv", 8)
        self.assertFalse((self.root / "result_t16.csv").exists())

    def test_scalar_environment_override_runs_once(self):
        result = self.run_harness(OY_THREADS="8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_result(self.root / "result.csv", 8)

    def test_invalid_thread_lists_do_not_execute_queries(self):
        for specification in ("", "1", "16 1", "16,16", "0", "-2", "16 nope"):
            with self.subTest(specification=specification):
                result = self.run_harness("--threads", specification)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertFalse(self.calls.exists())

    def test_failed_correctness_is_not_timed_but_other_thread_config_runs(self):
        result = self.run_harness("--check-correctness", "--threads", "16,32", FAIL_CORRECTNESS_THREADS="16")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_result(self.root / "result_t16.csv", 16, "FALSE", "-")
        self.assert_result(self.root / "result_t32.csv", 32, "TRUE")
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertFalse(any(call["timing"] and call["threads"] == 16 for call in calls))
        self.assertFalse(any(call["profiling"] and call["threads"] == 16 for call in calls))

    def assert_correctness_timeout(self, mode, **overrides):
        result = self.run_harness("--check-correctness", TIMEOUT_CORRECTNESS=mode, **overrides)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = self.assert_result(
            self.root / "result.csv", 32, expected_correct="TIMEOUT", expected_speedup="NA"
        )
        for output in (result.stderr, report):
            self.assertIn("result: correct=TIMEOUT", output)
            self.assertNotIn("result: correct=FALSE", output)
            self.assertIn(f"TIMEOUT (0s, {mode}): sample", output)
        row = self.read_row()
        failed, completed = ("duckdb", "outeryan") if mode == "off" else ("outeryan", "duckdb")
        self.assertIn(f"TIMEOUT-{mode.upper()}-CORRECTNESS", row["note"])
        self.assertEqual(row[f"{failed}_status"], "timeout")
        self.assertEqual(row[f"{failed}_timeout_stage"], "correctness")
        self.assertEqual(row[f"{completed}_status"], "measured")
        self.assertEqual(row[f"{completed}_correctness_status"], "ok")
        self.assertEqual(row["tm_off" if mode == "off" else "tm_on"], "NA")
        self.assertGreater(float(row["tm_on" if mode == "off" else "tm_off"]), 0)
        self.assertEqual(row["optimizer_profile_status"], "PARTIAL")
        self.assertGreater(float(row[f"optimizer_{completed}_total_s"]), 0)
        self.assertEqual(row[f"optimizer_{failed}_total_s"], "NA")
        self.assertEqual(row["optimizer_overhead_s"], "NA")
        self.assertEqual(row["profile_status"], "OK" if mode == "off" else "timeout")
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        executions = [call for call in calls if "EXPLAIN" not in call["sql"]]
        # Both equivalence executions occur; the timed-out side is never retried.
        self.assertEqual([c["off"] for c in executions[:2]], [True, False])
        self.assertEqual(len([c for c in executions if c["off"] == (mode == "off")]), 1)
        timed = [c for c in executions if c["timing"]]
        self.assertEqual(len(timed), 1)
        self.assertEqual(timed[0]["off"], mode != "off")
        self.assertIn("correct=0", report)
        self.assertIn("timed=0", report)

    def test_correctness_off_timeout_is_recorded_once_without_retry(self):
        self.assert_correctness_timeout("off")

    def test_correctness_on_timeout_is_recorded_once_without_retry(self):
        self.assert_correctness_timeout("on")

    def test_native_correctness_timeout_is_not_misclassified_as_error(self):
        self.assert_correctness_timeout("off", NATIVE_TIMEOUT="1")

    def test_both_correctness_timeouts_are_attempted_once_without_measurement(self):
        result = self.run_harness(TIMEOUT_CORRECTNESS="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read_row()["correct"], "TIMEOUT")
        self.assertEqual(self.read_row()["duckdb_status"], "timeout")
        self.assertEqual(self.read_row()["outeryan_status"], "timeout")
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertFalse(any(call["timing"] or call["profiling"] for call in calls))
        self.assertEqual(len([call for call in calls if "EXPLAIN" not in call["sql"]]), 2)

    def test_explicit_correctness_opt_out_remains_unchecked(self):
        result = self.run_harness("--no-check-correctness")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_result(self.root / "result.csv", 32, expected_correct="NOT-CHECKED")
        self.assertEqual(self.read_row()["correctness_check"], "disabled")

    def test_check_flag_overrides_stale_disabled_environment(self):
        result = self.run_harness("--check-correctness", OY_CHECK_CORRECTNESS="0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read_row()["correct"], "TRUE")
        self.assertEqual(self.read_row()["correctness_check"], "enabled")

    def test_off_timing_timeout_does_not_stop_outeryan(self):
        result = self.run_harness(TIMEOUT_TIMING="off")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = self.assert_result(
            self.root / "result.csv", 32, expected_speedup="NA"
        )
        row = self.read_row()
        self.assertIn("TIMEOUT-OFF-TIMING", row["note"])
        self.assertEqual(row["duckdb_status"], "timeout")
        self.assertEqual(row["outeryan_status"], "measured")
        self.assertEqual(row["tm_on"], "2.500000000")
        self.assertEqual(row["optimizer_profile_status"], "PARTIAL")
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        timed = [call for call in calls if call["timing"]]
        self.assertEqual(len(timed), 2)
        self.assertTrue(timed[0]["off"])
        self.assertTrue(timed[0]["profiling"])
        self.assertIn("timed=0", report)

    def test_failed_timing_is_not_counted_as_measured(self):
        result = self.run_harness("--threads", "16", FAIL_TIMING_THREADS="16")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = self.assert_result(self.root / "result.csv", 16, expected_speedup="NA")
        self.assertIn("timed=0", report)

    def test_side_specific_timeouts_override_common_limit(self):
        result = self.run_harness("--duckdb-timeout", "0", "--outeryan-timeout", "7", "--timeout", "600")
        self.assertEqual(result.returncode, 0, result.stderr)
        row = self.read_row()
        self.assertEqual(row["timeout_seconds"], "NA")
        self.assertEqual(row["duckdb_timeout_seconds"], "0")
        self.assertEqual(row["outeryan_timeout_seconds"], "7")
        for call in [json.loads(line) for line in self.calls.read_text().splitlines()]:
            if call["off"]:
                self.assertNotIn("SET max_execution_time=", call["sql"])
            else:
                self.assertIn("SET max_execution_time=7000;", call["sql"])

    def test_side_specific_environment_limits(self):
        result = self.run_harness(OY_DUCKDB_TIMEOUT_SECS="11", OY_OUTERYAN_TIMEOUT_SECS="13")
        self.assertEqual(result.returncode, 0, result.stderr)
        for call in [json.loads(line) for line in self.calls.read_text().splitlines()]:
            self.assertIn(f"SET max_execution_time={11000 if call['off'] else 13000};", call["sql"])

    def test_profile_and_timing_failures_preserve_other_engine_measurements(self):
        for failure in ("FAIL_PROFILE", "TIMEOUT_TIMING"):
            for side in ("off", "on"):
                with self.subTest(failure=failure, side=side):
                    if self.calls.exists():
                        self.calls.unlink()
                    result = self.run_harness(**{failure: side})
                    self.assertEqual(result.returncode, 0, result.stderr)
                    row = self.read_row()
                    failed, completed = ("duckdb", "outeryan") if side == "off" else ("outeryan", "duckdb")
                    self.assertEqual(row[f"{failed}_status"], "timeout")
                    self.assertEqual(row[f"{completed}_status"], "measured")
                    self.assertEqual(row[f"tm_{side}"], "NA")
                    self.assertGreater(float(row["tm_on" if side == "off" else "tm_off"]), 0)
                    self.assertEqual(row["tm_speedup"], "NA")
                    self.assertEqual(row["optimizer_profile_status"], "PARTIAL")
                    calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
                    self.assertEqual(len([c for c in calls if c["timing"]]), 2)


    def test_stale_binary_cannot_publish_trace_contaminated_timings(self):
        result = self.run_harness(STALE_PROFILE_BINARY="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        row = self.read_row()
        self.assertEqual(row["timing_status"], "error")
        self.assertEqual(row["tm_on"], "NA")
        self.assertEqual(row["tm_speedup"], "NA")

    def test_profile_timeout_stops_before_formal_measurement_without_retry(self):
        result = self.run_harness(FAIL_PROFILE="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        row = self.read_row()
        self.assertIn("TIMEOUT-OFF-PROFILE", row["note"])
        self.assertIn("TIMEOUT-ON-PROFILE", row["note"])
        self.assertEqual(row["timing_status"], "timeout")
        self.assertEqual(row["tm_off"], "NA")
        self.assertEqual(row["tm_on"], "NA")
        self.assertEqual(row["correct"], "TRUE")
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual(len([c for c in calls if c["profiling"]]), 2)
        self.assertTrue(Path(row["profile_directory"]).is_dir())

    def test_explicit_three_samples_still_exclude_all_warmup_work(self):
        result = self.run_harness("--runs", "3")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_result(self.root / "result.csv", 32)
        row = self.read_row()
        self.assertEqual(row["timing_samples"], "3")
        self.assertEqual(row["timing_estimator"], "median_post_warmup")
        for call in [json.loads(line) for line in self.calls.read_text().splitlines()]:
            if call["timing"]:
                self.assertEqual(call["sql"].count("SELECT * FROM example;"), 5)
                self.assertEqual(call["sql"].split(".timer on\n")[1].count("SELECT * FROM example;"), 3)

    def test_default_uses_all_five_samples_and_ratio_of_independent_medians(self):
        result = self.run_harness(TIMER_VALUES_OFF="[11, 5, 9, 1, 7]",
                                  TIMER_VALUES_ON="[4, 1, 2, 8, 3]")
        self.assertEqual(result.returncode, 0, result.stderr)
        row = self.read_row()
        self.assertEqual(float(row["tm_off"]), 7)
        self.assertEqual(float(row["tm_on"]), 3)
        self.assertEqual(row["tm_speedup"], "2.333")
        self.assertEqual(row["timing_samples"], "5")

    def test_incomplete_five_samples_do_not_produce_partial_median(self):
        result = self.run_harness(TIMER_VALUES_OFF="[11, 5, 9]")
        self.assertEqual(result.returncode, 0, result.stderr)
        row = self.read_row()
        self.assertEqual(row["timing_status"], "error")
        self.assertEqual(row["tm_off"], "NA")
        self.assertEqual(row["tm_speedup"], "NA")
        self.assertEqual(row["outeryan_status"], "measured")

    def test_cli_runs_override_environment_and_can_select_one_sample(self):
        result = self.run_harness("--runs", "1", OY_RUNS="3")
        self.assertEqual(result.returncode, 0, result.stderr)
        row = self.read_row()
        self.assertEqual(row["timing_samples"], "1")
        self.assertEqual(row["timing_estimator"], "single_post_warmup")
        for call in [json.loads(line) for line in self.calls.read_text().splitlines()]:
            if call["timing"]:
                self.assertEqual(call["sql"].count("SELECT * FROM example;"), 3)

    def test_environment_runs_override_default(self):
        result = self.run_harness(OY_RUNS="3")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read_row()["timing_samples"], "3")

    def test_no_profile_flag_preserves_unprofiled_performance(self):
        result = self.run_harness("--no-profile")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_result(self.root / "result.csv", 32)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertFalse(any(call["profiling"] for call in calls))
        row = self.read_row()
        self.assertEqual(row["profile_status"], "disabled")
        self.assertEqual(row["profile_wall_time_s"], "NA")
        self.assertEqual(row["profile_total_time_s"], "NA")
        self.assertEqual(row["optimizer_profile_status"], "disabled")
        self.assertEqual(row["warmup_runs_per_side"], "1")
        for call in calls:
            if call["timing"]:
                self.assertEqual(call["sql"].count("SELECT * FROM example;"), 6)
        self.assertFalse((self.root / "result.profiles").exists())

    def test_profile_flag_overrides_environment(self):
        result = self.run_harness("--profile", OY_PROFILE="0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_result(self.root / "result.csv", 32)
        row = self.read_row()
        self.assertEqual(row["profile_status"], "OK")

    def test_native_kernel_timeout_stops_only_outeryan_not_duckdb(self):
        result = self.run_harness(TIMEOUT_KERNEL="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        row = self.read_row()
        self.assertEqual(row["timing_status"], "timeout")
        self.assertIn("TIMEOUT-ON-KERNEL", row["note"])
        self.assertGreater(float(row["tm_off"]), 0)
        self.assertEqual(row["tm_on"], "NA")
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        timed = [call for call in calls if call["timing"]]
        self.assertEqual(len(timed), 1)
        self.assertTrue(timed[0]["off"])
        execution = [call for call in calls if "EXPLAIN" not in call["sql"]]
        self.assertEqual(len(execution), 4)
        self.assertIn(".mode trash", execution[2]["sql"])

    def test_nonaggregate_duckdb_fallback_checks_equivalence_but_skips_timing(self):
        result = self.run_harness(SELECTED_PLAN="DUCKDB")
        self.assertEqual(result.returncode, 0, result.stderr)
        row = self.read_row()
        self.assertEqual(row["aggregate_query"], "0")
        self.assertEqual(row["correct"], "TRUE")
        self.assertEqual(row["note"], "FALLBACK-SKIP")
        self.assertEqual(row["timing_status"], "fallback-skip")
        self.assertEqual(row["profile_status"], "fallback-skip")
        self.assertEqual(row["optimizer_profile_status"], "fallback-skip")
        self.assertEqual(row["tm_off"], "NA")
        self.assertEqual(row["tm_on"], "NA")
        self.assertEqual(row["tm_speedup"], "1.000")
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertFalse(any(call["timing"] for call in calls))
        self.assertFalse(any(call["profiling"] for call in calls))
        checked = [call for call in calls if "EXPLAIN" not in call["sql"]]
        self.assertEqual([call["off"] for call in checked], [True, False])
        self.assertTrue(all(".mode trash" not in call["sql"] for call in checked))
        report = (self.root / "result.txt").read_text()
        self.assertIn("correct=1  not-checked=0  fallback-skip=1  incorrect/not-run=0  timed=0", report)

    def test_fallback_mismatch_is_not_hidden_by_default_speedup(self):
        result = self.run_harness(SELECTED_PLAN="DUCKDB", FAIL_CORRECTNESS_THREADS="32")
        self.assertEqual(result.returncode, 0, result.stderr)
        row = self.read_row()
        self.assertEqual(row["correct"], "FALSE")
        self.assertEqual(row["note"], "NOT-EQUIV")
        self.assertEqual(row["timing_status"], "not-run")
        self.assertNotEqual(row["tm_speedup"], "1.000")
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertFalse(any(call["timing"] or call["profiling"] for call in calls))

    def test_fallback_opt_out_skips_all_execution(self):
        result = self.run_harness("--no-check-correctness", SELECTED_PLAN="DUCKDB")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read_row()["correct"], "SKIPPED")
        self.assertEqual(self.read_row()["timing_status"], "fallback-skip")
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertTrue(all("EXPLAIN" in call["sql"] for call in calls))

    def test_aggregate_duckdb_fallback_without_pushdown_is_skipped(self):
        result = self.run_harness(SELECTED_PLAN="DUCKDB", AGGREGATE_QUERY="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        row = self.read_row()
        self.assertEqual(row["aggregate_query"], "1")
        self.assertEqual(row["aggregate_pushdown_applied"], "0")
        self.assertEqual(row["correct"], "TRUE")
        self.assertEqual(row["note"], "FALLBACK-SKIP")
        self.assertEqual(row["timing_status"], "fallback-skip")
        self.assertEqual(row["tm_speedup"], "1.000")
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertFalse(any(call["timing"] for call in calls))

    def test_aggregate_outeryan_without_pushdown_is_executed(self):
        (self.root / "corpus/tpch/sample.sql").write_text("SELECT COUNT(*) FROM example;\n")
        result = self.run_harness(AGGREGATE_PUSHDOWN="0")
        self.assertEqual(result.returncode, 0, result.stderr)
        row = self.read_row()
        self.assertEqual(row["aggregate_query"], "1")
        self.assertEqual(row["aggregate_pushdown_applied"], "0")
        self.assertEqual(row["selected_plan"], "OUTERYAN")
        self.assertEqual(row["outer_yan_selected"], "1")
        self.assertEqual(row["correct"], "TRUE")
        self.assertEqual(row["note"], "OK")
        self.assertEqual(row["timing_status"], "measured")
        self.assertEqual(row["tm_speedup"], "2.000")
        self.assertEqual(row["profile_status"], "OK")
        self.assertEqual(row["optimizer_profile_status"], "OK")
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual([call["off"] for call in calls if call["timing"]], [True, False])
        checked = [call for call in calls if "EXPLAIN" not in call["sql"] and ".mode trash" not in call["sql"]]
        self.assertEqual([call["off"] for call in checked], [True, False])

    def test_unchecked_aggregate_outeryan_without_pushdown_is_measured_with_or_without_profiles(self):
        query = "SELECT COUNT(*) FROM example;"
        (self.root / "corpus/tpch/sample.sql").write_text(query + "\n")
        for profile in (True, False):
            with self.subTest(profile=profile):
                self.calls.unlink(missing_ok=True)
                result = self.run_harness(
                    "--no-check-correctness", "--profile" if profile else "--no-profile",
                    AGGREGATE_PUSHDOWN="0",
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                row = self.read_row()
                self.assertEqual(row["aggregate_query"], "1")
                self.assertEqual(row["aggregate_pushdown_applied"], "0")
                self.assertEqual(row["selected_plan"], "OUTERYAN")
                self.assertEqual(row["outer_yan_selected"], "1")
                self.assertEqual(row["correct"], "NOT-CHECKED")
                self.assertEqual(row["correctness_check"], "disabled")
                self.assertEqual(row["note"], "OK;CORRECTNESS-NOT-CHECKED")
                self.assertEqual(row["timing_status"], "measured")
                self.assertEqual(row["duckdb_status"], "measured")
                self.assertEqual(row["outeryan_status"], "measured")
                self.assertEqual(float(row["tm_off"]), 5)
                self.assertEqual(float(row["tm_on"]), 2.5)
                self.assertEqual(row["tm_speedup"], "2.000")
                self.assertEqual(row["profile_status"], "OK" if profile else "disabled")
                self.assertEqual(row["optimizer_profile_status"], "OK" if profile else "disabled")
                self.assertEqual(row["timing_samples"], "5")
                self.assertEqual(row["timing_estimator"], "median_post_warmup")
                self.assertEqual(row["warmup_runs_per_side"], "2" if profile else "1")
                calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
                self.assertTrue(all("EXPLAIN" in call["sql"] or ".mode trash" in call["sql"] for call in calls))
                timed = [call for call in calls if call["timing"]]
                self.assertEqual([call["off"] for call in timed], [True, False])
                self.assertEqual(len([call for call in calls if call["profiling"]]), 2 if profile else 0)
                for call in timed:
                    self.assertEqual(call["sql"].count(query), 7 if profile else 6)
                    self.assertEqual(call["sql"].split(".timer on\n")[1].count(query), 5)

    def test_aggregate_outeryan_with_pushdown_is_executed(self):
        result = self.run_harness(AGGREGATE_QUERY="1", AGGREGATE_PUSHDOWN="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        row = self.read_row()
        self.assertEqual(row["aggregate_query"], "1")
        self.assertEqual(row["aggregate_pushdown_applied"], "1")
        self.assertEqual(row["correct"], "TRUE")
        self.assertEqual(row["note"], "OK")
        self.assertEqual(row["timing_status"], "measured")
        self.assertEqual(row["tm_speedup"], "2.000")
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual(len([call for call in calls if call["timing"]]), 2)

    def test_profile_failures_keep_timing_and_do_not_fabricate_phases(self):
        for failure in ("BAD_PROFILE_JSON", "BAD_PROFILE_ROUND"):
            with self.subTest(failure=failure):
                result = self.run_harness(**{failure: "1"})
                self.assertEqual(result.returncode, 0, result.stderr)
                report = self.assert_result(self.root / "result.csv", 32)
                row = self.read_row()
                expected_status = "timeout" if failure == "FAIL_PROFILE" else "ERROR"
                self.assertEqual(row["profile_status"], expected_status)
                self.assertEqual(row["profile_wall_time_s"], "NA")
                self.assertEqual(row["profile_total_time_s"], "NA")
                self.assertEqual(row["profile_round1_operator_s"], "NA")
                self.assertTrue(Path(row["profile_directory"]).is_dir())
                self.assertIn(
                    "TIMEOUT-PROFILE" if failure == "FAIL_PROFILE" else "PROFILE-ERROR",
                    report,
                )

    def test_invalid_profile_setting_does_not_execute_queries(self):
        result = self.run_harness(OY_PROFILE="sometimes")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(self.calls.exists())


if __name__ == "__main__":
    unittest.main()
