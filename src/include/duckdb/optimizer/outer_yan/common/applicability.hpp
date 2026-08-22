//===----------------------------------------------------------------------===//
//                         DuckDB
//
// duckdb/optimizer/outer_yan/applicability.hpp
//
//
//===----------------------------------------------------------------------===//

#pragma once

#include "duckdb/common/string.hpp"
#include "duckdb/common/unordered_map.hpp"
#include "duckdb/common/unordered_set.hpp"
#include "duckdb/common/vector.hpp"
#include "duckdb/planner/column_binding.hpp"
#include "duckdb/planner/logical_operator.hpp"
#include "duckdb/planner/logical_operator_visitor.hpp"

namespace duckdb {

class LogicalComparisonJoin;
class Expression;

//! Identifier for a base relation in the OuterYan join graph.
using RelationId = idx_t;

//! One edge of the join graph: a single join condition between two relations.
struct JoinGraphEdge {
	RelationId left;
	RelationId right;
	const LogicalComparisonJoin *join;
	idx_t condition_index;
};

//! Result of the applicability check at the entrance of OuterYanPre.
struct ApplicabilityResult {
	bool applicable = false;
	//! Diagnostic string, exposed via EXPLAIN when not applicable.
	string reason;

	//! Populated only when applicable == true.
	vector<const LogicalOperator *> relations;
	unordered_map<idx_t, RelationId> table_index_to_relation;
	vector<JoinGraphEdge> edges;
	bool has_root_aggregate = false;
};

//! Applicability gate for OuterYan. Accepts iff:
//!   - all joins are inner or LEFT/RIGHT/FULL outer (and at least one outer),
//!   - join predicates are null-rejecting equi-comparisons between two base
//!     relations,
//!   - no semi/anti/mark joins, set ops, correlated subqueries, or window
//!     operators appear inside the skeleton,
//!   - aggregation, if present, sits only at the root above the joins,
//!   - residual filters are unary; root and base-local predicates are retained,
//!     while an intermediate post-join predicate must be NULL-rejecting,
//!   - the join graph (relations as nodes, conditions as edges) is acyclic.
//!
//! Implemented as a LogicalOperatorVisitor that walks the skeleton top-down,
//! collecting leaves and edges and short-circuiting on the first violation.
class OuterYanApplicability : public LogicalOperatorVisitor {
public:
	OuterYanApplicability();

	//! Entry point. Runs the visitor and returns the populated result.
	//! `require_outer=false` is used only by PostgreSQL replay after DuckDB's
	//! filter pushdown may already have safely reduced every syntactic outer join
	//! to INNER. Replay also requires stable intermediate filters because its
	//! imported regrouping may change their evaluation count/scope. OuterYan
	//! itself keeps both defaults.
	static ApplicabilityResult Check(LogicalOperator &plan, bool require_outer = true,
	                                 bool require_stable_intermediate_filters = false,
	                                 bool allow_anchored_join_residuals = false);

	void VisitOperator(LogicalOperator &op) override;

	//! Collect table_index values of all BoundColumnRefs reachable from `expr`.
	//! Shared with `OuterYanTree::CollectReferencedRelations`, which adds a
	//! translation step through `table_to_relation` to produce RelationIds.
	static void CollectColumnTables(const Expression &expr, unordered_set<idx_t> &tables);

	//! True when changing the input relation set at which a filter is evaluated
	//! can observably change its behavior. Volatile expressions always require
	//! their original scope. Potentially throwing expressions do as well, except
	//! for the narrow, independently-proven `% positive-integral-constant` form.
	//! The latter cannot divide by zero or hit signed MIN % -1.
	static bool FilterRequiresOriginalScope(const Expression &expr);

private:
	bool require_stable_intermediate_filters = false;
	//! PGPlan preserves the exact imported split and all bound ON predicates. It
	//! can therefore retain stable residuals anchored by one ordinary equality;
	//! normal OuterYan keeps this false and remains strict equi-only.
	bool allow_anchored_join_residuals = false;
	void VisitComparisonJoin(LogicalComparisonJoin &join);
	void RegisterLeaf(LogicalOperator &leaf);
	void Reject(string reason);

	// Walk past projection/filter (and a single root aggregate) to find
	// the top of the join skeleton.
	LogicalOperator &SkeletonRoot(LogicalOperator &plan);

	// True iff every LOGICAL_FILTER expression in `op`'s subtree references at
	// most ONE base relation. Root residuals remain in their original logical
	// position, but the current null-rejection analysis is relation-granular and
	// therefore supports only unary predicates.
	bool ResidualsAreUnary(LogicalOperator &op);

	// Union-find helpers for graph-cycle detection.
	RelationId Find(RelationId x);
	bool UnionRelations(RelationId a, RelationId b);

private:
	ApplicabilityResult result;
	vector<RelationId> uf_parent;
	unordered_set<uint64_t> seen_pairs;
	bool has_outer = false;
	bool rejected = false;
};

} // namespace duckdb
