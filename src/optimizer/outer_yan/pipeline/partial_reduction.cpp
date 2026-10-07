#include "duckdb/optimizer/outer_yan/pipeline/partial_reduction.hpp"

#include "duckdb/optimizer/outer_yan/common/outer_yan_trace.hpp"
#include "duckdb/optimizer/outer_yan/pipeline/resimplification.hpp"
#include "duckdb/planner/expression/bound_columnref_expression.hpp"

#include <algorithm>
#include <functional>

namespace duckdb {
namespace {

bool PartialPreserves(const OJTEdge &edge, RelationId relation, bool original) {
	const auto kind = original ? edge.original_kind : edge.kind;
	return kind == JoinType::OUTER ||
	       (kind == JoinType::LEFT && relation == edge.parent_relation_id) ||
	       (kind == JoinType::RIGHT && relation == edge.child->relation_id);
}

struct ReductionLink {
	idx_t other;
	const OJTEdge *edge;
};

bool MakePartialPair(const OuterYanTree &tree, const OJTEdge &edge, RelationId build, RelationId probe,
                     OuterYanSemiPair &pair) {
	if (!edge.info || edge.info->conditions.empty()) {
		return false;
	}
	pair.build = build;
	pair.probe = probe;
	for (const auto &condition : edge.info->conditions) {
		if (!condition.IsComparison() || condition.GetComparisonType() != ExpressionType::COMPARE_EQUAL ||
		    condition.GetLHS().GetExpressionClass() != ExpressionClass::BOUND_COLUMN_REF ||
		    condition.GetRHS().GetExpressionClass() != ExpressionClass::BOUND_COLUMN_REF) {
			return false;
		}
		const auto lhs = condition.GetLHS().Cast<BoundColumnRefExpression>().binding;
		const auto rhs = condition.GetRHS().Cast<BoundColumnRefExpression>().binding;
		const auto left = tree.table_to_relation.find(lhs.table_index.index);
		const auto right = tree.table_to_relation.find(rhs.table_index.index);
		if (left == tree.table_to_relation.end() || right == tree.table_to_relation.end()) {
			return false;
		}
		OuterYanSemiKey key;
		if (left->second == build && right->second == probe) {
			key.build_binding = lhs;
			key.probe_binding = rhs;
		} else if (right->second == build && left->second == probe) {
			key.build_binding = rhs;
			key.probe_binding = lhs;
		} else {
			return false;
		}
		pair.keys.push_back(key);
	}
	return true;
}

} // namespace

bool PartialReduction::Apply(OuterYanTree &tree) const {
	// The partial-reduction proof is for joins over base tuples. Do not extend
	// it to weighted/grouped inputs without a separate aggregation proof.
	if (!tree.HasOJT() || tree.root_aggregation.type != OuterYanAggregationType::NONE ||
	    !Resimplification::IsSimple(tree.OJT())) {
		return false;
	}
	for (const auto &filter : tree.filter_records) {
		if (filter && !filter->retained_at_original_scope &&
		    (filter->requires_original_scope || filter->referenced_relations.size() != 1)) {
			return false;
		}
	}
	const auto count = tree.ot_relations_by_id.size();
	if (count < 2) {
		return false;
	}
	vector<vector<ReductionLink>> adjacent(count);
	vector<const OJTEdge *> first(count, nullptr);
	vector<bool> seen(count, false);
	const OJTEdge *first_join = nullptr;
	idx_t edge_count = 0;
	bool valid = true;
	std::function<void(const OJTNode &)> index = [&](const OJTNode &node) {
		if (node.relation_id >= count || seen[node.relation_id]) {
			valid = false;
			return;
		}
		seen[node.relation_id] = true;
		for (const auto &edge : node.children) {
			if (!edge.child || edge.child->relation_id >= count || edge.parent_relation_id != node.relation_id ||
			    edge.order == 0) {
				valid = false;
				return;
			}
			const auto parent = node.relation_id;
			const auto child = edge.child->relation_id;
			adjacent[parent].push_back({child, &edge});
			adjacent[child].push_back({parent, &edge});
			for (auto relation : {parent, child}) {
				if (!first[relation] || edge.order < first[relation]->order) {
					first[relation] = &edge;
				}
			}
			if (!first_join || edge.order < first_join->order) {
				first_join = &edge;
			}
			edge_count++;
			index(*edge.child);
		}
	};
	index(tree.OJT().Root());
	if (!valid || edge_count != count - 1 || !first_join || first_join->order != 1 ||
	    std::find(seen.begin(), seen.end(), false) != seen.end()) {
		return false;
	}
	// Keep the selected binary join tree untouched. Only reduction directions
	// change; preserving the first join's endpoint determines the reduction root.
	const auto root = first_join->kind == JoinType::RIGHT ? first_join->child->relation_id
	                                                   : first_join->parent_relation_id;
	vector<idx_t> parent(count, DConstants::INVALID_INDEX);
	vector<const OJTEdge *> incoming(count, nullptr);
	vector<idx_t> preorder;
	parent[root] = root;
	std::function<void(idx_t)> orient = [&](idx_t node) {
		preorder.push_back(node);
		std::sort(adjacent[node].begin(), adjacent[node].end(),
		          [](const ReductionLink &a, const ReductionLink &b) { return a.edge->order < b.edge->order; });
		for (const auto &link : adjacent[node]) {
			if (link.other == parent[node]) {
				continue;
			}
			parent[link.other] = node;
			incoming[link.other] = link.edge;
			orient(link.other);
		}
	};
	orient(root);

	vector<bool> keep_path(count, false);
	for (auto node : preorder) {
		if (node == root) {
			continue;
		}
		// (a) The first incident join attaches a child instead of this node's
		// parent. (b) De-simplification newly preserves this node at its first
		// join. Both need fully reduced input, including the entire ancestor path.
		const bool child_first = first[node] != incoming[node];
		const bool newly_preserved = PartialPreserves(*first[node], node, false) &&
		                             !PartialPreserves(*first[node], node, true);
		if (child_first || newly_preserved) {
			for (auto current = node; current != root; current = parent[current]) {
				keep_path[current] = true;
			}
		}
	}
	vector<OuterYanSemiPair> bottom_up;
	vector<OuterYanSemiPair> top_down;
	for (auto node : preorder) {
		if (node == root || !keep_path[node] || PartialPreserves(*incoming[node], node, true)) {
			continue;
		}
		OuterYanSemiPair pair;
		if (!MakePartialPair(tree, *incoming[node], parent[node], node, pair)) {
			return false;
		}
		top_down.push_back(std::move(pair));
	}
	const bool root_used_by_top_down = std::any_of(top_down.begin(), top_down.end(),
	                                              [&](const OuterYanSemiPair &pair) { return pair.build == root; });
	for (auto it = preorder.rbegin(); it != preorder.rend(); ++it) {
		const auto node = *it;
		if (node == root || PartialPreserves(*incoming[node], parent[node], true)) {
			continue;
		}
		if (incoming[node] == first_join && parent[node] == root && !root_used_by_top_down &&
		    !PartialPreserves(*first_join, root, false)) {
			continue;
		}
		OuterYanSemiPair pair;
		if (!MakePartialPair(tree, *incoming[node], node, parent[node], pair)) {
			return false;
		}
		bottom_up.push_back(std::move(pair));
	}
	// Re-rooting invalidates the old schedule's FK-elimination flags. Retain
	// all otherwise required pairs here, and keep the old constraint-pruned
	// schedule if this would not strictly reduce its operator count.
	const auto before_bu = tree.bottom_up_pairs.size();
	const auto before_td = tree.top_down_pairs.size();
	if (bottom_up.size() + top_down.size() >= before_bu + before_td) {
		return false;
	}
	tree.bottom_up_pairs = std::move(bottom_up);
	tree.top_down_pairs = std::move(top_down);
	if (OuterYanTrace::Enabled()) {
		OuterYanTrace::Stage("partial reduction",
		                     "root=R" + to_string(root) + " bottom_up=" + to_string(before_bu) + "->" +
		                         to_string(tree.bottom_up_pairs.size()) + " top_down=" + to_string(before_td) + "->" +
		                         to_string(tree.top_down_pairs.size()));
	}
	return true;
}

} // namespace duckdb
