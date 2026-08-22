#!/usr/bin/env python3

import copy
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
MODULE_PATH = SCRIPT_DIR / "normalize_plan.py"
SPEC = importlib.util.spec_from_file_location("normalize_plan", MODULE_PATH)
NORMALIZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NORMALIZER)


def load_fixture(name):
    with (SCRIPT_DIR / "fixtures" / name).open(encoding="utf-8") as source:
        return json.load(source)


def normalize(name, query=b"SELECT 1;\n"):
    return NORMALIZER.normalize_explain(load_fixture(name), query, 160002)


class FixtureExtractionTest(unittest.TestCase):
    def test_hash_left_removes_hash_and_keeps_orientation(self):
        tree = normalize("hash_left.json")["tree"]
        self.assertEqual(tree["op"], "join")
        self.assertEqual(tree["join_type"], "left")
        self.assertEqual(tree["left"]["relation"], "nation")
        self.assertEqual(tree["right"]["relation"], "supplier")
        self.assertEqual(
            tree["diagnostics"]["predicates"]["hash_cond"],
            "(n.n_nationkey = s.s_nationkey)",
        )
        self.assertEqual(
            tree["right"]["diagnostics"]["wrappers"][0]["postgres_node_type"],
            "Hash",
        )

    def test_merge_right_removes_both_sorts(self):
        tree = normalize("merge_right.json")["tree"]
        self.assertEqual(tree["join_type"], "right")
        self.assertEqual(tree["left"]["relation"], "part")
        self.assertEqual(tree["right"]["relation"], "partsupp")
        self.assertEqual(
            tree["left"]["diagnostics"]["wrappers"][0]["postgres_node_type"],
            "Sort",
        )
        self.assertEqual(
            tree["right"]["diagnostics"]["wrappers"][0]["postgres_node_type"],
            "Sort",
        )

    def test_incremental_sort_is_a_transparent_wrapper(self):
        plan = load_fixture("merge_right.json")
        plan[0]["Plan"]["Plans"][0]["Node Type"] = "Incremental Sort"
        tree = NORMALIZER.normalize_explain(plan, b"SELECT 1", 160002)["tree"]
        self.assertEqual(tree["left"]["relation"], "part")
        self.assertEqual(
            tree["left"]["diagnostics"]["wrappers"][0]["postgres_node_type"],
            "Incremental Sort",
        )

    def test_nested_loop_inner_removes_materialize_and_memoize(self):
        tree = normalize("nested_inner.json")["tree"]
        self.assertEqual(tree["join_type"], "inner")
        self.assertEqual(tree["left"]["relation"], "nation")
        self.assertEqual(tree["right"]["relation"], "supplier")
        self.assertEqual(
            tree["left"]["diagnostics"]["wrappers"][0]["postgres_node_type"],
            "Materialize",
        )
        self.assertEqual(
            tree["right"]["diagnostics"]["wrappers"][0]["postgres_node_type"],
            "Memoize",
        )
        self.assertIn("index_cond", tree["right"]["diagnostics"]["predicates"])

    def test_full_join_and_root_sort(self):
        tree = normalize("hash_full.json")["tree"]
        self.assertEqual(tree["join_type"], "full")
        self.assertEqual(tree["left"]["relation"], "customer")
        self.assertEqual(tree["right"]["relation"], "nation")
        self.assertEqual(
            tree["diagnostics"]["wrappers"][0]["postgres_node_type"], "Sort"
        )
        predicates = tree["diagnostics"]["predicates"]
        self.assertEqual(set(predicates), {"hash_cond", "join_filter"})

    def test_fixtures_cover_every_supported_join_kind(self):
        fixtures = (
            "hash_left.json",
            "merge_right.json",
            "nested_inner.json",
            "hash_full.json",
        )
        kinds = {normalize(name)["tree"]["join_type"] for name in fixtures}
        self.assertEqual(kinds, {"inner", "left", "right", "full"})


class ArtifactValidationTest(unittest.TestCase):
    def test_artifact_metadata_and_canonical_hash(self):
        query = b"\r\n  SELECT 1; \r\n"
        artifact = normalize("hash_left.json", query)
        self.assertEqual(artifact["format"], "duckyan.pg_join_tree.v1")
        self.assertEqual(
            artifact["query_sha256_canonicalization"], "duckyan.sql_text.v1"
        )
        self.assertEqual(artifact["postgres"]["version_num"], 160002)
        self.assertEqual(artifact["postgres"]["plan_schema"], "public")
        self.assertEqual(artifact["postgres"]["plan_data"], "tpch-sf0.01")
        self.assertEqual(
            artifact["query_sha256"], hashlib.sha256(b"SELECT 1").hexdigest()
        )

    def test_rejects_wrong_postgres_version(self):
        with self.assertRaisesRegex(NORMALIZER.PlanError, "160002"):
            NORMALIZER.normalize_explain(
                load_fixture("hash_left.json"), b"SELECT 1", 160003
            )

    def test_rejects_extra_planner_setting(self):
        plan = load_fixture("hash_left.json")
        plan[0]["Settings"]["enable_hashjoin"] = "off"
        with self.assertRaisesRegex(NORMALIZER.PlanError, "planner settings"):
            NORMALIZER.normalize_explain(plan, b"SELECT 1", 160002)

    def test_rejects_unsupported_join_kind(self):
        plan = load_fixture("hash_left.json")
        plan[0]["Plan"]["Join Type"] = "Anti"
        with self.assertRaisesRegex(NORMALIZER.PlanError, "unsupported.*join type"):
            NORMALIZER.normalize_explain(plan, b"SELECT 1", 160002)

    def test_rejects_ambiguous_child_relationship(self):
        plan = load_fixture("hash_left.json")
        plan[0]["Plan"]["Plans"][1]["Parent Relationship"] = "Outer"
        with self.assertRaisesRegex(NORMALIZER.PlanError, "duplicate outer"):
            NORMALIZER.normalize_explain(plan, b"SELECT 1", 160002)

    def test_self_join_occurrences_follow_query_aliases_not_pg_plan_order(self):
        plan = load_fixture("hash_left.json")
        left_scan = plan[0]["Plan"]["Plans"][0]
        right_scan = plan[0]["Plan"]["Plans"][1]["Plans"][0]
        left_scan["Alias"] = "n2"
        right_scan["Relation Name"] = "nation"
        right_scan["Alias"] = "n1"
        artifact = NORMALIZER.normalize_explain(
            plan,
            b"SELECT * FROM nation n1 LEFT JOIN nation n2 ON n1.n_nationkey = n2.n_nationkey",
            160002,
        )
        # PostgreSQL emitted n2 on the outer side, but occurrence identity is
        # defined by the immutable source query (n1 first, n2 second).
        self.assertEqual(artifact["tree"]["left"]["occurrence"], 1)
        self.assertEqual(artifact["tree"]["right"]["occurrence"], 0)

    def test_rejects_self_join_when_query_cannot_identify_occurrences(self):
        plan = load_fixture("hash_left.json")
        right_scan = plan[0]["Plan"]["Plans"][1]["Plans"][0]
        right_scan["Relation Name"] = "nation"
        right_scan["Alias"] = "n2"
        with self.assertRaisesRegex(NORMALIZER.PlanError, "self-joins"):
            NORMALIZER.normalize_explain(plan, b"SELECT 1", 160002)

    def test_sampled_family_schema_and_root_aggregate(self):
        plan = load_fixture("hash_left.json")
        for scan in (
            plan[0]["Plan"]["Plans"][0],
            plan[0]["Plan"]["Plans"][1]["Plans"][0],
        ):
            scan["Schema"] = "pgplan_job"
        plan[0]["Settings"]["search_path"] = "pgplan_job, pg_catalog"
        plan[0]["Plan"] = {
            "Node Type": "Aggregate",
            "Strategy": "Hashed",
            "Plans": [plan[0]["Plan"]],
        }
        artifact = NORMALIZER.normalize_explain(
            plan,
            b"SELECT count(*) FROM nation n LEFT JOIN supplier s ON n.n_nationkey = s.s_nationkey",
            160002,
            "pgplan_job",
            "job-duckdb-sample-1000",
        )
        self.assertEqual(artifact["postgres"]["plan_schema"], "pgplan_job")
        self.assertEqual(artifact["postgres"]["plan_data"], "job-duckdb-sample-1000")
        self.assertEqual(artifact["tree"]["diagnostics"]["wrappers"][0]["postgres_node_type"], "Aggregate")
        self.assertEqual(artifact["tree"]["left"]["schema"], "public")

    def test_single_scan_after_postgres_join_elimination(self):
        plan = load_fixture("hash_left.json")
        plan[0]["Plan"] = plan[0]["Plan"]["Plans"][0]
        artifact = NORMALIZER.normalize_explain(
            plan, b"SELECT n.n_name FROM nation n", 160002
        )
        self.assertEqual(artifact["tree"]["op"], "scan")
        self.assertEqual(artifact["tree"]["relation"], "nation")
        self.assertEqual(artifact["tree"]["occurrence"], 0)

    def test_rejects_mismatched_sampled_schema_and_data_label(self):
        with self.assertRaisesRegex(NORMALIZER.PlanError, "pgplan_tpcds"):
            NORMALIZER.validate_plan_provenance(
                "pgplan_job", "tpcds-duckdb-sample-1000"
            )

    def test_rejects_scan_resolved_outside_prepared_public_schema(self):
        plan = load_fixture("hash_left.json")
        plan[0]["Plan"]["Plans"][0]["Schema"] = "analyst"
        with self.assertRaisesRegex(NORMALIZER.PlanError, "prepared public schema"):
            NORMALIZER.normalize_explain(plan, b"SELECT 1", 160002)

    def test_input_object_is_not_modified(self):
        plan = load_fixture("hash_full.json")
        original = copy.deepcopy(plan)
        NORMALIZER.normalize_explain(plan, b"SELECT 1", 160002)
        self.assertEqual(plan, original)


class QueryValidationTest(unittest.TestCase):
    def test_line_endings_whitespace_and_final_semicolon_are_canonical(self):
        query = b" \r\nSELECT ';' AS value\r\n;\r\n"
        self.assertEqual(NORMALIZER.canonicalize_query(query), b"SELECT ';' AS value")

    def test_semicolons_inside_quotes_comments_and_dollar_strings_are_safe(self):
        query = b"SELECT ';', $$;$$ /* ; */ -- ;\n;"
        self.assertEqual(
            NORMALIZER.canonicalize_query(query), b"SELECT ';', $$;$$ /* ; */ -- ;"
        )

    def test_leading_line_and_nested_block_comments_are_removed(self):
        query = (
            b" \r\n-- benchmark provenance;\r\n"
            b"/* outer /* nested ; */ comment */\r\n SELECT 1; \r\n"
        )
        self.assertEqual(NORMALIZER.canonicalize_query(query), b"SELECT 1")

    def test_comments_after_the_first_sql_token_remain_byte_exact(self):
        query = b"-- discard\nSELECT /* keep */ 1 -- keep tail"
        self.assertEqual(
            NORMALIZER.canonicalize_query(query),
            b"SELECT /* keep */ 1 -- keep tail",
        )

    def test_semicolon_at_end_of_line_comment_is_not_a_statement_terminator(self):
        query = b"SELECT 1 -- diagnostic;"
        self.assertEqual(NORMALIZER.canonicalize_query(query), query)

    def test_rejects_multiple_statements(self):
        with self.assertRaisesRegex(NORMALIZER.PlanError, "one SQL statement"):
            NORMALIZER.canonicalize_query(b"SELECT 1; SELECT 2;")

    def test_rejects_non_select_and_cte(self):
        with self.assertRaisesRegex(NORMALIZER.PlanError, "SELECT"):
            NORMALIZER.canonicalize_query(b"DELETE FROM part")
        with self.assertRaisesRegex(NORMALIZER.PlanError, "SELECT"):
            NORMALIZER.canonicalize_query(b"WITH q AS (SELECT 1) SELECT * FROM q")

    def test_render_uses_explain_without_analyze_in_read_only_transaction(self):
        sql = NORMALIZER.render_explain_sql(b"SELECT 1;")
        self.assertIn("BEGIN READ ONLY;", sql)
        self.assertIn("SET LOCAL max_parallel_workers_per_gather = 0;", sql)
        self.assertIn(
            "EXPLAIN (FORMAT JSON, VERBOSE, COSTS TRUE, SETTINGS TRUE)", sql
        )
        self.assertNotIn("ANALYZE", sql)
        self.assertTrue(sql.endswith("ROLLBACK;\n"))

    def test_render_sets_nonpublic_search_path(self):
        sql = NORMALIZER.render_explain_sql(
            b"SELECT * FROM title t JOIN cast_info ci ON t.id = ci.movie_id",
            "pgplan_job",
        )
        self.assertIn("SET LOCAL search_path = pgplan_job, pg_catalog;", sql)

    def test_capture_normalizer_avoids_python_39_string_removal_apis(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn(".removeprefix(", source)
        self.assertNotIn(".removesuffix(", source)


if __name__ == "__main__":
    unittest.main()
