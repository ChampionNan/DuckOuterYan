//===----------------------------------------------------------------------===//
//                         DuckDB
//
// duckdb/optimizer/join_order/statistics_extractor.hpp
//
//
//===----------------------------------------------------------------------===//
#pragma once

#include "duckdb/planner/filter/conjunction_filter.hpp"
#include "duckdb/planner/logical_operator.hpp"

namespace duckdb {

class CardinalityEstimator;

struct DistinctCount {
	idx_t distinct_count;
	bool from_hll;
};

struct ExpressionBinding {
public:
	bool FoundExpression() const {
		return expression;
	}
	bool FoundColumnRef() const {
		if (!FoundExpression()) {
			return false;
		}
		return expression->type == ExpressionType::BOUND_COLUMN_REF;
	}

public:
	optional_ptr<Expression> expression;
	ColumnBinding child_binding;
	bool expression_is_constant = false;
};

struct RelationStats {
	// column_id -> estimated distinct count for column
	vector<DistinctCount> column_distinct_count;
	idx_t cardinality;
	//! Cardinality before pushed-down table filters. Consumers can use this as
	//! an upper bound when `cardinality` came from the generic selectivity
	//! fallback rather than column statistics.
	idx_t base_cardinality;
	double filter_strength = 1;
	bool stats_initialized = false;
	bool cardinality_uses_default_filter_selectivity = false;
	bool cardinality_uses_modulo_selectivity = false;

	// for debug, column names and tables
	vector<string> column_names;
	string table_name;

	RelationStats() : cardinality(1), base_cardinality(1), filter_strength(1), stats_initialized(false) {
	}
};

class RelationStatisticsHelper {
public:
	static constexpr double DEFAULT_SELECTIVITY = 0.2;

public:
	//! Uniform residue estimate for column modulo equality and hash-modulo bucket predicates.
	//! Accepts both logical column references and scan-local bound references.
	static bool TryGetModuloSelectivity(const Expression &expr, double &selectivity);
	static idx_t InspectTableFilter(idx_t cardinality, const TableFilter &filter, BaseStatistics &base_stats,
	                               optional_ptr<bool> uses_modulo_selectivity = nullptr);
	//	static idx_t InspectConjunctionOR(idx_t cardinality, idx_t column_index, ConjunctionOrFilter &filter,
	//	                                  BaseStatistics &base_stats);
	//! Extract Statistics from a LogicalGet.
	static RelationStats ExtractGetStats(LogicalGet &get, ClientContext &context);
	static RelationStats ExtractDelimGetStats(LogicalDelimGet &delim_get, ClientContext &context);
	//! Create the statistics for a projection using the statistics of the operator that sits underneath the
	//! projection. Then also create statistics for any extra columns the projection creates.
	static RelationStats ExtractDummyScanStats(LogicalDummyScan &dummy_scan, ClientContext &context);
	static RelationStats ExtractExpressionGetStats(LogicalExpressionGet &expression_get, ClientContext &context);
	//! All relation extractors for blocking relations
	static RelationStats ExtractProjectionStats(LogicalProjection &proj, RelationStats &child_stats);
	static RelationStats ExtractAggregationStats(LogicalAggregate &aggr, RelationStats &child_stats);
	static RelationStats ExtractWindowStats(LogicalWindow &window, RelationStats &child_stats);
	static RelationStats ExtractEmptyResultStats(LogicalEmptyResult &empty);
	//! Called after reordering a query plan with potentially 2+ relations.
	static RelationStats CombineStatsOfReorderableOperator(vector<ColumnBinding> &bindings,
	                                                       vector<RelationStats> relation_stats);
	//! Called after reordering a query plan with potentially 2+ relations.
	static RelationStats CombineStatsOfNonReorderableOperator(LogicalOperator &op,
	                                                          const vector<RelationStats> &child_stats);
	static void CopyRelationStats(RelationStats &to, const RelationStats &from);

private:
	static idx_t GetDistinctCount(LogicalGet &get, ClientContext &context, const ColumnIndex &column_id);
};

} // namespace duckdb
