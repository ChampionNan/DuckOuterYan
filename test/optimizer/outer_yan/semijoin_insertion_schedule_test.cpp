#include "catch.hpp"
#include "test_helpers.hpp"

#include "duckdb.hpp"
#include "duckdb/catalog/catalog_entry/table_catalog_entry.hpp"
#include "duckdb/optimizer/outer_yan/semi_join/semijoin_insertion.hpp"
#include "duckdb/planner/operator/logical_get.hpp"

#include <functional>

using namespace duckdb;

namespace {

void SharingAddPair(vector<OuterYanSemiPair> &pairs, idx_t build, idx_t probe,
                    const vector<ColumnBinding> &bindings) {
	OuterYanSemiPair pair;
	pair.build = build;
	pair.probe = probe;
	pair.keys.push_back({bindings[build], bindings[probe]});
	pairs.push_back(std::move(pair));
}

} // namespace

TEST_CASE("outer_yan semijoin insertion: top-down filters rebuild after reduction and share within round",
          "[outer_yan][semi][schedule]") {
	DuckDB db(nullptr);
	Connection con(db);
	const vector<string> names {"sj_share_a", "sj_share_b", "sj_share_c", "sj_share_d"};
	for (const auto &name : names) {
		REQUIRE_NO_FAIL(con.Query("CREATE TABLE " + name + "(k INTEGER)"));
		REQUIRE_NO_FAIL(con.Query("INSERT INTO " + name + " VALUES (1),(2)"));
	}
	REQUIRE_NO_FAIL(con.Query("SET disabled_optimizers TO 'outer_yan'"));
	// The insertion pass needs only base scans and relation bindings; using a
	// cross product here makes this white-box fixture independent of DP choices.
	auto plan = con.ExtractPlan("SELECT a.k,b.k,c.k,d.k FROM sj_share_a a, sj_share_b b, "
	                            "sj_share_c c, sj_share_d d", false);
	REQUIRE(plan);
	OuterYanTree tree;
	vector<ColumnBinding> bindings(names.size());
	std::function<void(LogicalOperator &)> index = [&](LogicalOperator &op) {
		if (op.type == LogicalOperatorType::LOGICAL_GET) {
			auto &get = op.Cast<LogicalGet>();
			auto table = get.GetTable();
			REQUIRE(table);
			for (idx_t relation = 0; relation < names.size(); relation++) {
				if (table->name == names[relation]) {
					tree.table_to_relation.emplace(get.table_index.index, relation);
					const auto columns = get.GetColumnBindings();
					REQUIRE(columns.size() == 1);
					bindings[relation] = columns[0];
					return;
				}
			}
		}
		for (auto &child : op.children) {
			index(*child);
		}
	};
	index(*plan);
	REQUIRE(tree.table_to_relation.size() == names.size());

	// A is the root; B has children C and D. All use B.k, so B's BU
	// filter (B after C/D reduction) must not serve its TD probes after A
	// has further reduced B. The two TD children may share the fresh filter.
	SharingAddPair(tree.bottom_up_pairs, 2, 1, bindings);
	SharingAddPair(tree.bottom_up_pairs, 3, 1, bindings);
	SharingAddPair(tree.bottom_up_pairs, 1, 0, bindings);
	SharingAddPair(tree.top_down_pairs, 0, 1, bindings);
	SharingAddPair(tree.top_down_pairs, 1, 2, bindings);
	SharingAddPair(tree.top_down_pairs, 1, 3, bindings);
	plan = SemijoinInsertion().Apply(std::move(plan), tree, *con.context, 0, false);
	REQUIRE(plan);

	vector<LogicalSJBuild *> b_builds;
	vector<LogicalSJProbe *> child_probes;
	std::function<void(LogicalOperator &)> inspect = [&](LogicalOperator &op) {
		const auto columns = op.GetColumnBindings();
		if (columns.size() == 1 && op.type == LogicalOperatorType::LOGICAL_SJ_BUILD &&
		    columns[0] == bindings[1]) {
			b_builds.push_back(&op.Cast<LogicalSJBuild>());
		}
		if (columns.size() == 1 && op.type == LogicalOperatorType::LOGICAL_SJ_PROBE &&
		    (columns[0] == bindings[2] || columns[0] == bindings[3]) && op.Cast<LogicalSJProbe>().top_down) {
			child_probes.push_back(&op.Cast<LogicalSJProbe>());
		}
		for (auto &child : op.children) {
			inspect(*child);
		}
	};
	inspect(*plan);
	REQUIRE(b_builds.size() == 2);
	LogicalSJBuild *bottom_up = nullptr;
	LogicalSJBuild *top_down = nullptr;
	for (auto *build : b_builds) {
		(build->top_down ? top_down : bottom_up) = build;
	}
	REQUIRE(bottom_up);
	REQUIRE(top_down);
	REQUIRE(bottom_up->filter_ids.size() == 1);
	REQUIRE(top_down->filter_ids.size() == 1);
	REQUIRE(bottom_up->filter_ids[0] != top_down->filter_ids[0]);
	REQUIRE(bottom_up->sj_to_create[0] != top_down->sj_to_create[0]);
	REQUIRE(top_down->children.size() == 1);
	REQUIRE(top_down->children[0]->type == LogicalOperatorType::LOGICAL_SJ_PROBE);
	REQUIRE(top_down->children[0]->Cast<LogicalSJProbe>().top_down);
	REQUIRE(child_probes.size() == 2);
	for (auto *probe : child_probes) {
		REQUIRE(probe->related_sj_build.size() == 1);
		REQUIRE(probe->related_sj_build[0] == top_down);
		REQUIRE(probe->filter_ids[0] == top_down->filter_ids[0]);
		REQUIRE(probe->sj_to_use[0] == top_down->sj_to_create[0]);
	}
}
