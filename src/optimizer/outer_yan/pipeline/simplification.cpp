#include "duckdb/optimizer/outer_yan/pipeline/simplification.hpp"

#include "duckdb/common/enum_util.hpp"
#include "duckdb/execution/expression_executor.hpp"
#include "duckdb/optimizer/outer_yan/common/outer_yan_common.hpp"
#include "duckdb/planner/expression/bound_between_expression.hpp"
#include "duckdb/planner/expression/bound_cast_expression.hpp"
#include "duckdb/planner/expression/bound_columnref_expression.hpp"
#include "duckdb/planner/expression/bound_comparison_expression.hpp"
#include "duckdb/planner/expression/bound_constant_expression.hpp"
#include "duckdb/planner/expression/bound_conjunction_expression.hpp"
#include "duckdb/planner/expression/bound_function_expression.hpp"
#include "duckdb/planner/expression/bound_operator_expression.hpp"
#include "duckdb/planner/expression_iterator.hpp"
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

//! Conservative proof that `expr` evaluates to NULL when the referenced
//! relation is NULL-extended. Returning false means "not proven", not that the
//! expression is necessarily non-NULL.
static bool BecomesNullOnNullExtendedInput(const Expression &expr) {
	switch (expr.GetExpressionClass()) {
	case ExpressionClass::BOUND_COLUMN_REF:
		return true;
	case ExpressionClass::BOUND_CAST:
		return BecomesNullOnNullExtendedInput(*expr.Cast<BoundCastExpression>().child);
	case ExpressionClass::BOUND_FUNCTION: {
		auto &func = expr.Cast<BoundFunctionExpression>();
		if (func.function.GetNullHandling() != FunctionNullHandling::DEFAULT_NULL_HANDLING) {
			return false;
		}
		for (const auto &child : func.children) {
			if (BecomesNullOnNullExtendedInput(*child)) {
				return true;
			}
		}
		return false;
	}
	case ExpressionClass::BOUND_COMPARISON: {
		if (expr.GetExpressionType() == ExpressionType::COMPARE_DISTINCT_FROM ||
		    expr.GetExpressionType() == ExpressionType::COMPARE_NOT_DISTINCT_FROM) {
			return false;
		}
		auto &comparison = expr.Cast<BoundComparisonExpression>();
		return BecomesNullOnNullExtendedInput(*comparison.left) ||
		       BecomesNullOnNullExtendedInput(*comparison.right);
	}
	case ExpressionClass::BOUND_BETWEEN:
		return BecomesNullOnNullExtendedInput(*expr.Cast<BoundBetweenExpression>().input);
	default:
		return false;
	}
}

// NOTE: Implementation strategy
// -----------------------------
// 1. At each OT node, activate null-rejecting filter records whose original
//    evaluation scope is exactly that subtree. This makes root predicates
//    active at the root while preventing an intermediate predicate from
//    simplifying joins above its source location.
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

void Simplification::Apply(OuterYanTree &tree, bool allow_scan_filter_seeding) {
	if (!tree.HasOT()) {
		return;
	}
	subtree_relations.clear();
	ComputeSubtreeRelations(tree.OT().Root());

	unordered_set<idx_t> null_rej;
	// Experimental (env-gated, OFF by default): also seed from predicates that
	// filter-pushdown folded into table scans. UNSOUND in general — see
	// ScanFilterSimplifyEnabled. Provided so the effect can be benchmarked.
	if (allow_scan_filter_seeding && ScanFilterSimplifyEnabled()) {
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

static bool StructurallyRejectsNulls(const Expression &expr) {
	switch (expr.GetExpressionClass()) {
	case ExpressionClass::BOUND_OPERATOR: {
		const auto t = expr.GetExpressionType();
		if (t == ExpressionType::OPERATOR_IS_NOT_NULL) {
			auto &op = expr.Cast<BoundOperatorExpression>();
			return op.children.size() == 1 && BecomesNullOnNullExtendedInput(*op.children[0]);
		}
		// `x IN (...)` / `x NOT IN (...)`: a NULL `x` yields NULL, so the row is
		// rejected. The recursive proof accepts NULL-propagating wrappers and
		// excludes forms such as coalesce(x, 0).
		if (t == ExpressionType::COMPARE_IN || t == ExpressionType::COMPARE_NOT_IN) {
			auto &op = expr.Cast<BoundOperatorExpression>();
			return !op.children.empty() && BecomesNullOnNullExtendedInput(*op.children[0]);
		}
		return false;
	}
	case ExpressionClass::BOUND_COMPARISON: {
		const auto t = expr.GetExpressionType();
		// NULL-tolerant comparisons (`IS [NOT] DISTINCT FROM`) do not reject NULL.
		if (t == ExpressionType::COMPARE_DISTINCT_FROM ||
		    t == ExpressionType::COMPARE_NOT_DISTINCT_FROM) {
			return false;
		}
		return BecomesNullOnNullExtendedInput(expr);
	}
	case ExpressionClass::BOUND_BETWEEN: {
		// `input BETWEEN lo AND hi` ≡ `input >= lo AND input <= hi`: a NULL `input`
		// yields NULL ⇒ the row is rejected. DuckDB's optimizer normalises a
		// `col >= a AND col <= b` WHERE clause into a single BoundBetweenExpression,
		// so without this case the null-rejection (and the outer→inner collapse it
		// licenses) is silently lost. The recursive proof excludes
		// non-NULL-propagating wrappers such as coalesce(x, 0).
		auto &bet = expr.Cast<BoundBetweenExpression>();
		return bet.input && BecomesNullOnNullExtendedInput(*bet.input);
	}
	case ExpressionClass::BOUND_FUNCTION: {
		// A NULL-propagating scalar function used as a boolean filter (LIKE `~~`,
		// NOT LIKE, GLOB, …) rejects NULL when a NULL-propagating argument is
		// derived from the referenced relation. coalesce/ifnull use SPECIAL null
		// handling and are excluded.
		auto &func = expr.Cast<BoundFunctionExpression>();
		if (func.function.GetNullHandling() != FunctionNullHandling::DEFAULT_NULL_HANDLING) {
			return false;
		}
		return BecomesNullOnNullExtendedInput(expr);
	}
	case ExpressionClass::BOUND_CONJUNCTION: {
		auto &conj = expr.Cast<BoundConjunctionExpression>();
		if (conj.GetExpressionType() == ExpressionType::CONJUNCTION_AND) {
			// AND rejects NULL if ANY conjunct does.
			for (auto &child : conj.children) {
				if (StructurallyRejectsNulls(*child)) {
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
			if (!StructurallyRejectsNulls(*child)) {
				return false;
			}
		}
		return true;
	}
	default:
		return false;
	}
}

static void ReplaceColumnsWithNull(unique_ptr<Expression> &expr) {
	if (expr->GetExpressionClass() == ExpressionClass::BOUND_COLUMN_REF) {
		expr = make_uniq<BoundConstantExpression>(Value(expr->return_type));
		return;
	}
	ExpressionIterator::EnumerateChildren(*expr, [&](unique_ptr<Expression> &child) { ReplaceColumnsWithNull(child); });
}

bool Simplification::FilterRejectsNulls(const Expression &expr, optional_ptr<ClientContext> context) {
	if (StructurallyRejectsNulls(expr)) {
		return true;
	}
	if (!context || expr.return_type != LogicalType::BOOLEAN ||
	    OuterYanApplicability::FilterRequiresOriginalScope(expr)) {
		return false;
	}
	// SPECIAL null handling (e.g., hash) need not propagate NULL. Evaluate the
	// actual bound predicate instead of assuming that it accepts or rejects it.
	auto null_input = expr.Copy();
	ReplaceColumnsWithNull(null_input);
	if (!null_input->IsFoldable()) {
		return false;
	}
	Value result;
	return ExpressionExecutor::TryEvaluateScalar(*context, *null_input, result) &&
	       (result.IsNull() || !BooleanValue::Get(result));
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
	const auto &node_relations = subtree_relations[&node];
	for (const auto &rec : tree.filter_records) {
		if (!rec || !rec->filter || rec->evaluation_relations != node_relations ||
		    !FilterRejectsNulls(*rec->filter, tree.context)) {
			continue;
		}
		for (auto rel : rec->referenced_relations) {
			null_rej.insert(rel);
		}
	}
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
