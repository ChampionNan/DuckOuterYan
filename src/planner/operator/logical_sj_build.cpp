#include "duckdb/planner/operator/logical_sj_build.hpp"

#include "duckdb/catalog/catalog_entry/table_catalog_entry.hpp"
#include "duckdb/common/exception.hpp"
#include "duckdb/common/serializer/deserializer.hpp"
#include "duckdb/common/serializer/serializer.hpp"
#include "duckdb/optimizer/outer_yan/semi_join/semi_join_filter.hpp"
#include "duckdb/planner/operator/logical_get.hpp"

#include <functional>

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
	// Stable filter ids re-establish build↔probe filter sharing after the
	// roundtrip (live filter objects cannot survive serialization).
	serializer.WriteProperty(202, "filter_ids", filter_ids);
}

unique_ptr<LogicalOperator> LogicalSJBuild::Copy(ClientContext &context) const {
	// Structural copy that shares SemiJoinFilter instances (shared_ptr semantics).
	// The default Copy goes via serialize/deserialize, which is unimplemented for
	// SJ operators.  AggregatePushdownOuter needs a throwaway deep copy of the plan
	// to run its speculative rewrite; sharing the live filters is safe because the
	// copy is never executed.
	auto copy = make_uniq<LogicalSJBuild>(sj_to_create);
	copy->build_col_ids_per_filter = build_col_ids_per_filter;
	copy->filter_ids = filter_ids;
	for (const auto &child : children) {
		copy->children.push_back(child->Copy(context));
	}
	copy->types = types;
	return copy;
}

unique_ptr<LogicalOperator> LogicalSJBuild::Deserialize(Deserializer &deserializer) {
	auto num_filters = deserializer.ReadProperty<idx_t>(200, "num_filters");
	auto build_col_ids = deserializer.ReadProperty<vector<vector<idx_t>>>(201, "build_col_ids_per_filter");
	auto filter_ids = deserializer.ReadProperty<vector<idx_t>>(202, "filter_ids");
	vector<shared_ptr<SemiJoinFilter>> filters;
	filters.reserve(num_filters);
	for (idx_t i = 0; i < num_filters; i++) {
		filters.push_back(make_shared_ptr<SemiJoinFilter>());
	}
	auto result = make_uniq<LogicalSJBuild>(std::move(filters));
	result->build_col_ids_per_filter = std::move(build_col_ids);
	result->filter_ids = std::move(filter_ids);
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

string LogicalSJBuild::DescribeKeyColumn(const LogicalOperator &root, const ColumnBinding &binding) {
	// Locate the base LogicalGet for this binding's table_index within `root`.
	const LogicalGet *found = nullptr;
	std::function<void(const LogicalOperator &)> walk = [&](const LogicalOperator &op) {
		if (found) {
			return;
		}
		if (op.type == LogicalOperatorType::LOGICAL_GET) {
			auto &get = op.Cast<LogicalGet>();
			if (get.table_index.index == binding.table_index.index) {
				found = &get;
				return;
			}
		}
		for (auto &child : op.children) {
			walk(*child);
		}
	};
	walk(root);

	const idx_t ti = binding.table_index.index;
	const idx_t ci = binding.column_index.GetIndexUnsafe();
	string table_label = "t" + to_string(ti);
	string col_label = "col" + to_string(ci);
	if (found) {
		if (auto tbl = found->GetTable()) {
			table_label = tbl->name + "(t" + to_string(ti) + ")";
		}
		// `ci` is the projection index within the Get's projected column list;
		// map it through GetColumnIds() to the base column name.
		auto &col_ids = found->GetColumnIds();
		if (ci < col_ids.size()) {
			auto base = col_ids[ci].GetPrimaryIndex();
			if (base < found->names.size()) {
				col_label = found->names[base];
			}
		}
	}
	return table_label + "." + col_label;
}

InsertionOrderPreservingMap<string> LogicalSJBuild::ParamsToString() const {
	InsertionOrderPreservingMap<string> result;
	const auto child_bindings = children.empty() ? vector<ColumnBinding>() : children[0]->GetColumnBindings();
	for (idx_t f = 0; f < sj_to_create.size(); f++) {
		const idx_t tag = f < filter_ids.size() ? filter_ids[f] : f;
		string keys = "build ";
		if (f < build_col_ids_per_filter.size()) {
			const auto &cols = build_col_ids_per_filter[f];
			for (idx_t k = 0; k < cols.size(); k++) {
				if (k > 0) {
					keys += ", ";
				}
				keys += (children.empty() || cols[k] >= child_bindings.size())
				            ? ("#" + to_string(cols[k]))
				            : DescribeKeyColumn(*children[0], child_bindings[cols[k]]);
			}
		}
		result["filter#" + to_string(tag)] = keys;
	}
	return result;
}

} // namespace duckdb
