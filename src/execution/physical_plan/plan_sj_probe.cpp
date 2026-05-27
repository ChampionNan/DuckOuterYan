//===----------------------------------------------------------------------===//
// CreatePlan(LogicalSJProbe&) — OuterYan semi-join probe lowering.
//
// IMPLEMENTATION REFERENCES — cross-check against these when editing.
//
// Primary references:
//   - embryo-labs/dynamic-predicate-transfer:
//       src/execution/physical_plan/plan_use_bf.cpp
//     (Local /tmp/dpt_plan_use_bf.cpp during the design session.)
//     The pattern of (1) recurse into child, (2) resolve each related
//     build via CreatePlanFromRelated, (3) construct PhysicalSJProbe via
//     Make, (4) push back the child, comes from this file.
//   - embryo-labs/Robust-Predicate-Transfer:
//       src/execution/physical_plan/plan_use_bf.cpp
//     (Local /tmp/rpt_plan_use_bf.cpp.) Older variant with the same shape.
//
// DuckDB-side patterns referenced:
//   - `Make<PhysicalT>` — arena allocation, see plan_filter.cpp.
//   - `CreatePlan(*op.children[0])` — DuckDB standard recursive lowering.
//
// Column-id resolution: now done upstream in SemijoinInsertion::InsertAtBase
// (mirrors DPT's pre-resolved `bound_cols_probe`). Plan-gen just moves
// LogicalSJProbe::probe_col_ids_per_filter onto the physical op.
//
// Multi-filter per probe is still supported: PhysicalSJProbe carries a
// vector of (filter, probe_col_ids) pairs (index-aligned), unlike DPT's
// PhysicalUseBF which carries a single BloomFilterUsage.
//===----------------------------------------------------------------------===//

#include "duckdb/execution/operator/join/physical_sj_build.hpp"
#include "duckdb/execution/operator/join/physical_sj_probe.hpp"
#include "duckdb/execution/physical_plan_generator.hpp"
#include "duckdb/planner/operator/logical_sj_build.hpp"
#include "duckdb/planner/operator/logical_sj_probe.hpp"

namespace duckdb {

// Reference: DPT plan_use_bf.cpp `CreatePlan(LogicalUseBF&)`. Same shape:
//   1. CreatePlan(child) → child PhysicalOperator&.
//   2. Move pre-resolved probe_col_ids_per_filter off the logical op.
//   3. Construct PhysicalSJProbe via Make<>.
//   4. Wire related_sj_build via CreatePlanFromRelated for each entry.
//      (Order in vector matches op.sj_to_use, so probe[i] uses build[i]
//      to resolve its filter's payload at probe time.)
//   5. Push back child.
PhysicalOperator &PhysicalPlanGenerator::CreatePlan(LogicalSJProbe &op) {
	auto &child_plan = CreatePlan(*op.children[0]);

	// Build the related_sj_build pointer list BEFORE constructing the
	// PhysicalSJProbe (it's a constructor argument-adjacent field). Each
	// CreatePlanFromRelated call may construct the related PhysicalSJBuild
	// on first encounter; subsequent encounters reuse the cached pointer.
	vector<PhysicalSJBuild *> related;
	related.reserve(op.related_sj_build.size());
	for (auto *logical_build : op.related_sj_build) {
		if (!logical_build) {
			throw InternalException("plan_sj_probe: null related_sj_build entry");
		}
		related.emplace_back(CreatePlanFromRelated(*logical_build));
	}

	auto &sj_probe = Make<PhysicalSJProbe>(child_plan.GetTypes(), std::move(op.sj_to_use),
	                                       std::move(op.probe_col_ids_per_filter), op.estimated_cardinality);
	auto &probe_typed = sj_probe.Cast<PhysicalSJProbe>();
	probe_typed.related_sj_build = std::move(related);
	sj_probe.children.push_back(child_plan);
	return sj_probe;
}

} // namespace duckdb
