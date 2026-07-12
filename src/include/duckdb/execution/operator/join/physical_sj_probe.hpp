//===----------------------------------------------------------------------===//
//                         DuckDB
//
// duckdb/execution/operator/join/physical_sj_probe.hpp
//
//
//===----------------------------------------------------------------------===//

#pragma once

#include "duckdb/common/shared_ptr.hpp"
#include "duckdb/execution/operator/join/physical_sj_build.hpp"
#include "duckdb/execution/physical_operator.hpp"
#include "duckdb/optimizer/outer_yan/semi_join/semi_join_filter.hpp"

namespace duckdb {

//! PhysicalSJProbe — probe-side of an OuterYan semi-join reducer pair.
//!
//! Filters input chunks against the shared SemiJoinFilter instances in
//! `sj_to_use`, populated by the paired PhysicalSJBuild operators tracked
//! in `related_sj_build`. Each filter applies in order; the surviving
//! row set is narrowed step by step.
//!
//! Lifecycle: operator-in-the-middle. Pipeline membership is the probe
//! pipeline; the build pipeline is set up as a dependency via
//! `related_sj_build[i]->BuildPipelinesFromRelated(...)` in BuildPipelines.
class PhysicalSJProbe : public CachingPhysicalOperator {
public:
	static constexpr const PhysicalOperatorType TYPE = PhysicalOperatorType::SJ_PROBE;

public:
	PhysicalSJProbe(PhysicalPlan &physical_plan, vector<LogicalType> types,
	                vector<shared_ptr<SemiJoinFilter>> sj_to_use,
	                vector<vector<idx_t>> probe_col_ids_per_filter,
	                idx_t estimated_cardinality, bool top_down);

	//! Shared filters this operator probes against. Same shared_ptr instances
	//! are populated by the paired PhysicalSJBuild operators tracked in
	//! `related_sj_build` (index-aligned).
	vector<shared_ptr<SemiJoinFilter>> sj_to_use;

	//! For each filter in `sj_to_use`, the list of column indices within
	//! input chunks corresponding to that filter's probe keys. Resolved
	//! upstream in SemijoinInsertion::InsertAtBase; moved onto this op by plan-gen.
	vector<vector<idx_t>> probe_col_ids_per_filter;

	//! Back-pointers to upstream PhysicalSJBuild operators (one per distinct
	//! build). Re-derived after the whole plan is built by matching `filter_ids`
	//! against the generator's id→build registry, so the dependency survives plan
	//! Copy/Serialize/Deserialize (the logical raw pointers do not).
	vector<PhysicalSJBuild *> related_sj_build;

	//! Stable filter ids (index-aligned with `sj_to_use`), copied from the
	//! LogicalSJProbe. Used only during plan generation to resolve shared filters
	//! and the related builds; not consulted at execution.
	vector<idx_t> filter_ids;
	bool top_down;

public:
	string GetName() const override;

	// Operator interface
	unique_ptr<OperatorState> GetOperatorState(ExecutionContext &context) const override;

	OrderPreservationType OperatorOrder() const override {
		return OrderPreservationType::INSERTION_ORDER;
	}
	bool ParallelOperator() const override {
		return true;
	}

	void BuildPipelines(Pipeline &current, MetaPipeline &meta_pipeline) override;

protected:
	OperatorResultType ExecuteInternal(ExecutionContext &context, DataChunk &input, DataChunk &chunk,
	                                   GlobalOperatorState &gstate, OperatorState &state) const override;
};

} // namespace duckdb
