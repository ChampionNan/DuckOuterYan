#include "duckdb/optimizer/outer_yan/pipeline/simplification.hpp"

#include "duckdb/common/enum_util.hpp"
#include "duckdb/optimizer/outer_yan/common/outer_yan_common.hpp"
#include "duckdb/planner/expression/bound_between_expression.hpp"
#include "duckdb/planner/expression/bound_columnref_expression.hpp"
#include "duckdb/planner/expression/bound_comparison_expression.hpp"
#include "duckdb/planner/expression/bound_conjunction_expression.hpp"
#include "duckdb/planner/expression/bound_function_expression.hpp"
#include "duckdb/planner/expression/bound_operator_expression.hpp"
#include "duckdb/planner/filter/conjunction_filter.hpp"
#include "duckdb/planner/operator/logical_comparison_join.hpp"
#include "duckdb/planner/operator/logical_get.hpp"

#include <cstdlib>

namespace duckdb {

// Experimental, OFF by default. When `DUCKDB_OY_SIMPLIFY_SCAN_FILTERS` is set to
// a non-empty, non-"0" value, Simplification ALSO seeds its null-rejection set
// from predicates that filter-pushdown folded into LogicalGet::table_filters.
//
// WARNING — this is UNSOUND in general and provided only for measurement. A scan
// filter is applied pre-join, so it does NOT null-reject the join *output*: e.g.
// `q LEFT JOIN r ON q.id=r.id AND r.rx>5` keeps the LEFT join while pushing
// `rx>5` into r's scan, yet q's unmatched rows must survive with NULL r. Treating
// that scan filter as null-rejection would rewrite to INNER and drop rows. The
// flag exists so the effect can be benchmarked, not because it is correct.
static bool ScanFilterSimplifyEnabled() {
	const char *p = std::getenv("DUCKDB_OY_SIMPLIFY_SCAN_FILTERS");
	return p && p[0] != '\0' && !(p[0] == '0' && p[1] == '\0');
}

// Does a pushed-down table filter reject NULL on its column? Recognition mirrors
// FilterRejectsNulls but over the TableFilter representation. Conservative:
// anything not provably NULL-rejecting returns false.
static bool TableFilterRejectsNulls(const TableFilter &filter) {
	switch (filter.filter_type) {
	case TableFilterType::CONSTANT_COMPARISON: // x <op> C — NULL x fails
	case TableFilterType::IS_NOT_NULL:
	case TableFilterType::IN_FILTER: // x IN (...) — NULL x yields NULL
		return true;
	case TableFilterType::CONJUNCTION_AND: {
		auto &c = filter.Cast<ConjunctionAndFilter>();
		for (auto &child : c.child_filters) {
			if (TableFilterRejectsNulls(*child)) {
				return true;
			}
		}
		return false;
	}
	case TableFilterType::CONJUNCTION_OR: {
		auto &c = filter.Cast<ConjunctionOrFilter>();
		if (c.child_filters.empty()) {
			return false;
		}
		for (auto &child : c.child_filters) {
			if (!TableFilterRejectsNulls(*child)) {
				return false;
			}
		}
		return true;
	}
	default:
		// IS_NULL, OPTIONAL_FILTER, DYNAMIC/BLOOM/PERFECT_HASH/PREFIX_RANGE,
		// EXPRESSION_FILTER, STRUCT_EXTRACT — not provably NULL-rejecting.
		return false;
	}
}

// NOTE: Implementation strategy
// -----------------------------
// 1. Seed `null_rej` once, from every null-rejecting record in
//    `tree.filter_records`. The filter's physical position in the input plan
//    is intentionally ignored — a filter that constrains a relation's column
//    is taken to constrain that relation in the final result, so any join
//    above the filter that would null-pad those columns must be rewritten.
//    `DominatesJoin`-style structural checks belong to filter-pushdown
//    placement, not to this pass.
// 2. Walk the OT top-down. At each JOIN node:
//      (a) Look at which child subtree (left / right / both) contains a
//          relation in `null_rej`. Collapse the join kind accordingly:
//            LEFT  + rhs_nullrej              -> INNER
//            RIGHT + lhs_nullrej              -> INNER
//            OUTER + both                     -> INNER
//            OUTER + lhs_nullrej only         -> LEFT
//            OUTER + rhs_nullrej only         -> RIGHT
//      (b) The join condition itself null-rejects on the relation referenced
//          on each preserved side; insert those relation_ids into `null_rej`
//          before recursing so deeper joins observe the same constraint:
//            INNER -> insert both child relation_ids
//            LEFT  -> insert right child relation_id
//            RIGHT -> insert left  child relation_id
//            OUTER -> nothing
// 3. `null_rej` is passed by value into recursive calls so additions made
//    while walking one subtree do not contaminate the sibling subtree.

// Snapshot every JOIN's post-Simplify kind into `original_join_kind`, the
// baseline that Desimplification rewrites from and Resimplification reverts to.
// The raw kind set at BuildOT was only provisional: Resimplify's inverse is
// Desimplify, so it must undo only Desimplify's reorder-enabling rewrites and
// never re-introduce outerness that Simplify (order-independently) removed.
static void RebaseOriginalKinds(OTNode &node) {
	if (node.kind != OTNode::Kind::JOIN) {
		return;
	}
	node.info->original_join_kind = node.info->join_kind;
	RebaseOriginalKinds(*node.children[0]);
	RebaseOriginalKinds(*node.children[1]);
}

void Simplification::Apply(OuterYanTree &tree) {
	if (!tree.HasOT()) {
		return;
	}
	subtree_relations.clear();
	ComputeSubtreeRelations(tree.OT().Root());

	// Seed: every null-rejecting filter contributes its relations.
	unordered_set<idx_t> null_rej;
	for (auto &rec : tree.filter_records) {
		if (!rec || !rec->filter) {
			continue;
		}
		if (!FilterRejectsNulls(*rec->filter)) {
			continue;
		}
		for (auto rel : rec->referenced_relations) {
			null_rej.insert(rel);
		}
	}

	// Experimental (env-gated, OFF by default): also seed from predicates that
	// filter-pushdown folded into table scans. UNSOUND in general — see
	// ScanFilterSimplifyEnabled. Provided so the effect can be benchmarked.
	if (ScanFilterSimplifyEnabled()) {
		for (auto *rel : tree.ot_relations_by_id) {
			if (!rel) {
				continue;
			}
			const LogicalOperator *base = FindBaseOp(rel->origin);
			if (!base || base->type != LogicalOperatorType::LOGICAL_GET) {
				continue;
			}
			auto &get = base->Cast<LogicalGet>();
			for (const auto &entry : get.table_filters) {
				if (TableFilterRejectsNulls(entry.Filter())) {
					null_rej.insert(rel->relation_id);
					break;
				}
			}
		}
	}

	VisitNode(tree, tree.OT().Root(), std::move(null_rej));

	// Done after the single top-down VisitNode walk so it captures the final
	// simplified kind, not an intermediate one.
	RebaseOriginalKinds(tree.OT().Root());
}

const unordered_set<idx_t> &Simplification::ComputeSubtreeRelations(OTNode &node) {
	auto &out = subtree_relations[&node];
	if (node.kind == OTNode::Kind::RELATION) {
		out.insert(node.relation_id);
		return out;
	}
	const auto &left = ComputeSubtreeRelations(*node.children[0]);
	const auto &right = ComputeSubtreeRelations(*node.children[1]);
	out.insert(left.begin(), left.end());
	out.insert(right.begin(), right.end());
	return out;
}

bool Simplification::FilterRejectsNulls(const Expression &expr) {
	switch (expr.GetExpressionClass()) {
	case ExpressionClass::BOUND_OPERATOR: {
		const auto t = expr.GetExpressionType();
		if (t == ExpressionType::OPERATOR_IS_NOT_NULL) {
			return true;
		}
		// `x IN (...)` / `x NOT IN (...)`: a NULL `x` yields NULL, so the row is
		// rejected. Require `x` to be a direct column ref (mirrors DuckDB's
		// HandleExpression discipline — keeps it sound for e.g. coalesce(x,0) IN …).
		if (t == ExpressionType::COMPARE_IN || t == ExpressionType::COMPARE_NOT_IN) {
			auto &op = expr.Cast<BoundOperatorExpression>();
			return !op.children.empty() &&
			       op.children[0]->GetExpressionClass() == ExpressionClass::BOUND_COLUMN_REF;
		}
		return false;
	}
	case ExpressionClass::BOUND_COMPARISON: {
		const auto t = expr.GetExpressionType();
		// NULL-tolerant comparisons (`IS [NOT] DISTINCT FROM`) do not reject NULL.
		return t != ExpressionType::COMPARE_DISTINCT_FROM && t != ExpressionType::COMPARE_NOT_DISTINCT_FROM;
	}
	case ExpressionClass::BOUND_BETWEEN: {
		// `input BETWEEN lo AND hi` ≡ `input >= lo AND input <= hi`: a NULL `input`
		// yields NULL ⇒ the row is rejected. DuckDB's optimizer normalises a
		// `col >= a AND col <= b` WHERE clause into a single BoundBetweenExpression,
		// so without this case the null-rejection (and the outer→inner collapse it
		// licenses) is silently lost. Require `input` to be a direct column ref
		// (mirrors the IN discipline) so a non-NULL-propagating wrapper such as
		// `coalesce(x,0) BETWEEN …` is not mistaken for null-rejecting.
		auto &bet = expr.Cast<BoundBetweenExpression>();
		return bet.input &&
		       bet.input->GetExpressionClass() == ExpressionClass::BOUND_COLUMN_REF;
	}
	case ExpressionClass::BOUND_FUNCTION: {
		// A NULL-propagating scalar function used as a boolean filter (LIKE `~~`,
		// NOT LIKE, GLOB, …) rejects NULL on a column it takes directly: NULL in ⇒
		// NULL out ⇒ row rejected. coalesce/ifnull use SPECIAL null handling and
		// are excluded; requiring a direct column-ref argument keeps it sound when
		// the column is buried under a non-propagating sub-expression.
		auto &func = expr.Cast<BoundFunctionExpression>();
		if (func.function.GetNullHandling() != FunctionNullHandling::DEFAULT_NULL_HANDLING) {
			return false;
		}
		for (auto &child : func.children) {
			if (child->GetExpressionClass() == ExpressionClass::BOUND_COLUMN_REF) {
				return true;
			}
		}
		return false;
	}
	case ExpressionClass::BOUND_CONJUNCTION: {
		auto &conj = expr.Cast<BoundConjunctionExpression>();
		if (conj.GetExpressionType() == ExpressionType::CONJUNCTION_AND) {
			// AND rejects NULL if ANY conjunct does.
			for (auto &child : conj.children) {
				if (FilterRejectsNulls(*child)) {
					return true;
				}
			}
			return false;
		}
		// CONJUNCTION_OR: rejects NULL only if EVERY disjunct does — otherwise a
		// non-rejecting branch could be TRUE for the all-NULL tuple.
		if (conj.children.empty()) {
			return false;
		}
		for (auto &child : conj.children) {
			if (!FilterRejectsNulls(*child)) {
				return false;
			}
		}
		return true;
	}
	default:
		return false;
	}
}

bool Simplification::SubtreeIntersectsNullRejection(OTNode &node,
                                                    const unordered_set<idx_t> &null_rej) {
	if (null_rej.empty()) {
		return false;
	}
	const auto &rels = subtree_relations[&node];
	for (auto rel : rels) {
		if (null_rej.find(rel) != null_rej.end()) {
			return true;
		}
	}
	return false;
}

void Simplification::VisitNode(OuterYanTree &tree, OTNode &node,
                               unordered_set<idx_t> null_rej) {
	if (node.kind == OTNode::Kind::RELATION) {
		return;
	}
	D_ASSERT(node.kind == OTNode::Kind::JOIN);
	D_ASSERT(node.info);
	auto &join_info = *node.info;

	// (a) Collapse the join kind based on which child subtree contains a
	//     null-rejected relation.
	const bool lhs_nullrej =
	    SubtreeIntersectsNullRejection(*node.children[0], null_rej);
	const bool rhs_nullrej =
	    SubtreeIntersectsNullRejection(*node.children[1], null_rej);

	const OuterYanJoinKind kind_before = join_info.join_kind;
	switch (join_info.join_kind) {
	case JoinType::INNER:
		break;
	case JoinType::LEFT:
		if (rhs_nullrej) {
			join_info.join_kind = JoinType::INNER;
		}
		break;
	case JoinType::RIGHT:
		if (lhs_nullrej) {
			join_info.join_kind = JoinType::INNER;
		}
		break;
	case JoinType::OUTER:
		if (lhs_nullrej && rhs_nullrej) {
			join_info.join_kind = JoinType::INNER;
		} else if (lhs_nullrej) {
			// LHS cannot be null-introducing → drop right-preservation.
			join_info.join_kind = JoinType::LEFT;
		} else if (rhs_nullrej) {
			// RHS cannot be null-introducing → drop left-preservation.
			join_info.join_kind = JoinType::RIGHT;
		}
		break;
	default:
		throw InternalException("OuterYan Simplification: unexpected join type %s",
		                        EnumUtil::ToString(join_info.join_kind));
	}

	if (join_info.join_kind != kind_before) {
		tree.stage_stats.simplify_collapses++;
	}

	// (b) Extend null_rej with the relations the (possibly rewritten) join
	//     condition itself null-rejects on the preserved side(s).
	switch (join_info.join_kind) {
	case JoinType::INNER:
		null_rej.insert(join_info.cond_left_relation_id);
		null_rej.insert(join_info.cond_right_relation_id);
		break;
	case JoinType::LEFT:
		// R1 ⟕ R2 on R1.x = R2.y: matched R2 rows must have R2.y non-null.
		null_rej.insert(join_info.cond_right_relation_id);
		break;
	case JoinType::RIGHT:
		// R1 ⟖ R2 on R1.x = R2.y: matched R1 rows must have R1.x non-null.
		null_rej.insert(join_info.cond_left_relation_id);
		break;
	case JoinType::OUTER:
		break;
	default:
		throw InternalException("OuterYan Simplification: unexpected join type %s",
		                        EnumUtil::ToString(join_info.join_kind));
	}

	VisitNode(tree, *node.children[0], null_rej);
	VisitNode(tree, *node.children[1], null_rej);
}

} // namespace duckdb
