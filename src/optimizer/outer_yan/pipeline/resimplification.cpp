#include "duckdb/optimizer/outer_yan/pipeline/resimplification.hpp"

#include "duckdb/common/exception.hpp"

#include <algorithm>

namespace duckdb {

namespace {

struct SimplicityGroup {
	unordered_set<idx_t> relations;
	unordered_set<idx_t> null_extended;
};

bool CollectSimplicityInfo(const OJTNode &node, unordered_map<idx_t, idx_t> &group_by_relation,
                          vector<SimplicityGroup> &groups, vector<const OJTEdge *> &edges) {
	if (!group_by_relation.emplace(node.relation_id, groups.size()).second) {
		return false;
	}
	SimplicityGroup group;
	group.relations.insert(node.relation_id);
	groups.push_back(std::move(group));
	for (const auto &edge : node.children) {
		if (!edge.child || edge.parent_relation_id != node.relation_id) {
			return false;
		}
		edges.push_back(&edge);
		if (!CollectSimplicityInfo(*edge.child, group_by_relation, groups, edges)) {
			return false;
		}
	}
	return true;
}

} // namespace

bool Resimplification::IsSimple(const OrderedJoinTree &ojt) {
	unordered_map<idx_t, idx_t> group_by_relation;
	vector<SimplicityGroup> groups;
	vector<const OJTEdge *> edges;
	if (!CollectSimplicityInfo(ojt.Root(), group_by_relation, groups, edges)) {
		return false;
	}
	std::sort(edges.begin(), edges.end(),
	          [](const OJTEdge *a, const OJTEdge *b) { return a->order < b->order; });
	idx_t previous_order = 0;
	for (const auto *edge : edges) {
		if (edge->order <= previous_order || !edge->info || edge->info->conditions.empty()) {
			return false;
		}
		previous_order = edge->order;
		const idx_t parent = edge->parent_relation_id;
		const idx_t child = edge->child->relation_id;
		const auto &info = *edge->info;
		if (!((info.cond_left_relation_id == parent && info.cond_right_relation_id == child) ||
		      (info.cond_left_relation_id == child && info.cond_right_relation_id == parent))) {
			return false;
		}
		for (const auto &condition : info.conditions) {
			if (!condition.IsComparison() || condition.GetComparisonType() != ExpressionType::COMPARE_EQUAL ||
			    condition.GetLHS().GetExpressionClass() != ExpressionClass::BOUND_COLUMN_REF ||
			    condition.GetRHS().GetExpressionClass() != ExpressionClass::BOUND_COLUMN_REF) {
				return false;
			}
		}
		if (edge->kind != JoinType::INNER && edge->kind != JoinType::LEFT && edge->kind != JoinType::RIGHT &&
		    edge->kind != JoinType::OUTER) {
			return false;
		}
		const auto parent_group = group_by_relation.at(parent);
		const auto child_group = group_by_relation.at(child);
		if (parent_group == child_group) {
			return false;
		}
		const auto &left = groups[parent_group];
		const auto &right = groups[child_group];
		const bool preserves_left = IsLeftOuterJoin(edge->kind);
		const bool preserves_right = IsRightOuterJoin(edge->kind);
		if ((!preserves_left && left.null_extended.count(parent)) ||
		    (!preserves_right && right.null_extended.count(child))) {
			return false;
		}

		SimplicityGroup merged;
		merged.relations = left.relations;
		merged.relations.insert(right.relations.begin(), right.relations.end());
		merged.null_extended = left.null_extended;
		merged.null_extended.insert(right.null_extended.begin(), right.null_extended.end());
		if (preserves_left) {
			merged.null_extended.insert(right.relations.begin(), right.relations.end());
		}
		if (preserves_right) {
			merged.null_extended.insert(left.relations.begin(), left.relations.end());
		}
		for (const auto relation : merged.relations) {
			group_by_relation[relation] = groups.size();
		}
		groups.push_back(std::move(merged));
	}
	return !groups.empty() && groups.back().relations.size() == group_by_relation.size();
}

void Resimplification::IndexOJT(OJTNode &node) {
	node_by_rel[node.relation_id] = &node;
	for (auto &edge : node.children) {
		if (!edge.child) {
			throw InternalException("Resimplification: OJT edge missing child");
		}
		all_edges.push_back(&edge);
		parent_edge_by_rel[edge.child->relation_id] = &edge;
		IndexOJT(*edge.child);
	}
}

bool Resimplification::ArrowTargetsSharedNode(const OJTEdge &k_edge, idx_t shared_rel) {
	D_ASSERT(k_edge.child);
	const bool shared_is_child = (shared_rel == k_edge.child->relation_id);
	D_ASSERT(shared_is_child || shared_rel == k_edge.parent_relation_id);
	switch (k_edge.kind) {
	case JoinType::INNER:
		return false;
	case JoinType::LEFT:
		// OJT places child on the right; arrow on right side.
		return shared_is_child;
	case JoinType::RIGHT:
		// Arrow on left = parent side.
		return !shared_is_child;
	case JoinType::OUTER:
		return true;
	default:
		throw InternalException(
		    "Resimplification: unsupported OuterYanJoinKind on OJT edge");
	}
}

bool Resimplification::TryRevert(OJTEdge &i_edge, const OrderedJoinTree &ojt) {
	if (i_edge.kind == i_edge.original_kind) {
		return false; // not de-simplified.
	}
	if (!i_edge.child) {
		throw InternalException("Resimplification: OJT edge missing child");
	}
	const idx_t i_p = i_edge.parent_relation_id;
	const idx_t i_c = i_edge.child->relation_id;

	auto try_with = [&](OJTEdge *k, idx_t shared) -> bool {
		if (!k || k == &i_edge) {
			return false;
		}
		if (k->order <= i_edge.order) {
			return false;
		}
		if (!ArrowTargetsSharedNode(*k, shared)) {
			return false;
		}
		const auto relaxed_kind = i_edge.kind;
		i_edge.kind = i_edge.original_kind;
		// Order and arrow dominance alone are insufficient: restoration can
		// reject NULL padding introduced inside the selected input subtree.
		if (!IsSimple(ojt)) {
			i_edge.kind = relaxed_kind;
			return false;
		}
		reverts++;
		return true;
	};

	// Adjacent at i_p: the parent edge into OJTNode(i_p), plus i_edge's siblings.
	auto pe_it = parent_edge_by_rel.find(i_p);
	if (pe_it != parent_edge_by_rel.end() && try_with(pe_it->second, i_p)) {
		return true;
	}
	auto p_node_it = node_by_rel.find(i_p);
	if (p_node_it != node_by_rel.end()) {
		for (auto &sib : p_node_it->second->children) {
			if (try_with(&sib, i_p)) {
				return true;
			}
		}
	}

	// Adjacent at i_c: child edges of OJTNode(i_c). Monotonic order keeps
	// their order < i_edge.order, so they are filtered out; kept for
	// completeness in case the invariant ever weakens.
	for (auto &ce : i_edge.child->children) {
		if (try_with(&ce, i_c)) {
			return true;
		}
	}

	return false;
}

void Resimplification::Apply(OrderedJoinTree &ojt) {
	reverts = 0;
	all_edges.clear();
	node_by_rel.clear();
	parent_edge_by_rel.clear();

	IndexOJT(ojt.Root());
	if (all_edges.size() < 2) {
		return;
	}

	// Ascending order keeps later $\Diamond_k$'s (possibly de-simplified)
	// arrow sides intact for as long as possible.
	std::sort(all_edges.begin(), all_edges.end(),
	          [](const OJTEdge *a, const OJTEdge *b) { return a->order < b->order; });

	bool changed;
	do {
		changed = false;
		for (auto *i_edge : all_edges) {
			if (TryRevert(*i_edge, ojt)) {
				changed = true;
			}
		}
	} while (changed);
}

} // namespace duckdb
