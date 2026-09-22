//===----------------------------------------------------------------------===//
//                         DuckDB
//
// duckdb/optimizer/outer_yan/common/ordered_join_tree.hpp
//
//
//===----------------------------------------------------------------------===//

#pragma once

#include "duckdb/common/enums/join_type.hpp"
#include "duckdb/common/optional.hpp"
#include "duckdb/common/optional_ptr.hpp"
#include "duckdb/common/string.hpp"
#include "duckdb/common/unique_ptr.hpp"
#include "duckdb/common/unordered_map.hpp"
#include "duckdb/common/unordered_set.hpp"
#include "duckdb/common/vector.hpp"
#include "duckdb/optimizer/join_order/relation_statistics_helper.hpp"
#include "duckdb/optimizer/outer_yan/common/operator_tree.hpp"
#include "duckdb/optimizer/outer_yan/common/outer_yan_common.hpp"
#include "duckdb/planner/column_binding.hpp"
#include "duckdb/planner/expression.hpp"
#include "duckdb/planner/logical_operator.hpp"

#include <functional>
#include <sstream>

namespace duckdb {

//! `OuterYanJoinKind` (defined in operator_tree.hpp) is the single edge-kind
//! type shared by OperatorTree and OrderedJoinTree. The OJT-edge orientation
//! convention "parent KIND child" still applies: when the OJT places the
//! original RHS as parent, `LEFT_OUTER` and `RIGHT_OUTER` are flipped so the
//! kind continues to label the OJT-parent's role. `INNER` and `FULL_OUTER`
//! are symmetric and unaffected. See `CheckOuterYanJoinFlip` in
//! tree_conversions.cpp for the single source of truth.

struct OJTNode;

//! Edge from an OJTNode to a child subtree.
//!
//! Semijoin insertion is two whole-OJT passes with fixed directions:
//!   1. Bottom-up — every edge reduces child→parent.
//!   2. Top-down  — every edge reduces parent→child.
//! Each pass adds at most one SJ pair per edge, so an edge carries at most
//! two reductions total. Presence is recorded by the `bottom_up` /
//! `top_down` markers below; the actual `LogicalSJBuild` / `LogicalSJProbe`
//! operators are inserted later by the SemijoinInsertion module when
//! lowering to LogicalPlan, driven by these markers.
struct OJTEdge {
	//! Current edge classification (may have been transformed by Desimplification).
	//! Always oriented as "parent KIND child" — LEFT/RIGHT are flipped by
	//! CheckOuterYanJoinFlip in BuildOJTImpl when the OJT places the original
	//! RHS relation as the parent, so the kind consistently labels the parent's
	//! role regardless of LHS/RHS position in the original LogicalPlan:
	//!   INNER  — both sides inner; fires in both bottom-up AND top-down passes.
	//!   LEFT   — parent is the preserved (outer) side, child is null-extended;
	//!            fires only in the top-down pass  (R_child ⋉ R_parent).
	//!   RIGHT  — child is the preserved (outer) side, parent is null-extended;
	//!            fires only in the bottom-up pass (R_parent ⋉ R_child).
	//!   OUTER  — both sides preserved (full outer); fires in neither pass.
	OuterYanJoinKind kind = JoinType::INNER;
	//! Original edge classification, recorded before Desimplification rules were
	//! applied. Follows the same "parent KIND child" orientation as `kind`.
	//! Resimplification uses this to revert back to the original join type when
	//! the chosen ordering makes the rewrite redundant.
	OuterYanJoinKind original_kind = JoinType::INNER;
	//! Build order of the underlying join in the currently materialized plan.
	//! 1-based, starting from the bottommost join (`order = 1`) up to the
	//! root join (`order = n`). Initially derived from the input tree; DP rebuilds
	//! and renumbers it in post-order for the chosen candidate. 0 is uninitialised.
	idx_t order = 0;
	//! `relation_id` of the OJTNode that owns this edge. Set in BuildOJT
	//! when the edge is attached to its parent; lets OJTToLogicalPlan
	//! flatten edges into an order-sorted vector without losing the
	//! parent-child link.
	idx_t parent_relation_id = DConstants::INVALID_INDEX;
	//! Owned join metadata (kind, original_kind, conditions,
	//! cond_left/right_relation_id, distinct_count). Moved out of the
	//! originating OT JOIN OTNode during BuildOJT. Replaces the prior
	//! `LogicalOperator *join_op`: the OJT is now self-contained and no
	//! longer reaches into the source plan for condition information.
	unique_ptr<OTJoin> info;
	unique_ptr<OJTNode> child;

	//! Bottom-up round marker (child→parent): set iff the round inserted
	//! an SJBuild + SJProbe pair on this edge.
	optional<bool> bottom_up;
	//! Top-down round marker (parent→child): set iff the round inserted
	//! an SJBuild + SJProbe pair on this edge.
	optional<bool> top_down;

	//! Whether either side's join keys cover a UNIQUE / PRIMARY KEY
	//! constraint. This legacy uniqueness marker is used by aggregate pushdown;
	//! on its own it does not prove FK coverage and must not justify semi-join
	//! elimination. See
	//! `AggregationPushdown::CheckPKFK` in DuckDBYanPlus
	//! (src/optimizer/aggregation_pushdown.cpp ~L547) for the reference
	//! implementation: bindings → `LogicalGet::GetColumnIds()` →
	//! `TableCatalogEntry::GetConstraints()` → `ConstraintType::UNIQUE`.
	bool has_pk_fk_constraint = false;
	//! When `has_pk_fk_constraint` is true: which side holds the PK.
	//! `true`  — child is PK side, parent is FK side.
	//! `false` — parent is PK side, child is FK side.
	//! Undefined when `has_pk_fk_constraint` is false.
	bool child_is_pk = false;
	//! Every parent join-key tuple is guaranteed to match a child tuple. This
	//! requires an exact, enforced parent-FK -> child-UNIQUE/PK mapping and a
	//! declared NOT NULL constraint on every parent FK component.
	bool parent_covered_by_child = false;
	//! Every child join-key tuple is guaranteed to match a parent tuple. This is
	//! the direction-reversed counterpart of `parent_covered_by_child`.
	bool child_covered_by_parent = false;
	//! Bottom-up semi-join R_parent ⋉ R_child on this edge is provably
	//! redundant; OuterYanPre::BottomUpPass skips the pair. Set by
	//! BuildOJTImpl after the full tree is assembled. True iff:
	//!   (1) parent_covered_by_child — exact total FK coverage is proven.
	//!   (2) child is a terminal leaf — no OJT children reduce it before
	//!       its SJBuild materialises (stack: SJBuild ← GET, no probe
	//!       operators in between).
	//!   (3) child has no base predicates — no LOGICAL_FILTER above its
	//!       GET and no single-relation filter_record targets it.
	bool bottom_up_eliminated = false;
	//! Top-down semi-join R_child ⋉ R_parent on this edge is provably
	//! redundant; OuterYanPre::TopDownPass skips the pair. True iff:
	//!   (1) child_covered_by_parent — exact total FK coverage is proven.
	//!   (2) parent has no base predicates.
	//!   (3) parent has no bottom-up probes — none of its OJT children
	//!       connect via RIGHT or INNER (those would sit below its
	//!       top-down SJBuild and reduce it first).
	//!   (4) parent has no top-down probe from its grandparent — i.e.
	//!       parent is the OJT root, or its incoming edge has kind RIGHT.
	bool top_down_eliminated = false;
};

//! Node in the Ordered Join Tree.
struct OJTNode {
	idx_t relation_id = 0;
	//! Raw pointer to the base-relation subtree (typically `LogicalGet`,
	//! possibly under a single-child `LogicalFilter` / `LogicalProjection`)
	//! inside the original plan held by `OrderedJoinTree::source_plan`.
	//! The OJT does not own it.
	LogicalOperator *base_op = nullptr;
	//! Single-relation predicates pushed down to this node by OuterYan
	//! passes (independent of any filters already inside `base_op`).
	vector<unique_ptr<Expression>> filters;
	//! Ordered children — order is meaningful for evaluation-order regimes.
	vector<OJTEdge> children;
	RelationStats stats;
};

//! `OuterYanFilterRecord` (defined in operator_tree.hpp) is the single
//! filter-record type shared by OperatorTree and OrderedJoinTree. It is
//! populated during `LogicalPlanToOT`, carried unchanged through OT-stage
//! transforms and `OTToOJT`, and finally consumed during `OJTToLogicalPlan`.

//! Ordered Join Tree — internal IR used inside OuterYanDP and OuterYanPost.
//! Built from a `LogicalOperator` tree by `LogicalPlanToOJT`. The OJT does
//! NOT take ownership of individual join / base-relation operators; instead
//! it holds raw pointers into them and owns the original plan as a whole
//! via `source_plan`. This keeps the original plan structure intact during
//! OJT manipulation passes (Simplification, DP enumeration, etc.). The
//! original plan is consumed during `OJTToLogicalPlan` to materialise the
//! rebuilt plan.
class OrderedJoinTree {
public:
	OrderedJoinTree();
	explicit OrderedJoinTree(unique_ptr<OJTNode> root);

	OJTNode &Root() {
		return *root;
	}
	const OJTNode &Root() const {
		return *root;
	}

	//! Visit every node in post-order. Callback receives node, its parent (or
	//! null for root), and the edge kind from parent to node.
	void PostOrder(std::function<void(OJTNode &, optional_ptr<OJTNode>, OuterYanJoinKind)> callback);

	//! Flat edge-list printer. Lists every relation once and every edge as
	//! `Rparent --KIND/order--> Rchild`. Intended for quick inspection /
	//! golden-file tests. Filter records are not printed here — they live
	//! on `OuterYanTree`, not on the OJT, so callers print them
	//! separately if needed.
	string Print() const;

	//! Indented-tree printer. Same information as `Print` but rendered
	//! parent-child tree style, EXPLAIN-style. With `verbose`, each edge also
	//! reports `original_kind` (as `was=…` when it differs from the current
	//! kind), the PK/FK side, and the bottom-up / top-down elimination markers,
	//! and each node reports its `relation_id` — the signal the pipeline tracer
	//! needs to see which rule rewrote which edge across stages.
	string PrintAsTree(bool verbose = false) const;

private:
	// Printer helpers.
	static string RelationLabel(const OJTNode &node);
	static void CollectNodes(const OJTNode &node, vector<const OJTNode *> &out);
	static void CollectEdges(const OJTNode &node, vector<const OJTEdge *> &out);
	static void PrintNodeRecursive(const OJTNode &node, std::ostringstream &os,
	                               const string &indent, bool is_last_child, bool is_root,
	                               const OJTEdge *incoming_edge, bool verbose,
	                               const unordered_map<idx_t, string> &alias);
	//! Short relation_id → name map (table name, or `R<id>`), built once per
	//! print so verbose edges can render "parent ⋈/⟕/⟖/⟗ child".
	static unordered_map<idx_t, string> BuildAlias(const OJTNode &root);

	unique_ptr<OJTNode> root;
};

} // namespace duckdb
