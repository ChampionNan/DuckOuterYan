//===----------------------------------------------------------------------===//
//                         DuckDB
//
// duckdb/optimizer/outer_yan/semi_join/semijoin_insertion.hpp
//
//
//===----------------------------------------------------------------------===//

#pragma once

#include "duckdb/common/optional_ptr.hpp"
#include "duckdb/common/shared_ptr.hpp"
#include "duckdb/common/unique_ptr.hpp"
#include "duckdb/common/unordered_map.hpp"
#include "duckdb/common/vector.hpp"
#include "duckdb/optimizer/outer_yan/common/outer_yan_common.hpp"
#include "duckdb/optimizer/outer_yan/common/outer_yan_tree.hpp"
#include "duckdb/optimizer/outer_yan/semi_join/semi_join_filter.hpp"
#include "duckdb/planner/column_binding.hpp"
#include "duckdb/planner/logical_operator.hpp"
#include "duckdb/planner/operator/logical_sj_build.hpp"
#include "duckdb/planner/operator/logical_sj_probe.hpp"

namespace duckdb {

class ClientContext;
class LogicalGet;

//! Semi-join (SJBuild / SJProbe) insertion pass.
//!
//! Runs as the final OuterYan pass on the rebuilt LogicalPlan, after
//! `OuterYanTree::OJTToLogicalPlan` (and after aggregation pushdown, when
//! that lands). Input pairs are pre-decided by
//! `OuterYanPre::{BottomUpPass, TopDownPass}` and stored on
//! `OuterYanTree::{bottom_up_pairs, top_down_pairs}`.
//!
//! Algorithm:
//!   1. Group all pairs by their shared-filter key — sorted set of
//!      `keys[i].build_binding` plus the probe relation id. Each group
//!      corresponds to one shared `SemiJoinFilter`. Iteration order is
//!      bottom_up first, then top_down. Within a probe relation, earlier-
//!      iterated pairs end up earlier in `probe_wraps_[rid]`, which makes
//!      them the *first-applied* filters inside the merged LogicalSJProbe.
//!   2. Pre-create one `LogicalSJBuild` per build relation carrying all
//!      filters for that relation; keep raw pointers so probes can wire up
//!      `related_sj_build`.
//!   3. Walk the rebuilt plan pre-order. At every "base unit" (a bare
//!      LogicalGet, or a LogicalFilter+LogicalGet) known to
//!      `tree.table_to_relation`, insert ONE merged LogicalSJProbe holding
//!      every probe filter for that relation (innermost over the base),
//!      then the relation's LogicalSJBuild (outermost). Non-base nodes
//!      recurse so the wraps land as close to the LogicalGet as possible.
//!
//! Per-relation insertion is adjacency-safe: each call produces at most one
//! LogicalSJBuild and at most one LogicalSJProbe directly above the base,
//! so the plan never grows a `build → probe → probe → build` chain at a
//! single base.
class SemijoinInsertion {
public:
	//! Insert LogicalSJBuild / LogicalSJProbe operators into `plan` based on
	//! `tree.{bottom_up_pairs, top_down_pairs}`. Returns the (possibly
	//! mutated) plan. The OJT inside `tree` has already been consumed by
	//! `OJTToLogicalPlan`; this pass reads only the pair lists and
	//! `table_to_relation`.
	//!
	//! When `stats_prefilter_enabled` is true, each fresh SemiJoinFilter is
	//! consulted against base-table min/max statistics for its single-column
	//! build key; if the implied bitmap byte footprint exceeds
	//! `bitmap_byte_budget`, the filter is tagged `ForceHash` so
	//! PhysicalSJBuild::Finalize skips the bitmap attempt.
	unique_ptr<LogicalOperator> Apply(unique_ptr<LogicalOperator> plan, const OuterYanTree &tree,
	                                  ClientContext &context, idx_t bitmap_byte_budget,
	                                  bool stats_prefilter_enabled);

private:
	//! One probe-side contribution from a single OuterYanSemiPair. Multiple
	//! ProbeWraps for the same probe relation are merged by
	//! MakeProbeOperator into ONE LogicalSJProbe holding all filters,
	//! mirroring LogicalSJBuild's "all filters in one op" pattern.
	struct ProbeWrap {
		shared_ptr<SemiJoinFilter> filter;
		//! Order matches the originating pair.keys; resolved to positional
		//! column indices in MakeProbeOperator and stored on
		//! LogicalSJProbe::probe_col_ids_per_filter.
		vector<ColumnBinding> probe_bindings;
		//! The pair's build relation id — used to look up the corresponding
		//! LogicalSJBuild for `related_sj_build` wiring.
		RelationId related_build_rid = 0;
	};

	//! True iff `node` is a LogicalFilter whose single child is a
	//! LogicalGet. Treated as one atomic base unit by InsertionTraverse —
	//! wraps go above the filter so the build materialises post-filter
	//! data (smaller SemiJoinFilter, less work for downstream probes).
	static bool IsFilterGetBase(const LogicalOperator &node);

	//! Pre-order plan walk. At each node:
	//!   - base unit (Filter+Get OR bare Get) known to `table_to_relation_`:
	//!     call InsertAtBase and stop descending.
	//!   - anything else: recurse into children.
	//! Pre-order is chosen for simplicity: a single "match base → act →
	//! stop" rule covers both base-unit shapes without an exception case.
	void InsertionTraverse(unique_ptr<LogicalOperator> &node);

	//! Insertion action at one base unit. Wraps `node` with the merged
	//! LogicalSJProbe (innermost) and then the relation's pre-created
	//! LogicalSJBuild (outermost). Both child-binding resolutions happen
	//! BEFORE the child is moved into `children[]`.
	void InsertAtBase(unique_ptr<LogicalOperator> &node, RelationId rid);

	//! Construct the merged LogicalSJProbe for relation `rid` (one
	//! operator, N filters). Filter ordering inside `sj_to_use` matches
	//! the order of `probe_wraps_[rid]` (bottom_up pairs first, then
	//! top_down), so PhysicalSJProbe::ExecuteInternal applies the
	//! earliest-decided filter first. Returns nullptr if the relation has
	//! no probe contributions.
	unique_ptr<LogicalSJProbe> MakeProbeOperator(RelationId rid,
	                                             const vector<ColumnBinding> &child_bindings);

	//! Move the pre-created LogicalSJBuild for `rid` out of
	//! `pending_builds_`, resolve its build-key bindings against
	//! `child_bindings`, and return it. Returns nullptr if no build was
	//! pre-created for this relation.
	unique_ptr<LogicalSJBuild> TakeBuildOperator(RelationId rid,
	                                             const vector<ColumnBinding> &child_bindings);

	//! Resolve each `per_filter_bindings[i]` to positional indices within
	//! `child_bindings`. Throws InternalException on a missing binding —
	//! that's a structural plan invariant violation (binding produced
	//! upstream is not visible to the SJ operator). Both inputs are tiny
	//! (a few filters; a few keys each), so the linear scan is fine.
	static vector<vector<idx_t>>
	ResolveColIds(const vector<ColumnBinding> &child_bindings,
	              const vector<vector<ColumnBinding>> &per_filter_bindings);

	//! Recursively walk `node` and return the first LogicalGet whose
	//! `table_index.index` equals `table_idx`. Returns nullptr if no match.
	static optional_ptr<LogicalGet> FindLogicalGet(LogicalOperator &node, idx_t table_idx);

	//! Stats-prefilter helper. Walks `root` for the LogicalGet matching
	//! `binding.table_index`, then queries its base-table statistics for
	//! column `binding.column_index`. On success, writes [min, max] cast to
	//! int64 into `out_min` / `out_max` and returns true. Returns false when:
	//! no matching LogicalGet, the column index is out of range, the table
	//! function exposes no statistics callback, the stats lack a min/max, or
	//! the BIGINT cast fails (e.g. UBIGINT overflow). Static so it can be
	//! exercised directly in tests without instantiating the pass.
	static bool LookupBaseStatsRange(LogicalOperator &root, ColumnBinding binding, ClientContext &context,
	                                 int64_t &out_min, int64_t &out_max);

	// ─── Walk state ─────────────────────────────────────────────────────
	// Populated by Apply, consumed by InsertionTraverse / InsertAtBase /
	// MakeProbeOperator / TakeBuildOperator. Cleared at the start of every
	// Apply so the instance is safely re-usable (OuterYanPost owns a
	// single SemijoinInsertion across multiple plans).
	//
	// Ordering invariant on probe_wraps_[rid]: front entry is the
	// earliest-decided filter. Apply populates bottom_up pairs first, then
	// top_down, so PhysicalSJProbe::ExecuteInternal applies them in
	// decision order.
	const unordered_map<idx_t, RelationId> *table_to_relation_ = nullptr;
	unordered_map<RelationId, vector<ProbeWrap>> probe_wraps_;
	unordered_map<RelationId, unique_ptr<LogicalSJBuild>> pending_builds_;
	unordered_map<RelationId, LogicalSJBuild *> build_ptr_map_;
	unordered_map<RelationId, vector<vector<ColumnBinding>>> build_bindings_by_rid_;
};

} // namespace duckdb
