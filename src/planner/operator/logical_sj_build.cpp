#include "duckdb/planner/operator/logical_sj_build.hpp"

#include "duckdb/common/exception.hpp"
#include "duckdb/common/serializer/deserializer.hpp"
#include "duckdb/common/serializer/serializer.hpp"
#include "duckdb/optimizer/outer_yan/semi_join/semi_join_filter.hpp"

namespace duckdb {

LogicalSJBuild::LogicalSJBuild(vector<shared_ptr<SemiJoinFilter>> sj_to_create_p)
    : LogicalOperator(LogicalOperatorType::LOGICAL_SJ_BUILD), sj_to_create(std::move(sj_to_create_p)) {
}

void LogicalSJBuild::Serialize(Serializer &serializer) const {
	LogicalOperator::Serialize(serializer);
	// Serialize structural shape only — the live SemiJoinFilter data is
	// runtime state that cannot survive serialization.  The deserialized copy
	// has empty (UNDECIDED) filters; valid for plan analysis but not execution.
	serializer.WriteProperty(200, "num_filters", (idx_t)sj_to_create.size());
	serializer.WriteProperty(201, "build_col_ids_per_filter", build_col_ids_per_filter);
}

unique_ptr<LogicalOperator> LogicalSJBuild::Copy(ClientContext &context) const {
	// Structural copy that shares SemiJoinFilter instances (shared_ptr semantics).
	// The default Copy goes via serialize/deserialize, which is unimplemented for
	// SJ operators.  AggregatePushdownOuter needs a throwaway deep copy of the plan
	// to run its speculative rewrite; sharing the live filters is safe because the
	// copy is never executed.
	auto copy = make_uniq<LogicalSJBuild>(sj_to_create);
	copy->build_col_ids_per_filter = build_col_ids_per_filter;
	for (const auto &child : children) {
		copy->children.push_back(child->Copy(context));
	}
	copy->types = types;
	return copy;
}

unique_ptr<LogicalOperator> LogicalSJBuild::Deserialize(Deserializer &deserializer) {
	auto num_filters = deserializer.ReadProperty<idx_t>(200, "num_filters");
	auto build_col_ids = deserializer.ReadProperty<vector<vector<idx_t>>>(201, "build_col_ids_per_filter");
	vector<shared_ptr<SemiJoinFilter>> filters;
	filters.reserve(num_filters);
	for (idx_t i = 0; i < num_filters; i++) {
		filters.push_back(make_shared_ptr<SemiJoinFilter>());
	}
	auto result = make_uniq<LogicalSJBuild>(std::move(filters));
	result->build_col_ids_per_filter = std::move(build_col_ids);
	return result;
}

idx_t LogicalSJBuild::EstimateCardinality(ClientContext &context) {
	return children[0]->EstimateCardinality(context);
}

vector<ColumnBinding> LogicalSJBuild::GetColumnBindings() {
	return children[0]->GetColumnBindings();
}

void LogicalSJBuild::ResolveTypes() {
	types = children[0]->types;
}

} // namespace duckdb
