// Isolated experiment runner. It does not change the native/OY optimizer path.
#include "duckdb.hpp"
#include "duckdb/execution/operator/join/join_filter_pushdown.hpp"
#include "duckdb/main/config.hpp"
#include "duckdb/optimizer/column_lifetime_analyzer.hpp"
#include "duckdb/optimizer/join_filter_pushdown_optimizer.hpp"
#include "duckdb/optimizer/optimizer_extension.hpp"
#include "duckdb/optimizer/outer_yan/postgres_plan_replay.hpp"
#include "duckdb/optimizer/remove_unused_columns.hpp"
#include "duckdb/optimizer/statistics_propagator.hpp"
#include "duckdb/planner/operator/logical_comparison_join.hpp"
#include "duckdb/planner/operator/logical_filter.hpp"
#include "duckdb/planner/operator/logical_get.hpp"

#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>

using namespace duckdb;

namespace {

struct ExperimentState : OptimizerExtensionInfo {
	bool active = false;
	bool replay = false;
	bool capture_plan = false;
	string semantic_signature;
	idx_t repaired_queries = 0;
};

void JSONString(std::ostream &out, const string &value) {
	out << '"';
	for (unsigned char byte : value) {
		if (byte == '"' || byte == '\\') {
			out << '\\' << char(byte);
		} else if (byte < 32) {
			out << "\\u00" << "0123456789abcdef"[byte >> 4] << "0123456789abcdef"[byte & 15];
		} else {
			out << char(byte);
		}
	}
	out << '"';
}

void CheckRepairScope(const LogicalOperator &op) {
	switch (op.type) {
	case LogicalOperatorType::LOGICAL_GET:
	case LogicalOperatorType::LOGICAL_PROJECTION:
	case LogicalOperatorType::LOGICAL_FILTER:
	case LogicalOperatorType::LOGICAL_COMPARISON_JOIN:
		break;
	default:
		throw std::runtime_error("replay repair requires a scan/filter/projection/comparison-join SELECT");
	}
	for (const auto &child : op.children) {
		CheckRepairScope(*child);
	}
}

void ClearDerivedMetadata(LogicalOperator &op) {
	// These refer to bindings/projections that the second pruning pass can change.
	// Reset both ends of dynamic filters; regenerate them only after all rewrites.
	if (op.type == LogicalOperatorType::LOGICAL_COMPARISON_JOIN) {
		auto &join = op.Cast<LogicalComparisonJoin>();
		join.filter_pushdown.reset();
		join.left_projection_map.clear();
		join.right_projection_map.clear();
	} else if (op.type == LogicalOperatorType::LOGICAL_FILTER) {
		op.Cast<LogicalFilter>().projection_map.clear();
	} else if (op.type == LogicalOperatorType::LOGICAL_GET) {
		op.Cast<LogicalGet>().dynamic_filters.reset();
	}
	for (auto &child : op.children) {
		ClearDerivedMetadata(*child);
	}
}

void RepairReplay(OptimizerExtensionInput &input, unique_ptr<LogicalOperator> &plan) {
	auto &state = static_cast<ExperimentState &>(*input.info);
	if (!state.active) {
		return;
	}
	if (!state.replay) {
		if (state.capture_plan) {
			state.semantic_signature = PostgresPlanReplay::SemanticSignature(*plan);
		}
		return;
	}
	if (!PostgresPlanReplay::ConfiguredPlanPath(input.context)) {
		throw std::runtime_error("PG mode did not activate PostgreSQL replay");
	}
	CheckRepairScope(*plan);
	const auto signature = PostgresPlanReplay::SemanticSignature(*plan);
	ClearDerivedMetadata(*plan);
	// Replay initially prunes before build/probe swapping. Repeating native
	// pruning now canonicalizes INNER equality keys to the final probe side.
	RemoveUnusedColumns unused(input.optimizer);
	unused.VisitOperator(plan);
	plan->ResolveOperatorTypes();
	StatisticsPropagator statistics(input.optimizer, *plan);
	statistics.PropagateStatistics(plan);
	ColumnLifetimeAnalyzer lifetime(input.optimizer, *plan, true);
	lifetime.VisitOperator(*plan);
	JoinFilterPushdownOptimizer filters(input.optimizer);
	filters.VisitOperator(*plan);
	plan->ResolveOperatorTypes();
	if (PostgresPlanReplay::SemanticSignature(*plan) != signature) {
		throw std::runtime_error("replay repair changed the imported typed join tree");
	}
	// Optimizer::Optimize additionally verifies the original artifact signature
	// after this callback, including its stable scan-occurrence assignments.
	state.repaired_queries++;
	if (state.capture_plan) {
		state.semantic_signature = signature;
	}
}

void Configure(Connection &connection, const string &sql) {
	auto result = connection.Query(sql);
	if (result->HasError()) {
		throw std::runtime_error(result->GetError());
	}
}

} // namespace

int main(int argc, char **argv) {
	if (argc < 6 || argc > 8) {
		std::cerr << "usage: fair_replay_runner DATABASE QUERY_SQL {PG|native|OY} ARTIFACT_OR_- "
		             "PROFILE_OR_- [RESULT_ROWS_OR_- [ids|jsonl]]\n";
		return 2;
	}
	try {
		const string mode = argv[3], artifact = argv[4], profile = argv[5];
		const string row_format = argc == 8 ? argv[7] : "ids";
		if (row_format != "ids" && row_format != "jsonl") {
			throw std::runtime_error("row format must be ids or jsonl");
		}
		if (mode != "PG" && mode != "native" && mode != "OY") {
			throw std::runtime_error("mode must be PG, native or OY");
		}
		if ((mode == "PG") != (artifact != "-")) {
			throw std::runtime_error("only PG mode requires an artifact path");
		}
		std::ifstream input(argv[2]);
		if (!input) {
			throw std::runtime_error("cannot read query file");
		}
		std::stringstream query;
		query << input.rdbuf();
		std::ofstream rows;
		if (argc >= 7 && string(argv[6]) != "-") {
			rows.open(argv[6], std::ios::binary);
			if (!rows) {
				throw std::runtime_error("cannot open result file");
			}
		}
		DBConfig config;
		config.options.access_mode = AccessMode::READ_ONLY;
		config.options.maximum_threads = 1;
		auto state = make_shared_ptr<ExperimentState>();
		state->replay = mode == "PG";
		state->capture_plan = profile != "-";
		OptimizerExtension extension;
		extension.optimize_function = RepairReplay;
		extension.optimizer_info = state;
		OptimizerExtension::Register(config, std::move(extension));
		DuckDB database(argv[1], &config);
		Connection connection(database);
		auto statements = connection.ExtractStatements(query.str());
		if (statements.size() != 1 || statements[0]->type != StatementType::SELECT_STATEMENT) {
			throw std::runtime_error("query file must contain exactly one bare SELECT");
		}
		Configure(connection, "SET threads=1; SET memory_limit='4GB'; SET max_execution_time=3600000; "
		                      "SET disabled_optimizers='" + string(mode == "OY" ? "" : "outer_yan") + "';");
		if (profile != "-") {
			Configure(connection, "CALL enable_profiling(format='json', save_location=" +
			                          Value(profile).ToSQLString() + ");");
		}
		if (state->replay) {
			Configure(connection, "SET VARIABLE pgplan=" + Value(artifact).ToSQLString());
		}
		state->active = true;
		const auto start = std::chrono::steady_clock::now();
		auto result = connection.SendQuery(query.str());
		if (result->HasError()) {
			throw std::runtime_error(result->GetError());
		}
		idx_t row_count = 0;
		while (auto chunk = result->Fetch()) {
			row_count += chunk->size();
			if (rows.is_open()) {
				for (idx_t row = 0; row < chunk->size(); row++) {
					if (row_format == "jsonl") {
						rows << '[';
					}
					for (idx_t col = 0; col < chunk->ColumnCount(); col++) {
						if (col) {
							rows << ',';
						}
						auto value = chunk->GetValue(col, row);
						if (row_format == "jsonl") {
							if (value.IsNull()) {
								rows << "null";
							} else if (value.type().IsIntegral() || value.type().id() == LogicalTypeId::VARCHAR) {
								JSONString(rows, value.ToString());
							} else {
								throw std::runtime_error("JSONL comparison supports integer, VARCHAR and NULL results");
							}
						} else if (!value.IsNull() && !value.type().IsIntegral()) {
							throw std::runtime_error("result CSV supports only integer/NULL benchmark row identifiers");
						} else {
							rows << value.ToSQLString();
						}
					}
					if (row_format == "jsonl") {
						rows << ']';
					}
					rows << '\n';
				}
			}
		}
		if (result->HasError()) {
			throw std::runtime_error(result->GetError());
		}
		const double elapsed_ms =
		    std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - start).count();
		state->active = false;
		if (state->replay && state->repaired_queries != 1) {
			throw std::runtime_error("expected exactly one repaired bare query");
		}
		if (rows.is_open()) {
			rows.close();
			if (!rows) {
				throw std::runtime_error("result output failed");
			}
		}
		std::cout << std::setprecision(12) << "[FAIR_RUN] {\"mode\":\"" << mode << "\",\"elapsed_ms\":"
		          << elapsed_ms << ",\"rows\":" << row_count << ",\"repaired_queries\":" << state->repaired_queries
		          << ",\"profiled\":" << (profile == "-" ? "false" : "true")
		          << ",\"rows_exported\":" << (argc >= 7 && string(argv[6]) != "-" ? "true" : "false")
		          << ",\"semantic_signature\":";
		JSONString(std::cout, state->semantic_signature);
		std::cout << ",\"types\":[";
		for (idx_t i = 0; i < result->types.size(); i++) {
			if (i) {
				std::cout << ',';
			}
			JSONString(std::cout, result->types[i].ToString());
		}
		std::cout << "]}\n";
	} catch (const std::exception &error) {
		std::cerr << error.what() << '\n';
		return 1;
	}
	return 0;
}
