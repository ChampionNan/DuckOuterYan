#include "duckdb/optimizer/outer_yan/common/outer_yan_tree.hpp"

#include "duckdb/catalog/catalog_entry/schema_catalog_entry.hpp"
#include "duckdb/catalog/catalog_entry/table_catalog_entry.hpp"
#include "duckdb/common/enum_util.hpp"
#include "duckdb/common/enums/join_type.hpp"
#include "duckdb/common/exception.hpp"
#include "duckdb/common/reference_map.hpp"
#include "duckdb/common/string_util.hpp"
#include "duckdb/common/unordered_map.hpp"
#include "duckdb/optimizer/join_order/join_relation.hpp"
#include "duckdb/optimizer/join_order/relation_index.hpp"
#include "duckdb/parser/constraints/foreign_key_constraint.hpp"
#include "duckdb/parser/constraints/not_null_constraint.hpp"
#include "duckdb/parser/constraints/unique_constraint.hpp"
#include "duckdb/planner/expression/bound_aggregate_expression.hpp"
#include "duckdb/planner/expression/bound_columnref_expression.hpp"
#include "duckdb/planner/expression_iterator.hpp"
#include "duckdb/planner/operator/logical_aggregate.hpp"
#include "duckdb/planner/operator/logical_comparison_join.hpp"
#include "duckdb/planner/operator/logical_distinct.hpp"
#include "duckdb/planner/operator/logical_filter.hpp"
#include "duckdb/planner/operator/logical_get.hpp"
#include "duckdb/planner/operator/logical_projection.hpp"

#include <algorithm>
#include <functional>

namespace duckdb {

// ============================================================================
// BuildOT helpers
// ============================================================================

void OuterYanTree::MapTableToRelId(const LogicalOperator &op, idx_t relation_id,
                                   unordered_map<idx_t, RelationId> &table_to_relation) {
	if (op.type == LogicalOperatorType::LOGICAL_GET) {
		auto &get = op.Cast<LogicalGet>();
		table_to_relation[get.table_index.index] = relation_id;
	}
	for (auto &child : op.children) {
		if (child) {
			MapTableToRelId(*child, relation_id, table_to_relation);
		}
	}
}

void OuterYanTree::CollectReferencedRelations(const Expression &expr,
                                              const unordered_map<idx_t, RelationId> &table_to_relation,
                                              unordered_set<idx_t> &out) {
	// Delegate the walk to the applicability gate's shared helper, then
	// translate each raw `table_index` to its OT/OJT `RelationId`. Skips
	// table_indexes that lie outside the join skeleton.
	unordered_set<idx_t> tables;
	OuterYanApplicability::CollectColumnTables(expr, tables);
	for (auto ti : tables) {
		auto it = table_to_relation.find(ti);
		if (it != table_to_relation.end()) {
			out.insert(it->second);
		}
	}
}

optional<idx_t> OuterYanTree::LookupSingleRelation(const Expression &expr,
                                                   const unordered_map<idx_t, RelationId> &table_to_relation) {
	unordered_set<idx_t> relations;
	CollectReferencedRelations(expr, table_to_relation, relations);
	if (relations.size() != 1) {
		return optional<idx_t>();
	}
	return *relations.begin();
}

// ============================================================================
// CheckApplicability
// ============================================================================

bool OuterYanTree::CheckApplicability(LogicalOperator &plan, bool require_outer,
                                      bool require_stable_intermediate_filters) {
	pgplan_filter_scope_mode = false;
	applicability = OuterYanApplicability::Check(plan, require_outer, require_stable_intermediate_filters,
	                                           /*allow_anchored_join_residuals=*/false, context);
	return applicability.applicable;
}

bool OuterYanTree::CheckPGPlanApplicability(LogicalOperator &plan) {
	pgplan_filter_scope_mode = true;
	applicability = OuterYanApplicability::Check(plan, /*require_outer=*/false,
	                                            /*require_stable_intermediate_filters=*/false,
	                                            /*allow_anchored_join_residuals=*/true, context);
	return applicability.applicable;
}

// ============================================================================
// BuildOT — Collect phase
// ============================================================================

class OuterYanTree::OTBuilder {
public:
	OTBuilder(LogicalOperator &plan_p, OuterYanTree &tree_p)
	    : plan_root(plan_p), tree(tree_p) {
	}

	unique_ptr<OperatorTree> Build() {
		auto root = BuildNode(plan_root);
		tree.ot_joins_by_order.clear();
		AssignJoinOrders(*root);
		SetJoinTwoSides();
		// `tree.table_to_relation` is fully populated only after every RELATION
		// node has been built; resolve aggregate column bindings into relation
		// ids now.
		ResolveAggregationRelations();

		auto ot = make_uniq<OperatorTree>();
		ot->root = std::move(root);
		// Populate `OTNode::subtree_relations` and canonicalise every JOIN so
		// that `conditions[0]` LHS / RHS line up with `children[0]` / `children[1]`.
		// Downstream passes (Simplification, Desimplification, OTToOJT, etc.)
		// assume this canonical form.
		ot->Finalize();
		return ot;
	}

private:
	LogicalOperator &plan_root;
	OuterYanTree &tree;

	idx_t next_relation_id = 0;
	idx_t join_depth = 0;

	static void CollectRelationIds(const OTNode &node, unordered_set<idx_t> &out) {
		if (node.kind == OTNode::Kind::RELATION) {
			out.insert(node.relation_id);
			return;
		}
		CollectRelationIds(*node.children[0], out);
		CollectRelationIds(*node.children[1], out);
	}

	unique_ptr<OTNode> BuildNode(LogicalOperator &op) {
		if (IsBaseRelationSubtree(op)) {
			return BuildRelationNode(op);
		}
		switch (op.type) {
		case LogicalOperatorType::LOGICAL_COMPARISON_JOIN:
			return BuildJoinNode(op);
		case LogicalOperatorType::LOGICAL_FILTER:
			return BuildThroughFilter(op);
		case LogicalOperatorType::LOGICAL_PROJECTION:
			return BuildThroughProjection(op);
		case LogicalOperatorType::LOGICAL_AGGREGATE_AND_GROUP_BY:
			return BuildThroughAggregate(op);
		case LogicalOperatorType::LOGICAL_DISTINCT:
			return BuildThroughDistinct(op);
		default:
			throw NotImplementedException("LogicalPlanToOT: unsupported operator %s",
			                              EnumUtil::ToString(op.type));
		}
	}

	unique_ptr<OTNode> BuildRelationNode(LogicalOperator &op) {
		auto node = make_uniq<OTNode>();
		node->kind = OTNode::Kind::RELATION;
		node->origin = &op;
		node->relation_id = next_relation_id++;
		MapTableToRelId(op, node->relation_id, tree.table_to_relation);
		if (node->relation_id >= tree.ot_relations_by_id.size()) {
			tree.ot_relations_by_id.resize(node->relation_id + 1, nullptr);
		}
		tree.ot_relations_by_id[node->relation_id] = node.get();
		return node;
	}

	unique_ptr<OTNode> BuildJoinNode(LogicalOperator &op) {
		if (op.children.size() != 2) {
			throw NotImplementedException(
			    "LogicalPlanToOT: LogicalComparisonJoin with %llu children (expected 2)",
			    op.children.size());
		}
		auto &join = op.Cast<LogicalComparisonJoin>();
		auto node = make_uniq<OTNode>();
		node->kind = OTNode::Kind::JOIN;

		auto info = make_uniq<OTJoin>();
		info->join_kind = join.join_type;
		info->original_join_kind = join.join_type;
		info->conditions.reserve(join.conditions.size());
		for (const auto &cond : join.conditions) {
			info->conditions.push_back(cond.Copy());
		}
		node->info = std::move(info);

		join_depth++;
		node->children[0] = BuildNode(*op.children[0]);
		node->children[1] = BuildNode(*op.children[1]);
		join_depth--;
		return node;
	}

	unique_ptr<OTNode> BuildThroughFilter(LogicalOperator &op) {
		if (op.children.size() != 1) {
			throw InternalException("LogicalFilter with %llu children", op.children.size());
		}
		const bool root_cap_filter = join_depth == 0;
		// A root predicate stays in `source_plan`; its record is an analysis copy.
		// Applicability permits an intermediate predicate only when it is
		// NULL-rejecting, in which case scope-aware Simplification makes leaf
		// placement semantics-preserving before DP runs.
		if (root_cap_filter) {
			tree.root_skeleton_parent = &op;
		}
		auto child_node = BuildNode(*op.children[0]);
		unordered_set<idx_t> evaluation_relations;
		CollectRelationIds(*child_node, evaluation_relations);
		auto &filter = op.Cast<LogicalFilter>();
		for (auto &expr : filter.expressions) {
			unordered_set<idx_t> refs;
			CollectReferencedRelations(*expr, tree.table_to_relation, refs);
			if (refs.empty()) {
				throw NotImplementedException(
				    "LogicalPlanToOT: residual filter expression references no OT base "
				    "relation (likely a projection-introduced table_index above the join "
				    "tree); not yet supported");
			}
			auto record_expr = root_cap_filter ? expr->Copy() : std::move(expr);
			auto rec = make_uniq<OuterYanFilterRecord>(std::move(record_expr), std::move(refs),
			                                           tree.filter_records.size());
			rec->evaluation_relations = evaluation_relations;
			rec->from_residual_predicate = true;
			rec->retained_at_original_scope = root_cap_filter;
			rec->requires_original_scope =
			    tree.pgplan_filter_scope_mode && !root_cap_filter &&
			    OuterYanApplicability::FilterRequiresOriginalScope(*rec->filter);
			tree.filter_records.push_back(std::move(rec));
		}
		if (!root_cap_filter) {
			filter.expressions.clear();
		}
		return child_node;
	}

	//! Peel a root LogicalProjection — a cap above the join skeleton. Record it
	//! as the current splice anchor; the recursion below overwrites the anchor
	//! with any deeper cap, so the FINAL anchor is the operator directly above
	//! the skeleton root. `OJTToLogicalPlan` re-attaches the rebuilt skeleton
	//! into that slot, preserving every cap above it.
	unique_ptr<OTNode> BuildThroughProjection(LogicalOperator &op) {
		if (op.children.size() != 1) {
			throw InternalException("LogicalProjection with %llu children",
			                        op.children.size());
		}
		tree.root_skeleton_parent = &op;
		return BuildNode(*op.children[0]);
	}

	//! Peel a root LogicalAggregate, classify it into `tree.root_aggregation`,
	//! and descend into the join skeleton beneath. The applicability gate
	//! already rejects aggregates that appear inside the join skeleton, so
	//! this case fires only on the root chain.
	unique_ptr<OTNode> BuildThroughAggregate(LogicalOperator &op) {
		if (op.children.size() != 1) {
			throw InternalException("LogicalAggregate with %llu children",
			                        op.children.size());
		}
		auto &agg = op.Cast<LogicalAggregate>();
		ClassifyRootAggregate(agg);
		// The aggregate is a cap that MUST survive the OJT roundtrip (unlike a
		// pruning projection it carries the COUNT/SUM/GROUP BY semantics).
		// Record it as the splice anchor; a deeper cap (the aggregate's own
		// input projection) overwrites it during recursion, so the skeleton is
		// re-attached directly beneath whatever sits lowest.
		tree.root_skeleton_parent = &op;
		return BuildNode(*op.children[0]);
	}

	//! Peel a root LogicalDistinct, classify it as `SELECT_DISTINCT`, and
	//! record each child binding as a distinct target in
	//! `tree.root_aggregation.columns`. Mirrors the reference's
	//! `StoreDistinctAggregates` (`aggregation_pushdown.cpp:272`).
	unique_ptr<OTNode> BuildThroughDistinct(LogicalOperator &op) {
		if (op.children.size() != 1) {
			throw InternalException("LogicalDistinct with %llu children",
			                        op.children.size());
		}
		auto &distinct = op.Cast<LogicalDistinct>();
		auto &info = tree.root_aggregation;
		// Outermost classifier wins — defensive against nested distincts.
		if (info.type == OuterYanAggregationType::NONE) {
			info.type = OuterYanAggregationType::SELECT_DISTINCT;
			info.has_group_by = false;
			// Record each child binding as a "distinct" target so the
			// rewriter knows which columns the root distinct cares about.
			auto child_bindings = distinct.children[0]->GetColumnBindings();
			distinct.children[0]->ResolveOperatorTypes();
			for (idx_t i = 0; i < child_bindings.size(); i++) {
				OuterYanAggregateColumn col;
				col.function_name = "distinct";
				col.binding = child_bindings[i];
				info.columns.push_back(std::move(col));
			}
		}
		// DISTINCT is a cap that must survive the roundtrip; record it as the
		// splice anchor (a deeper projection below it overwrites it).
		tree.root_skeleton_parent = &op;
		return BuildNode(*op.children[0]);
	}

	//! Record the root aggregate's type tag and per-expression column info on
	//! `tree.root_aggregation`. Classification is by aggregate function name
	//! only -- mirrors `the earlier DetectQueryType implementation` (optimizer.cpp:533) and
	//! `aggregation_pushdown.cpp:102`.
	void ClassifyRootAggregate(LogicalAggregate &agg) {
		auto &info = tree.root_aggregation;
		// Outermost aggregate wins; binding layers never emit nested
		// LogicalAggregate so this is defensive only.
		if (info.type != OuterYanAggregationType::NONE) {
			return;
		}
		info.agg_op = &agg;
		info.has_group_by = !agg.groups.empty();

		// Capture GROUP BY column bindings. These columns anchor the OJT root:
		// `ResolveAggregationRelations` feeds them into `tree.root_relations`,
		// which OuterYanDP consults to force the corresponding relations to the
		// top of the chosen tree. Non-column GROUP BY expressions (e.g.
		// `GROUP BY a + b`) are skipped here -- handling them would require a
		// full expression walk; prototype scope leaves it as future work.
		for (auto &group_expr : agg.groups) {
			if (!group_expr ||
			    group_expr->GetExpressionClass() != ExpressionClass::BOUND_COLUMN_REF) {
				continue;
			}
			OuterYanAggregateColumn col;
			col.function_name = "group_by";
			col.binding = group_expr->Cast<BoundColumnRefExpression>().binding;
			info.columns.push_back(std::move(col));
		}

		bool any_count_star = false;
		bool any_minmax = false;
		bool any_sum = false;
		bool any_other = false;

		for (auto &expr : agg.expressions) {
			if (expr->GetExpressionClass() != ExpressionClass::BOUND_AGGREGATE) {
				any_other = true;
				continue;
			}
			auto &bag = expr->Cast<BoundAggregateExpression>();
			OuterYanAggregateColumn col;
			col.function_name = bag.function.name;
			if (!bag.children.empty() && bag.children[0] &&
			    bag.children[0]->GetExpressionClass() == ExpressionClass::BOUND_COLUMN_REF) {
				col.binding = bag.children[0]->Cast<BoundColumnRefExpression>().binding;
			}
			info.columns.push_back(std::move(col));

			const auto &name = bag.function.name;
			if (name == "count_star") {
				if (bag.filter || bag.order_bys) {
					// Filtered or ordered counts need their predicate/order semantics
					// carried into every pushed partial aggregate. Keep them on the
					// ordinary aggregate path until that representation is supported.
					any_other = true;
				} else {
					// Both grouped and global COUNT(*) need multiplicity
					// annotations. The SUM path has no count input column and
					// would otherwise deduplicate join inputs without weights.
					any_count_star = true;
				}
			} else if (name == "count") {
				// COUNT(expr) needs non-NULL multiplicity annotations, not the
				// COUNT(*) padding rule. Keep its aggregation above the joins
				// until that separate annotation semantics is implemented.
				any_other = true;
			} else if (name == "min" || name == "max") {
				any_minmax = true;
			} else if (name == "sum") {
				any_sum = true;
			} else {
				any_other = true;
			}
		}

		if (any_other) {
			info.type = OuterYanAggregationType::OTHER;
		} else if (any_minmax && !any_sum && !any_count_star) {
			info.type = OuterYanAggregationType::MINMAX;
		} else if (any_sum && !any_minmax && !any_count_star) {
			info.type = OuterYanAggregationType::SUM;
		} else if (any_count_star && !any_minmax && !any_sum) {
			info.type = OuterYanAggregationType::COUNT_STAR;
		} else {
			info.type = OuterYanAggregationType::OTHER;
		}
	}

	//! Map each recorded aggregate column's `binding.table_index` back to its
	//! OT relation id. Runs once after every RELATION node has been built so
	//! `tree.table_to_relation` is complete. Unresolved entries (e.g.,
	//! count_star with no column, or a column whose table_index sits outside
	//! the skeleton) are left with an empty `relation`.
	void ResolveAggregationRelations() {
		for (auto &col : tree.root_aggregation.columns) {
			if (col.binding.table_index.index == DConstants::INVALID_INDEX) {
				continue;
			}
			auto it = tree.table_to_relation.find(col.binding.table_index.index);
			if (it == tree.table_to_relation.end()) {
				continue;
			}
			col.relation = it->second;
			// Only GROUP BY / SELECT DISTINCT bindings anchor the OJT root --
			// raw aggregate-function arguments (e.g. min/max/sum input columns)
			// do not impose a position constraint on their relation.
			if (col.function_name == "group_by" || col.function_name == "distinct") {
				tree.root_relations.insert(it->second);
			}
		}
	}

	// Keep edge order identical to a left-to-right post-order walk of the
	// logical join tree. Positional consumers such as aggregate pushdown rely
	// on this exact order, including for bushy trees.
	void AssignJoinOrders(OTNode &node) {
		if (node.kind == OTNode::Kind::RELATION) {
			return;
		}
		AssignJoinOrders(*node.children[0]);
		AssignJoinOrders(*node.children[1]);
		node.order = tree.ot_joins_by_order.size() + 1;
		tree.ot_joins_by_order.push_back(&node);
	}

	void SetJoinTwoSides() {
		for (auto *node : tree.ot_joins_by_order) {
			D_ASSERT(node->info);
			auto &info = *node->info;
			if (info.conditions.empty()) {
				throw NotImplementedException(
				    "LogicalPlanToOT: cross product (join with no conditions)");
			}
			unordered_set<idx_t> left_relations;
			unordered_set<idx_t> right_relations;
			CollectRelationIds(*node->children[0], left_relations);
			CollectRelationIds(*node->children[1], right_relations);
			optional_idx anchor_index;
			for (idx_t condition_index = 0; condition_index < info.conditions.size(); condition_index++) {
				auto &candidate = info.conditions[condition_index];
				if (!candidate.IsComparison() ||
				    candidate.GetComparisonType() != ExpressionType::COMPARE_EQUAL) {
					continue;
				}
				auto candidate_left = LookupSingleRelation(candidate.GetLHS(), tree.table_to_relation);
				auto candidate_right = LookupSingleRelation(candidate.GetRHS(), tree.table_to_relation);
				if (!candidate_left || !candidate_right || *candidate_left == *candidate_right) {
					continue;
				}
				const bool aligned = left_relations.count(*candidate_left) != 0 &&
				                     right_relations.count(*candidate_right) != 0;
				const bool reversed = right_relations.count(*candidate_left) != 0 &&
				                      left_relations.count(*candidate_right) != 0;
				if (aligned || reversed) {
					anchor_index = optional_idx(condition_index);
					break;
				}
			}
			if (!anchor_index.IsValid()) {
				throw NotImplementedException(
				    "LogicalPlanToOT: could not find a safe two-relation equality anchor");
			}
			if (anchor_index.GetIndex() != 0) {
				std::swap(info.conditions[0], info.conditions[anchor_index.GetIndex()]);
			}
			auto &cond = info.conditions[0];
			auto left = LookupSingleRelation(cond.GetLHS(), tree.table_to_relation);
			auto right = LookupSingleRelation(cond.GetRHS(), tree.table_to_relation);
			if (!left || !right) {
				throw NotImplementedException(
				    "LogicalPlanToOT: could not resolve both sides of a join condition "
				    "to a single OT base relation");
			}
			info.cond_left_relation_id = *left;
			info.cond_right_relation_id = *right;
		}
	}
};

void OuterYanTree::BuildOT(unique_ptr<LogicalOperator> plan) {
	if (!plan) {
		throw InternalException("OuterYanTree::BuildOT: null plan");
	}
	OTBuilder builder(*plan, *this);
	ot = builder.Build();
	source_plan = std::move(plan);
}

// ============================================================================
// BuildOJT / ConstructOJT
// ============================================================================

//! Shared OJT-assembly body. Reads `ot_relations_by_id` and
//! `ot_joins_by_order` (both populated by `BuildOT` and stable across
//! Simplification / Desimplification join-kind mutations), returns a fresh
//! OJT without persisting it. `BuildOJT` and `ConstructOJT` are thin
//! wrappers that choose where to store the result.
// True iff the base-relation subtree at `base_op` carries a predicate that
// reduces its row set before an SJBuild sitting above it can materialise:
// either a LOGICAL_FILTER wrapper in the original plan, or a relocatable entry
// in `filter_records` that references only `relation_id`. A retained root
// predicate is deliberately not a base predicate.
static bool HasBasePredicates(const LogicalOperator *base_op, idx_t relation_id,
                               const vector<unique_ptr<OuterYanFilterRecord>> &filter_records) {
	// A base subtree may contain an arbitrary Filter/Projection wrapper chain.
	// Inspect every wrapper rather than only the outermost node: Projection ->
	// Filter -> Get is just as filtered as Filter -> Projection -> Get.
	const LogicalOperator *base = base_op;
	while (base && (base->type == LogicalOperatorType::LOGICAL_FILTER ||
	                base->type == LogicalOperatorType::LOGICAL_PROJECTION)) {
		if (base->type == LogicalOperatorType::LOGICAL_FILTER) {
			return true;
		}
		if (base->children.size() != 1 || !base->children[0]) {
			// An unexpected wrapper shape cannot support the "complete build"
			// proof, so conservatively retain the semi-join.
			return true;
		}
		base = base->children[0].get();
	}
	// FILTER_PUSHDOWN runs before OuterYan and folds a unary "col OP const"
	// predicate into LogicalGet::table_filters, deleting the LogicalFilter
	// wrapper — so the predicate is gone from the plan tree but still reduces
	// the relation's row set. Treat it as a base predicate, otherwise a PK-side
	// leaf whose only predicate was pushed into the scan looks "unfiltered" and
	// its (beneficial) reducer is wrongly eliminated. At this point in the
	// pipeline table_filters holds ONLY real query value-predicates (col OP
	// const / IN / LIKE / BETWEEN and their transitive implications): DuckDB
	// does not null-reject join keys into table_filters, and runtime/dynamic
	// join filters are added later by JOIN_FILTER_PUSHDOWN. A table filter on a
	// Get is single-relation by construction, so no relation_id match is needed.
	if (base && base->type == LogicalOperatorType::LOGICAL_GET &&
	    base->Cast<LogicalGet>().table_filters.HasFilters()) {
		return true;
	}
	for (const auto &rec : filter_records) {
		if (rec && rec->filter && !rec->retained_at_original_scope &&
		    rec->referenced_relations.size() == 1 &&
		    *rec->referenced_relations.begin() == relation_id) {
			return true;
		}
	}
	return false;
}

// Post-OJT-build DFS. Assigns bottom_up_eliminated / top_down_eliminated on
// every OJTEdge once the tree is fully assembled. Call on the OJT root with
// top_down_probed_by_parent = false.
//
// OJT edge-kind convention (established by CheckOuterYanJoinFlip in BuildOJTImpl):
//   edge.kind always reads as "parent KIND child", regardless of the original
//   LHS/RHS orientation in the LogicalPlan. LEFT and RIGHT are flipped when
//   necessary so the kind consistently labels the parent's role:
//     INNER  — both sides inner; fires in both bottom-up AND top-down passes.
//     LEFT   — parent is the preserved (outer) side, child is null-extended;
//              fires only in the top-down pass  (R_child ⋉ R_parent).
//     RIGHT  — child is the preserved (outer) side, parent is null-extended;
//              fires only in the bottom-up pass (R_parent ⋉ R_child).
//     OUTER  — both sides preserved (full outer); fires in neither pass.
static void ComputeEliminationFlags(OJTNode &node, bool top_down_probed_by_parent,
                                     const vector<unique_ptr<OuterYanFilterRecord>> &filter_records) {
	// Does any child contribute a bottom-up probe on `node`?
	// Per the convention above, RIGHT or INNER → bottom-up fires:
	//   build = child, probe = node  (R_node ⋉ R_child).
	bool node_has_bottom_up_probe = false;
	for (const auto &edge : node.children) {
		if (edge.kind == JoinType::RIGHT || edge.kind == JoinType::INNER) {
			node_has_bottom_up_probe = true;
			break;
		}
	}
	const bool node_has_predicates =
	    HasBasePredicates(node.base_op, node.relation_id, filter_records);

	for (auto &edge : node.children) {
		if (!edge.child) {
			continue;
		}

		// Bottom-up: R_node ⋉ R_child (build=child, probe=node).
		// Fires when edge.kind ∈ {RIGHT, INNER} — child is preserved or inner,
		// so the bottom-up pass uses child's keys to reduce the parent (node).
		// Redundant iff every parent key is covered by the child and the
		// child's SJBuild sees all its base rows: child is PK-side, a terminal
		// leaf (no probes from below reduce it first), and has no predicates.
		if (edge.kind == JoinType::RIGHT || edge.kind == JoinType::INNER) {
			edge.bottom_up_eliminated =
			    edge.parent_covered_by_child && edge.child->children.empty() &&
			    !HasBasePredicates(edge.child->base_op, edge.child->relation_id, filter_records);
		}

		// Top-down: R_child ⋉ R_node (build=node, probe=child).
		// Fires when edge.kind ∈ {LEFT, INNER} — parent (node) is preserved
		// or inner, so the top-down pass uses the parent's keys to reduce the
		// child. Redundant iff every child key is covered by the parent and
		// node's SJBuild sees all its base rows: node is PK-side, has no
		// predicates, no bottom-up probes from its own children, and no
		// top-down probe from its grandparent.
		if (edge.kind == JoinType::LEFT || edge.kind == JoinType::INNER) {
			edge.top_down_eliminated = edge.child_covered_by_parent && !node_has_predicates &&
			                           !node_has_bottom_up_probe && !top_down_probed_by_parent;
		}

		// A LEFT or INNER outgoing edge top-down-probes the child (node
		// builds, child probes). Pass this down so the child's own
		// top_down_eliminated evaluations can account for it.
		const bool child_top_down_probed =
		    (edge.kind == JoinType::LEFT || edge.kind == JoinType::INNER);
		ComputeEliminationFlags(*edge.child, child_top_down_probed, filter_records);
	}
}

static void CollectRelationNodes(OTNode &node, vector<OTNode *> &out) {
	if (node.kind == OTNode::Kind::RELATION) {
		if (node.relation_id >= out.size()) {
			out.resize(node.relation_id + 1, nullptr);
		}
		out[node.relation_id] = &node;
		return;
	}
	CollectRelationNodes(*node.children[0], out);
	CollectRelationNodes(*node.children[1], out);
}

// True iff `origin`'s join-key column(s) in `conditions` cover a UNIQUE /
// PRIMARY KEY constraint of its base table — i.e. this relation is the PK side
// of THIS join. This is the column-accurate form of the documented
// OJTEdge::child_is_pk contract ("child's join key is unique"). A per-relation
// "the table has *some* unique column" check is insufficient: it
// misfires whenever a table carries a surrogate PK on a column that is not the
// join key — e.g. orders.o_orderkey while the join is on orders.o_custkey — which
// is the norm once real PK-FK schemas are loaded. We pick out this relation's
// own join columns by matching each condition column's table_index to the base
// Get's table_index (orientation-independent: it does not assume LHS/RHS line up
// with cond_left/right_relation_id, which Finalize may have swapped).
static bool JoinSideIsUnique(LogicalOperator *origin, const vector<JoinCondition> &conditions) {
	const LogicalOperator *base = FindBaseOp(origin);
	if (!base || base->type != LogicalOperatorType::LOGICAL_GET) {
		return false;
	}
	auto &get = base->Cast<LogicalGet>();
	auto table_entry = get.GetTable();
	if (!table_entry) {
		return false;
	}
	const auto &column_ids = get.GetColumnIds();
	const idx_t my_table_index = get.table_index.index;

	// Actual *table-column* indices of THIS relation's join-key columns. A join
	// condition column's binding.column_index is a projection index into the
	// Get; column_ids maps it to the underlying table column. (get.names and a
	// UNIQUE constraint's index/columns are keyed by table column, not by
	// projection index — at OuterYan time the Get is already pruned, so the two
	// differ, e.g. proj 0 -> table column o_custkey.)
	vector<idx_t> key_cols;
	key_cols.reserve(conditions.size());
	for (const auto &cond : conditions) {
		if (!cond.IsComparison() || cond.GetComparisonType() != ExpressionType::COMPARE_EQUAL) {
			continue;
		}
		for (const Expression *side : {&cond.GetLHS(), &cond.GetRHS()}) {
			if (side->GetExpressionClass() != ExpressionClass::BOUND_COLUMN_REF) {
				continue;
			}
			const auto &binding = side->Cast<BoundColumnRefExpression>().binding;
			if (binding.table_index.index != my_table_index) {
				continue;
			}
			const auto proj_idx = binding.column_index.GetIndexUnsafe();
			if (proj_idx < column_ids.size()) {
				const auto &column_id = column_ids[proj_idx];
				if (column_id.HasPrimaryIndex() && !column_id.IsVirtualColumn() && !column_id.HasChildren()) {
					key_cols.push_back(column_id.GetPrimaryIndex());
				}
			}
		}
	}
	if (key_cols.empty()) {
		return false;
	}

	// Does the set of join-key columns cover any UNIQUE / PRIMARY KEY constraint?
	// A single-column constraint is encoded either as `index` (inline DDL) or as
	// a one-element `columns` list (ALTER ... ADD PRIMARY KEY); handle both.
	auto key_has_column = [&](idx_t table_col) {
		for (idx_t c : key_cols) {
			if (c == table_col) {
				return true;
			}
		}
		return false;
	};
	auto key_has_name = [&](const string &name) {
		for (idx_t c : key_cols) {
			if (c < get.names.size() && StringUtil::CIEquals(get.names[c], name)) {
				return true;
			}
		}
		return false;
	};
	for (auto &constraint : table_entry->GetConstraints()) {
		if (constraint->type != ConstraintType::UNIQUE) {
			continue;
		}
		auto &unique_constraint = constraint->Cast<UniqueConstraint>();
		if (unique_constraint.index.index != DConstants::INVALID_INDEX) {
			if (key_has_column(unique_constraint.index.index)) {
				return true;
			}
		} else if (!unique_constraint.columns.empty()) {
			// Every constraint column must be one of the join keys.
			bool all_present = true;
			for (auto &constraint_col_name : unique_constraint.columns) {
				if (!key_has_name(constraint_col_name)) {
					all_present = false;
					break;
				}
			}
			if (all_present) {
				return true;
			}
		}
	}
	return false;
}

struct JoinColumnPair {
	idx_t probe_logical;
	idx_t probe_physical;
	idx_t build_physical;
};

static const LogicalGet *GetBaseTableGet(const LogicalOperator *origin) {
	const auto *base = FindBaseOp(origin);
	if (!base || base->type != LogicalOperatorType::LOGICAL_GET) {
		return nullptr;
	}
	return &base->Cast<LogicalGet>();
}

static bool TryGetBaseColumn(const LogicalGet &get, const BoundColumnRefExpression &column_ref,
                             idx_t &logical_index) {
	const auto &binding = column_ref.binding;
	if (binding.table_index != get.table_index) {
		return false;
	}
	const auto projection_index = binding.column_index.GetIndexUnsafe();
	const auto &column_ids = get.GetColumnIds();
	if (projection_index >= column_ids.size()) {
		return false;
	}
	const auto &column_id = column_ids[projection_index];
	if (!column_id.HasPrimaryIndex() || column_id.IsVirtualColumn() || column_id.HasChildren()) {
		return false;
	}
	logical_index = column_id.GetPrimaryIndex();
	return true;
}

static bool ExtractJoinColumnPairs(const LogicalGet &probe_get, const LogicalGet &build_get,
                                   const vector<JoinCondition> &conditions, vector<JoinColumnPair> &result) {
	auto probe_table = probe_get.GetTable();
	auto build_table = build_get.GetTable();
	if (!probe_table || !build_table || conditions.empty()) {
		return false;
	}

	result.clear();
	result.reserve(conditions.size());
	for (const auto &condition : conditions) {
		if (!condition.IsComparison() || condition.GetComparisonType() != ExpressionType::COMPARE_EQUAL ||
		    condition.GetLHS().GetExpressionClass() != ExpressionClass::BOUND_COLUMN_REF ||
		    condition.GetRHS().GetExpressionClass() != ExpressionClass::BOUND_COLUMN_REF) {
			return false;
		}

		const auto &lhs = condition.GetLHS().Cast<BoundColumnRefExpression>();
		const auto &rhs = condition.GetRHS().Cast<BoundColumnRefExpression>();
		const BoundColumnRefExpression *probe_ref = nullptr;
		const BoundColumnRefExpression *build_ref = nullptr;
		if (lhs.binding.table_index == probe_get.table_index && rhs.binding.table_index == build_get.table_index) {
			probe_ref = &lhs;
			build_ref = &rhs;
		} else if (rhs.binding.table_index == probe_get.table_index &&
		           lhs.binding.table_index == build_get.table_index) {
			probe_ref = &rhs;
			build_ref = &lhs;
		} else {
			return false;
		}

		idx_t probe_logical;
		idx_t build_logical;
		if (!TryGetBaseColumn(probe_get, *probe_ref, probe_logical) ||
		    !TryGetBaseColumn(build_get, *build_ref, build_logical)) {
			return false;
		}
		const auto &probe_columns = probe_table->GetColumns();
		const auto &build_columns = build_table->GetColumns();
		if (probe_logical >= probe_columns.LogicalColumnCount() ||
		    build_logical >= build_columns.LogicalColumnCount()) {
			return false;
		}
		const auto &probe_column = probe_columns.GetColumn(LogicalIndex(probe_logical));
		const auto &build_column = build_columns.GetColumn(LogicalIndex(build_logical));
		if (probe_column.Generated() || build_column.Generated()) {
			return false;
		}
		result.push_back({probe_logical, probe_columns.LogicalToPhysical(LogicalIndex(probe_logical)).index,
		                  build_columns.LogicalToPhysical(LogicalIndex(build_logical)).index});
	}
	return true;
}

static bool IsDeclaredNotNull(const TableCatalogEntry &table, idx_t logical_index) {
	for (const auto &constraint : table.GetConstraints()) {
		if (constraint->type != ConstraintType::NOT_NULL) {
			continue;
		}
		if (constraint->Cast<NotNullConstraint>().index.index == logical_index) {
			return true;
		}
	}
	return false;
}

// True iff every row read from `probe_origin` has exactly one guaranteed match
// in `build_origin` for this join. Uniqueness alone proves "at most one"; the
// exact enforced FK proves existence for non-NULL keys, and explicit NOT NULL
// constraints close the SQL-FK NULL exemption.
static bool JoinSideHasTotalCoverage(LogicalOperator *probe_origin, LogicalOperator *build_origin,
                                     const vector<JoinCondition> &conditions, bool build_is_unique) {
	const auto *probe_get = GetBaseTableGet(probe_origin);
	const auto *build_get = GetBaseTableGet(build_origin);
	if (!probe_get || !build_get) {
		return false;
	}
	auto probe_table = probe_get->GetTable();
	auto build_table = build_get->GetTable();
	if (!probe_table || !build_table || !probe_table->IsDuckTable() || !build_table->IsDuckTable()) {
		return false;
	}

	// Retain the independent build-key uniqueness proof. Foreign keys can target
	// either PRIMARY KEY or UNIQUE constraints in DuckDB.
	if (!build_is_unique) {
		return false;
	}

	vector<JoinColumnPair> join_pairs;
	if (!ExtractJoinColumnPairs(*probe_get, *build_get, conditions, join_pairs)) {
		return false;
	}
	vector<pair<idx_t, idx_t>> actual_pairs;
	actual_pairs.reserve(join_pairs.size());
	for (const auto &join_pair : join_pairs) {
		if (!IsDeclaredNotNull(*probe_table, join_pair.probe_logical)) {
			return false;
		}
		actual_pairs.emplace_back(join_pair.probe_physical, join_pair.build_physical);
	}
	std::sort(actual_pairs.begin(), actual_pairs.end());
	if (std::adjacent_find(actual_pairs.begin(), actual_pairs.end()) != actual_pairs.end()) {
		return false;
	}

	const bool self_reference = probe_table.get() == build_table.get();
	if (&probe_table->ParentCatalog() != &build_table->ParentCatalog() ||
	    &probe_table->ParentSchema() != &build_table->ParentSchema()) {
		return false;
	}
	for (const auto &constraint : probe_table->GetConstraints()) {
		if (constraint->type != ConstraintType::FOREIGN_KEY) {
			continue;
		}
		const auto &foreign_key = constraint->Cast<ForeignKeyConstraint>();
		if (self_reference) {
			if (foreign_key.info.type != ForeignKeyType::FK_TYPE_SELF_REFERENCE_TABLE) {
				continue;
			}
		} else if (foreign_key.info.type != ForeignKeyType::FK_TYPE_FOREIGN_KEY_TABLE) {
			continue;
		}
		if (!StringUtil::CIEquals(foreign_key.info.table, build_table->name)) {
			continue;
		}
		if (!foreign_key.info.schema.empty() &&
		    !StringUtil::CIEquals(foreign_key.info.schema, build_table->ParentSchema().name)) {
			continue;
		}
		const auto key_count = foreign_key.info.fk_keys.size();
		if (key_count != foreign_key.info.pk_keys.size() || key_count != foreign_key.fk_columns.size() ||
		    key_count != foreign_key.pk_columns.size() || key_count != actual_pairs.size()) {
			continue;
		}

		vector<pair<idx_t, idx_t>> declared_pairs;
		declared_pairs.reserve(key_count);
		for (idx_t key_idx = 0; key_idx < key_count; key_idx++) {
			declared_pairs.emplace_back(foreign_key.info.fk_keys[key_idx].index,
			                            foreign_key.info.pk_keys[key_idx].index);
		}
		std::sort(declared_pairs.begin(), declared_pairs.end());
		if (declared_pairs == actual_pairs) {
			return true;
		}
	}
	return false;
}

unique_ptr<OrderedJoinTree> OuterYanTree::BuildOJTImpl() {
	if (!HasOT()) {
		throw InternalException("OuterYanTree::BuildOJTImpl: ot is null");
	}

	// Build a fresh relation-node index from the live OT tree.
	// ot_relations_by_id may be stale after RebuildOT replaces the root with
	// new OTNode allocations; walking the current root is always correct.
	vector<OTNode *> ot_relations;
	CollectRelationNodes(ot->Root(), ot_relations);
	const auto &ot_joins = ot_joins_by_order;

	if (ot_relations.empty()) {
		throw NotImplementedException("OuterYanTree::BuildOJTImpl: OT has no base relations");
	}
	for (idx_t r = 0; r < ot_relations.size(); r++) {
		if (!ot_relations[r]) {
			throw InternalException(
			    "OuterYanTree::BuildOJTImpl: missing OT relation for relation_id %llu", r);
		}
	}

	vector<unique_ptr<OJTNode>> nodes_by_id;
	nodes_by_id.reserve(ot_relations.size());
	for (idx_t r = 0; r < ot_relations.size(); r++) {
		auto ojt_node = make_uniq<OJTNode>();
		ojt_node->relation_id = r;
		ojt_node->base_op = ot_relations[r]->origin;
		nodes_by_id.push_back(std::move(ojt_node));
	}

	if (ot_joins.empty()) {
		if (nodes_by_id.size() != 1) {
			throw InternalException(
			    "OuterYanTree::BuildOJTImpl: %llu relations with 0 joins (disconnected OT)",
			    nodes_by_id.size());
		}
		return make_uniq<OrderedJoinTree>(std::move(nodes_by_id[0]));
	}

	vector<OJTNode *> node_pointer(nodes_by_id.size(), nullptr);
	for (idx_t i = 0; i < nodes_by_id.size(); i++) {
		node_pointer[i] = nodes_by_id[i].get();
	}

	unordered_set<idx_t> attached;
	idx_t ojt_root_id = DConstants::INVALID_INDEX;
	const idx_t n_joins = ot_joins.size();

	for (auto *jn : ot_joins) {
		if (!jn || !jn->info) {
			throw InternalException("OuterYanTree::BuildOJTImpl: OT JOIN node has null info");
		}
	}

	// Bug-C crash fix. The OJT is grown by BFS over the join-edge graph from a
	// chosen root, NOT by walking joins in reverse `order`. The order-walk assumed
	// a left/right-deep SPINE (each next join shares an endpoint with what is
	// already attached) and threw "connectivity invariant violated" on the bushy
	// orders the DP can materialise. BFS attaches a join the instant exactly ONE
	// endpoint is already in the tree (parent), the other being the child — true
	// for a tree of edges at ANY shape, so no "neither endpoint attached" state
	// arises. The root choice ("extends" heuristic on the top join) and the edge
	// construction (CheckOuterYanJoinFlip, OTJoin deep-copy, PK/FK) are unchanged;
	// edges connect ONLY the two real condition-referenced relations. NOTE: this
	// fixes the CRASH only; a separate, upstream Simplify/Desimplify defect drops
	// RIGHT/FULL OUTER NULL-padded rows (present on spines too — see KNOWN_BUGS.md),
	// independent of this assembly.

	// Root: side of the top join that does NOT continue into the next-deepest
	// join (identical to the previous step-0 heuristic).
	{
		auto &root_info = *ot_joins[n_joins - 1]->info;
		idx_t left_rel = root_info.cond_left_relation_id;
		idx_t right_rel = root_info.cond_right_relation_id;
		bool left_extends = false;
		bool right_extends = false;
		if (n_joins >= 2) {
			auto &next_info = *ot_joins[n_joins - 2]->info;
			idx_t nl = next_info.cond_left_relation_id;
			idx_t nr = next_info.cond_right_relation_id;
			left_extends = (left_rel == nl || left_rel == nr);
			right_extends = (right_rel == nl || right_rel == nr);
		}
		ojt_root_id = (left_extends && !right_extends) ? right_rel : left_rel;
	}

	// Index joins by the relations their condition references.
	unordered_map<idx_t, vector<OTNode *>> joins_by_relation;
	for (auto *jn : ot_joins) {
		joins_by_relation[jn->info->cond_left_relation_id].push_back(jn);
		joins_by_relation[jn->info->cond_right_relation_id].push_back(jn);
	}

	auto attach_edge = [&](idx_t parent_id, idx_t child_id, OTNode *ot_join) {
		auto &ot_info = *ot_join->info;
		idx_t left_rel = ot_info.cond_left_relation_id;
		idx_t right_rel = ot_info.cond_right_relation_id;
		auto *left_origin = ot_relations[left_rel]->origin;
		auto *right_origin = ot_relations[right_rel]->origin;
		// PK side is judged on the JOIN COLUMN, not the relation: a side is the
		// PK side iff its join-key column(s) cover a unique constraint. A
		// per-relation "table has some unique column" check would misfire whenever
		// a table carries a surrogate PK on a non-join column (e.g. orders.o_orderkey
		// while the join is on o_custkey) — the common case once real PK-FK schemas
		// are loaded. See JoinSideIsUnique.
		bool left_pk = JoinSideIsUnique(left_origin, ot_info.conditions);
		bool right_pk = JoinSideIsUnique(right_origin, ot_info.conditions);
		bool left_covered_by_right =
		    JoinSideHasTotalCoverage(left_origin, right_origin, ot_info.conditions, right_pk);
		bool right_covered_by_left =
		    JoinSideHasTotalCoverage(right_origin, left_origin, ot_info.conditions, left_pk);
		bool child_pk = (child_id == left_rel) ? left_pk : right_pk;
		bool parent_is_left = (parent_id == left_rel);

		OJTEdge edge;
		edge.kind = CheckOuterYanJoinFlip(ot_info.join_kind, parent_is_left);
		edge.original_kind = CheckOuterYanJoinFlip(ot_info.original_join_kind, parent_is_left);
		edge.order = ot_join->order;
		edge.parent_relation_id = parent_id;
		auto edge_info = make_uniq<OTJoin>();
		edge_info->join_kind = ot_info.join_kind;
		edge_info->original_join_kind = ot_info.original_join_kind;
		edge_info->cond_left_relation_id = ot_info.cond_left_relation_id;
		edge_info->cond_right_relation_id = ot_info.cond_right_relation_id;
		edge_info->distinct_count = ot_info.distinct_count;
		edge_info->conditions.reserve(ot_info.conditions.size());
		for (const auto &cond : ot_info.conditions) {
			edge_info->conditions.push_back(cond.Copy());
		}
		edge.info = std::move(edge_info);
		edge.has_pk_fk_constraint = left_pk || right_pk;
		edge.child_is_pk = child_pk;
		edge.parent_covered_by_child = parent_is_left ? left_covered_by_right : right_covered_by_left;
		edge.child_covered_by_parent = parent_is_left ? right_covered_by_left : left_covered_by_right;
		edge.child = std::move(nodes_by_id[child_id]);
		node_pointer[parent_id]->children.push_back(std::move(edge));
	};

	attached.insert(ojt_root_id);
	vector<idx_t> frontier;
	frontier.push_back(ojt_root_id);
	unordered_set<const OTNode *> processed_joins;
	for (idx_t f = 0; f < frontier.size(); f++) {
		const idx_t parent_rel = frontier[f];
		auto it = joins_by_relation.find(parent_rel);
		if (it == joins_by_relation.end()) {
			continue;
		}
		for (auto *jn : it->second) {
			if (processed_joins.count(jn)) {
				continue;
			}
			idx_t cl = jn->info->cond_left_relation_id;
			idx_t cr = jn->info->cond_right_relation_id;
			idx_t child_rel = (cl == parent_rel) ? cr : cl;
			if (attached.count(child_rel)) {
				throw NotImplementedException(
				    "OuterYanTree::BuildOJTImpl: cyclic join graph (both endpoints already in OJT)");
			}
			processed_joins.insert(jn);
			attach_edge(parent_rel, child_rel, jn);
			attached.insert(child_rel);
			frontier.push_back(child_rel);
		}
	}

	if (processed_joins.size() != n_joins) {
		throw InternalException(
		    "OuterYanTree::BuildOJTImpl: %llu of %llu joins unreached from the root (disconnected OT)",
		    static_cast<unsigned long long>(processed_joins.size()),
		    static_cast<unsigned long long>(n_joins));
	}
	if (ojt_root_id == DConstants::INVALID_INDEX) {
		throw InternalException("OuterYanTree::BuildOJTImpl: OJT root not assigned");
	}
	// Elimination flags require the fully-assembled tree; compute after all
	// edges are attached so terminal-leaf checks reflect the final structure.
	ComputeEliminationFlags(*node_pointer[ojt_root_id], /*top_down_probed_by_parent=*/false,
	                        filter_records);
	return make_uniq<OrderedJoinTree>(std::move(nodes_by_id[ojt_root_id]));
}

void OuterYanTree::BuildOJT() {
	ojt = BuildOJTImpl();
}

unique_ptr<OrderedJoinTree> OuterYanTree::ConstructOJT() {
	return BuildOJTImpl();
}

// ============================================================================
// OJTToLogicalPlan
// ============================================================================

//! Flatten the OJT into a vector of edge pointers ordered by post-order
//! traversal; sorted later by `OJTEdge::order` so OJTToLogicalPlan emits
//! deepest joins first.
void OuterYanTree::CollectOJTInfo(OJTNode &node, vector<OJTNode *> &nodes_by_rel,
                                  vector<OJTEdge *> &edges) {
	if (node.relation_id >= nodes_by_rel.size()) {
		nodes_by_rel.resize(node.relation_id + 1, nullptr);
	}
	nodes_by_rel[node.relation_id] = &node;
	for (auto &edge : node.children) {
		if (!edge.child) {
			throw InternalException("OJTToLogicalPlan: edge has no child");
		}
		if (!edge.info) {
			throw InternalException("OJTToLogicalPlan: edge has no OTJoin info");
		}
		edges.push_back(&edge);
		CollectOJTInfo(*edge.child, nodes_by_rel, edges);
	}
}

void OuterYanTree::PushFiltersAboveLeaf(unique_ptr<LogicalOperator> &subplan,
                                        vector<unique_ptr<Expression>> filters) {
	if (filters.empty()) {
		return;
	}
	auto new_filter = make_uniq<LogicalFilter>();
	new_filter->expressions = std::move(filters);
	if (!subplan || subplan->children.empty()) {
		new_filter->children.push_back(std::move(subplan));
		subplan = std::move(new_filter);
		return;
	}
	LogicalOperator *cur = subplan.get();
	while (!cur->children.empty() && cur->children[0] && !cur->children[0]->children.empty()) {
		cur = cur->children[0].get();
	}
	if (cur->children.empty() || !cur->children[0]) {
		throw InternalException(
		    "OJTToLogicalPlan: base subplan has no leaf to insert filter above");
	}
	auto leaf = std::move(cur->children[0]);
	new_filter->children.push_back(std::move(leaf));
	cur->children[0] = std::move(new_filter);
}

void OuterYanTree::TryPushFilter(unique_ptr<LogicalOperator> &subplan, unique_ptr<Expression> expr) {
	if (subplan->type == LogicalOperatorType::LOGICAL_FILTER) {
		subplan->Cast<LogicalFilter>().expressions.push_back(std::move(expr));
		return;
	}
	auto wrap = make_uniq<LogicalFilter>();
	wrap->expressions.push_back(std::move(expr));
	wrap->children.push_back(std::move(subplan));
	subplan = std::move(wrap);
}

unique_ptr<LogicalOperator> OuterYanTree::BuildJoinFromEdge(const OJTEdge &edge,
                                                            const JoinRelationSet &parent_set,
                                                            unique_ptr<LogicalOperator> parent_plan,
                                                            unique_ptr<LogicalOperator> child_plan) {
	D_ASSERT(edge.info);
	const auto &info = *edge.info;

	// Orientation: conditions[i].left is bound to info.cond_left_relation_id.
	// If the parent subtree contains that relation, the conditions already
	// align (parent on left). Otherwise swap each condition.
	bool parent_contains_lhs = false;
	for (idx_t i = 0; i < parent_set.count; i++) {
		if (parent_set.relations[i].index == info.cond_left_relation_id) {
			parent_contains_lhs = true;
			break;
		}
	}

	auto new_join = make_uniq<LogicalComparisonJoin>(edge.kind);
	new_join->conditions.reserve(info.conditions.size());
	for (const auto &cond : info.conditions) {
		JoinCondition copy = cond.Copy();
		if (!parent_contains_lhs) {
			copy.Swap();
		}
		new_join->conditions.push_back(std::move(copy));
	}
	new_join->children.push_back(std::move(parent_plan));
	new_join->children.push_back(std::move(child_plan));
	new_join->ResolveOperatorTypes();
	return std::move(new_join);
}

unique_ptr<LogicalOperator> OuterYanTree::OJTToLogicalPlan(ClientContext &context) {
	if (!ojt) {
		throw InternalException("OuterYanTree::OJTToLogicalPlan: ojt is null");
	}
	auto &ojt_ref = *ojt;

	vector<OJTNode *> nodes_by_rel;
	vector<OJTEdge *> edges;
	CollectOJTInfo(ojt_ref.Root(), nodes_by_rel, edges);
	const idx_t n_rels = nodes_by_rel.size();
	if (n_rels == 0) {
		throw InternalException("OuterYanTree::OJTToLogicalPlan: OJT has no relations");
	}

	JoinRelationSetManager set_manager;
	reference_map_t<JoinRelationSet, unique_ptr<LogicalOperator>> subplan_memo;
	vector<reference<JoinRelationSet>> current_set_by_rel;
	current_set_by_rel.reserve(n_rels);
	vector<bool> filter_records_status(filter_records.size(), false);

	for (idx_t r = 0; r < n_rels; r++) {
		auto *node = nodes_by_rel[r];
		if (!node || !node->base_op) {
			throw InternalException("OuterYanTree::OJTToLogicalPlan: missing OJTNode or base_op");
		}
		auto &singleton = set_manager.GetJoinRelation(RelationIndex(r));
		auto subplan = node->base_op->Copy(context);
		if (!subplan) {
			throw InternalException("OuterYanTree::OJTToLogicalPlan: base_op->Copy returned null");
		}
		if (!node->filters.empty()) {
			PushFiltersAboveLeaf(subplan, std::move(node->filters));
		}
		for (idx_t i = 0; i < filter_records.size(); i++) {
			if (filter_records_status[i]) {
				continue;
			}
			auto &rec = filter_records[i];
			if (!rec || !rec->filter || rec->retained_at_original_scope) {
				continue;
			}
			if (rec->referenced_relations.size() == 1 &&
			    *rec->referenced_relations.begin() == r) {
				TryPushFilter(subplan, std::move(rec->filter));
				filter_records_status[i] = true;
			}
		}
		subplan_memo.emplace(singleton, std::move(subplan));
		current_set_by_rel.emplace_back(singleton);
	}

	std::sort(edges.begin(), edges.end(),
	          [](const OJTEdge *a, const OJTEdge *b) { return a->order < b->order; });

	for (auto *e : edges) {
		auto &parent_set = current_set_by_rel[e->parent_relation_id].get();
		auto &child_set = current_set_by_rel[e->child->relation_id].get();
		if (&parent_set == &child_set) {
			throw InternalException(
			    "OuterYanTree::OJTToLogicalPlan: edge endpoints already in the same group "
			    "(cyclic OJT)");
		}

		auto parent_it = subplan_memo.find(parent_set);
		auto child_it = subplan_memo.find(child_set);
		if (parent_it == subplan_memo.end() || child_it == subplan_memo.end()) {
			throw InternalException(
			    "OuterYanTree::OJTToLogicalPlan: subplan_memo missing entry for edge endpoint");
		}
		auto parent_plan = std::move(parent_it->second);
		auto child_plan = std::move(child_it->second);
		subplan_memo.erase(parent_it);
		subplan_memo.erase(child_it);

		auto new_join = BuildJoinFromEdge(*e, parent_set, std::move(parent_plan), std::move(child_plan));
		auto &merged = set_manager.Union(parent_set, child_set);

		for (idx_t i = 0; i < parent_set.count; i++) {
			current_set_by_rel[parent_set.relations[i].index] = merged;
		}
		for (idx_t i = 0; i < child_set.count; i++) {
			current_set_by_rel[child_set.relations[i].index] = merged;
		}
		auto memo_it = subplan_memo.emplace(merged, std::move(new_join)).first;
		for (idx_t i = 0; i < filter_records.size(); i++) {
			if (filter_records_status[i]) {
				continue;
			}
			auto &rec = filter_records[i];
			if (!rec || !rec->filter || rec->retained_at_original_scope) {
				continue;
			}
			bool covered = true;
			for (auto rel : rec->referenced_relations) {
				if (&current_set_by_rel[rel].get() != &merged) {
					covered = false;
					break;
				}
			}
			if (covered) {
				TryPushFilter(memo_it->second, std::move(rec->filter));
				filter_records_status[i] = true;
			}
		}
	}

	if (subplan_memo.size() != 1) {
		throw InternalException(
		    "OuterYanTree::OJTToLogicalPlan: relations remain in disjoint groups after assembly");
	}
	auto plan = std::move(subplan_memo.begin()->second);
	if (!plan) {
		throw InternalException("OuterYanTree::OJTToLogicalPlan: final memo entry is null");
	}

	for (idx_t i = 0; i < filter_records.size(); i++) {
		if (filter_records_status[i]) {
			continue;
		}
		auto &rec = filter_records[i];
		if (!rec || !rec->filter || rec->retained_at_original_scope) {
			continue;
		}
		TryPushFilter(plan, std::move(rec->filter));
		filter_records_status[i] = true;
	}

	ojt.reset();
	// Re-attach the peeled cap chain stripped during BuildOT: splice the
	// rebuilt skeleton into the deepest cap's child slot so EVERY cap above it
	// — a root aggregate (COUNT/SUM/GROUP BY), a DISTINCT, the output
	// projection — survives the roundtrip. The cap chain rode along intact on
	// `source_plan`; only the skeleton-parent's child pointer is rewritten.
	// Root filters remain in this cap chain. Their analysis copies in
	// `filter_records` are never emitted into the rebuilt skeleton.
	if (root_skeleton_parent) {
		root_skeleton_parent->children[0] = std::move(plan);
		source_plan->ResolveOperatorTypes();
		return std::move(source_plan);
	}
	source_plan.reset();
	return plan;
}

unique_ptr<LogicalOperator> OuterYanTree::OTToLogicalPlanPreservingShape(ClientContext &context) {
	if (!ot || !source_plan) {
		throw InternalException("OuterYanTree::OTToLogicalPlanPreservingShape: tree is not built");
	}

	vector<bool> filter_records_status(filter_records.size(), false);
	std::function<unique_ptr<LogicalOperator>(const OTNode &)> lower = [&](const OTNode &node) {
		unique_ptr<LogicalOperator> result;
		if (node.kind == OTNode::Kind::RELATION) {
			if (!node.origin) {
				throw InternalException(
				    "OuterYanTree::OTToLogicalPlanPreservingShape: relation has no source operator");
			}
			result = node.origin->Copy(context);
			if (!result) {
				throw InternalException(
				    "OuterYanTree::OTToLogicalPlanPreservingShape: source operator copy failed");
			}
			for (idx_t i = 0; i < filter_records.size(); i++) {
				if (filter_records_status[i]) {
					continue;
				}
				auto &record = filter_records[i];
				if (!record || !record->filter || record->retained_at_original_scope) {
					continue;
				}
				const bool at_target_scope =
				    record->requires_original_scope
				        ? record->evaluation_relations.size() == 1 &&
				              record->evaluation_relations.count(node.relation_id) != 0
				        : record->referenced_relations.size() == 1 &&
				              *record->referenced_relations.begin() == node.relation_id;
				if (!at_target_scope) {
					continue;
				}
				TryPushFilter(result, std::move(record->filter));
				filter_records_status[i] = true;
			}
			return result;
		}

		if (!node.info || !node.children[0] || !node.children[1]) {
			throw InternalException(
			    "OuterYanTree::OTToLogicalPlanPreservingShape: malformed JOIN node");
		}
		auto left = lower(*node.children[0]);
		auto right = lower(*node.children[1]);
		auto join = make_uniq<LogicalComparisonJoin>(node.info->join_kind);
		join->conditions.reserve(node.info->conditions.size());
		const bool condition_aligned =
		    node.children[0]->subtree_relations.count(node.info->cond_left_relation_id) != 0 &&
		    node.children[1]->subtree_relations.count(node.info->cond_right_relation_id) != 0;
		const bool condition_reversed =
		    node.children[1]->subtree_relations.count(node.info->cond_left_relation_id) != 0 &&
		    node.children[0]->subtree_relations.count(node.info->cond_right_relation_id) != 0;
		if (!condition_aligned && !condition_reversed) {
			throw InternalException(
			    "OuterYanTree::OTToLogicalPlanPreservingShape: join condition does not span its children");
		}
		for (const auto &condition : node.info->conditions) {
			auto copy = condition.Copy();
			if (condition_reversed && copy.IsComparison()) {
				copy.Swap();
			}
			join->conditions.push_back(std::move(copy));
		}
		join->children.push_back(std::move(left));
		join->children.push_back(std::move(right));
		join->ResolveOperatorTypes();
		result = std::move(join);

		for (idx_t i = 0; i < filter_records.size(); i++) {
			if (filter_records_status[i]) {
				continue;
			}
			auto &record = filter_records[i];
			if (!record || !record->filter || record->retained_at_original_scope) {
				continue;
			}
			bool covered = record->requires_original_scope
			                   ? node.subtree_relations == record->evaluation_relations
			                   : true;
			if (!record->requires_original_scope) {
				for (auto relation_id : record->referenced_relations) {
					if (node.subtree_relations.count(relation_id) == 0) {
						covered = false;
						break;
					}
				}
			}
			if (covered) {
				TryPushFilter(result, std::move(record->filter));
				filter_records_status[i] = true;
			}
		}
		return result;
	};

	auto result = lower(ot->Root());
	for (idx_t i = 0; i < filter_records.size(); i++) {
		if (filter_records_status[i]) {
			continue;
		}
		auto &record = filter_records[i];
		if (!record || !record->filter || record->retained_at_original_scope) {
			continue;
		}
		if (record->requires_original_scope) {
			throw InternalException(
			    "PGPlan lowering could not restore a sensitive filter at its validated input scope");
		}
		TryPushFilter(result, std::move(record->filter));
		filter_records_status[i] = true;
	}

	ojt.reset();
	if (root_skeleton_parent) {
		root_skeleton_parent->children[0] = std::move(result);
		source_plan->ResolveOperatorTypes();
		return std::move(source_plan);
	}
	source_plan.reset();
	return result;
}

} // namespace duckdb
