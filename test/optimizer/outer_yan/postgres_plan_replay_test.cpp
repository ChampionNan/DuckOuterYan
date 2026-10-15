#include "catch.hpp"
#include "test_helpers.hpp"

#include "duckdb.hpp"
#include "duckdb/common/file_system.hpp"
#include "duckdb/common/string_util.hpp"
#include "duckdb/optimizer/outer_yan/common/outer_yan_tree.hpp"
#include "duckdb/optimizer/outer_yan/postgres_plan_replay.hpp"
#include "duckdb/planner/operator/logical_comparison_join.hpp"
#include "mbedtls_wrapper.hpp"

#include <cstdlib>
#include <fstream>

using namespace duckdb;

namespace {

string QueryHash(const string &query) {
	auto hash = duckdb_mbedtls::MbedTlsWrapper::ComputeSha256Hash(query);
	string result(duckdb_mbedtls::MbedTlsWrapper::SHA256_HASH_LENGTH_TEXT, '\0');
	duckdb_mbedtls::MbedTlsWrapper::ToBase16(&hash[0], &result[0], hash.size());
	return result;
}

string Scan(const string &relation, const string &alias = string(), idx_t occurrence = 0) {
	auto scan_alias = alias.empty() ? relation : alias;
	return "{\"op\":\"scan\",\"schema\":\"public\",\"relation\":\"" + relation +
	       "\",\"alias\":\"" + scan_alias + "\",\"occurrence\":" + to_string(occurrence) + "}";
}

string Join(const string &type, const string &left, const string &right) {
	return "{\"op\":\"join\",\"join_type\":\"" + type + "\",\"left\":" + left +
	       ",\"right\":" + right + "}";
}

string Artifact(const string &query, const string &tree, const string &hash = string(),
	              const string &settings = "{\"max_parallel_workers_per_gather\":\"0\"}",
	              const string &plan_data = "tpch-sf0.01", const string &plan_schema = "public") {
	return "{\"format\":\"duckyan.pg_join_tree.v1\",\"query_sha256\":\"" +
	       (hash.empty() ? QueryHash(query) : hash) +
	       "\",\"query_sha256_canonicalization\":\"duckyan.sql_text.v1\","
	       "\"postgres\":{\"version_num\":160002,\"settings\":" +
	       settings + ",\"plan_schema\":\"" + plan_schema + "\",\"plan_data\":\"" + plan_data +
	       "\"},\"tree\":" + tree + "}";
}

string WriteArtifact(const string &name, const string &contents) {
	auto fs = FileSystem::CreateLocal();
	auto path = TestCreatePath(name);
	if (!fs->IsPathAbsolute(path)) {
		path = fs->JoinPath(FileSystem::GetWorkingDirectory(), path);
	}
	std::ofstream output(path, std::ios::binary | std::ios::trunc);
	REQUIRE(output.good());
	output << contents;
	output.close();
	REQUIRE(output.good());
	return path;
}

void ActivatePGPlan(Connection &connection, const string &path) {
	auto escaped_path = StringUtil::Replace(path, "'", "''");
	REQUIRE_NO_FAIL(connection.Query("SET VARIABLE pgplan = '" + escaped_path + "'"));
}

void SeedAB(Connection &connection) {
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE a(id INTEGER, av INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE b(id INTEGER, bv INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO a VALUES (1, 10)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO b VALUES (2, 20)"));
}

void RequirePGPlanError(Connection &connection, const string &query, const string &expected) {
	auto result = connection.Query(query);
	REQUIRE(result->HasError());
	INFO("PGPlan error: " << result->GetError());
	REQUIRE(StringUtil::Contains(result->GetError(), "[PGPLAN]"));
	REQUIRE(StringUtil::Contains(result->GetError(), expected));
}

void RequireFinalSignatureError(const LogicalOperator &plan, const string &expected_signature) {
	try {
		PostgresPlanReplay::VerifyFinalPlan(plan, expected_signature, "signature-test.json");
		FAIL("final signature mismatch should have thrown");
	} catch (const InvalidInputException &error) {
		REQUIRE(StringUtil::Contains(error.what(), "final semantic signature mismatch"));
	}
}

LogicalComparisonJoin *FindJoinWithConditionCount(LogicalOperator &op, idx_t condition_count) {
	if (op.type == LogicalOperatorType::LOGICAL_COMPARISON_JOIN) {
		auto &join = op.Cast<LogicalComparisonJoin>();
		if (join.conditions.size() == condition_count) {
			return &join;
		}
	}
	for (auto &child : op.children) {
		auto result = FindJoinWithConditionCount(*child, condition_count);
		if (result) {
			return result;
		}
	}
	return nullptr;
}

class ScopedScanFilterSimplification {
public:
	ScopedScanFilterSimplification() {
		auto previous = std::getenv("DUCKDB_OY_SIMPLIFY_SCAN_FILTERS");
		if (previous) {
			had_previous = true;
			previous_value = previous;
		}
#ifdef _WIN32
		REQUIRE(_putenv_s("DUCKDB_OY_SIMPLIFY_SCAN_FILTERS", "1") == 0);
#else
		REQUIRE(setenv("DUCKDB_OY_SIMPLIFY_SCAN_FILTERS", "1", 1) == 0);
#endif
	}

	~ScopedScanFilterSimplification() {
#ifdef _WIN32
		_putenv_s("DUCKDB_OY_SIMPLIFY_SCAN_FILTERS", had_previous ? previous_value.c_str() : "");
#else
		if (had_previous) {
			setenv("DUCKDB_OY_SIMPLIFY_SCAN_FILTERS", previous_value.c_str(), 1);
		} else {
			unsetenv("DUCKDB_OY_SIMPLIFY_SCAN_FILTERS");
		}
#endif
	}

private:
	bool had_previous = false;
	string previous_value;
};

} // namespace

TEST_CASE("PGPlan: swaps LEFT to RIGHT while retaining the preserved table", "[outer_yan][pgplan]") {
	DuckDB database(nullptr);
	Connection connection(database);
	SeedAB(connection);
	const string query = "SELECT a.id, a.av, b.bv FROM a LEFT JOIN b ON a.id = b.id";
	const auto tree = Join("right", Scan("b"), Scan("a"));
	auto path = WriteArtifact("pg_replay_flip.json", Artifact(query, tree));
	ActivatePGPlan(connection, path);

	auto result = connection.Query(query);
	REQUIRE_NO_FAIL(*result);
	REQUIRE(CHECK_COLUMN(result, 0, {1}));
	REQUIRE(CHECK_COLUMN(result, 1, {10}));
	REQUIRE(CHECK_COLUMN(result, 2, {Value()}));

	auto explain = connection.Query("EXPLAIN " + query);
	REQUIRE_NO_FAIL(*explain);
	REQUIRE_FALSE(StringUtil::Contains(explain->ToString(), "SJ_BUILD"));
	REQUIRE_FALSE(StringUtil::Contains(explain->ToString(), "SJ_PROBE"));
	REQUIRE_NO_FAIL(connection.Query("RESET VARIABLE pgplan"));
}

TEST_CASE("PGPlan: preserves an exact bushy typed grouping", "[outer_yan][pgplan]") {
	DuckDB database(nullptr);
	Connection connection(database);
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE a(id INTEGER, av INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE b(id INTEGER, bv INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE c(id INTEGER, cv INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE d(id INTEGER, dv INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO a VALUES (1, 10)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO b VALUES (1, 20)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO c VALUES (1, 30)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO d VALUES (1, 40)"));
	// The bound query is left-deep. The imported tree deliberately regroups its
	// last edge into the right-hand branch, proving that replay is not merely
	// retaining DuckDB's source grouping.
	const string query =
	    "SELECT a.id, b.bv, c.cv, d.dv FROM a LEFT JOIN b ON a.id = b.id LEFT JOIN c ON "
	    "b.id = c.id LEFT JOIN d ON c.id = d.id";
	const auto tree = Join("left", Join("left", Scan("a"), Scan("b")),
	                       Join("left", Scan("c"), Scan("d")));
	auto path = WriteArtifact("pg_replay_bushy.json", Artifact(query, tree));
	ActivatePGPlan(connection, path);

	auto result = connection.Query(query);
	REQUIRE_NO_FAIL(*result);
	REQUIRE(CHECK_COLUMN(result, 0, {1}));
	REQUIRE(CHECK_COLUMN(result, 1, {20}));
	REQUIRE(CHECK_COLUMN(result, 2, {30}));
	REQUIRE(CHECK_COLUMN(result, 3, {40}));
}

TEST_CASE("PGPlan: accepts sampled-plan provenance and rejects inconsistent metadata",
          "[outer_yan][pgplan]") {
	DuckDB database(nullptr);
	Connection connection(database);
	SeedAB(connection);
	const string query = "SELECT a.id, b.bv FROM a LEFT JOIN b ON a.id = b.id";
	const auto tree = Join("left", Scan("a"), Scan("b"));
	const string sampled_settings =
	    "{\"max_parallel_workers_per_gather\":\"0\","
	    "\"search_path\":\"pgplan_job, pg_catalog\"}";

	SECTION("matching sampled data, schema, and settings") {
		auto path = WriteArtifact("pgplan_sampled_provenance.json",
		                          Artifact(query, tree, string(), sampled_settings,
		                                   "job-duckdb-sample-1000", "pgplan_job"));
		ActivatePGPlan(connection, path);
		auto result = connection.Query(query);
		REQUIRE_NO_FAIL(*result);
		REQUIRE(CHECK_COLUMN(result, 0, {1}));
		REQUIRE(CHECK_COLUMN(result, 1, {Value()}));
	}
	SECTION("sampled provenance requires its search path") {
		auto path = WriteArtifact("pgplan_sampled_missing_search_path.json",
		                          Artifact(query, tree, string(),
		                                   "{\"max_parallel_workers_per_gather\":\"0\"}",
		                                   "job-duckdb-sample-1000", "pgplan_job"));
		ActivatePGPlan(connection, path);
		RequirePGPlanError(connection, query, "postgres.settings");
	}
	SECTION("sampled provenance rejects a mismatched search path") {
		const string wrong_settings =
		    "{\"max_parallel_workers_per_gather\":\"0\","
		    "\"search_path\":\"pgplan_graph, pg_catalog\"}";
		auto path = WriteArtifact("pgplan_sampled_wrong_search_path.json",
		                          Artifact(query, tree, string(), wrong_settings,
		                                   "job-duckdb-sample-1000", "pgplan_job"));
		ActivatePGPlan(connection, path);
		RequirePGPlanError(connection, query, "postgres.settings");
	}
	SECTION("sampled provenance rejects a schema from another family") {
		auto path = WriteArtifact("pgplan_sampled_wrong_schema.json",
		                          Artifact(query, tree, string(), sampled_settings,
		                                   "job-duckdb-sample-1000", "pgplan_graph"));
		ActivatePGPlan(connection, path);
		RequirePGPlanError(connection, query, "postgres.plan_schema");
	}
	SECTION("sampled provenance requires a string schema") {
		auto artifact = Artifact(query, tree, string(), sampled_settings,
		                         "job-duckdb-sample-1000", "pgplan_job");
		artifact = StringUtil::Replace(artifact, "\"plan_schema\":\"pgplan_job\"", "\"plan_schema\":42");
		auto path = WriteArtifact("pgplan_sampled_malformed_schema.json", artifact);
		ActivatePGPlan(connection, path);
		RequirePGPlanError(connection, query, "plan_schema");
	}
	SECTION("sampled provenance requires an object settings value") {
		auto path = WriteArtifact("pgplan_sampled_malformed_settings.json",
		                          Artifact(query, tree, string(), "42",
		                                   "job-duckdb-sample-1000", "pgplan_job"));
		ActivatePGPlan(connection, path);
		RequirePGPlanError(connection, query, "settings");
	}
	SECTION("sampled provenance rejects malformed data labels") {
		auto path = WriteArtifact("pgplan_sampled_bad_data.json",
		                          Artifact(query, tree, string(), sampled_settings,
		                                   "job-duckdb-sample-0", "pgplan_job"));
		ActivatePGPlan(connection, path);
		RequirePGPlanError(connection, query, "postgres.plan_data");
	}
}

TEST_CASE("PGPlan: full DuckDB data provenance retains strict schema and settings validation", "[outer_yan][pgplan]") {
	DuckDB database(nullptr);
	Connection connection(database);
	SeedAB(connection);
	const string query = "SELECT a.id, b.bv FROM a LEFT JOIN b ON a.id = b.id";
	const auto tree = Join("left", Scan("a"), Scan("b"));
	for (const auto &family : {"tpch", "tpcds", "job"}) {
		const string schema = string("pgplan_") + family;
		const string settings = "{\"max_parallel_workers_per_gather\":\"0\",\"search_path\":\"" +
		                        schema + ", pg_catalog\"}";
		const string label = string(family) + "-duckdb-full";
		auto path = WriteArtifact(string("pgplan_full_") + family + ".json",
		                          Artifact(query, tree, string(), settings, label, schema));
		ActivatePGPlan(connection, path);
		auto result = connection.Query(query);
		REQUIRE_NO_FAIL(*result);
		REQUIRE(CHECK_COLUMN(result, 0, {1}));
		REQUIRE(CHECK_COLUMN(result, 1, {Value()}));
		path = WriteArtifact("pgplan_full_wrong_schema.json",
		                     Artifact(query, tree, string(), settings, label, "pgplan_graph"));
		ActivatePGPlan(connection, path);
		RequirePGPlanError(connection, query, "postgres.plan_schema");
		path = WriteArtifact("pgplan_full_missing_search_path.json",
		                     Artifact(query, tree, string(), "{\"max_parallel_workers_per_gather\":\"0\"}",
		                              label, schema));
		ActivatePGPlan(connection, path);
		RequirePGPlanError(connection, query, "postgres.settings");
	}
}

TEST_CASE("PGPlan: retains a root aggregate above the imported join tree", "[outer_yan][pgplan]") {
	DuckDB database(nullptr);
	Connection connection(database);
	SeedAB(connection);
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO a VALUES (2, 40)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO b VALUES (1, 30)"));
	const string query = "SELECT count(*) FROM a LEFT JOIN b ON a.id = b.id";
	auto path = WriteArtifact("pgplan_root_aggregate.json",
	                          Artifact(query, Join("left", Scan("a"), Scan("b"))));
	ActivatePGPlan(connection, path);

	auto result = connection.Query(query);
	REQUIRE_NO_FAIL(*result);
	REQUIRE(CHECK_COLUMN(result, 0, {2}));
}

TEST_CASE("PGPlan: preserves an anchored theta residual when children flip", "[outer_yan][pgplan]") {
	DuckDB database(nullptr);
	Connection connection(database);
	SeedAB(connection);
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO b VALUES (1, 5), (1, 15)"));
	const string query =
	    "SELECT a.av, b.bv FROM a LEFT JOIN b ON a.id = b.id AND a.av < b.bv";
	// The equality remains the graph anchor. The theta comparison must travel
	// with it and be inverted together with the LEFT-to-RIGHT child flip.
	auto path = WriteArtifact("pgplan_theta_residual.json",
	                          Artifact(query, Join("right", Scan("b"), Scan("a"))));
	ActivatePGPlan(connection, path);

	auto result = connection.Query(query);
	REQUIRE_NO_FAIL(*result);
	REQUIRE(CHECK_COLUMN(result, 0, {10}));
	REQUIRE(CHECK_COLUMN(result, 1, {15}));
}

TEST_CASE("PGPlan: skips a same-side equality when choosing the join anchor", "[outer_yan][pgplan]") {
	DuckDB database(nullptr);
	Connection connection(database);
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE a(id INTEGER, x INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE b(id INTEGER, x INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE c(id INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO a VALUES (1, 10), (2, 20)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO b VALUES (1, 10), (2, 999)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO c VALUES (1), (2)"));
	const string query =
	    "SELECT count(*), count(b.id), count(c.id) FROM (a LEFT JOIN b ON a.id = b.id) LEFT JOIN c ON "
	    "a.x = b.x AND b.id = c.id";
	// a.x = b.x is listed first, but both referenced relations belong to the
	// preserved child of the upper LEFT join. Only b.id = c.id is a valid graph
	// anchor for that join; the earlier equality remains an ON residual.
	REQUIRE_NO_FAIL(connection.Query(
	    "SET disabled_optimizers TO "
	    "'outer_yan_pre,outer_yan_dp,outer_yan_post,join_order,column_lifetime,"
	    "statistics_propagation,outer_join_simplification'"));
	auto plan = connection.ExtractPlan(query, /*resolve_column_bindings=*/false);
	REQUIRE_NO_FAIL(connection.Query("SET disabled_optimizers TO ''"));
	REQUIRE(plan);
	auto upper_join = FindJoinWithConditionCount(*plan, 2);
	REQUIRE(upper_join);

	// Locate the cross-child condition through the same applicability proof used
	// by production. DuckDB normally stores the same-side equality as an
	// arbitrary residual expression, so also prepend a redundant comparison copy
	// of the lower a.id = b.id anchor. At the upper join that comparison is wholly
	// within the left child, while the original b.id = c.id anchor must remain the
	// applicability-selected condition.
	OuterYanTree initial_check;
	REQUIRE(initial_check.CheckPGPlanApplicability(*plan));
	optional_idx initial_anchor;
	for (auto &edge : initial_check.Applicability().edges) {
		if (edge.join == upper_join) {
			initial_anchor = optional_idx(edge.condition_index);
			break;
		}
	}
	REQUIRE(initial_anchor.IsValid());
	REQUIRE(initial_anchor.GetIndex() < upper_join->conditions.size());
	auto lower_join = FindJoinWithConditionCount(*upper_join->children[0], 1);
	REQUIRE(lower_join);
	REQUIRE(lower_join->conditions[0].IsComparison());
	upper_join->conditions.insert(upper_join->conditions.begin(), lower_join->conditions[0].Copy());

	OuterYanTree tree;
	REQUIRE(tree.CheckPGPlanApplicability(*plan));
	optional_idx recorded_anchor;
	for (auto &edge : tree.Applicability().edges) {
		if (edge.join == upper_join) {
			recorded_anchor = optional_idx(edge.condition_index);
			break;
		}
	}
	REQUIRE(recorded_anchor.IsValid());
	REQUIRE(recorded_anchor.GetIndex() == initial_anchor.GetIndex() + 1);
	REQUIRE_NOTHROW(tree.BuildOT(std::move(plan)));

	auto path = WriteArtifact("pgplan_same_side_equality.json",
	                          Artifact(query, Join("left", Join("left", Scan("a"), Scan("b")),
	                                               Scan("c"))));
	ActivatePGPlan(connection, path);

	auto result = connection.Query(query);
	REQUIRE_NO_FAIL(*result);
	REQUIRE(CHECK_COLUMN(result, 0, {2}));
	REQUIRE(CHECK_COLUMN(result, 1, {2}));
	REQUIRE(CHECK_COLUMN(result, 2, {1}));
}

TEST_CASE("PGPlan: derives an implied equality for a PostgreSQL transitive split",
          "[outer_yan][pgplan]") {
	DuckDB database(nullptr);
	Connection connection(database);
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE a(id INTEGER, av INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE b(id INTEGER, bv INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE c(id INTEGER, cv INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO a VALUES (1, 10), (2, 20)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO b VALUES (1, 30), (3, 40)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO c VALUES (1, 50), (2, 60)"));
	const string query =
	    "SELECT a.id, b.bv, c.cv FROM a JOIN b ON a.id = b.id JOIN c ON b.id = c.id";
	// PostgreSQL can join a to c first by deriving a.id = c.id from the two
	// original bound equalities. PGPlan builds the same split without parsing a
	// PostgreSQL predicate string, then retains both original predicates at
	// their lowest covering imported node.
	auto path = WriteArtifact("pgplan_transitive_split.json",
	                          Artifact(query, Join("inner", Join("inner", Scan("a"), Scan("c")),
	                                               Scan("b"))));
	ActivatePGPlan(connection, path);

	auto result = connection.Query(query);
	REQUIRE_NO_FAIL(*result);
	REQUIRE(CHECK_COLUMN(result, 0, {1}));
	REQUIRE(CHECK_COLUMN(result, 1, {30}));
	REQUIRE(CHECK_COLUMN(result, 2, {50}));
}

TEST_CASE("PGPlan: uses a safe single-relation cast expression as its equality anchor",
          "[outer_yan][pgplan]") {
	DuckDB database(nullptr);
	Connection connection(database);
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE a(id INTEGER, av INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE b(id DOUBLE, bv INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO a VALUES (1, 10), (2, 20)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO b VALUES (1, 100)"));
	const string query = "SELECT a.id, b.bv FROM a LEFT JOIN b ON a.id = b.id";
	// DuckDB binds this as CAST(a.id AS DOUBLE) = b.id. PostgreSQL selected the
	// equivalent child-oriented RIGHT tree.
	auto path = WriteArtifact("pgplan_cast_anchor.json",
	                          Artifact(query, Join("right", Scan("b"), Scan("a"))));
	ActivatePGPlan(connection, path);

	auto result = connection.Query(query);
	REQUIRE_NO_FAIL(*result);
	REQUIRE(CHECK_COLUMN(result, 0, {1, 2}));
	REQUIRE(CHECK_COLUMN(result, 1, {100, Value()}));
}

TEST_CASE("PGPlan: rejects an equality side spanning multiple base relations",
          "[outer_yan][pgplan]") {
	DuckDB database(nullptr);
	Connection connection(database);
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE a(id INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE b(id INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE c(id INTEGER)"));
	const string query =
	    "SELECT a.id FROM a LEFT JOIN b ON a.id = b.id LEFT JOIN c ON COALESCE(a.id, b.id) = c.id";
	auto tree = Join("left", Join("left", Scan("a"), Scan("b")), Scan("c"));
	auto path = WriteArtifact("pgplan_multirelation_anchor_side.json", Artifact(query, tree));
	ActivatePGPlan(connection, path);
	RequirePGPlanError(connection, query, "safe two-relation equality anchor");
}

TEST_CASE("PGPlan: preserves a unary predicate on the preserved ON side",
          "[outer_yan][pgplan]") {
	DuckDB database(nullptr);
	Connection connection(database);
	SeedAB(connection);
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO a VALUES (2, 1)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO b VALUES (1, 30)"));
	const string query =
	    "SELECT count(*), count(b.bv) FROM a LEFT JOIN b ON a.id = b.id AND a.av > 5";
	// a.av > 5 is a non-comparison JoinCondition in DuckDB. It must remain on
	// the join (not be pushed into preserved input a) and must not be Swap()'d.
	auto path = WriteArtifact("pgplan_unary_on_residual.json",
	                          Artifact(query, Join("right", Scan("b"), Scan("a"))));
	ActivatePGPlan(connection, path);

	auto result = connection.Query(query);
	REQUIRE_NO_FAIL(*result);
	REQUIRE(CHECK_COLUMN(result, 0, {2}));
	REQUIRE(CHECK_COLUMN(result, 1, {1}));
}

TEST_CASE("PGPlan: matches repeated base-table scans by source occurrence", "[outer_yan][pgplan]") {
	DuckDB database(nullptr);
	Connection connection(database);
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE a(id INTEGER, av INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO a VALUES (1, 10), (10, 100)"));
	const string query =
	    "SELECT x.av, y.av FROM a x LEFT JOIN a y ON x.id = y.av WHERE x.id = 10";
	// PostgreSQL put source occurrence y (#1) on the left of a RIGHT join. The
	// artifact occurrence, rather than PG traversal order or relation name alone,
	// identifies the corresponding DuckDB LogicalGet.
	const auto tree = Join("right", Scan("a", "y", 1), Scan("a", "x", 0));
	auto path = WriteArtifact("pgplan_self_join_occurrences.json", Artifact(query, tree));
	ActivatePGPlan(connection, path);

	auto result = connection.Query(query);
	REQUIRE_NO_FAIL(*result);
	REQUIRE(CHECK_COLUMN(result, 0, {100}));
	REQUIRE(CHECK_COLUMN(result, 1, {10}));
}

TEST_CASE("PGPlan: independently proves PostgreSQL outer-join elimination", "[outer_yan][pgplan]") {
	DuckDB database(nullptr);
	Connection connection(database);
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE a(id INTEGER PRIMARY KEY, av INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE b(id INTEGER UNIQUE, bv INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO a VALUES (1, 10), (2, 20)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO b VALUES (1, 100)"));

	SECTION("LEFT join null-supplying side") {
		const string query = "SELECT a.id FROM a LEFT JOIN b ON a.id = b.id ORDER BY a.id";
		auto path = WriteArtifact("pgplan_eliminate_left.json", Artifact(query, Scan("a")));
		ActivatePGPlan(connection, path);
		auto result = connection.Query(query);
		REQUIRE_NO_FAIL(*result);
		REQUIRE(CHECK_COLUMN(result, 0, {1, 2}));
	}

	SECTION("RIGHT join null-supplying side") {
		const string query = "SELECT b.id FROM a RIGHT JOIN b ON a.id = b.id ORDER BY b.id";
		auto path = WriteArtifact("pgplan_eliminate_right.json", Artifact(query, Scan("b")));
		ActivatePGPlan(connection, path);
		auto result = connection.Query(query);
		REQUIRE_NO_FAIL(*result);
		REQUIRE(CHECK_COLUMN(result, 0, {1}));
	}
}

TEST_CASE("PGPlan: fails closed on unproven outer-join elimination", "[outer_yan][pgplan]") {
	SECTION("omitted side is not unique on the equality key") {
		DuckDB database(nullptr);
		Connection connection(database);
		REQUIRE_NO_FAIL(connection.Query("CREATE TABLE a(id INTEGER)"));
		REQUIRE_NO_FAIL(connection.Query("CREATE TABLE b(id INTEGER)"));
		const string query = "SELECT a.id FROM a LEFT JOIN b ON a.id = b.id";
		auto path = WriteArtifact("pgplan_eliminate_not_unique.json", Artifact(query, Scan("a")));
		ActivatePGPlan(connection, path);
		RequirePGPlanError(connection, query, "not independently eliminable");
	}

	SECTION("omitted output is observable") {
		DuckDB database(nullptr);
		Connection connection(database);
		REQUIRE_NO_FAIL(connection.Query("CREATE TABLE a(id INTEGER)"));
		REQUIRE_NO_FAIL(connection.Query("CREATE TABLE b(id INTEGER UNIQUE, bv INTEGER)"));
		const string query = "SELECT a.id, b.bv FROM a LEFT JOIN b ON a.id = b.id";
		auto path = WriteArtifact("pgplan_eliminate_observable.json", Artifact(query, Scan("a")));
		ActivatePGPlan(connection, path);
		RequirePGPlanError(connection, query, "not independently eliminable");
	}

	SECTION("join predicate is volatile") {
		DuckDB database(nullptr);
		Connection connection(database);
		REQUIRE_NO_FAIL(connection.Query("CREATE TABLE a(id INTEGER)"));
		REQUIRE_NO_FAIL(connection.Query("CREATE TABLE b(id INTEGER UNIQUE)"));
		const string query = "SELECT a.id FROM a LEFT JOIN b ON a.id = b.id AND random() > 0";
		auto path = WriteArtifact("pgplan_eliminate_volatile.json", Artifact(query, Scan("a")));
		ActivatePGPlan(connection, path);
		RequirePGPlanError(connection, query, "not independently eliminable");
	}
}

TEST_CASE("PGPlan: independently accepts outer to inner reduction", "[outer_yan][pgplan]") {
	DuckDB database(nullptr);
	Connection connection(database);
	SeedAB(connection);
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO b VALUES (1, 30)"));
	const string query =
	    "SELECT a.id, b.bv FROM a LEFT JOIN b ON a.id = b.id WHERE b.bv > 0";
	auto path = WriteArtifact("pg_replay_outer_to_inner.json",
	                          Artifact(query, Join("inner", Scan("a"), Scan("b"))));
	ActivatePGPlan(connection, path);

	auto result = connection.Query(query);
	REQUIRE_NO_FAIL(*result);
	REQUIRE(CHECK_COLUMN(result, 0, {1}));
	REQUIRE(CHECK_COLUMN(result, 1, {30}));
}

TEST_CASE("PGPlan: preserves a volatile intermediate filter only at its original scope",
	      "[outer_yan][pgplan]") {
	DuckDB database(nullptr);
	Connection connection(database);
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE a(id INTEGER, av INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE b(id INTEGER, bv INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE c(id INTEGER, cv INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO a VALUES (1, 10)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO b VALUES (1, 100), (3, 300)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO c VALUES (1, 1000)"));
	const string query =
	    "SELECT a.id, b.bv, c.cv FROM (a FULL JOIN b ON a.id=b.id) INNER JOIN c "
	    "ON a.id=c.id WHERE a.av + random() > -1000 AND b.bv + random() > -1000";

	SECTION("imported tree contains the original a-b evaluation scope") {
		auto tree = Join("inner", Join("inner", Scan("a"), Scan("b")), Scan("c"));
		auto path = WriteArtifact("pgplan_volatile_filter_scope.json", Artifact(query, tree));
		ActivatePGPlan(connection, path);
		auto result = connection.Query(query);
		REQUIRE_NO_FAIL(*result);
		REQUIRE(CHECK_COLUMN(result, 0, {1}));
		REQUIRE(CHECK_COLUMN(result, 1, {100}));
	}

	SECTION("cross-cut imported grouping cannot reproduce the original scope") {
		auto tree = Join("inner", Join("inner", Scan("a"), Scan("c")), Scan("b"));
		auto path = WriteArtifact("pgplan_volatile_filter_crosscut.json", Artifact(query, tree));
		ActivatePGPlan(connection, path);
		RequirePGPlanError(connection, query, "cannot preserve evaluation scope");
	}
}

TEST_CASE("PGPlan: positive constant modulo may move across an imported grouping",
	      "[outer_yan][pgplan]") {
	DuckDB database(nullptr);
	Connection connection(database);
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE a(id INTEGER, av INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE b(id INTEGER, bv INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE c(id INTEGER, cv INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO a VALUES (1, 100), (2, 201)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO b VALUES (1, 10), (3, 30)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO c VALUES (1, 1000), (2, 2000)"));
	const string query =
	    "SELECT a.id, b.bv, c.cv FROM (a FULL JOIN b ON a.id=b.id) INNER JOIN c "
	    "ON a.id=c.id WHERE a.av % 100 = 0 AND b.bv % 10 = 0";
	// DuckDB marks integral modulo as fallible in general. A positive constant
	// divisor proves away zero and signed MIN % -1, so this filter is safe to
	// place on a even though PostgreSQL's grouping cross-cuts the source a-b
	// filter scope.
	auto tree = Join("inner", Join("inner", Scan("a"), Scan("c")), Scan("b"));
	auto path = WriteArtifact("pgplan_safe_modulo_crosscut.json", Artifact(query, tree));
	ActivatePGPlan(connection, path);

	auto result = connection.Query(query);
	REQUIRE_NO_FAIL(*result);
	REQUIRE(CHECK_COLUMN(result, 0, {1}));
	REQUIRE(CHECK_COLUMN(result, 1, {10}));
	REQUIRE(CHECK_COLUMN(result, 2, {1000}));
}

TEST_CASE("PGPlan: query hash canonicalization preserves a semicolon in a line comment",
          "[outer_yan][pgplan]") {
	DuckDB database(nullptr);
	Connection connection(database);
	SeedAB(connection);
	const string query = "SELECT a.id, b.bv FROM a LEFT JOIN b ON a.id = b.id -- diagnostic;";
	auto path = WriteArtifact("pg_replay_comment_semicolon.json",
	                          Artifact(query, Join("left", Scan("a"), Scan("b"))));
	ActivatePGPlan(connection, path);
	auto result = connection.Query(query);
	REQUIRE_NO_FAIL(*result);
}

TEST_CASE("PGPlan: query hash ignores only comments before the first SQL token",
          "[outer_yan][pgplan]") {
	DuckDB database(nullptr);
	Connection connection(database);
	SeedAB(connection);
	const string query = "SELECT a.id, b.bv FROM a LEFT JOIN b ON a.id = b.id";
	auto path = WriteArtifact("pgplan_leading_comments.json",
	                          Artifact(query, Join("left", Scan("a"), Scan("b"))));
	ActivatePGPlan(connection, path);
	const string leading_comments =
	    " \r\n-- benchmark provenance;\r\n/* outer /* nested ; */ comment */\r\n";

	SECTION("bare query") {
		auto result = connection.Query(leading_comments + query);
		REQUIRE_NO_FAIL(*result);
	}
	SECTION("plain EXPLAIN") {
		auto result = connection.Query("EXPLAIN " + leading_comments + query);
		REQUIRE_NO_FAIL(*result);
	}
}

TEST_CASE("PGPlan: ignores the unsound scan-filter simplification experiment flag", "[outer_yan][pgplan]") {
	ScopedScanFilterSimplification scan_filter_flag;
	DuckDB database(nullptr);
	Connection connection(database);
	SeedAB(connection);
	const string query =
	    "SELECT a.id, b.bv FROM a LEFT JOIN b ON a.id = b.id AND b.bv > 5";
	auto path = WriteArtifact("pg_replay_unsound_env.json",
	                          Artifact(query, Join("inner", Scan("a"), Scan("b"))));
	ActivatePGPlan(connection, path);
	RequirePGPlanError(connection, query, "join type/preserved-side mismatch");
}

TEST_CASE("PGPlan: cannot be bypassed by disabled optimization or prepared execution", "[outer_yan][pgplan]") {
	DuckDB database(nullptr);
	Connection connection(database);
	SeedAB(connection);
	const string query = "SELECT a.id, b.bv FROM a LEFT JOIN b ON a.id = b.id";
	auto prepared = connection.Prepare(query);
	REQUIRE_FALSE(prepared->HasError());
	auto path = WriteArtifact("pg_replay_activation_guards.json",
	                          Artifact(query, Join("left", Scan("a"), Scan("b"))));
	ActivatePGPlan(connection, path);

	auto prepared_result = prepared->Execute();
	REQUIRE(prepared_result->HasError());
	REQUIRE(StringUtil::Contains(prepared_result->GetError(), "prepared-statement execution is unsupported"));

	REQUIRE_NO_FAIL(connection.Query("PRAGMA disable_optimizer"));
	RequirePGPlanError(connection, query, "PGPlan is configured but the optimizer is disabled");
}

TEST_CASE("PGPlan: RESET can recover from a malformed variable value", "[outer_yan][pgplan]") {
	DuckDB database(nullptr);
	Connection connection(database);
	REQUIRE_NO_FAIL(connection.Query("SET VARIABLE pgplan = 42"));
	REQUIRE_NO_FAIL(connection.Query("RESET VARIABLE pgplan"));
}

TEST_CASE("PGPlan: legacy activation variable remains a compatibility alias", "[outer_yan][pgplan]") {
	DuckDB database(nullptr);
	Connection connection(database);
	SeedAB(connection);
	const string query = "SELECT a.id, b.bv FROM a LEFT JOIN b ON a.id = b.id";
	auto path = WriteArtifact("pg_replay_legacy_alias.json",
	                          Artifact(query, Join("left", Scan("a"), Scan("b"))));
	auto escaped_path = StringUtil::Replace(path, "'", "''");
	REQUIRE_NO_FAIL(connection.Query("SET VARIABLE outer_yan_pg_replay_plan = '" + escaped_path + "'"));
	REQUIRE_NO_FAIL(connection.Query(query));
	REQUIRE_NO_FAIL(connection.Query("RESET VARIABLE outer_yan_pg_replay_plan"));
}

TEST_CASE("PGPlan: final signatures admit only legal swaps and reject semantic changes", "[outer_yan][pgplan]") {
	DuckDB database(nullptr);
	Connection connection(database);
	SeedAB(connection);
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO b VALUES (1, 30)"));
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE c(id INTEGER, cv INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("INSERT INTO c VALUES (1, 40)"));
	REQUIRE_NO_FAIL(connection.Query("SET disabled_optimizers TO 'outer_yan'"));

	auto left = connection.ExtractPlan("SELECT * FROM a LEFT JOIN b ON a.id = b.id", false);
	auto legal_swap = connection.ExtractPlan("SELECT * FROM b RIGHT JOIN a ON b.id = a.id", false);
	auto changed_side = connection.ExtractPlan("SELECT * FROM b LEFT JOIN a ON b.id = a.id", false);
	auto left_signature = PostgresPlanReplay::SemanticSignature(*left);
	REQUIRE(PostgresPlanReplay::SemanticSignature(*legal_swap) == left_signature);
	REQUIRE_NOTHROW(PostgresPlanReplay::VerifyFinalPlan(*legal_swap, left_signature, "signature-test.json"));
	RequireFinalSignatureError(*changed_side, left_signature);

	auto left_deep = connection.ExtractPlan(
	    "SELECT * FROM a LEFT JOIN b ON a.id = b.id LEFT JOIN c ON b.id = c.id", false);
	auto right_deep = connection.ExtractPlan(
	    "SELECT * FROM a LEFT JOIN (b LEFT JOIN c ON b.id = c.id) ON a.id = b.id", false);
	RequireFinalSignatureError(*right_deep, PostgresPlanReplay::SemanticSignature(*left_deep));
}

TEST_CASE("PGPlan: rejects a changed preserved side", "[outer_yan][pgplan]") {
	DuckDB database(nullptr);
	Connection connection(database);
	SeedAB(connection);
	const string query = "SELECT a.id, b.bv FROM a LEFT JOIN b ON a.id = b.id";
	auto path = WriteArtifact("pg_replay_bad_side.json",
	                          Artifact(query, Join("left", Scan("b"), Scan("a"))));
	ActivatePGPlan(connection, path);
	RequirePGPlanError(connection, query, "join type/preserved-side mismatch");
}

TEST_CASE("PGPlan: rejects malformed and unproven artifacts", "[outer_yan][pgplan]") {
	DuckDB database(nullptr);
	Connection connection(database);
	SeedAB(connection);
	const string query = "SELECT a.id, b.bv FROM a LEFT JOIN b ON a.id = b.id";

	SECTION("malformed tree") {
		auto path = WriteArtifact("pg_replay_malformed.json", Artifact(query, "{\"op\":\"join\"}"));
		ActivatePGPlan(connection, path);
		RequirePGPlanError(connection, query, "join_type");
	}
	SECTION("query hash mismatch") {
		auto path = WriteArtifact("pg_replay_hash.json",
		                          Artifact(query, Join("left", Scan("a"), Scan("b")), string(64, '0')));
		ActivatePGPlan(connection, path);
		RequirePGPlanError(connection, query, "query_sha256 mismatch");
	}
	SECTION("wrong query under plain EXPLAIN") {
		auto path = WriteArtifact("pg_replay_explain_hash.json",
		                          Artifact(query, Join("left", Scan("a"), Scan("b"))));
		ActivatePGPlan(connection, path);
		RequirePGPlanError(connection, "EXPLAIN " + query + " WHERE a.id > 0", "query_sha256 mismatch");
	}
	SECTION("EXPLAIN ANALYZE is rejected before execution") {
		auto path = WriteArtifact("pg_replay_explain_analyze.json",
		                          Artifact(query, Join("left", Scan("a"), Scan("b"))));
		ActivatePGPlan(connection, path);
		RequirePGPlanError(connection, "EXPLAIN ANALYZE " + query, "EXPLAIN ANALYZE is unsupported");
	}
	SECTION("extra PostgreSQL setting") {
		auto path = WriteArtifact(
		    "pg_replay_settings.json",
		    Artifact(query, Join("left", Scan("a"), Scan("b")), string(),
		             "{\"max_parallel_workers_per_gather\":\"0\",\"enable_hashjoin\":\"off\"}"));
		ActivatePGPlan(connection, path);
		RequirePGPlanError(connection, query, "postgres.settings");
	}
	SECTION("wrong plan-selection data") {
		auto path = WriteArtifact("pg_replay_data.json",
		                          Artifact(query, Join("left", Scan("a"), Scan("b")), string(),
		                                   "{\"max_parallel_workers_per_gather\":\"0\"}", "tpch-sf1"));
		ActivatePGPlan(connection, path);
		RequirePGPlanError(connection, query, "postgres.plan_data");
	}
	SECTION("non-default schema does not alias DuckDB main") {
		auto other_schema =
		    "{\"op\":\"scan\",\"schema\":\"other\",\"relation\":\"a\",\"alias\":\"a\","
		    "\"occurrence\":0}";
		auto path = WriteArtifact("pg_replay_schema.json",
		                          Artifact(query, Join("left", other_schema, Scan("b"))));
		ActivatePGPlan(connection, path);
		RequirePGPlanError(connection, query, "tree scan schema");
	}
}

TEST_CASE("PGPlan: rejects disconnected typed trees and retains multi-anchor joins",
          "[outer_yan][pgplan]") {
	DuckDB database(nullptr);
	Connection connection(database);
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE a(id INTEGER, av INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE b(id INTEGER, bv INTEGER)"));
	REQUIRE_NO_FAIL(connection.Query("CREATE TABLE c(id INTEGER, cv INTEGER)"));

	SECTION("imported split is disconnected") {
		const string query =
		    "SELECT a.av, b.bv, c.cv FROM a LEFT JOIN b ON a.id = b.id LEFT JOIN c ON b.id = c.id";
		auto tree = Join("left", Join("left", Scan("a"), Scan("c")), Scan("b"));
		auto path = WriteArtifact("pg_replay_disconnected.json", Artifact(query, tree));
		ActivatePGPlan(connection, path);
		RequirePGPlanError(connection, query, "join type/preserved-side mismatch");
	}
	SECTION("multiple equality anchors at one bound join remain attached") {
		const string query =
		    "SELECT a.av, b.bv, c.cv FROM a LEFT JOIN b ON a.id = b.id LEFT JOIN c ON "
		    "a.id = c.id AND b.id = c.id";
		auto tree = Join("left", Join("left", Scan("a"), Scan("b")), Scan("c"));
		auto path = WriteArtifact("pg_replay_cycle.json", Artifact(query, tree));
		ActivatePGPlan(connection, path);
		auto result = connection.Query(query);
		REQUIRE_NO_FAIL(*result);
	}
}
