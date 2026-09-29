// Planning-only experiment: extrapolate SF1 statistics without changing data.
#include "duckdb.hpp"
#include "duckdb/catalog/catalog_entry/table_catalog_entry.hpp"
#include "duckdb/function/table/table_scan.hpp"
#include "duckdb/main/config.hpp"
#include "duckdb/main/extension/extension_loader.hpp"
#include "duckdb/optimizer/optimizer_extension.hpp"
#include "duckdb/optimizer/outer_yan/pipeline/outer_yan_dp.hpp"
#include "duckdb/optimizer/outer_yan/pipeline/outer_yan_pre.hpp"
#include "duckdb/planner/operator/logical_get.hpp"
#include "duckdb/storage/statistics/base_statistics.hpp"
#include "duckdb/storage/statistics/node_statistics.hpp"
#include "duckdb/storage/statistics/numeric_stats.hpp"

#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>

using namespace duckdb;

static idx_t scale = 1;
static TableFunction original_scan = TableScanFunction::GetFunction();
static TableFunction whatif_scan = original_scan;
static std::map<string, idx_t> seen_rows, seen_ndv;

static bool IsJoinKey(const string &name) {
	return name == "c_custkey" || name == "o_custkey" || name == "o_orderkey" || name == "l_orderkey";
}

static unique_ptr<NodeStatistics> ScaledCardinality(ClientContext &context, const FunctionData *data) {
	auto stats = original_scan.cardinality(context, data);
	if (!stats || !stats->has_estimated_cardinality) throw std::runtime_error("Missing scan cardinality");
	stats->estimated_cardinality *= scale;
	if (stats->has_max_cardinality) stats->max_cardinality *= scale;
	seen_rows[data->Cast<TableScanBindData>().table.name] = stats->estimated_cardinality;
	return stats;
}

static unique_ptr<BaseStatistics> ScaledStatistics(ClientContext &context, TableFunctionGetStatisticsInput &input) {
	auto stats = original_scan.statistics_extended(context, input);
	if (!stats) return stats;
	auto &table = input.bind_data->Cast<TableScanBindData>().table;
	const auto &name = table.GetColumn(LogicalIndex(input.column_index.GetPrimaryIndex())).Name();
	if (IsJoinKey(name)) {
		stats->SetDistinctCount(stats->GetDistinctCount() * scale);
		if (NumericStats::HasMax(*stats)) {
			auto max = NumericStats::Max(*stats).GetValue<int64_t>();
			auto scaled_max = Value::BIGINT(max * static_cast<int64_t>(scale)).DefaultCastAs(stats->GetType());
			NumericStats::SetMax(*stats, scaled_max);
		}
	}
	seen_ndv[table.name + "." + name] = stats->GetDistinctCount();
	return stats;
}

static void InjectStatistics(LogicalOperator &op) {
	if (op.type == LogicalOperatorType::LOGICAL_GET) {
		auto &get = op.Cast<LogicalGet>();
		auto table = get.GetTable();
		if (!table || (table->name != "customer" && table->name != "orders" && table->name != "lineitem")) {
			throw std::runtime_error("This experiment only supports the supplied three-table query");
		}
		get.function = whatif_scan;
		get.has_estimated_cardinality = false;
	}
	for (auto &child : op.children) InjectStatistics(*child);
}

static void Configure(Connection &con, const string &sql) {
	auto result = con.Query(sql);
	if (result->HasError()) throw std::runtime_error(result->GetError());
}

static string Grouping(const OTNode &node, const OuterYanTree &tree) {
	if (node.kind == OTNode::Kind::RELATION) return tree.ot_relations_by_id[node.relation_id]->stats.table_name;
	return "(" + Grouping(*node.children[0], tree) + "," + Grouping(*node.children[1], tree) + ")";
}

static void PrintCost(const string &label, const OuterYanJoinCostBreakdown &cost) {
	std::cout << label << " total=" << cost.total_cost << " inputs=" << cost.total_input_rows;
	for (const auto &step : cost.steps) std::cout << " output=" << step.output;
	std::cout << '\n';
}

static void CompareAlternative(OuterYanTree &tree, const OuterYanDPCostSummary &summary, ClientContext &context) {
	idx_t customer = DConstants::INVALID_INDEX, orders = customer;
	for (auto *relation : tree.ot_relations_by_id) {
		if (relation->stats.table_name == "customer") customer = relation->relation_id;
		if (relation->stats.table_name == "orders") orders = relation->relation_id;
	}
	auto orient = [](OTNode &node, idx_t relation) {
		if (!node.children[0]->subtree_relations.count(relation)) {
			std::swap(node.children[0], node.children[1]);
			node.info->join_kind = FlipOuterYanJoinKind(node.info->join_kind);
			node.info->original_join_kind = FlipOuterYanJoinKind(node.info->original_join_kind);
		}
	};
	auto &root = tree.OT().Root();
	orient(root, customer);
	if (root.children[0]->kind != OTNode::Kind::RELATION || root.children[0]->relation_id != customer ||
	    root.children[1]->kind != OTNode::Kind::JOIN) {
		std::cout << "alternative_not_rotated: DP already changed grouping\n";
		return;
	}
	orient(*root.children[1], orders);
	auto co = std::move(tree.OT().root);
	auto ol = std::move(co->children[1]);
	if (co->info->join_kind != JoinType::LEFT || ol->info->join_kind != JoinType::LEFT) {
		throw std::runtime_error("Expected the post-Desimplify LEFT chain");
	}
	co->children[1] = std::move(ol->children[0]);
	co->order = 1;
	ol->children[0] = std::move(co);
	ol->order = 2;
	tree.OT().root = std::move(ol);
	tree.OT().Finalize();
	std::swap(tree.ot_joins_by_order[0], tree.ot_joins_by_order[1]);
	string reason;
	if (!tree.OT().IsValid(&reason)) throw std::runtime_error(reason);
	PrintCost("alternative_customer_orders_first",
	          OuterYanDP(context).ScoreCurrentJoinTreeDetailed(tree, &summary.reduced_cardinalities, true));
}

int main(int argc, char **argv) {
	try {
		if (argc != 5) throw std::runtime_error("Usage: stats_whatif DB QUERY SCALE OUTPUT_PREFIX");
		scale = std::stoull(argv[3]);
		if (scale < 1 || scale > 100) throw std::runtime_error("Supported scale range: 1..100");
		std::ifstream source(argv[2]);
		if (!source) throw std::runtime_error("Cannot open query");
		std::stringstream sql;
		sql << source.rdbuf();
		DBConfig config;
		config.options.access_mode = AccessMode::READ_ONLY;
		OptimizerExtension extension;
		extension.pre_optimize_function = [](OptimizerExtensionInput &, unique_ptr<LogicalOperator> &plan) {
			InjectStatistics(*plan);
		};
		OptimizerExtension::Register(config, std::move(extension));
		DuckDB db(argv[1], &config);
		// Register under a distinct name so the baseline plan's serialization/copy
		// also resolves the overridden callbacks instead of reverting to seq_scan.
		whatif_scan.name = "paper_stats_scan";
		whatif_scan.cardinality = ScaledCardinality;
		whatif_scan.statistics_extended = ScaledStatistics;
		ExtensionLoader loader(*db.instance, "paper_stats_whatif");
		loader.RegisterFunction(whatif_scan);
		Connection con(db);
		Configure(con, "SET disabled_optimizers=''; PRAGMA explain_output='all';");
		auto explain = con.Query("EXPLAIN " + sql.str());
		if (explain->HasError()) throw std::runtime_error(explain->GetError());
		std::ofstream plan_file(string(argv[4]) + ".plan.txt");
		if (!plan_file) throw std::runtime_error("Cannot open output file");
		for (idx_t i = 0; i < explain->RowCount(); i++) {
			plan_file << explain->GetValue(0, i).ToString() << '\n' << explain->GetValue(1, i).ToString() << "\n\n";
		}
		std::cout << std::setprecision(17) << "scale=" << scale << " source=SF1_extrapolation planning_only=1\n";
		for (const auto &entry : seen_rows) std::cout << "table=" << entry.first << " rows=" << entry.second << '\n';
		for (const auto &entry : seen_ndv) std::cout << "column=" << entry.first << " ndv=" << entry.second << '\n';
		// Inspect the normal-statistics DP candidate separately from the final
		// selector's conservative default-filter scenario (recorded in the trace).
		Configure(con, "SET disabled_optimizers='outer_yan_pre,outer_yan_dp,outer_yan_post,join_order,"
		               "column_lifetime,statistics_propagation,outer_join_simplification,join_elimination';");
		auto plan = con.ExtractPlan(sql.str(), false);
		Configure(con, "BEGIN TRANSACTION");
		OuterYanTree tree(*con.context);
		OuterYanPre().Optimize(std::move(plan), tree);
		auto summary = OuterYanDP(*con.context).Optimize(tree);
		if (!summary.has_complete_plan) throw std::runtime_error("DP failed");
		std::cout << "dp_grouping=" << Grouping(tree.OT().Root(), tree) << '\n';
		for (idx_t i = 0; i < summary.input_cardinalities.size(); i++) {
			std::cout << "relation=" << tree.ot_relations_by_id[i]->stats.table_name
			          << " filtered=" << summary.input_cardinalities[i] << " reduced=" << summary.reduced_cardinalities[i] << '\n';
		}
		PrintCost("dp_winner", summary.candidate_join_breakdown);
		CompareAlternative(tree, summary, *con.context);
		Configure(con, "ROLLBACK");
	} catch (const std::exception &error) {
		std::cerr << error.what() << '\n';
		return 1;
	}
}
