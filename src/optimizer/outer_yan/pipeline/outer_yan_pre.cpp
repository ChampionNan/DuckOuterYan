#include "duckdb/optimizer/outer_yan/pipeline/outer_yan_pre.hpp"

#include "duckdb/common/exception.hpp"
#include "duckdb/optimizer/outer_yan/common/outer_yan_trace.hpp"
#include "duckdb/planner/expression/bound_columnref_expression.hpp"
#include "duckdb/planner/operator/logical_comparison_join.hpp"
#include "duckdb/planner/operator/logical_get.hpp"

#include <chrono>

namespace duckdb {

// ============================================================================
// Trace helpers — OuterYanPre (only invoked when DUCKDB_OYTRACE is set)
// ============================================================================

static string OYRelName(const OuterYanTree &tree, RelationId rel_id) {
	if (rel_id >= tree.ot_relations_by_id.size() || !tree.ot_relations_by_id[rel_id]) {
		return "<R" + to_string(rel_id) + "?>";
	}
	const auto *base = FindBaseOp(tree.ot_relations_by_id[rel_id]->origin);
	if (!base || base->type != LogicalOperatorType::LOGICAL_GET) {
		return "R" + to_string(rel_id);
	}
	auto tbl = base->Cast<LogicalGet>().GetTable();
	return tbl ? tbl->name : ("R" + to_string(rel_id));
}

static string PrintSemiPairs(const OuterYanTree &tree) {
	std::ostringstream os;
	auto lbl = [&](RelationId r) { return OYRelName(tree, r); };
	os << "  bottom_up [parent := parent ⋉ child] (" << tree.bottom_up_pairs.size() << "):\n";
	for (const auto &p : tree.bottom_up_pairs) {
		os << "    build=" << lbl(p.build) << "  probe=" << lbl(p.probe);
		for (const auto &k : p.keys) {
			os << "  [" << k.build_binding.ToString() << " ⋉ " << k.probe_binding.ToString() << "]";
		}
		os << "\n";
	}
	os << "  top_down  [child  := child  ⋉ parent] (" << tree.top_down_pairs.size() << "):\n";
	for (const auto &p : tree.top_down_pairs) {
		os << "    build=" << lbl(p.build) << "  probe=" << lbl(p.probe);
		for (const auto &k : p.keys) {
			os << "  [" << k.build_binding.ToString() << " ⋉ " << k.probe_binding.ToString() << "]";
		}
		os << "\n";
	}
	return os.str();
}

void OuterYanPre::Optimize(unique_ptr<LogicalOperator> plan, OuterYanTree &tree) {
	// Applicability is the caller's responsibility (see `optimizer.cpp`: the
	// dispatch site calls `OuterYanTree::CheckApplicability` and only enters
	// `Optimize` when the gate passes).
	//
	// Pipeline (steps mirror the header comment):
	//   2. LogicalPlanToOT      -- lifts the plan into `tree.ot`, captures
	//                              residual filters, and classifies the root
	//                              aggregate into `tree.root_aggregation`.
	//   3. Simplify             -- outer -> inner where null-rejection permits.
	//   4. RecordSemiJoinPairs  -- transient OJT built off the post-
	//                              simplification OT; `BottomUpPass` /
	//                              `TopDownPass` walk it to populate
	//                              `tree.bottom_up_pairs` and
	//                              `tree.top_down_pairs`. The local OJT goes
	//                              out of scope at the end of this block, so
	//                              subsequent Desimplification mutations
	//                              never reach the recorded pairs. Prune the
	//                              outer-over-inner pattern's optional pairs
	//                              before DP costing and SJ insertion.
	//   5. Desimplify           -- six Galindo-Legaria / Rosenthal associativity
	//                              rules to fixpoint; mutates only
	//                              `OTNode::join_kind`.
	//   6. AllPairsSatisfy      -- post-condition: every (P, D) pair in an OK
	//                              cell.
	using Clock = std::chrono::steady_clock;
	auto phase_start = Clock::now();
	tree.BuildOT(std::move(plan));
	tree.phase_timings.build_ot +=
	    std::chrono::duration<double>(Clock::now() - phase_start).count();
	if (OuterYanTrace::Enabled()) {
		OuterYanTrace::Stage("after BuildOT (OT rendered as OJT)", tree.ConstructOJT()->PrintAsTree(true));
	}

	phase_start = Clock::now();
	Simplify(tree);
	tree.phase_timings.simplification +=
	    std::chrono::duration<double>(Clock::now() - phase_start).count();
	if (OuterYanTrace::Enabled()) {
		OuterYanTrace::Stage("after Simplify (" + to_string(tree.stage_stats.simplify_collapses) +
		                         " collapse(s); OT rendered as OJT)",
		                     tree.ConstructOJT()->PrintAsTree(true));
	}

	phase_start = Clock::now();
	{
		auto post_simp_ojt = tree.ConstructOJT();
		BottomUpPass(tree, post_simp_ojt->Root());
		TopDownPass(tree, post_simp_ojt->Root());
	}
	PruneThreeRelationOuterInnerPairs(tree);
	tree.phase_timings.semijoin_pair_planning +=
	    std::chrono::duration<double>(Clock::now() - phase_start).count();
	if (OuterYanTrace::Enabled()) {
		OuterYanTrace::Stage("semi-join pairs (bottom-up + top-down)", PrintSemiPairs(tree));
	}

	phase_start = Clock::now();
	Desimplify(tree);
	tree.phase_timings.desimplification +=
	    std::chrono::duration<double>(Clock::now() - phase_start).count();
	if (OuterYanTrace::Enabled()) {
		OuterYanTrace::Stage("after Desimplify (" + to_string(tree.stage_stats.desimplify_changes) +
		                         " kind rewrite(s); OT rendered as OJT)",
		                     tree.ConstructOJT()->PrintAsTree(true));
	}

	if (!desimplification.AllPairsSatisfy(tree)) {
		throw InternalException(
		    "OuterYanPre::Optimize: desimplification did not reach a fully "
		    "associative state (AllPairsSatisfy returned false after fixpoint)");
	}
}

ApplicabilityResult OuterYanPre::ApplicabilityCheck(LogicalOperator &plan) {
	return OuterYanApplicability::Check(plan);
}

void OuterYanPre::Simplify(OuterYanTree &tree) {
	simplification.Apply(tree);
}

void OuterYanPre::Desimplify(OuterYanTree &tree) {
	desimplification.Apply(tree);
}

// ============================================================================
// SemiPair recording
// ============================================================================

void OuterYanPre::BottomUpPass(OuterYanTree &tree, OJTNode &node) {
	// Post-order: recurse into children first so that pairs are appended in
	// bottom-up order (deepest edge fires first).
	for (auto &edge : node.children) {
		BottomUpPass(tree, *edge.child);
		// Phase 1 fires on R_p RIGHT R_i (child preserved) or R_p INNER R_i.
		if (edge.kind == JoinType::RIGHT || edge.kind == JoinType::INNER) {
			if (edge.bottom_up_eliminated) {
				continue;
			}
			OuterYanSemiPair pair;
			pair.build = edge.child->relation_id; // R_i provides keys
			pair.probe = node.relation_id;        // R_p is filtered
			ExtractSemiKeys(tree, pair.build, pair.probe, edge, pair);
			tree.bottom_up_pairs.push_back(std::move(pair));
		}
	}
}

void OuterYanPre::TopDownPass(OuterYanTree &tree, OJTNode &node) {
	// Pre-order (reverse post-order): emit the parent->child edge before
	// recursing.
	for (auto &edge : node.children) {
		// Phase 2 fires on R_p LEFT R_i (parent preserved) or R_p INNER R_i.
		if (edge.kind == JoinType::LEFT || edge.kind == JoinType::INNER) {
			if (!edge.top_down_eliminated) {
				OuterYanSemiPair pair;
				pair.build = node.relation_id;        // R_p provides keys
				pair.probe = edge.child->relation_id; // R_i is filtered
				ExtractSemiKeys(tree, pair.build, pair.probe, edge, pair);
				tree.top_down_pairs.push_back(std::move(pair));
			}
		}
		TopDownPass(tree, *edge.child);
	}
}

void OuterYanPre::PruneThreeRelationOuterInnerPairs(OuterYanTree &tree) {
	if (tree.ot_relations_by_id.size() != 3 || tree.ot_joins_by_order.size() != 2) {
		return;
	}
	const auto &root = tree.OT().Root();
	if (root.kind != OTNode::Kind::JOIN || !root.info) {
		return;
	}
	const auto kind = root.info->join_kind;
	if ((kind != JoinType::LEFT && kind != JoinType::RIGHT) || root.info->original_join_kind != kind) {
		return;
	}
	const idx_t preserved_side = kind == JoinType::LEFT ? 0 : 1;
	const auto &preserved = *root.children[preserved_side];
	const auto &inner = *root.children[1 - preserved_side];
	if (preserved.kind != OTNode::Kind::RELATION || inner.kind != OTNode::Kind::JOIN || !inner.info ||
	    inner.info->join_kind != JoinType::INNER || inner.info->original_join_kind != JoinType::INNER ||
	    inner.children[0]->kind != OTNode::Kind::RELATION || inner.children[1]->kind != OTNode::Kind::RELATION) {
		return;
	}
	// The identity below assumes filters have already been applied to the
	// leaves. Keep the general reducer for intermediate multi-relation or
	// scope-sensitive filters; a retained root filter stays above the result.
	for (const auto &record : tree.filter_records) {
		if (record && !record->retained_at_original_scope &&
		    (record->referenced_relations.size() != 1 || record->requires_original_scope)) {
			return;
		}
	}
	const auto middle = preserved_side == 0 ? root.info->cond_right_relation_id
	                                      : root.info->cond_left_relation_id;
	const auto leaf = inner.children[0]->relation_id == middle ? inner.children[1]->relation_id
	                                                        : inner.children[0]->relation_id;
	// Retain the existence check B := B semi-join C. It prevents a B row
	// without any C match from leaking through the desimplified LEFT join.
	// If an enforced total FK already eliminated this check, leave that case
	// to the existing constraint-based elimination rules.
	if (tree.bottom_up_pairs.size() != 1 || tree.bottom_up_pairs[0].build != leaf ||
	    tree.bottom_up_pairs[0].probe != middle) {
		return;
	}
	for (const auto &pair : tree.top_down_pairs) {
		if (!((pair.build == preserved.relation_id && pair.probe == middle) ||
		      (pair.build == middle && pair.probe == leaf))) {
			return;
		}
	}
	// A LEFT (B INNER C) = (A LEFT (B semi-join C)) LEFT C under
	// null-rejecting equality, including duplicate and orphan keys. B rows
	// without A and C rows without B cannot contribute to either grouping,
	// so B semi-join A and C semi-join B are optional reductions here.
	tree.top_down_pairs.clear();
}

void OuterYanPre::ExtractSemiKeys(OuterYanTree &tree, RelationId build_rel,
                                  RelationId probe_rel, const OJTEdge &edge,
                                  OuterYanSemiPair &out) {
	if (!edge.info) {
		throw InternalException(
		    "OuterYanPre::ExtractSemiKeys: edge has no OTJoin payload");
	}
	const auto &conditions = edge.info->conditions;
	out.keys.reserve(conditions.size());
	for (const auto &cond : conditions) {
		// The applicability gate forces each side to be a plain
		// BoundColumnRefExpression referencing exactly one base relation.
		auto &lhs = cond.GetLHS().Cast<BoundColumnRefExpression>();
		auto &rhs = cond.GetRHS().Cast<BoundColumnRefExpression>();
		auto lhs_it = tree.table_to_relation.find(lhs.binding.table_index.index);
		auto rhs_it = tree.table_to_relation.find(rhs.binding.table_index.index);
		if (lhs_it == tree.table_to_relation.end() ||
		    rhs_it == tree.table_to_relation.end()) {
			throw InternalException(
			    "OuterYanPre::ExtractSemiKeys: join condition references an unknown "
			    "table_index");
		}
		OuterYanSemiKey key;
		if (lhs_it->second == build_rel && rhs_it->second == probe_rel) {
			key.build_binding = lhs.binding;
			key.probe_binding = rhs.binding;
		} else if (lhs_it->second == probe_rel && rhs_it->second == build_rel) {
			key.build_binding = rhs.binding;
			key.probe_binding = lhs.binding;
		} else {
			throw InternalException(
			    "OuterYanPre::ExtractSemiKeys: condition does not connect build=%llu and "
			    "probe=%llu (saw lhs_rel=%llu, rhs_rel=%llu)",
			    build_rel, probe_rel, lhs_it->second, rhs_it->second);
		}
		out.keys.push_back(key);
	}
}

} // namespace duckdb
