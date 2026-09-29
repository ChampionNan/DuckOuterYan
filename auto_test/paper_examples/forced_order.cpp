// Standalone experiment for the supplied three-table paper query. This registers
// a process-local optimizer callback; the DuckDB library and database stay intact.
#include "duckdb.hpp"
#include "duckdb/catalog/catalog_entry/table_catalog_entry.hpp"
#include "duckdb/main/config.hpp"
#include "duckdb/optimizer/filter_pushdown.hpp"
#include "duckdb/optimizer/optimizer_extension.hpp"
#include "duckdb/optimizer/outer_yan/pipeline/outer_yan_dp.hpp"
#include "duckdb/optimizer/outer_yan/pipeline/outer_yan_post.hpp"
#include "duckdb/optimizer/outer_yan/pipeline/outer_yan_pre.hpp"
#include "duckdb/planner/operator/logical_get.hpp"

#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <set>
#include <sstream>
#include <stdexcept>

using namespace duckdb;

struct ExperimentState : OptimizerExtensionInfo {
	string mode;
	bool active = false;
	idx_t verified_plans = 0;
};

static bool ForcedMode(const string &mode) {
	return mode == "sj_original" || mode == "sj_customer_first";
}

static void Orient(OTNode &node, idx_t left_relation) {
	if (!node.children[0]->subtree_relations.count(left_relation)) {
		std::swap(node.children[0], node.children[1]);
		node.info->join_kind = FlipOuterYanJoinKind(node.info->join_kind);
		node.info->original_join_kind = FlipOuterYanJoinKind(node.info->original_join_kind);
	}
}

static void FixCustomerOrdersFirst(OuterYanTree &tree) {
	idx_t customer = DConstants::INVALID_INDEX, orders = customer, lineitem = customer;
	for (auto *relation : tree.ot_relations_by_id) {
		const auto &name = relation->stats.table_name;
		if (name == "customer") customer = relation->relation_id;
		if (name == "orders") orders = relation->relation_id;
		if (name == "lineitem") lineitem = relation->relation_id;
	}
	if (tree.ot_relations_by_id.size() != 3 || customer == DConstants::INVALID_INDEX ||
	    orders == DConstants::INVALID_INDEX || lineitem == DConstants::INVALID_INDEX) {
		throw std::runtime_error("Expected exactly customer, orders and lineitem");
	}
	auto &root = tree.OT().Root();
	Orient(root, customer);
	if (root.children[0]->kind != OTNode::Kind::RELATION ||
	    root.children[0]->relation_id != customer || root.children[1]->kind != OTNode::Kind::JOIN) {
		throw std::runtime_error("Expected the SF1 DP winner customer-(orders-lineitem)");
	}
	Orient(*root.children[1], orders);
	tree.OT().Finalize();
	auto co = std::move(tree.OT().root);
	auto ol = std::move(co->children[1]);
	if (co->info->join_kind != JoinType::LEFT || ol->info->join_kind != JoinType::LEFT ||
	    ol->children[0]->kind != OTNode::Kind::RELATION || ol->children[0]->relation_id != orders ||
	    ol->children[1]->kind != OTNode::Kind::RELATION || ol->children[1]->relation_id != lineitem) {
		throw std::runtime_error("Expected the post-Desimplify LEFT chain");
	}
	// Same reduced relations and join predicates; only rotate the associative OT.
	co->children[1] = std::move(ol->children[0]);
	co->order = 1;
	ol->children[0] = std::move(co);
	ol->order = 2;
	tree.OT().root = std::move(ol);
	tree.OT().Finalize();
	std::swap(tree.ot_joins_by_order[0], tree.ot_joins_by_order[1]);
	string reason;
	if (!tree.OT().IsValid(&reason)) throw std::runtime_error(reason);
	tree.BuildOJT();
}

static void PreOptimize(OptimizerExtensionInput &input, unique_ptr<LogicalOperator> &plan) {
	auto &state = static_cast<ExperimentState &>(*input.info);
	if (!state.active || !ForcedMode(state.mode)) return;
	unique_ptr<LogicalOperator> explain;
	if (plan->type == LogicalOperatorType::LOGICAL_EXPLAIN) {
		explain = std::move(plan);
		plan = std::move(explain->children[0]);
	}
	plan = FilterPushdown(input.optimizer).Rewrite(std::move(plan));
	OuterYanTree tree(input.context);
	if (!tree.CheckApplicability(*plan)) throw std::runtime_error("Paper query is not applicable");
	OuterYanPre().Optimize(std::move(plan), tree);
	auto candidate = OuterYanDP(input.context).Optimize(tree);
	if (!candidate.has_complete_plan) throw std::runtime_error("OuterYan DP failed");
	if (state.mode == "sj_customer_first") FixCustomerOrdersFirst(tree);
	plan = OuterYanPost(input.context).Optimize(tree);
	if (explain) {
		explain->children[0] = std::move(plan);
		plan = std::move(explain);
	}
}

using Tables = std::set<string>;
static Tables CollectGroups(LogicalOperator &op, std::set<Tables> &groups, idx_t &sj_count) {
	Tables tables;
	if (op.type == LogicalOperatorType::LOGICAL_GET) {
		auto table = op.Cast<LogicalGet>().GetTable();
		if (table) tables.insert(table->name);
	}
	if (op.type == LogicalOperatorType::LOGICAL_SJ_PROBE) sj_count++;
	for (auto &child : op.children) {
		auto child_tables = CollectGroups(*child, groups, sj_count);
		tables.insert(child_tables.begin(), child_tables.end());
	}
	if (op.type == LogicalOperatorType::LOGICAL_COMPARISON_JOIN) groups.insert(tables);
	return tables;
}

static void VerifyFinalGrouping(OptimizerExtensionInput &input, unique_ptr<LogicalOperator> &plan) {
	auto &state = static_cast<ExperimentState &>(*input.info);
	if (!state.active) return;
	std::set<Tables> groups;
	idx_t sj_count = 0;
	auto tables = CollectGroups(*plan, groups, sj_count);
	const Tables all {"customer", "orders", "lineitem"};
	const Tables pair = state.mode == "sj_customer_first" ? Tables {"customer", "orders"}
	                                                     : Tables {"orders", "lineitem"};
	if (tables != all || groups != std::set<Tables> {all, pair}) {
		throw std::runtime_error("Final optimizer plan does not have the requested grouping");
	}
	if (ForcedMode(state.mode) && sj_count != 3) {
		throw std::runtime_error("Expected the original three semi-join probes");
	}
	state.verified_plans++;
}

static void Configure(Connection &con, const string &sql) {
	auto result = con.Query(sql);
	if (result->HasError()) throw std::runtime_error(result->GetError());
}

static idx_t Execute(Connection &con, const string &sql, std::ostream *rows = nullptr) {
	auto result = con.SendQuery(sql);
	if (result->HasError()) throw std::runtime_error(result->GetError());
	idx_t row_count = 0;
	while (auto chunk = result->Fetch()) {
		row_count += chunk->size();
		if (rows) {
			for (idx_t row = 0; row < chunk->size(); row++) {
				for (idx_t col = 0; col < chunk->ColumnCount(); col++) {
					// SQL literals preserve NULL, exact decimal values and string quoting.
					if (col) *rows << '\t';
					*rows << chunk->GetValue(col, row).ToSQLString();
				}
				*rows << '\n';
			}
		}
	}
	if (result->HasError()) throw std::runtime_error(result->GetError());
	return row_count;
}

int main(int argc, char **argv) {
	try {
		if (argc != 8) {
			std::cerr << "Usage: forced_order DB QUERY MODE ACTION RUNS THREADS OUTPUT\n";
			return 2;
		}
		const string mode = argv[3], action = argv[4], output = argv[7];
		const int runs = std::stoi(argv[5]), threads = std::stoi(argv[6]);
		if (runs < 1 || threads < 1) throw std::runtime_error("runs and threads must be positive");
		if (mode != "off" && mode != "on" && mode != "controlled_off" && !ForcedMode(mode)) {
			throw std::runtime_error("Unknown mode");
		}
		std::ifstream source(argv[2]);
		if (!source) throw std::runtime_error("Cannot read query");
		std::stringstream query;
		query << source.rdbuf();
		DBConfig config;
		config.options.access_mode = AccessMode::READ_ONLY;
		auto state = make_shared_ptr<ExperimentState>();
		state->mode = mode;
		OptimizerExtension extension;
		extension.pre_optimize_function = PreOptimize;
		extension.optimize_function = VerifyFinalGrouping;
		extension.optimizer_info = state;
		OptimizerExtension::Register(config, std::move(extension));
		DuckDB db(argv[1], &config);
		Connection con(db);
		const string disabled = mode == "on" ? "" : mode == "off" ? "outer_yan"
		                                                            : "outer_yan,join_order,unused_columns";
		Configure(con, "SET disabled_optimizers='" + disabled + "'; SET threads=" + std::to_string(threads) +
		               "; SET max_execution_time=120000; CALL disable_profiling();");
		idx_t row_count = 0;
		std::cout << std::setprecision(12);
		if (action == "explain") {
			Configure(con, "PRAGMA explain_output='all';");
			state->active = true;
			auto result = con.Query("EXPLAIN " + query.str());
			if (result->HasError()) throw std::runtime_error(result->GetError());
			std::ofstream file(output);
			for (idx_t row = 0; row < result->RowCount(); row++) {
				file << result->GetValue(0, row).ToString() << '\n' << result->GetValue(1, row).ToString() << "\n\n";
			}
		} else if (action == "correctness") {
			std::ofstream file(output);
			if (!file) throw std::runtime_error("Cannot open result file");
			state->active = true;
			row_count = Execute(con, query.str(), &file);
		} else if (action == "timing") {
			state->active = true;
			Execute(con, query.str());
			Execute(con, query.str());
			std::cout << "{\"seconds\":[";
			for (int i = 0; i < runs; i++) {
				auto start = std::chrono::steady_clock::now();
				row_count = Execute(con, query.str());
				double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
				if (i) std::cout << ',';
				std::cout << seconds;
			}
			std::cout << "],";
		} else if (action == "profile") {
			state->active = true;
			Execute(con, query.str());
			state->active = false;
			Configure(con, "CALL enable_profiling(format='json', save_location=" + Value(output).ToSQLString() + ");");
			state->active = true;
			row_count = Execute(con, query.str());
		} else {
			throw std::runtime_error("Unknown action");
		}
		std::cout << (action == "timing" ? "" : "{") << "\"rows\":" << row_count
		          << ",\"verified_plans\":" << state->verified_plans << "}\n";
	} catch (const std::exception &error) {
		std::cerr << error.what() << '\n';
		return 1;
	}
}
