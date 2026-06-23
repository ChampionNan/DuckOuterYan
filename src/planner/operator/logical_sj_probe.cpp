#include "duckdb/planner/operator/logical_sj_probe.hpp"

#include "duckdb/common/exception.hpp"
#include "duckdb/common/serializer/deserializer.hpp"
#include "duckdb/common/serializer/serializer.hpp"
#include "duckdb/optimizer/outer_yan/semi_join/semi_join_filter.hpp"

namespace duckdb {

LogicalSJProbe::LogicalSJProbe(vector<shared_ptr<SemiJoinFilter>> sj_to_use_p)
    : LogicalOperator(LogicalOperatorType::LOGICAL_SJ_PROBE), sj_to_use(std::move(sj_to_use_p)) {
}

void LogicalSJProbe::Serialize(Serializer &serializer) const {
	LogicalOperator::Serialize(serializer);
	serializer.WriteProperty(200, "num_filters", (idx_t)sj_to_use.size());
	serializer.WriteProperty(201, "probe_col_ids_per_filter", probe_col_ids_per_filter);
	// Stable filter ids re-establish build↔probe filter sharing + the build
	// dependency after the roundtrip (related_sj_build pointers do not survive).
	serializer.WriteProperty(202, "filter_ids", filter_ids);
}

unique_ptr<LogicalOperator> LogicalSJProbe::Copy(ClientContext &context) const {
	// Structural copy sharing SemiJoinFilter shared_ptrs; see LogicalSJBuild::Copy.
	// related_sj_build raw pointers are left pointing at the original build nodes —
	// the copy is never executed, so pipeline wiring is irrelevant.
	auto copy = make_uniq<LogicalSJProbe>(sj_to_use);
	copy->probe_col_ids_per_filter = probe_col_ids_per_filter;
	copy->filter_ids = filter_ids;
	for (const auto &child : children) {
		copy->children.push_back(child->Copy(context));
	}
	copy->types = types;
	return std::move(copy);
}

unique_ptr<LogicalOperator> LogicalSJProbe::Deserialize(Deserializer &deserializer) {
	auto num_filters = deserializer.ReadProperty<idx_t>(200, "num_filters");
	auto probe_col_ids = deserializer.ReadProperty<vector<vector<idx_t>>>(201, "probe_col_ids_per_filter");
	auto filter_ids = deserializer.ReadProperty<vector<idx_t>>(202, "filter_ids");
	vector<shared_ptr<SemiJoinFilter>> filters;
	filters.reserve(num_filters);
	for (idx_t i = 0; i < num_filters; i++) {
		filters.push_back(make_shared_ptr<SemiJoinFilter>());
	}
	auto result = make_uniq<LogicalSJProbe>(std::move(filters));
	result->probe_col_ids_per_filter = std::move(probe_col_ids);
	result->filter_ids = std::move(filter_ids);
	return std::move(result);
}

idx_t LogicalSJProbe::EstimateCardinality(ClientContext &context) {
	return children[0]->EstimateCardinality(context);
}

vector<ColumnBinding> LogicalSJProbe::GetColumnBindings() {
	return children[0]->GetColumnBindings();
}

void LogicalSJProbe::ResolveTypes() {
	types = children[0]->types;
}

void LogicalSJProbe::AddDownStreamOperator(LogicalSJBuild *op) {
	related_sj_build.emplace_back(op);
}

InsertionOrderPreservingMap<string> LogicalSJProbe::ParamsToString() const {
	InsertionOrderPreservingMap<string> result;
	const auto child_bindings = children.empty() ? vector<ColumnBinding>() : children[0]->GetColumnBindings();
	for (idx_t f = 0; f < sj_to_use.size(); f++) {
		const idx_t tag = f < filter_ids.size() ? filter_ids[f] : f;
		string keys = "probe ";
		if (f < probe_col_ids_per_filter.size()) {
			const auto &cols = probe_col_ids_per_filter[f];
			for (idx_t k = 0; k < cols.size(); k++) {
				if (k > 0) {
					keys += ", ";
				}
				// Reuse the build operator's column resolver — same logic.
				keys += (children.empty() || cols[k] >= child_bindings.size())
				            ? ("#" + to_string(cols[k]))
				            : LogicalSJBuild::DescribeKeyColumn(*children[0], child_bindings[cols[k]]);
			}
		}
		result["filter#" + to_string(tag)] = keys;
	}
	return result;
}

} // namespace duckdb
