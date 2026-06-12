#include "duckdb/optimizer/outer_yan/pipeline/outer_yan_pre.hpp"

#include "duckdb/common/exception.hpp"
#include "duckdb/common/printer.hpp"
#include "duckdb/planner/expression/bound_columnref_expression.hpp"
#include "duckdb/planner/operator/logical_comparison_join.hpp"
#include "duckdb/planner/operator/logical_get.hpp"

namespace duckdb {

#ifndef NDEBUG
// ============================================================================
// Debug helpers — OuterYanPre
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
#endif // DEBUG

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
	//                              never reach the recorded pairs.
	//   5. Desimplify           -- six Galindo-Legaria / Rosenthal associativity
	//                              rules to fixpoint; mutates only
	//                              `OTNode::join_kind`.
	//   6. AllPairsSatisfy      -- post-condition: every (P, D) pair in an OK
	//                              cell.
	tree.BuildOT(std::move(plan));
#ifndef NDEBUG
	Printer::Print("[OuterYanPre] after BuildOT:\n" + tree.ConstructOJT()->PrintAsTree());
#endif

	Simplify(tree);
#ifndef NDEBUG
	Printer::Print("[OuterYanPre] after Simplify:\n" + tree.ConstructOJT()->PrintAsTree());
#endif

	{
		auto post_simp_ojt = tree.ConstructOJT();
		BottomUpPass(tree, post_simp_ojt->Root());
		TopDownPass(tree, post_simp_ojt->Root());
	}
#ifndef NDEBUG
	Printer::Print("[OuterYanPre] semi-join pairs:\n" + PrintSemiPairs(tree));
#endif

	Desimplify(tree);
#ifndef NDEBUG
	Printer::Print("[OuterYanPre] after Desimplify:\n" + tree.ConstructOJT()->PrintAsTree());
#endif

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
