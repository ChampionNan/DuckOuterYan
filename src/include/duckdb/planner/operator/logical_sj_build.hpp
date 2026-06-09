//===----------------------------------------------------------------------===//
//                         DuckDB
//
// duckdb/planner/operator/logical_sj_build.hpp
//
//
//===----------------------------------------------------------------------===//

#pragma once

#include "duckdb/common/shared_ptr.hpp"
#include "duckdb/optimizer/outer_yan/semi_join/semi_join_filter.hpp"
#include "duckdb/planner/logical_operator.hpp"

namespace duckdb {
class PhysicalSJBuild;

//! LogicalSJBuild — OuterYan semi-join build side.
//!
//! Pairing follows the RPT shared-pointer pattern: `sj_to_create` holds
//! shared_ptrs to SemiJoinFilter instances that the paired LogicalSJProbe
//! also references via `sj_to_use`. The shared filter object IS the
//! binding; no separate registry / handle id.
//!
//! Pass-through on the data path — rows are forwarded unchanged; the side
//! effect is populating the bound filters during build-pipeline Finalize.
class LogicalSJBuild : public LogicalOperator {
public:
	static constexpr const LogicalOperatorType TYPE = LogicalOperatorType::LOGICAL_SJ_BUILD;

	//! Back-pointer to the physical translation, set by the physical plan
	//! generator. Lets `CreatePlan(LogicalSJProbe&)` reuse one PhysicalSJBuild
	//! when multiple Probes target the same Build.
	PhysicalSJBuild *physical = nullptr;

public:
	explicit LogicalSJBuild(vector<shared_ptr<SemiJoinFilter>> sj_to_create);

	//! Filters this operator populates. Same shared_ptr instances appear in
	//! the paired LogicalSJProbe::sj_to_use.
	vector<shared_ptr<SemiJoinFilter>> sj_to_create;

	//! For each filter in `sj_to_create`, the column indices within the
	//! child's output schema corresponding to that filter's build keys.
	//! Resolved by SemijoinInsertion::InsertAtBase at the moment the child is
	//! attached (mirrors DPT's pre-resolved `bound_cols_build` on FilterPlan).
	//! Plan-gen moves this onto PhysicalSJBuild verbatim.
	vector<vector<idx_t>> build_col_ids_per_filter;

public:
	void Serialize(Serializer &serializer) const override;
	static unique_ptr<LogicalOperator> Deserialize(Deserializer &deserializer);
	// Structural deep copy that shares SemiJoinFilter shared_ptrs. Overrides
	// the default serialize-based Copy so AggregatePushdownOuter can clone the
	// plan without hitting the unimplemented Serialize path.
	unique_ptr<LogicalOperator> Copy(ClientContext &context) const override;

	idx_t EstimateCardinality(ClientContext &context) override;
	vector<ColumnBinding> GetColumnBindings() override;

protected:
	void ResolveTypes() override;
};

} // namespace duckdb
