#include "catch.hpp"
#include "test_helpers.hpp"

#include "duckdb.hpp"
#include "duckdb/main/client_context.hpp"
#include "duckdb/optimizer/outer_yan/pipeline/partial_reduction.hpp"
#include "duckdb/optimizer/outer_yan/pipeline/resimplification.hpp"
#include "duckdb/planner/expression/bound_columnref_expression.hpp"
#include "duckdb/planner/expression/bound_constant_expression.hpp"

#include <algorithm>
#include <cstdlib>
#include <functional>

using namespace duckdb;

namespace {

class PartialReductionForceCandidate {
public:
	PartialReductionForceCandidate() {
		const auto previous = std::getenv("DUCKDB_OY_FORCE_CANDIDATE");
		if (previous) {
			had_previous = true;
			previous_value = previous;
		}
#ifdef _WIN32
		const auto status = _putenv_s("DUCKDB_OY_FORCE_CANDIDATE", "1");
#else
		const auto status = setenv("DUCKDB_OY_FORCE_CANDIDATE", "1", 1);
#endif
		if (status != 0) {
			throw InternalException("Cannot enable forced OuterYan candidate for partial-reduction test");
		}
	}

	~PartialReductionForceCandidate() {
#ifdef _WIN32
		_putenv_s("DUCKDB_OY_FORCE_CANDIDATE", had_previous ? previous_value.c_str() : "");
#else
		if (had_previous) {
			setenv("DUCKDB_OY_FORCE_CANDIDATE", previous_value.c_str(), 1);
		} else {
			unsetenv("DUCKDB_OY_FORCE_CANDIDATE");
		}
#endif
	}

	PartialReductionForceCandidate(const PartialReductionForceCandidate &) = delete;
	PartialReductionForceCandidate &operator=(const PartialReductionForceCandidate &) = delete;

private:
	bool had_previous = false;
	string previous_value;
};

void SeedPartialReduction(Connection &con) {
	for (const auto table : {"pr_a", "pr_b", "pr_c", "pr_d"}) {
		REQUIRE_NO_FAIL(con.Query(string("CREATE TABLE ") + table + "(k INTEGER, part INTEGER, v INTEGER)"));
	}
	REQUIRE_NO_FAIL(con.Query("INSERT INTO pr_a VALUES (1,1,10),(1,1,10),(1,2,11),(2,1,20),"
	                          "(3,1,30),(NULL,1,40),(4,NULL,50),(9,1,NULL)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO pr_b VALUES (1,1,100),(1,1,100),(1,2,101),(2,1,-20),"
	                          "(5,1,500),(NULL,1,600),(4,NULL,700),(9,1,NULL)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO pr_c VALUES (1,1,1000),(1,1,1000),(1,2,1001),(3,1,3000),"
	                          "(5,2,5000),(NULL,1,6000),(4,NULL,7000),(8,1,8000)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO pr_d VALUES (1,1,10000),(1,2,10001),(2,1,20000),(5,1,50000),"
	                          "(NULL,1,60000),(4,NULL,70000),(7,1,70001)"));
}

vector<string> PartialResultBag(MaterializedQueryResult &result) {
	vector<string> rows;
	for (idx_t row = 0; row < result.RowCount(); row++) {
		string serialized;
		for (idx_t col = 0; col < result.ColumnCount(); col++) {
			const auto value = result.GetValue(col, row);
			const auto text = value.ToString();
			serialized += value.IsNull() ? "N;" : "V" + to_string(text.size()) + ":" + text + ";";
		}
		rows.push_back(std::move(serialized));
	}
	std::sort(rows.begin(), rows.end());
	return rows;
}

idx_t PartialProbeCount(const LogicalOperator &op) {
	idx_t result = op.type == LogicalOperatorType::LOGICAL_SJ_PROBE ? 1 : 0;
	for (const auto &child : op.children) {
		result += PartialProbeCount(*child);
	}
	return result;
}

//! Execute the bare SQL in all three modes. Comparing the complete row bag
//! retains duplicates and NULL-padded columns; aggregate wrappers could mask
//! the plan being tested or a multiplicity defect.
bool CheckPartialReductionResult(Connection &con, const string &sql) {
	INFO(sql);
	REQUIRE_NO_FAIL(con.Query("SET disabled_optimizers TO 'outer_yan'"));
	auto baseline = con.Query(sql);
	REQUIRE_NO_FAIL(*baseline);
	const auto expected = PartialResultBag(*baseline);
	PartialReductionForceCandidate force;
	REQUIRE_NO_FAIL(con.Query("SET disabled_optimizers TO ''"));
	REQUIRE_NO_FAIL(con.Query("SET VARIABLE outer_yan_partial_reduction = false"));
	auto reference_plan = con.ExtractPlan(sql, false);
	REQUIRE(reference_plan);
	const auto reference_probes = PartialProbeCount(*reference_plan);
	auto reference = con.Query(sql);
	REQUIRE_NO_FAIL(*reference);
	REQUIRE(reference->types == baseline->types);
	REQUIRE(PartialResultBag(*reference) == expected);

	REQUIRE_NO_FAIL(con.Query("SET VARIABLE outer_yan_partial_reduction = true"));
	auto partial_plan = con.ExtractPlan(sql, false);
	REQUIRE(partial_plan);
	const auto partial_probes = PartialProbeCount(*partial_plan);
	auto partial = con.Query(sql);
	REQUIRE_NO_FAIL(*partial);
	REQUIRE(partial->types == baseline->types);
	REQUIRE(PartialResultBag(*partial) == expected);
	REQUIRE(partial_probes <= reference_probes);
	return partial_probes < reference_probes;
}

unique_ptr<OJTNode> PartialNode(idx_t relation) {
	auto node = make_uniq<OJTNode>();
	node->relation_id = relation;
	return node;
}

void PartialAddEdge(OJTNode &parent, unique_ptr<OJTNode> child, idx_t order, JoinType selected,
	                JoinType original, idx_t key_count = 1) {
	OJTEdge edge;
	edge.parent_relation_id = parent.relation_id;
	edge.order = order;
	edge.kind = selected;
	edge.original_kind = original;
	edge.info = make_uniq<OTJoin>();
	edge.info->join_kind = selected;
	edge.info->original_join_kind = original;
	edge.info->cond_left_relation_id = parent.relation_id;
	edge.info->cond_right_relation_id = child->relation_id;
	for (idx_t key = 0; key < key_count; key++) {
		edge.info->conditions.emplace_back(
		    make_uniq<BoundColumnRefExpression>(LogicalType::INTEGER, ColumnBinding(TableIndex(parent.relation_id), ProjectionIndex(key))),
		    make_uniq<BoundColumnRefExpression>(LogicalType::INTEGER, ColumnBinding(TableIndex(child->relation_id), ProjectionIndex(key))),
		    ExpressionType::COMPARE_EQUAL);
	}
	edge.child = std::move(child);
	parent.children.push_back(std::move(edge));
}

void PartialRecordReference(OJTNode &node, vector<OuterYanSemiPair> &bottom_up,
	                        vector<OuterYanSemiPair> &top_down) {
	for (auto &edge : node.children) {
		PartialRecordReference(*edge.child, bottom_up, top_down);
		if (edge.original_kind == JoinType::INNER || edge.original_kind == JoinType::RIGHT) {
			OuterYanSemiPair pair;
			pair.build = edge.child->relation_id;
			pair.probe = node.relation_id;
			for (idx_t key = 0; key < edge.info->conditions.size(); key++) {
				pair.keys.push_back({ColumnBinding(TableIndex(pair.build), ProjectionIndex(key)),
				                     ColumnBinding(TableIndex(pair.probe), ProjectionIndex(key))});
			}
			bottom_up.push_back(std::move(pair));
		}
	}
	// Prepend this level to descendants so the reference TD order is parent
	// before child, independently of the preceding bottom-up recursion.
	vector<OuterYanSemiPair> current;
	for (auto &edge : node.children) {
		if (edge.original_kind == JoinType::INNER || edge.original_kind == JoinType::LEFT) {
			OuterYanSemiPair pair;
			pair.build = node.relation_id;
			pair.probe = edge.child->relation_id;
			for (idx_t key = 0; key < edge.info->conditions.size(); key++) {
				pair.keys.push_back({ColumnBinding(TableIndex(pair.build), ProjectionIndex(key)),
				                     ColumnBinding(TableIndex(pair.probe), ProjectionIndex(key))});
			}
			current.push_back(std::move(pair));
		}
	}
	for (auto &pair : top_down) {
		current.push_back(std::move(pair));
	}
	top_down = std::move(current);
}

//! Hand-built selected schedules isolate R1/R2/R3 from cost-model choices.
//! A real one-table source establishes OuterYanTree ownership; the scheduling
//! fixture then supplies its own relation IDs and bound equality conditions.
unique_ptr<OuterYanTree> PartialScheduleTree(Connection &con, unique_ptr<OJTNode> root, idx_t relations) {
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE partial_seed(k INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO partial_seed VALUES (1)"));
	auto source = con.ExtractPlan("SELECT * FROM partial_seed", false);
	REQUIRE(source);
	auto tree = make_uniq<OuterYanTree>(*con.context);
	con.context->transaction.BeginTransaction();
	tree->BuildOT(std::move(source));
	tree->BuildOJT();
	con.context->transaction.Commit();
	tree->OJT().Root() = std::move(*root);
	tree->ot_relations_by_id.resize(relations, nullptr);
	tree->table_to_relation.clear();
	for (idx_t relation = 0; relation < relations; relation++) {
		tree->table_to_relation.emplace(relation, relation);
	}
	PartialRecordReference(tree->OJT().Root(), tree->bottom_up_pairs, tree->top_down_pairs);
	return tree;
}

bool PartialHasPair(const vector<OuterYanSemiPair> &pairs, idx_t build, idx_t probe) {
	return std::any_of(pairs.begin(), pairs.end(), [&](const OuterYanSemiPair &pair) {
		return pair.build == build && pair.probe == probe;
	});
}

string PartialScheduleSignature(const OuterYanTree &tree) {
	string result;
	for (const auto *pairs : {&tree.bottom_up_pairs, &tree.top_down_pairs}) {
		result += "|";
		for (const auto &pair : *pairs) {
			result += to_string(pair.build) + ">" + to_string(pair.probe) + ":";
			for (const auto &key : pair.keys) {
				result += key.build_binding.ToString() + "=" + key.probe_binding.ToString() + ";";
			}
		}
	}
	return result;
}

} // namespace

TEST_CASE("outer_yan partial reduction: mixed chains preserve complete result bags",
	      "[outer_yan][partial_reduction][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedPartialReduction(con);
	bool removed_pair = false;
	const vector<string> joins {"INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "FULL JOIN"};
	for (const auto &first : joins) {
		for (const auto &second : joins) {
			for (const auto &third : joins) {
				const vector<string> expressions {
				    "pr_a a " + first + " pr_b b ON a.k=b.k " + second +
				        " pr_c c ON b.k=c.k " + third + " pr_d d ON a.k=d.k",
				    "(pr_a a " + first + " pr_b b ON a.k=b.k) " + second +
				        " (pr_c c " + third + " pr_d d ON c.k=d.k) ON b.k=c.k",
				    "pr_a a " + first + " (pr_b b " + second + " (pr_c c " + third +
				        " pr_d d ON c.k=d.k) ON b.k=c.k) ON a.k=b.k",
				};
				for (const auto &expression : expressions) {
					removed_pair = CheckPartialReductionResult(con, "SELECT a.*,b.*,c.*,d.* FROM " + expression) ||
					               removed_pair;
				}
			}
		}
	}
	REQUIRE(removed_pair);
}

TEST_CASE("outer_yan partial reduction: bushy composite and filtered queries preserve bags",
	      "[outer_yan][partial_reduction][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedPartialReduction(con);
	const vector<string> queries {
	    "SELECT a.*,b.*,c.*,d.* FROM (pr_a a INNER JOIN pr_b b ON a.k=b.k AND a.part=b.part) "
	    "FULL JOIN (pr_c c RIGHT JOIN pr_d d ON c.k=d.k AND c.part=d.part) ON b.k=c.k AND b.part=c.part",
	    "SELECT a.*,b.*,c.*,d.* FROM (pr_a a LEFT JOIN pr_b b ON a.k=b.k AND a.part=b.part) "
	    "RIGHT JOIN (pr_c c INNER JOIN pr_d d ON c.k=d.k AND c.part=d.part) ON a.k=c.k AND a.part=c.part",
	    "SELECT a.*,b.*,c.*,d.* FROM pr_a a LEFT JOIN (pr_b b INNER JOIN pr_c c "
	    "ON b.k=c.k AND b.part=c.part) ON a.k=b.k AND a.part=b.part LEFT JOIN pr_d d ON a.k=d.k",
	    "SELECT a.*,b.*,c.*,d.* FROM pr_a a LEFT JOIN (SELECT * FROM pr_b WHERE v>=0) b "
	    "ON a.k=b.k AND a.part=b.part LEFT JOIN pr_c c ON b.k=c.k AND b.part=c.part "
	    "FULL JOIN pr_d d ON a.k=d.k AND a.part=d.part",
	    "SELECT a.*,b.*,c.* FROM pr_a a LEFT JOIN pr_b b ON a.k=b.k "
	    "LEFT JOIN pr_c c ON b.k=c.k WHERE b.v IS NULL OR b.v>100",
	    "SELECT a.*,b.*,c.* FROM pr_a a LEFT JOIN pr_b b ON a.k=b.k "
	    "LEFT JOIN pr_c c ON b.k=c.k WHERE a.v>=20",
	};
	SECTION("duplicates, NULL keys, unmatched rows and optional attributes") {
	}
	SECTION("empty inner input") {
		REQUIRE_NO_FAIL(con.Query("DELETE FROM pr_c"));
	}
	for (const auto &sql : queries) {
		CheckPartialReductionResult(con, sql);
	}
}

TEST_CASE("outer_yan partial reduction: aggregate queries retain the reference schedule",
	      "[outer_yan][partial_reduction][aggregate]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedPartialReduction(con);
	const string from = " FROM pr_a a LEFT JOIN pr_b b ON a.k=b.k LEFT JOIN pr_c c ON b.k=c.k";
	for (const auto &sql : {"SELECT COUNT(*)" + from,
	                        "SELECT a.k,COUNT(*)" + from + " GROUP BY a.k",
	                        "SELECT a.k,COUNT(c.v)" + from + " GROUP BY a.k",
	                        "SELECT a.k,COUNT(*),SUM(c.v)" + from + " GROUP BY a.k",
	                        "SELECT a.k,COUNT(*),MIN(c.v)" + from + " GROUP BY a.k",
	                        "SELECT a.k,COUNT(*),MAX(c.v)" + from + " GROUP BY a.k",
	                        "SELECT a.k,COUNT(*) FILTER (WHERE c.v>1000)" + from + " GROUP BY a.k",
	                        "SELECT a.k,MIN(c.v),MAX(c.v)" + from + " GROUP BY a.k",
	                        "SELECT a.k,SUM(c.v)" + from + " GROUP BY a.k"}) {
		REQUIRE_FALSE(CheckPartialReductionResult(con, sql));
	}
}

TEST_CASE("outer_yan partial reduction: order compatible schedule omits top down and first inner reducer",
	      "[outer_yan][partial_reduction][schedule]") {
	DuckDB db(nullptr);
	Connection con(db);
	auto root = PartialNode(0);
	PartialAddEdge(*root, PartialNode(1), 1, JoinType::INNER, JoinType::INNER, 2);
	PartialAddEdge(*root, PartialNode(2), 2, JoinType::INNER, JoinType::INNER, 2);
	PartialAddEdge(*root, PartialNode(3), 3, JoinType::LEFT, JoinType::LEFT, 2);
	auto tree = PartialScheduleTree(con, std::move(root), 4);
	const auto selected_tree = tree->OJT().Print();
	REQUIRE(PartialReduction().Apply(*tree));
	REQUIRE(tree->top_down_pairs.empty());
	REQUIRE(tree->bottom_up_pairs.size() == 1);
	REQUIRE(PartialHasPair(tree->bottom_up_pairs, 2, 0));
	REQUIRE(tree->bottom_up_pairs[0].keys.size() == 2);
	REQUIRE(tree->bottom_up_pairs[0].keys[1].build_binding == ColumnBinding(TableIndex(2), ProjectionIndex(1)));
	REQUIRE(tree->bottom_up_pairs[0].keys[1].probe_binding == ColumnBinding(TableIndex(0), ProjectionIndex(1)));
	REQUIRE(tree->OJT().Print() == selected_tree);
	const auto signature = PartialScheduleSignature(*tree);
	REQUIRE_FALSE(PartialReduction().Apply(*tree));
	REQUIRE(PartialScheduleSignature(*tree) == signature);
}

TEST_CASE("outer_yan partial reduction: child first retains ancestor reduction and root dependency",
	      "[outer_yan][partial_reduction][schedule]") {
	DuckDB db(nullptr);
	Connection con(db);
	auto root = PartialNode(0);
	PartialAddEdge(*root, PartialNode(1), 1, JoinType::INNER, JoinType::INNER);
	auto branch = PartialNode(2);
	PartialAddEdge(*branch, PartialNode(3), 2, JoinType::INNER, JoinType::INNER);
	PartialAddEdge(*root, std::move(branch), 3, JoinType::INNER, JoinType::INNER);
	PartialAddEdge(*root, PartialNode(4), 4, JoinType::LEFT, JoinType::LEFT);
	auto tree = PartialScheduleTree(con, std::move(root), 5);
	REQUIRE(PartialReduction().Apply(*tree));
	REQUIRE(tree->top_down_pairs.size() == 1);
	REQUIRE(PartialHasPair(tree->top_down_pairs, 0, 2));
	REQUIRE(tree->bottom_up_pairs.size() == 3);
	REQUIRE(PartialHasPair(tree->bottom_up_pairs, 1, 0));
	REQUIRE(PartialHasPair(tree->bottom_up_pairs, 3, 2));
	REQUIRE(PartialHasPair(tree->bottom_up_pairs, 2, 0));
}

TEST_CASE("outer_yan partial reduction: newly preserved input keeps required top down",
	      "[outer_yan][partial_reduction][schedule]") {
	DuckDB db(nullptr);
	Connection con(db);
	auto root = PartialNode(0);
	PartialAddEdge(*root, PartialNode(1), 1, JoinType::INNER, JoinType::INNER);
	PartialAddEdge(*root, PartialNode(2), 2, JoinType::LEFT, JoinType::INNER);
	PartialAddEdge(*root, PartialNode(3), 3, JoinType::LEFT, JoinType::LEFT);
	auto tree = PartialScheduleTree(con, std::move(root), 4);
	// LEFT preserves R0, not R2: orient the relaxation as RIGHT so that the
	// newly joined child is preserved. No subsequent edge rejects R0 padding.
	tree->OJT().Root().children[1].kind = JoinType::RIGHT;
	tree->OJT().Root().children[1].info->join_kind = JoinType::RIGHT;
	REQUIRE(Resimplification::IsSimple(tree->OJT()));
	REQUIRE(PartialReduction().Apply(*tree));
	REQUIRE(tree->top_down_pairs.size() == 1);
	REQUIRE(PartialHasPair(tree->top_down_pairs, 0, 2));
	REQUIRE(PartialHasPair(tree->bottom_up_pairs, 1, 0));
}

TEST_CASE("outer_yan partial reduction: bushy dependency retains the complete ancestor path",
	      "[outer_yan][partial_reduction][schedule]") {
	DuckDB db(nullptr);
	Connection con(db);
	auto root = PartialNode(0);
	PartialAddEdge(*root, PartialNode(1), 1, JoinType::INNER, JoinType::INNER);
	auto upper = PartialNode(2);
	auto lower = PartialNode(3);
	PartialAddEdge(*lower, PartialNode(4), 2, JoinType::INNER, JoinType::INNER);
	PartialAddEdge(*upper, std::move(lower), 3, JoinType::INNER, JoinType::INNER);
	PartialAddEdge(*root, std::move(upper), 4, JoinType::INNER, JoinType::INNER);
	PartialAddEdge(*root, PartialNode(5), 5, JoinType::LEFT, JoinType::LEFT);
	auto tree = PartialScheduleTree(con, std::move(root), 6);
	REQUIRE(PartialReduction().Apply(*tree));
	REQUIRE(tree->top_down_pairs.size() == 2);
	REQUIRE(tree->top_down_pairs[0].build == 0);
	REQUIRE(tree->top_down_pairs[0].probe == 2);
	REQUIRE(tree->top_down_pairs[1].build == 2);
	REQUIRE(tree->top_down_pairs[1].probe == 3);
	REQUIRE(PartialHasPair(tree->bottom_up_pairs, 1, 0));
	REQUIRE(PartialHasPair(tree->bottom_up_pairs, 4, 3));
}

TEST_CASE("outer_yan partial reduction: RIGHT first join roots at its preserved endpoint",
	      "[outer_yan][partial_reduction][schedule]") {
	DuckDB db(nullptr);
	Connection con(db);
	auto root = PartialNode(0);
	PartialAddEdge(*root, PartialNode(1), 1, JoinType::RIGHT, JoinType::RIGHT);
	PartialAddEdge(*root, PartialNode(2), 2, JoinType::LEFT, JoinType::LEFT);
	auto tree = PartialScheduleTree(con, std::move(root), 3);
	REQUIRE(tree->bottom_up_pairs.size() == 1);
	REQUIRE(tree->top_down_pairs.size() == 1);
	const auto selected_tree = tree->OJT().Print();
	REQUIRE(PartialReduction().Apply(*tree));
	REQUIRE(tree->bottom_up_pairs.empty());
	REQUIRE(tree->top_down_pairs.empty());
	REQUIRE(tree->OJT().Print() == selected_tree);
}

TEST_CASE("outer_yan partial reduction: unsupported schedules leave all pairs intact",
	      "[outer_yan][partial_reduction][schedule]") {
	DuckDB db(nullptr);
	Connection con(db);
	auto root = PartialNode(0);
	PartialAddEdge(*root, PartialNode(1), 1, JoinType::INNER, JoinType::INNER);
	PartialAddEdge(*root, PartialNode(2), 2, JoinType::LEFT, JoinType::LEFT);
	auto tree = PartialScheduleTree(con, std::move(root), 3);
	SECTION("aggregation needs a separate proof") {
		tree->root_aggregation.type = OuterYanAggregationType::COUNT_STAR;
	}
	SECTION("selected order rejects previous NULL padding") {
		tree->OJT().Root().children[0].kind = JoinType::RIGHT;
		tree->OJT().Root().children[1].kind = JoinType::INNER;
	}
	SECTION("unsafe intermediate filter") {
		auto filter = make_uniq<OuterYanFilterRecord>(
		    make_uniq<BoundConstantExpression>(Value::BOOLEAN(true)), unordered_set<idx_t> {0, 1}, 0);
		filter->requires_original_scope = true;
		tree->filter_records.push_back(std::move(filter));
	}
	SECTION("invalid relation binding") {
		tree->table_to_relation.clear();
		// Force a required pair, rather than an order-compatible zero-pair
		// schedule that has no binding to construct.
		tree->OJT().Root().children[1].kind = JoinType::RIGHT;
		tree->OJT().Root().children[1].original_kind = JoinType::INNER;
	}
	SECTION("already empty constraint pruned schedule") {
		tree->bottom_up_pairs.clear();
		tree->top_down_pairs.clear();
	}
	const auto signature = PartialScheduleSignature(*tree);
	REQUIRE_FALSE(PartialReduction().Apply(*tree));
	REQUIRE(PartialScheduleSignature(*tree) == signature);
}
