#include "duckdb.hpp"
#include "duckdb/catalog/catalog_entry/table_catalog_entry.hpp"
#include "duckdb/execution/operator/join/join_filter_pushdown.hpp"
#include "duckdb/main/config.hpp"
#include "duckdb/optimizer/optimizer_extension.hpp"
#include "duckdb/planner/expression/bound_columnref_expression.hpp"
#include "duckdb/planner/operator/logical_comparison_join.hpp"
#include "duckdb/planner/operator/logical_get.hpp"

#include <fstream>
#include <iostream>
#include <sstream>

using namespace duckdb;

static void PrintExpression(const Expression &expr) {
	std::cout << expr.ToString();
	if (expr.GetExpressionClass() == ExpressionClass::BOUND_COLUMN_REF) {
		const auto &ref = expr.Cast<BoundColumnRefExpression>();
		std::cout << " [" << ref.binding.ToString() << "]";
	}
}

static void PrintPlan(LogicalOperator &op, unsigned depth = 0) {
	std::cout << std::string(depth * 2, ' ') << LogicalOperatorToString(op.type);
	std::cout << " estimated=" << op.estimated_cardinality << " has_estimate=" << op.has_estimated_cardinality;
	if (op.type == LogicalOperatorType::LOGICAL_GET) {
		auto &get = op.Cast<LogicalGet>();
		std::cout << " table=" << get.GetTable()->name << " table_index=" << get.table_index.index;
	}
	if (op.type == LogicalOperatorType::LOGICAL_COMPARISON_JOIN) {
		auto &join = op.Cast<LogicalComparisonJoin>();
		std::cout << " join=" << JoinTypeToString(join.join_type);
		for (const auto &cond : join.conditions) {
			std::cout << " condition=(";
			if (cond.IsComparison()) {
				PrintExpression(cond.GetLHS());
				std::cout << " = ";
				PrintExpression(cond.GetRHS());
			}
			std::cout << ")";
		}
		std::cout << " pushdown_targets=" << (join.filter_pushdown ? join.filter_pushdown->probe_info.size() : 0);
		if (join.filter_pushdown) {
			for (const auto &target : join.filter_pushdown->probe_info) {
				for (const auto &column : target.columns) {
					std::cout << " target=" << column.probe_column_index.ToString();
				}
			}
		}
	}
	std::cout << '\n';
	for (auto &child : op.children) {
		PrintPlan(*child, depth + 1);
	}
}

int main(int argc, char **argv) {
	if (argc != 5) {
		std::cerr << "usage: inspect_replay DATABASE QUERY_SQL SETUP_SQL LABEL\n";
		return 2;
	}
	try {
		DBConfig config;
		config.options.access_mode = AccessMode::READ_ONLY;
		config.options.maximum_threads = 1;
		OptimizerExtension inspector;
		inspector.optimize_function = [](OptimizerExtensionInput &, unique_ptr<LogicalOperator> &plan) {
			if (plan->type == LogicalOperatorType::LOGICAL_EXPLAIN) {
				PrintPlan(*plan);
			}
		};
		OptimizerExtension::Register(config, std::move(inspector));
		DuckDB database(argv[1], &config);
		Connection connection(database);
		std::ifstream query_file(argv[2]), setup_file(argv[3]);
		if (!query_file || !setup_file) {
			throw std::runtime_error("cannot read query or setup");
		}
		std::stringstream query, setup;
		query << query_file.rdbuf();
		setup << setup_file.rdbuf();
		auto result = connection.Query(setup.str());
		if (result->HasError()) {
			throw std::runtime_error(result->GetError());
		}
		std::cout << "MODE " << argv[4] << '\n';
		auto explained = connection.Query("EXPLAIN " + query.str());
		if (explained->HasError()) {
			throw std::runtime_error(explained->GetError());
		}
	} catch (const std::exception &ex) {
		std::cerr << ex.what() << '\n';
		return 1;
	}
}
