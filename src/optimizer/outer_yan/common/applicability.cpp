#include "duckdb/optimizer/outer_yan/common/applicability.hpp"

#include "duckdb/optimizer/outer_yan/common/outer_yan_common.hpp"
#include "duckdb/optimizer/outer_yan/pipeline/simplification.hpp"

#include "duckdb/planner/expression/bound_columnref_expression.hpp"
#include "duckdb/planner/expression/bound_constant_expression.hpp"
#include "duckdb/planner/expression/bound_function_expression.hpp"
#include "duckdb/planner/expression_iterator.hpp"
#include "duckdb/planner/operator/logical_comparison_join.hpp"

namespace duckdb {

OuterYanApplicability::OuterYanApplicability() {
}

void OuterYanApplicability::CollectColumnTables(const Expression &expr,
                                                unordered_set<idx_t> &tables) {
	if (expr.GetExpressionClass() == ExpressionClass::BOUND_COLUMN_REF) {
		tables.insert(expr.Cast<BoundColumnRefExpression>().binding.table_index.index);
	}
	ExpressionIterator::EnumerateChildren(
	    expr, [&](const Expression &child) { CollectColumnTables(child, tables); });
}

static bool IsPositiveIntegralModuloDivisor(const BoundFunctionExpression &function) {
	if (function.function.name != "%" || function.children.size() != 2 ||
	    function.children[1]->GetExpressionClass() != ExpressionClass::BOUND_CONSTANT) {
		return false;
	}
	auto &divisor = function.children[1]->Cast<BoundConstantExpression>().value;
	if (divisor.IsNull() || !divisor.type().IsIntegral()) {
		return false;
	}
	// A strictly positive integral divisor excludes both runtime hazards of
	// DuckDB's fallible integral modulo implementation: zero and signed -1.
	return divisor > Value::Numeric(divisor.type(), int64_t(0));
}

static bool IsProvablyNonThrowingForPGPlan(const Expression &expr) {
	if (!expr.CanThrow()) {
		return true;
	}
	if (expr.GetExpressionClass() == ExpressionClass::BOUND_CAST) {
		// BoundCastExpression::CanThrow includes conversion failures which cannot
		// be discharged from type information alone.
		return false;
	}
	if (expr.GetExpressionClass() == ExpressionClass::BOUND_FUNCTION) {
		auto &function = expr.Cast<BoundFunctionExpression>();
		if (function.function.GetErrorMode() == FunctionErrors::CAN_THROW_RUNTIME_ERROR &&
		    !IsPositiveIntegralModuloDivisor(function)) {
			return false;
		}
	}
	bool children_safe = true;
	ExpressionIterator::EnumerateChildren(expr, [&](const Expression &child) {
		if (!IsProvablyNonThrowingForPGPlan(child)) {
			children_safe = false;
		}
	});
	return children_safe;
}

bool OuterYanApplicability::FilterRequiresOriginalScope(const Expression &expr) {
	if (expr.IsVolatile()) {
		return true;
	}
	return !IsProvablyNonThrowingForPGPlan(expr);
}

ApplicabilityResult OuterYanApplicability::Check(LogicalOperator &plan, bool require_outer,
                                                 bool require_stable_intermediate_filters,
                                                 bool allow_anchored_join_residuals) {
	OuterYanApplicability v;
	v.require_stable_intermediate_filters = require_stable_intermediate_filters;
	v.allow_anchored_join_residuals = allow_anchored_join_residuals;
	auto &entry = v.SkeletonRoot(plan);

	if (entry.type != LogicalOperatorType::LOGICAL_COMPARISON_JOIN) {
		v.result.applicable = false;
		v.result.reason = "not a SELECT join query";
		return std::move(v.result);
	}
	v.VisitOperator(entry);

	if (v.rejected) {
		v.result.applicable = false;
		return std::move(v.result);
	}
	if (require_outer && !v.has_outer) {
		v.result.applicable = false;
		v.result.reason = "pure inner-join query — defer to JoinOrderOptimizer";
		return std::move(v.result);
	}
	// Residuals must be unary (≤1 base relation each). table_index_to_relation is
	// fully populated by the walk above, so the arity is now resolvable.
	if (!v.ResidualsAreUnary(plan)) {
		v.result.applicable = false;
		v.result.reason = "residual predicate spans >1 relation (only unary "
		                  "\"column OP constant\" residuals supported)";
		return std::move(v.result);
	}
	v.result.applicable = true;
	return std::move(v.result);
}

bool OuterYanApplicability::ResidualsAreUnary(LogicalOperator &op) {
	if (op.type == LogicalOperatorType::LOGICAL_FILTER) {
		for (auto &expr : op.expressions) {
			unordered_set<idx_t> tables;
			CollectColumnTables(*expr, tables);
			unordered_set<RelationId> rels;
			for (auto ti : tables) {
				auto it = result.table_index_to_relation.find(ti);
				if (it != result.table_index_to_relation.end()) {
					rels.insert(it->second);
				}
			}
			if (rels.size() > 1) {
				return false;
			}
		}
	}
	for (auto &child : op.children) {
		if (!ResidualsAreUnary(*child)) {
			return false;
		}
	}
	return true;
}

LogicalOperator &OuterYanApplicability::SkeletonRoot(LogicalOperator &plan) {
	auto *cur = &plan;
	auto peel = [&]() {
		while (!cur->children.empty() &&
		       (cur->type == LogicalOperatorType::LOGICAL_PROJECTION ||
		        cur->type == LogicalOperatorType::LOGICAL_FILTER)) {
			cur = cur->children[0].get();
		}
	};
	peel();
	if ((cur->type == LogicalOperatorType::LOGICAL_AGGREGATE_AND_GROUP_BY ||
	     cur->type == LogicalOperatorType::LOGICAL_DISTINCT) &&
	    !cur->children.empty()) {
		result.has_root_aggregate = true;
		cur = cur->children[0].get();
		peel();
	}
	return *cur;
}

void OuterYanApplicability::VisitOperator(LogicalOperator &op) {
	if (rejected) {
		return;
	}
	switch (op.type) {
	case LogicalOperatorType::LOGICAL_COMPARISON_JOIN:
		VisitComparisonJoin(op.Cast<LogicalComparisonJoin>());
		return;

	case LogicalOperatorType::LOGICAL_FILTER:
		// Root-cap filters were peeled by SkeletonRoot. A Filter/Projection/Get
		// chain is an opaque base relation and is safe to retain as-is. Any
		// remaining filter sits between joins. Such a predicate can move to its
		// referenced leaf only when it is provably NULL-rejecting: Simplification
		// then lowers every affected outer join inside the recorded scope before
		// DP reorders it. A NULL-tolerant intermediate predicate must retain an
		// exact evaluation boundary that DP does not currently model.
		if (IsBaseRelationSubtree(op)) {
			VisitOperatorChildren(op);
			return;
		}
		for (const auto &expr : op.expressions) {
			if (require_stable_intermediate_filters && FilterRequiresOriginalScope(*expr)) {
				Reject("volatile or throwing filter inside join skeleton not supported by PGPlan "
				       "(evaluation count/scope may change)");
				return;
			}
			if (!Simplification::FilterRejectsNulls(*expr)) {
				Reject("NULL-tolerant filter inside join skeleton not supported "
				       "(filter scope may not survive reordering)");
				return;
			}
		}
		VisitOperatorChildren(op);
		return;

	case LogicalOperatorType::LOGICAL_AGGREGATE_AND_GROUP_BY:
		Reject("aggregation inside join skeleton not supported");
		return;
	case LogicalOperatorType::LOGICAL_WINDOW:
		Reject("window operator inside join skeleton not supported");
		return;
	case LogicalOperatorType::LOGICAL_UNION:
	case LogicalOperatorType::LOGICAL_EXCEPT:
	case LogicalOperatorType::LOGICAL_INTERSECT:
		Reject("set operation inside join skeleton not supported");
		return;
	case LogicalOperatorType::LOGICAL_ANY_JOIN:
	case LogicalOperatorType::LOGICAL_DELIM_JOIN:
	case LogicalOperatorType::LOGICAL_ASOF_JOIN:
	case LogicalOperatorType::LOGICAL_POSITIONAL_JOIN:
	case LogicalOperatorType::LOGICAL_DEPENDENT_JOIN:
		Reject("unsupported join operator (only comparison joins allowed)");
		return;

	default:
		// Opaque leaf: LogicalGet, LogicalExpressionGet, LogicalCTERef,
		// LogicalDummyScan, sub-plans, etc.
		RegisterLeaf(op);
		return;
	}
}

void OuterYanApplicability::VisitComparisonJoin(LogicalComparisonJoin &join) {
	switch (join.join_type) {
	case JoinType::INNER:
		break;
	case JoinType::LEFT:
	case JoinType::RIGHT:
	case JoinType::OUTER:
		has_outer = true;
		break;
	default:
		Reject("unsupported join type (semi/anti/mark/single not allowed)");
		return;
	}

	if (join.conditions.empty()) {
		Reject("cross product (join with no conditions) not supported");
		return;
	}

	const auto left_begin = result.relations.size();
	VisitOperator(*join.children[0]);
	if (rejected) {
		return;
	}
	const auto left_end = result.relations.size();
	const auto right_begin = left_end;
	VisitOperator(*join.children[1]);
	if (rejected) {
		return;
	}
	const auto right_end = result.relations.size();

	if (allow_anchored_join_residuals) {
		optional_idx anchor_index;
		RelationId anchor_left = DConstants::INVALID_INDEX;
		RelationId anchor_right = DConstants::INVALID_INDEX;

		for (idx_t cond_idx = 0; cond_idx < join.conditions.size(); cond_idx++) {
			const auto &cond = join.conditions[cond_idx];
			unordered_set<idx_t> tables;
			unordered_set<idx_t> lhs_tables;
			unordered_set<idx_t> rhs_tables;
			if (cond.IsComparison()) {
				const auto comparison = cond.GetComparisonType();
				if (comparison == ExpressionType::COMPARE_DISTINCT_FROM ||
				    comparison == ExpressionType::COMPARE_NOT_DISTINCT_FROM) {
					Reject("NULL-tolerant join condition (IS [NOT] DISTINCT FROM) not supported");
					return;
				}
				if (cond.GetLHS().IsVolatile() || cond.GetLHS().CanThrow() ||
				    cond.GetRHS().IsVolatile() || cond.GetRHS().CanThrow()) {
					Reject("volatile or throwing PGPlan join condition not supported");
					return;
				}
				CollectColumnTables(cond.GetLHS(), lhs_tables);
				CollectColumnTables(cond.GetRHS(), rhs_tables);
				tables.insert(lhs_tables.begin(), lhs_tables.end());
				tables.insert(rhs_tables.begin(), rhs_tables.end());
			} else {
				const auto &expression = cond.GetJoinExpression();
				if (expression.IsVolatile() || expression.CanThrow()) {
					Reject("volatile or throwing PGPlan join condition not supported");
					return;
				}
				CollectColumnTables(expression, tables);
			}

			unordered_set<RelationId> relations;
			for (auto table_index : tables) {
				auto entry = result.table_index_to_relation.find(table_index);
				if (entry == result.table_index_to_relation.end()) {
					Reject("join condition references a column outside the join skeleton");
					return;
				}
				relations.insert(entry->second);
			}
			if (relations.empty()) {
				Reject("PGPlan join residual must reference at least one anchor relation");
				return;
			}
			for (auto relation : relations) {
				if (relation < left_begin || relation >= right_end) {
					Reject("PGPlan join condition references a relation outside its bound join subtree");
					return;
				}
			}

			if (!anchor_index.IsValid() && cond.IsComparison() &&
			    cond.GetComparisonType() == ExpressionType::COMPARE_EQUAL) {
				unordered_set<RelationId> lhs_relations;
				unordered_set<RelationId> rhs_relations;
				for (auto table_index : lhs_tables) {
					auto entry = result.table_index_to_relation.find(table_index);
					if (entry != result.table_index_to_relation.end()) {
						lhs_relations.insert(entry->second);
					}
				}
				for (auto table_index : rhs_tables) {
					auto entry = result.table_index_to_relation.find(table_index);
					if (entry != result.table_index_to_relation.end()) {
						rhs_relations.insert(entry->second);
					}
				}
				if (lhs_relations.size() == 1 && rhs_relations.size() == 1 &&
				    *lhs_relations.begin() != *rhs_relations.begin()) {
					auto lhs_relation = *lhs_relations.begin();
					auto rhs_relation = *rhs_relations.begin();
					const bool lhs_left = lhs_relation >= left_begin && lhs_relation < left_end;
					const bool lhs_right = lhs_relation >= right_begin && lhs_relation < right_end;
					const bool rhs_left = rhs_relation >= left_begin && rhs_relation < left_end;
					const bool rhs_right = rhs_relation >= right_begin && rhs_relation < right_end;
					if (!((lhs_left && rhs_right) || (lhs_right && rhs_left))) {
						continue;
					}
					anchor_index = optional_idx(cond_idx);
					anchor_left = lhs_left ? lhs_relation : rhs_relation;
					anchor_right = lhs_left ? rhs_relation : lhs_relation;
				}
			}
		}

		if (!anchor_index.IsValid()) {
			Reject("each PGPlan join requires a safe two-relation equality anchor");
			return;
		}
		RelationId low = anchor_left < anchor_right ? anchor_left : anchor_right;
		RelationId high = anchor_left < anchor_right ? anchor_right : anchor_left;
		uint64_t key = (uint64_t(low) << 32) | uint64_t(high);
		if (!seen_pairs.insert(key).second || !UnionRelations(anchor_left, anchor_right)) {
			Reject("join graph has a cycle");
			return;
		}
		result.edges.push_back({anchor_left, anchor_right, &join, anchor_index.GetIndex()});
		return;
	}

	for (idx_t cond_idx = 0; cond_idx < join.conditions.size(); cond_idx++) {
		const auto &cond = join.conditions[cond_idx];
		if (!cond.IsComparison()) {
			Reject("non-comparison join condition not supported");
			return;
		}
		auto cmp = cond.GetComparisonType();
		if (cmp == ExpressionType::COMPARE_DISTINCT_FROM ||
		    cmp == ExpressionType::COMPARE_NOT_DISTINCT_FROM) {
			Reject("NULL-tolerant join condition (IS [NOT] DISTINCT FROM) not supported");
			return;
		}
		// Equi-join enforcement: comparator must be `=` and both sides must
		// be plain BoundColumnRefs. Theta / inequality / expression-on-side
		// joins are deferred to a future relaxation.
		if (cmp != ExpressionType::COMPARE_EQUAL) {
			Reject("non-equi join condition (only `=` supported)");
			return;
		}
		if (cond.GetLHS().GetExpressionClass() != ExpressionClass::BOUND_COLUMN_REF ||
		    cond.GetRHS().GetExpressionClass() != ExpressionClass::BOUND_COLUMN_REF) {
			Reject("equi-join condition sides must be plain column references");
			return;
		}

		unordered_set<idx_t> tables;
		CollectColumnTables(cond.GetLHS(), tables);
		CollectColumnTables(cond.GetRHS(), tables);

		unordered_set<RelationId> rels;
		for (auto ti : tables) {
			auto it = result.table_index_to_relation.find(ti);
			if (it == result.table_index_to_relation.end()) {
				Reject("join condition references a column outside the join skeleton");
				return;
			}
			rels.insert(it->second);
		}
		if (rels.size() != 2) {
			Reject("join condition must reference exactly two base relations");
			return;
		}

		auto rit = rels.begin();
		RelationId a = *rit++;
		RelationId b = *rit;
		RelationId lo = a < b ? a : b;
		RelationId hi = a < b ? b : a;
		uint64_t key = (uint64_t(lo) << 32) | uint64_t(hi);
		bool first_for_pair = seen_pairs.insert(key).second;
		if (first_for_pair) {
			if (!UnionRelations(a, b)) {
				Reject("join graph has a cycle");
				return;
			}
			result.edges.push_back({a, b, &join, cond_idx});
		}
		// Multi-edges between the same pair are tolerated: same node pair,
		// no cycle introduced.
	}
}

void OuterYanApplicability::RegisterLeaf(LogicalOperator &leaf) {
	RelationId id = result.relations.size();
	result.relations.push_back(&leaf);
	uf_parent.push_back(id);
	for (auto &ti : leaf.GetTableIndex()) {
		auto inserted = result.table_index_to_relation.emplace(ti.index, id);
		if (!inserted.second) {
			Reject("duplicate table index across leaf relations");
			return;
		}
	}
}

void OuterYanApplicability::Reject(string reason) {
	if (!rejected) {
		rejected = true;
		result.reason = std::move(reason);
	}
}

RelationId OuterYanApplicability::Find(RelationId x) {
	while (uf_parent[x] != x) {
		uf_parent[x] = uf_parent[uf_parent[x]];
		x = uf_parent[x];
	}
	return x;
}

bool OuterYanApplicability::UnionRelations(RelationId a, RelationId b) {
	auto ra = Find(a);
	auto rb = Find(b);
	if (ra == rb) {
		return false;
	}
	uf_parent[ra] = rb;
	return true;
}

} // namespace duckdb
