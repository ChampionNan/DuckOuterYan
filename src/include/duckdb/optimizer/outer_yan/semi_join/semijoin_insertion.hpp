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
//! Algorithm (mirrors RPT's create/use insertion, generalised to honour the
//! recorded two-pass schedule instead of a fixed nest shape):
//!   1. Walk pairs in decision order — `bottom_up_pairs` (pass 0), then
//!      `top_down_pairs` (pass 1). Pairs are grouped by shared-filter key
//!      (the sorted set of `keys[i].build_binding`, canonicalising {a,b} ==
//!      {b,a}) so two pairs that build the same column set share one
//!      `SemiJoinFilter`. The LogicalSJBuild that materialises a filter is
//!      remembered alongside it, so a reused filter's probe wires straight to
//!      that build — no separate relation→build map.
//!   2. For each pair, append a build to its build relation's nest stack and
//!      a probe to its probe relation's nest stack (`stacks_`). A new op
//!      coalesces into the relation's current top op only when that op is the
//!      same kind AND from the same pass; a kind change or a pass boundary
//!      opens a fresh op. This reproduces the schedule verbatim — including
//!      the `probe → build → probe` interleavings an outer-join schedule can
//!      emit — while collapsing only genuinely adjacent same-kind steps.
//!   3. Walk the rebuilt plan pre-order. At every "base unit" (a bare
//!      LogicalGet, or a LogicalFilter+LogicalGet) known to
//!      `tree.table_to_relation`, splice that relation's whole nest stack
//!      above the base, innermost-first. Non-base nodes recurse so the stack
//!      lands as close to the LogicalGet as possible.
//!
//! Cross-pass safety is structural: `bottom_up` is fully processed before
//! `top_down`, and every new op nests outside the current one, so a bottom-up
//! build can never end up above a top-down probe that (transitively) depends
//! on it — no build/probe pipeline cycle.
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
	//! One semi-join operator (LogicalSJBuild or LogicalSJProbe) parked in a
	//! base relation's nest stack until the plan walk splices it in. Holds the
	//! still-unresolved key bindings for each filter the op carries, plus the
	//! pass that produced it so cross-pass ops never coalesce. The build phase
	//! appends a filter into `op` when this entry is the stack's current top
	//! AND a same-kind, same-pass match; otherwise it pushes a new entry.
	struct StackOp {
		StackOp(unique_ptr<LogicalOperator> op, bool is_build, bool top_down,
		        vector<vector<ColumnBinding>> bindings_per_filter)
		    : op(std::move(op)), is_build(is_build), top_down(top_down),
		      bindings_per_filter(std::move(bindings_per_filter)) {
		}
		unique_ptr<LogicalOperator> op; //!< LogicalSJBuild | LogicalSJProbe
		bool is_build;                  //!< true: build, false: probe
		bool top_down;                  //!< false: bottom_up pass, true: top_down pass
		//! One binding list per filter in `op`, in the op's filter order.
		//! InsertAtBase resolves these to positional ids against the base
		//! schema, into build_col_ids_per_filter / probe_col_ids_per_filter.
		vector<vector<ColumnBinding>> bindings_per_filter;
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

	//! Insertion action at one base unit. Splices `stacks_[rid]` above `node`
	//! front (innermost) → back (outermost), resolving each op's key bindings
	//! against the base schema before moving the child in. Empties the stack to
	//! mark the relation spliced (checked after the walk). No-op when the
	//! relation has no stack.
	void InsertAtBase(unique_ptr<LogicalOperator> &node, RelationId rid);

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
	// Populated by Apply's build phase, consumed by InsertionTraverse /
	// InsertAtBase. Cleared at the start of every Apply so the instance is
	// safely re-usable (OuterYanPost owns a single SemijoinInsertion across
	// multiple plans).
	//
	// `stacks_[rid]` is the ordered nest stack for relation `rid`: front =
	// innermost (closest to the LogicalGet), back = outermost. The build-phase
	// append order — bottom_up pairs then top_down — is exactly the
	// bottom-to-top order the operators take above the base.
	const unordered_map<idx_t, RelationId> *table_to_relation_ = nullptr;
	unordered_map<RelationId, vector<StackOp>> stacks_;
};

} // namespace duckdb
