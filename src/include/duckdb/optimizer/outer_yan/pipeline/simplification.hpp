//===----------------------------------------------------------------------===//
//                         DuckDB
//
// duckdb/optimizer/outer_yan/pipeline/simplification.hpp
//
//
//===----------------------------------------------------------------------===//

#pragma once

#include "duckdb/common/unordered_map.hpp"
#include "duckdb/common/unordered_set.hpp"
#include "duckdb/optimizer/outer_yan/common/outer_yan_tree.hpp"

namespace duckdb {

//! Walks the OperatorTree top-down and rewrites outer joins to the strongest
//! join kind whose semantics are preserved by the surrounding plan. Unlike
//! the binding-level OuterJoinSimplification, the analysis here works at the
//! granularity of OT base relations: a relation is null-rejected (i.e.,
//! cannot legally be the null-introducing side) iff a null-rejecting filter
//! anywhere in `filter_records` references it, or an enclosing join's
//! condition forbids NULLs in any of its columns.
//!
//! NOTE: every record stores the relation set below its source filter. A
//! null-rejecting record becomes active only at that exact OT subtree and is
//! propagated downward; it never simplifies an ancestor outside its original
//! evaluation scope. Root predicates therefore cover the complete skeleton.
//! Applicability rejects NULL-tolerant intermediate filters whose boundary may
//! not survive DP reordering.
class Simplification {
public:
	//! `allow_scan_filter_seeding` exists only for OuterYan's explicitly
	//! unsound measurement mode. Replay always passes false so an inherited
	//! environment variable can never weaken its null-rejection proof.
	void Apply(OuterYanTree &tree, bool allow_scan_filter_seeding = true);

	//! Conservative test used both by applicability and this pass. With a context,
	//! stable predicates may also be evaluated on an all-NULL input.
	//! True only when replacing every referenced column by NULL cannot make the
	//! predicate TRUE.
	static bool FilterRejectsNulls(const Expression &expr, optional_ptr<ClientContext> context = nullptr);

private:
	//! Top-down walk. RELATION nodes are no-ops. JOIN nodes:
	//!   a) collapse the join kind based on which child subtree intersects
	//!      `null_rej`;
	//!   b) extend `null_rej` with the relations that the (possibly rewritten)
	//!      join condition itself null-rejects, then recurse.
	//! `null_rej` is taken by value so per-subtree augmentations do not leak
	//! across siblings.
	void VisitNode(OuterYanTree &tree, OTNode &node,
	               unordered_set<idx_t> null_rej);

	//! Memoised set of relation_ids covered by `node`'s subtree.
	const unordered_set<idx_t> &ComputeSubtreeRelations(OTNode &node);

	//! True iff `subtree_relations[&node]` ∩ `null_rej` ≠ ∅.
	bool SubtreeIntersectsNullRejection(OTNode &node,
	                                    const unordered_set<idx_t> &null_rej);

private:
	unordered_map<const OTNode *, unordered_set<idx_t>> subtree_relations;
};

} // namespace duckdb
