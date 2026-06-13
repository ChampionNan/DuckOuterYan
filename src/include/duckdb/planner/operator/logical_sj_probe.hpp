//===----------------------------------------------------------------------===//
//                         DuckDB
//
// duckdb/planner/operator/logical_sj_probe.hpp
//
//
//===----------------------------------------------------------------------===//

#pragma once

#include "duckdb/common/shared_ptr.hpp"
#include "duckdb/optimizer/outer_yan/semi_join/semi_join_filter.hpp"
#include "duckdb/planner/logical_operator.hpp"
#include "duckdb/planner/operator/logical_sj_build.hpp"

namespace duckdb {

//! LogicalSJProbe — OuterYan semi-join probe side.
//!
//! Pairing via shared SemiJoinFilter shared_ptrs (same instances held by
//! the upstream LogicalSJBuild). Additionally tracks back-pointers to the
//! upstream LogicalSJBuild operators (`related_sj_build`) — used by the
//! physical plan generator to wire pipeline dependencies, mirroring RPT's
//! `LogicalUseBF::related_create_bf`.
//!
//! Pass-through filter on the data path — schema unchanged from the input.
class LogicalSJProbe : public LogicalOperator {
public:
	static constexpr const LogicalOperatorType TYPE = LogicalOperatorType::LOGICAL_SJ_PROBE;

public:
	explicit LogicalSJProbe(vector<shared_ptr<SemiJoinFilter>> sj_to_use);

	//! Filters this operator probes against. Same shared_ptr instances are
	//! populated by the paired LogicalSJBuild operators.
	vector<shared_ptr<SemiJoinFilter>> sj_to_use;

	//! Back-pointers to the upstream LogicalSJBuild operators populating the
	//! filters in `sj_to_use`. Index-aligned with `sj_to_use`: entry i here
	//! is the build for filter i there. Mirrors RPT's `related_create_bf`.
	vector<LogicalSJBuild *> related_sj_build;

	//! For each filter in `sj_to_use`, the column indices within the child's
	//! output schema corresponding to that filter's probe keys. Resolved by
	//! SemijoinInsertion::InsertAtBase; plan-gen moves it onto PhysicalSJProbe.
	vector<vector<idx_t>> probe_col_ids_per_filter;

	//! Stable, plan-local id for each filter in `sj_to_use` (index-aligned),
	//! matching the id the paired LogicalSJBuild carries for the same filter.
	//! Survives Copy / Serialize / Deserialize; the physical plan generator uses
	//! it to share one runtime SemiJoinFilter with the build and to re-derive
	//! `related_sj_build` after the plan is built. Authoritative over the
	//! `related_sj_build` raw pointers, which copy/serialize do not preserve.
	vector<idx_t> filter_ids;

public:
	void Serialize(Serializer &serializer) const override;
	static unique_ptr<LogicalOperator> Deserialize(Deserializer &deserializer);
	// Structural deep copy that shares SemiJoinFilter shared_ptrs. See SJBuild.
	unique_ptr<LogicalOperator> Copy(ClientContext &context) const override;

	idx_t EstimateCardinality(ClientContext &context) override;
	vector<ColumnBinding> GetColumnBindings() override;

	//! Append an upstream LogicalSJBuild that populates one of `sj_to_use`'s
	//! filters. Caller must keep the index alignment with `sj_to_use`.
	void AddDownStreamOperator(LogicalSJBuild *op);

protected:
	void ResolveTypes() override;
};

} // namespace duckdb
