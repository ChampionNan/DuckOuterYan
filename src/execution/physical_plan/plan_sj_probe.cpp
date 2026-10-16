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

	// Resolve each probed filter from the per-plan id registry, so it is the SAME
	// runtime SemiJoinFilter the paired build finalizes. We deliberately do NOT
	// trust op.sj_to_use / op.related_sj_build here: plan Copy/Serialize/-
	// Deserialize (statement verification, plan caching) hand the probe fresh,
	// unshared filters and an empty related list. related_sj_build is re-derived
	// from filter_ids once the whole plan is built (LinkSemiJoinProbes), because
	// the build may be planned after this probe in tree order.
	vector<shared_ptr<SemiJoinFilter>> filters;
	filters.reserve(op.filter_ids.size());
	for (auto id : op.filter_ids) {
		filters.push_back(GetOrCreateSJFilter(id));
	}

	auto &sj_probe = Make<PhysicalSJProbe>(child_plan.GetTypes(), std::move(filters),
	                                       std::move(op.probe_col_ids_per_filter), op.estimated_cardinality,
	                                       op.top_down);
	auto &probe_typed = sj_probe.Cast<PhysicalSJProbe>();
	probe_typed.filter_ids = op.filter_ids;
	sj_probe.children.push_back(child_plan);
	sj_probes_to_link.push_back(&probe_typed);
	return sj_probe;
}

} // namespace duckdb
