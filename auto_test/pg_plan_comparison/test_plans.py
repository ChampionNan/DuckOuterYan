"""Regression tests for measurement/evidence errors that could alter conclusions."""

import filecmp
import json
import os
from pathlib import Path
import signal
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from plans import (accepted_pair, duck_tree, grouping, pg_tree, profile_metrics, query_text,
                   replay_verified, semantic, trace_evidence)
from run import Postgres, clean_and_sort, replay_diagnostics
import run as study_run


def scan(relation, rows=1):
    return {"operator_name": "SEQ_SCAN", "operator_cardinality": rows,
            "extra_info": {"Table": "snapshot.main." + relation}, "children": []}


def join(left, right, rows=1, kind="LEFT"):
    return {"operator_name": "HASH_JOIN", "operator_cardinality": rows,
            "extra_info": {"Join Type": kind}, "children": [left, right]}


class PlanTests(unittest.TestCase):
    def test_benchmark_header_hash_preserves_statement_identity(self):
        from benchmark_pg import query_sha256
        from fair_baseline import query_sha256 as simple_hash
        sql = "SELECT id FROM title WHERE title LIKE 'Ba%';"
        self.assertEqual(query_sha256(' \r\n-- corpus header\r\n-- source\r\n' + sql), simple_hash(sql))
        self.assertNotEqual(query_sha256(sql.replace('Ba%', 'Bb%')), simple_hash(sql))
        with self.assertRaises(ValueError):
            query_sha256(sql + ' SELECT 1;')

    def test_profile_quoted_identifier_matches_pg_name(self):
        self.assertEqual(duck_tree(scan('"name"'), True)['relation'], 'name')

    def test_repeated_table_occurrences_follow_source_aliases(self):
        left = {'Node Type': 'Seq Scan', 'Schema': 'pgplan_job', 'Relation Name': 'comp_cast_type',
                'Alias': 'cct2', 'Parent Relationship': 'Outer'}
        right = dict(left, Alias='cct1', **{'Parent Relationship': 'Inner'})
        tree = pg_tree({'Node Type': 'Hash Join', 'Join Type': 'Right', 'Plans': [left, right]},
                       'pgplan_job', {'cct1': 'comp_cast_type', 'cct2': 'comp_cast_type'},
                       {'cct1': 0, 'cct2': 1})
        self.assertEqual(tree['left']['occurrence'], 1)
        self.assertEqual(tree['right']['occurrence'], 0)
        self.assertEqual(semantic(tree), 'left(comp_cast_type#0,comp_cast_type#1)')

    def test_crlf_csv_uses_native_fast_path_and_preserves_raw_output(self):
        if not all(shutil.which(name) for name in ('grep', 'wc', 'tr')):
            self.skipTest('native CSV tools not installed')
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'crlf.csv'
            raw = b'NULL,-1,0,001\r\n1,2,3,4\r\nNULL,-1,0,001\r\n'
            p.write_bytes(raw)
            execute = study_run.subprocess.run
            calls = []

            def recorded(argv, **kwargs):
                calls.append(str(argv[0]))
                self.assertNotEqual(str(argv[0]), 'awk')
                return execute(argv, **kwargs)

            with patch('run.subprocess.run', side_effect=recorded):
                result, rows = clean_and_sort(p, 10)
            self.assertEqual(rows, 3)
            self.assertEqual(result.read_bytes(), b'1,2,3,4\nNULL,-1,0,001\nNULL,-1,0,001\n')
            self.assertEqual(p.read_bytes(), raw)
            self.assertIn('tr', calls)

    def test_native_result_check_matches_fallback_and_rejects_bad_rows(self):
        if not shutil.which('awk'):
            self.skipTest('awk not installed')
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'values.csv'
            valid = ['', 'NULL,-1,0,001\r\nNULL,-1,0,001\n',
                     '[PGPLAN] {"event":"verified"}\n1,2,3,4\n', '1,2,3,4']
            which = shutil.which
            for contents in valid:
                p.write_text(contents)
                native, native_rows = clean_and_sort(p, 10)
                native_bytes = native.read_bytes()
                with patch('run.shutil.which', side_effect=lambda n: None if n in ('awk', 'grep', 'wc') else which(n)):
                    fallback, fallback_rows = clean_and_sort(p, 10)
                self.assertEqual((native_rows, native_bytes), (fallback_rows, fallback.read_bytes()))
            for contents in ('1,2,3\n', '1,2,3,4,5\n', '1,2,,4\n', '1,2,+3,4\n',
                             '1,2,3.0,4\n', '1,2, 3,4\n', '1,2,--3,4\n',
                             '1,2,٣,4\n', '1,2,3\r,4\n', '1,2,3,4\nError: failed\n',
                             '[PGPLAN] invalid-json\n1,2,3,4\n'):
                p.write_text(contents)
                with self.assertRaises(ValueError):
                    clean_and_sort(p, 10)

    def test_replay_diagnostics_only_reads_prefixed_records(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'result.csv'
            p.write_text('1,2,3,4\n[PGPLAN] {"event":"verified"}\nother [PGPLAN] text\n')
            self.assertEqual(replay_diagnostics(p), '[PGPLAN] {"event":"verified"}\n')
            p.write_text('1,2,3,4\n')
            self.assertEqual(replay_diagnostics(p), '')

    def test_completed_case_is_saved_before_later_case_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'results'
            args = SimpleNamespace(out=out, duckdb=Path('/duckdb'),
                                   pg_bin_dir=Path('/pg/bin'), case='both', plans_only=False)
            row = {'case': 'A', 'plan': 'OuterYan', 'runtime_median_ms': 12.5}
            with patch('run.parse_args', return_value=args), \
                 patch('run.sha256', return_value='a' * 64), \
                 patch('run.Postgres'), \
                 patch('run.prepare_case', side_effect=[('SELECT 1', Path('/db'), {}),
                                                       RuntimeError('second case interrupted')]), \
                 patch('run.capture', return_value=(Path('/plan'), {'eligible': True})), \
                 patch('run.correctness', return_value={}), \
                 patch('run.measure', return_value=([row], {})), \
                 patch('run.assert_unchanged'), patch('run.report'):
                with self.assertRaisesRegex(RuntimeError, 'second case interrupted'):
                    study_run.main()
            self.assertEqual(json.loads((out / 'case_a/measurements.json').read_text()), [row])
            self.assertIn('A,OuterYan,12.5', (out / 'summary.csv').read_text())
            self.assertEqual(json.loads((out / 'status.json').read_text())['status'], 'failed')

    def test_pg_cleanup_survives_repeated_interrupt_and_restores_handlers(self):
        handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
        with tempfile.TemporaryDirectory() as directory:
            pg = Postgres(SimpleNamespace(pg_bin_dir=Path('/pg/bin')), Path(directory))
            pg.data.mkdir()
            (pg.data / 'postmaster.pid').write_text('123\n')
            pg.socket = tempfile.TemporaryDirectory(dir=directory)
            socket_path = Path(pg.socket.name)

            def stop(argv):
                self.assertEqual(str(argv[0]), '/pg/bin/pg_ctl')
                for sig in handlers:
                    os.kill(os.getpid(), sig)
                (pg.data / 'postmaster.pid').unlink()

            with patch('run.command', side_effect=stop):
                pg.close()
            self.assertFalse(socket_path.exists())
        self.assertEqual({sig: signal.getsignal(sig) for sig in handlers}, handlers)

    def test_pg_stop_failure_is_visible_and_restores_handlers(self):
        handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
        with tempfile.TemporaryDirectory() as directory:
            pg = Postgres(SimpleNamespace(pg_bin_dir=Path('/pg/bin')), Path(directory))
            pg.data.mkdir()
            (pg.data / 'postmaster.pid').write_text('123\n')
            with patch('run.command', side_effect=RuntimeError('pg_ctl failed')):
                with self.assertRaisesRegex(RuntimeError, 'pg_ctl failed'):
                    pg.close()
            self.assertTrue((pg.data / 'postmaster.pid').exists())
        self.assertEqual({sig: signal.getsignal(sig) for sig in handlers}, handlers)

    def test_child_swap_preserves_side_semantics_but_grouping_ignores_kind(self):
        left = duck_tree(join(scan("r1"), scan("r2"), kind="LEFT"), True)
        right = duck_tree(join(scan("r2"), scan("r1"), kind="RIGHT"), True)
        wrong = duck_tree(join(scan("r2"), scan("r1"), kind="LEFT"), True)
        self.assertEqual(semantic(left), semantic(right))
        self.assertNotEqual(semantic(left), semantic(wrong))
        self.assertEqual(grouping(left), grouping(wrong))

    def test_pg_parent_relationship_not_array_position_controls_orientation(self):
        a = {"Node Type": "Seq Scan", "Schema": "pgplan_graph", "Relation Name": "r1",
             "Alias": "r1", "Parent Relationship": "Inner"}
        b = {**a, "Relation Name": "r2", "Alias": "r2", "Parent Relationship": "Outer"}
        plan = pg_tree({"Node Type": "Hash Join", "Join Type": "Right", "Plans": [a, b]}, "pgplan_graph", {"r1": "r1", "r2": "r2"})
        self.assertEqual(plan["left"]["relation"], "r2")
        self.assertEqual(plan["right"]["relation"], "r1")
        a["Parent Relationship"] = "InitPlan"
        with self.assertRaises(ValueError):
            pg_tree({"Node Type": "Hash Join", "Join Type": "Right", "Plans": [a, b]}, "pgplan_graph", {"r1": "r1", "r2": "r2"})

    def test_actual_join_work_uses_reduced_child_output_and_excludes_sj(self):
        sj = {"operator_name": "SJ_PROBE_ROUND_2", "operator_cardinality": 2,
              "extra_info": {}, "children": [scan("r1", 100)]}
        profile = {"query_name": "SELECT 1;", "rows_returned": 9,
                   "children": [join(join(sj, scan("r2", 4), 7), scan("r3", 5), 9)]}
        tree, metrics = profile_metrics(profile, "SELECT 1")
        self.assertEqual(metrics["real_join_input_rows"], 2 + 4 + 7 + 5)
        self.assertEqual(metrics["max_intermediate_rows"], 9)
        self.assertEqual(metrics["max_nonroot_intermediate_rows"], 7)
        self.assertNotIn("SJ_", grouping(tree))
        with self.assertRaises(ValueError):
            profile_metrics(profile, "SELECT 2")
        del sj["operator_cardinality"]
        with self.assertRaises(ValueError):
            profile_metrics(profile, "SELECT 1")

    def test_reject_unknown_branches_instead_of_silently_dropping_them(self):
        plan = {"operator_name": "SJ_BUILD_ROUND_1", "children": [scan("r1"), scan("r2")]}
        with self.assertRaises(ValueError):
            duck_tree(plan, True)

    def test_pg_replay_requires_import_hash_and_final_verification(self):
        imported = {"event": "imported", "query_sha256_verified": True}
        verified = {"event": "verified", "expected_semantic_signature": "x", "final_semantic_signature": "x"}
        text = "\n".join("[PGPLAN] " + json.dumps(e) for e in (imported, verified))
        replay_verified(text, 1)
        with self.assertRaises(ValueError):
            replay_verified(text, 2)
        with self.assertRaises(ValueError):
            replay_verified("[PGPLAN] " + json.dumps(verified), 1)

    def test_legality_rejection_is_not_inferred_from_final_plan(self):
        tree = duck_tree(join(join(scan("r1"), scan("r2")), scan("r3")), True)
        trace = """PGOJ PAIR_PROPOSE rel1=(b 1) rel2=(b 2) union=(b 1 2)
PGOJ LEGAL_REJECT candidate=(b 1 2) oj=5 reason=RHS_CONFLICT
PGOJ PAIR_RESULT union=(b 1 2) accepted=0
"""
        self.assertEqual(trace_evidence(trace, tree, "A", {1: "r1", 2: "r2", 3: "r3"})["status"], "two_base_group_rejected")
        accepted = """PGOJ PAIR_PROPOSE rel1=(b 2) rel2=(b 1) union=(b 1 2)
PGOJ PAIR_RESULT canonical=(b 1 2 5) accepted=1
"""
        self.assertEqual(trace_evidence(trace + accepted, tree, "A", {1: "r1", 2: "r2", 3: "r3"})["status"], "unproven")
        self.assertEqual(trace_evidence("", tree, "A", {1: "r1", 2: "r2", 3: "r3"})["status"], "unproven")
        self.assertEqual(trace_evidence(trace.replace("candidate=(b 1 2)", "candidate=(b 2 3)"),
                                       tree, "A", {1: "r1", 2: "r2", 3: "r3"})["status"], "unproven")

    def test_full_barrier_requires_actual_crossing_and_uses_rte_mapping(self):
        tree = duck_tree(join(scan("r1"), join(scan("r2"), scan("r3"))), True)
        trace = "PGOJ FULL_BARRIER oj=3 left=(b 1) right=(b 2) action=MAKE_NESTED_SUBPROBLEM"
        self.assertEqual(trace_evidence(trace, tree, "B", {1: "r1", 2: "r2", 4: "r3"})["status"], "crosses_full_barrier")
        # The complete root boundary does not exclude an internal grouping.
        root_barrier = "PGOJ FULL_BARRIER oj=5 left=(b 1 2 3) right=(b 4)"
        self.assertEqual(trace_evidence(root_barrier, tree, "B", {1: "r1", 2: "r2", 4: "r3"})["status"], "unproven")
        same = duck_tree(join(join(scan("r1"), scan("r2")), scan("r3")), True)
        self.assertEqual(trace_evidence(trace, same, "B", {1: "r1", 2: "r2", 4: "r3"})["status"], "unproven")

    def test_positive_control_ignores_oj_ids_without_accepting_three_base_groups(self):
        mapping = {1: "title", 2: "movie_info", 3: "movie_keyword"}
        pair = {"title", "movie_info"}
        trace = "PGOJ PAIR_PROPOSE union=(b 1 2)\nPGOJ PAIR_RESULT canonical=(b 1 2 5) accepted=1"
        self.assertTrue(accepted_pair(trace, mapping, pair))
        self.assertFalse(accepted_pair(trace.replace("1 2", "1 2 3"), mapping, pair))
        self.assertFalse(accepted_pair(trace.split("\n")[1], mapping, pair))

    def test_result_comparison_retains_duplicates_and_nulls(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = (Path(directory) / name for name in ("a.csv", "b.csv"))
            one = "1,2,NULL,4\n"
            two = "1,2,3,NULL\n"
            a.write_text(one + one + two)
            b.write_text(two + one + one)
            sa, na = clean_and_sort(a, 10)
            sb, nb = clean_and_sort(b, 10)
            self.assertEqual((na, nb), (3, 3))
            self.assertTrue(filecmp.cmp(sa, sb, shallow=False))
            b.write_text(two + one)
            sb, _ = clean_and_sort(b, 10)
            self.assertFalse(filecmp.cmp(sa, sb, shallow=False))
            b.write_text("Error: query failed\n")
            with self.assertRaises(ValueError):
                clean_and_sort(b, 10)

    def test_query_hash_is_canonical_and_multiple_statements_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "q.sql"
            path.write_text("-- source\n SELECT 1;\n")
            self.assertEqual(query_text(path), "SELECT 1")
            for value in ("SELECT 1; SELECT 2;", "SELECT 1;;", "COPY x TO 'file';"):
                path.write_text(value)
                with self.assertRaises(ValueError):
                    query_text(path)


if __name__ == "__main__":
    unittest.main()
